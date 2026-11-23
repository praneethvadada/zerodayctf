"""ZeroDayCTF solution write-ups.

Every participant who solved at least one challenge must explain how they solved
each of them: written steps plus screenshots. Participants write during the
write-up window (``end`` -> ``writeup_end`` in the config); admins review
everything under /admin/writeups.
"""
import datetime
import io
import time

from flask import Blueprint, abort, redirect, render_template, request, url_for
from PIL import Image
from werkzeug.datastructures import FileStorage

from CTFd.models import Challenges, Solves, Users, db
from CTFd.utils import get_config
from CTFd.utils.decorators import admins_only, authed_only
from CTFd.utils.uploads import get_uploader
from CTFd.utils.user import get_current_user, is_admin

MAX_TEXT = 10000          # characters of written steps per challenge
MIN_TEXT = 50             # characters needed for a challenge to count as "explained"
MAX_IMAGES = 10           # screenshots per challenge
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_FORMATS = {"PNG", "JPEG", "GIF", "WEBP"}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


class Writeups(db.Model):
    __tablename__ = "writeups"
    __table_args__ = (db.UniqueConstraint("user_id", "challenge_id"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE")
    )
    content = db.Column(db.Text, default="")
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated = db.Column(
        db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
    files = db.relationship(
        "WriteupFiles", backref="writeup", cascade="all, delete-orphan", lazy="select"
    )

    @property
    def is_complete(self):
        return len((self.content or "").strip()) >= MIN_TEXT and len(self.files) >= 1


class WriteupFiles(db.Model):
    __tablename__ = "writeup_files"
    id = db.Column(db.Integer, primary_key=True)
    writeup_id = db.Column(db.Integer, db.ForeignKey("writeups.id", ondelete="CASCADE"))
    location = db.Column(db.String(512))
    filename = db.Column(db.String(256))
    size = db.Column(db.Integer)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)


def _as_int(key):
    try:
        return int(get_config(key))
    except (TypeError, ValueError):
        return None


def phase():
    """before | solve | writeup | over, from the server clock and config."""
    now = time.time()
    start, end, writeup_end = _as_int("start"), _as_int("end"), _as_int("writeup_end")
    if start and now < start:
        return "before"
    if end and now < end:
        return "solve"
    if writeup_end is None or now < writeup_end:
        return "writeup"
    return "over"


def solved_challenges(user_id):
    rows = (
        db.session.query(Solves, Challenges)
        .join(Challenges, Challenges.id == Solves.challenge_id)
        .filter(Solves.user_id == user_id)
        .order_by(Solves.date.asc())
        .all()
    )
    return [(s, c) for s, c in rows]


def user_progress(user_id):
    """(solved, explained) counts for one user."""
    solved = solved_challenges(user_id)
    ids = [c.id for _, c in solved]
    done = 0
    if ids:
        for w in Writeups.query.filter(
            Writeups.user_id == user_id, Writeups.challenge_id.in_(ids)
        ).all():
            if w.is_complete:
                done += 1
    return len(solved), done


Image.MAX_IMAGE_PIXELS = 25_000_000   # refuse decompression bombs (about 5000 x 5000)


def _clean_image(file_storage):
    """Validate AND re-encode an uploaded screenshot.

    Returns (clean_file_storage, error). Re-encoding drops anything appended to the
    file (HTML/script polyglots) and strips EXIF/GPS metadata.
    """
    name = (file_storage.filename or "").lower()
    if not any(name.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        return None, "Only PNG, JPG, GIF or WEBP screenshots are allowed."
    data = file_storage.read()
    file_storage.seek(0)
    if len(data) == 0:
        return None, "An empty file was skipped."
    if len(data) > MAX_IMAGE_BYTES:
        return None, "Each screenshot must be 8 MB or smaller."
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED_FORMATS:
            return None, "That file is not a supported image."
        if img.width * img.height > Image.MAX_IMAGE_PIXELS:
            return None, "That image is too large (max about 5000 x 5000 pixels)."
        img.load()  # fully decode: catches truncated / malformed files
        fmt = "JPEG" if img.format == "JPEG" else "WEBP" if img.format == "WEBP" else "PNG"
        if fmt == "JPEG" and img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, fmt)
    except Exception:  # noqa: BLE001 - any decode problem means "not a valid image"
        return None, "That file is not a valid image."
    ext = {"JPEG": ".jpg", "WEBP": ".webp", "PNG": ".png"}[fmt]
    stem = (file_storage.filename or "screenshot").rsplit(".", 1)[0][:80] or "screenshot"
    out.seek(0)
    return FileStorage(stream=out, filename=stem + ext, content_type="image/" + fmt.lower()), ""


writeups_bp = Blueprint("writeups", __name__)


@writeups_bp.route("/writeups", methods=["GET"])
@authed_only
def my_writeups():
    if is_admin():
        return redirect(url_for("writeups_admin.listing"))
    user = get_current_user()
    current = phase()
    items = []
    for solve, chal in solved_challenges(user.id):
        w = Writeups.query.filter_by(user_id=user.id, challenge_id=chal.id).first()
        items.append(
            {
                "challenge": chal,
                "solved_at": solve.date,
                "writeup": w,
                "content": (w.content if w else "") or "",
                "files": list(w.files) if w else [],
                "complete": bool(w and w.is_complete),
            }
        )
    return render_template(
        "writeups.html",
        items=items,
        phase=current,
        can_edit=(current == "writeup"),
        done=sum(1 for i in items if i["complete"]),
        total=len(items),
        message=request.args.get("msg", ""),
        message_kind=request.args.get("kind", "success"),
        max_text=MAX_TEXT,
        min_text=MIN_TEXT,
        max_images=MAX_IMAGES,
    )


def _back(chal_id, msg, kind="success"):
    return redirect(
        url_for("writeups.my_writeups", msg=msg, kind=kind) + "#chal-%d" % chal_id
    )


@writeups_bp.route("/writeups/<int:challenge_id>", methods=["POST"])
@authed_only
def save_writeup(challenge_id):
    if is_admin():
        abort(403)
    if phase() != "writeup":
        return _back(
            challenge_id,
            "The writeup window is not open right now.",
            "danger",
        )
    user = get_current_user()
    if not Solves.query.filter_by(user_id=user.id, challenge_id=challenge_id).first():
        abort(403)  # you can only explain challenges you solved

    content = (request.form.get("content") or "").strip()
    if len(content) > MAX_TEXT:
        return _back(
            challenge_id,
            "Your steps are too long (max %d characters)." % MAX_TEXT,
            "danger",
        )

    w = Writeups.query.filter_by(user_id=user.id, challenge_id=challenge_id).first()
    if w is None:
        w = Writeups(user_id=user.id, challenge_id=challenge_id, content="")
        db.session.add(w)
        db.session.flush()
    w.content = content

    notes = []
    uploader = get_uploader()
    for f in request.files.getlist("screenshots"):
        if not f or not f.filename:
            continue
        if len(w.files) >= MAX_IMAGES:
            notes.append("Maximum %d screenshots per challenge." % MAX_IMAGES)
            break
        clean, err = _clean_image(f)
        if clean is None:
            notes.append(err)
            continue
        size = clean.stream.getbuffer().nbytes
        location = uploader.upload(file_obj=clean, filename=clean.filename)
        w.files.append(
            WriteupFiles(location=location, filename=clean.filename[:250], size=size)
        )
    db.session.commit()

    if notes:
        return _back(challenge_id, "Saved. " + " ".join(sorted(set(notes))), "warning")
    return _back(challenge_id, "Saved.")


@writeups_bp.route(
    "/writeups/<int:challenge_id>/files/<int:file_id>/delete", methods=["POST"]
)
@authed_only
def delete_file(challenge_id, file_id):
    if is_admin():
        abort(403)
    if phase() != "writeup":
        return _back(challenge_id, "The writeup window is not open right now.", "danger")
    user = get_current_user()
    f = (
        WriteupFiles.query.join(Writeups)
        .filter(
            WriteupFiles.id == file_id,
            Writeups.user_id == user.id,
            Writeups.challenge_id == challenge_id,
        )
        .first_or_404()
    )
    get_uploader().delete(f.location)
    db.session.delete(f)
    db.session.commit()
    return _back(challenge_id, "Screenshot removed.")


@writeups_bp.route("/writeups/file/<int:file_id>")
@authed_only
def view_file(file_id):
    f = WriteupFiles.query.get_or_404(file_id)
    owner_id = f.writeup.user_id
    if not is_admin() and get_current_user().id != owner_id:
        abort(404)
    return get_uploader().download(f.location)


admin_bp = Blueprint("writeups_admin", __name__)


@admin_bp.route("/admin/writeups")
@admins_only
def listing():
    only_missing = request.args.get("filter") == "missing"
    rows = []
    solver_ids = [
        uid for (uid,) in db.session.query(Solves.user_id).distinct().all() if uid
    ]
    for u in Users.query.filter(Users.id.in_(solver_ids)).order_by(Users.name).all():
        solved, done = user_progress(u.id)
        last = (
            db.session.query(db.func.max(Writeups.updated))
            .filter(Writeups.user_id == u.id)
            .scalar()
        )
        rows.append(
            {
                "user": u,
                "solved": solved,
                "done": done,
                "complete": solved > 0 and done == solved,
                "last": last,
            }
        )
    if only_missing:
        rows = [r for r in rows if not r["complete"]]
    return render_template(
        "admin/writeups/list.html",
        rows=rows,
        phase=phase(),
        only_missing=only_missing,
        total_participants=len(solver_ids),
    )


@admin_bp.route("/admin/writeups/<int:user_id>")
@admins_only
def detail(user_id):
    user = Users.query.get_or_404(user_id)
    items = []
    for solve, chal in solved_challenges(user.id):
        w = Writeups.query.filter_by(user_id=user.id, challenge_id=chal.id).first()
        items.append(
            {
                "challenge": chal,
                "solved_at": solve.date,
                "content": (w.content if w else "") or "",
                "files": list(w.files) if w else [],
                "complete": bool(w and w.is_complete),
                "updated": w.updated if w else None,
            }
        )
    return render_template("admin/writeups/detail.html", user=user, items=items)


def load(app):
    app.db.create_all()
    app.register_blueprint(writeups_bp)
    app.register_blueprint(admin_bp)
