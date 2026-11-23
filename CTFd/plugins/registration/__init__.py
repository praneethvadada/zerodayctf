"""ZeroDayCTF registration: student details, admin-managed colleges and e-mail OTP verification.

Flow
  1. /register collects name, username, e-mail, password, college, branch and roll number.
  2. A 6-digit code is e-mailed; nothing is created yet (the details wait in a "pending" row).
  3. /register/verify checks the code, then the account is created with a verified e-mail and the student is signed in.

Rules
  * Roll number, branch and "other" college names are upper-cased and limited to letters and digits (branch and
    college names also allow spaces and - . & ( ) /).
  * Students cannot change roll number, branch or college afterwards: only an admin can (Admin > Students).
  * A student who picks "Other" adds a college that stays "pending" until an admin approves it (Admin > Colleges).

Mail settings come from the environment (see deploy/.env.production.example): OTP_SMTP_HOST, OTP_SMTP_PORT,
OTP_SMTP_USER, OTP_SMTP_PASSWORD, OTP_SMTP_SSL, OTP_FROM.
"""
import csv
import datetime
import hashlib
import hmac
import io
import os
import re
import secrets
import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr

from flask import Blueprint, Response, abort, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from CTFd.models import Users, db
from CTFd.utils import get_config, validators
from CTFd.utils import email as ctfd_email
from CTFd.utils.decorators import admins_only, ratelimit_from_config
from CTFd.utils.decorators.visibility import check_registration_visibility
from CTFd.utils.logging import log
from CTFd.utils.security.auth import login_user
from CTFd.utils.user import authed

OTP_TTL = 10 * 60          # a code is valid for 10 minutes
OTP_RESEND_WAIT = 60       # seconds before another code can be requested
OTP_MAX_SENDS = 5          # codes per registration attempt
OTP_MAX_TRIES = 5          # wrong guesses per code
OTHER = "other"

ROLL_RE = re.compile(r"^[A-Z0-9]{3,30}$")
TEXT_RE = re.compile(r"^[A-Z0-9][A-Z0-9 .&()/\-]{1,119}$")
FULLNAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,99}$")


# ----------------------------------------------------------------------------- models
class RegColleges(db.Model):
    __tablename__ = "reg_colleges"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    approved = db.Column(db.Boolean, default=True, nullable=False)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class RegProfiles(db.Model):
    __tablename__ = "reg_profiles"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    roll_no = db.Column(db.String(30), nullable=False, index=True)
    branch = db.Column(db.String(120), nullable=False)
    college_id = db.Column(db.Integer, db.ForeignKey("reg_colleges.id"), nullable=False)
    college = db.relationship("RegColleges")
    user = db.relationship("Users", foreign_keys=[user_id])


class RegPending(db.Model):
    __tablename__ = "reg_pending"
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(128), nullable=False, index=True)
    username = db.Column(db.String(128), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    roll_no = db.Column(db.String(30), nullable=False)
    branch = db.Column(db.String(120), nullable=False)
    college_id = db.Column(db.Integer, nullable=True)          # an approved college, or
    other_college = db.Column(db.String(120), nullable=True)   # a new name typed by the student
    otp_hash = db.Column(db.String(64), nullable=False)
    otp_expires = db.Column(db.Integer, nullable=False)
    tries = db.Column(db.Integer, default=0, nullable=False)
    sends = db.Column(db.Integer, default=1, nullable=False)
    last_sent = db.Column(db.Integer, nullable=False)
    created = db.Column(db.Integer, nullable=False)


# ----------------------------------------------------------------------------- helpers
def clean_upper(value):
    return re.sub(r"\s+", " ", (value or "").strip()).upper()


def _otp_hash(app_key, email, code):
    return hmac.new(app_key.encode(), ("%s:%s" % (email, code)).encode(), hashlib.sha256).hexdigest()


def _secret():
    from flask import current_app

    return str(current_app.config.get("SECRET_KEY") or "")


def send_mail(to_addr, subject, body):
    """Send one plain-text e-mail through the SMTP account in the environment. Returns (ok, message)."""
    host = os.getenv("OTP_SMTP_HOST", "").strip()
    if not host:
        if os.getenv("OTP_DEV_PRINT") == "1":          # local development only: show the mail in the log
            print("[DEV MAIL] to=%s subject=%s\n%s" % (to_addr, subject, body), flush=True)
            return True, "printed"
        return False, "The e-mail service is not configured."
    port = int(os.getenv("OTP_SMTP_PORT", "465") or 465)
    user = os.getenv("OTP_SMTP_USER", "")
    pw = os.getenv("OTP_SMTP_PASSWORD", "")
    ssl_on = os.getenv("OTP_SMTP_SSL", "true").lower() not in ("0", "false", "no")
    sender = os.getenv("OTP_FROM", "") or user
    name = get_config("ctf_name") or "ZeroDayCTF"
    name = "ZeroDayCTF" if name == "CTFd" else name
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((name, sender))
    msg["To"] = to_addr
    msg.set_content(body)
    try:
        smtp = smtplib.SMTP_SSL(host, port, timeout=20) if ssl_on else smtplib.SMTP(host, port, timeout=20)
        try:
            if not ssl_on and os.getenv("OTP_SMTP_STARTTLS", "true").lower() not in ("0", "false", "no"):
                smtp.starttls()
            if user:
                smtp.login(user, pw)
            smtp.send_message(msg)
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001
                pass
        return True, "sent"
    except Exception as e:  # noqa: BLE001 - report any mail problem to the caller, never crash the page
        return False, "%s: %s" % (type(e).__name__, e)


def _send_code(p, code):
    name = get_config("ctf_name") or "ZeroDayCTF"
    body = (
        "Your %s verification code is:\n\n    %s\n\n"
        "It is valid for %d minutes. If you did not try to register, you can ignore this e-mail.\n"
        % (name, code, OTP_TTL // 60)
    )
    return send_mail(p.email, "%s verification code: %s" % (name, code), body)


def approved_colleges():
    return RegColleges.query.filter_by(approved=True).order_by(RegColleges.name).all()


def _college_by_name(name):
    return RegColleges.query.filter(db.func.upper(RegColleges.name) == name.upper()).first()


# ----------------------------------------------------------------------------- student side
@check_registration_visibility
@ratelimit_from_config(method="POST", config_key="RATELIMIT_REGISTER")
def register():
    if authed():
        return redirect(url_for("challenges.listing"))
    errors = []
    form = {k: request.form.get(k, "") for k in ("full_name", "name", "email", "college", "other_college", "branch", "roll_no")}
    if request.method == "POST":
        full_name = re.sub(r"\s+", " ", form["full_name"].strip())
        username = request.form.get("name", "").strip()
        email_addr = form["email"].strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        roll_no = clean_upper(form["roll_no"]).replace(" ", "")
        branch = clean_upper(form["branch"])
        college_sel = form["college"].strip()
        other_college = clean_upper(form["other_college"])
        form.update(roll_no=roll_no, branch=branch, other_college=other_college)

        if not FULLNAME_RE.match(full_name):
            errors.append("Enter your full name (letters only).")
        if not username or len(username) > 80:
            errors.append("Pick a username (up to 80 characters).")
        elif validators.validate_email(username):
            errors.append("Your username cannot be an email address.")
        elif Users.query.filter_by(name=username).first():
            errors.append("That username is already taken.")
        if not validators.validate_email(email_addr):
            errors.append("Please enter a valid email address.")
        else:
            if ctfd_email.check_email_is_whitelisted(email_addr) is False or ctfd_email.check_email_is_blacklisted(email_addr) is True:
                errors.append("Your email address is not from an allowed domain.")
            if Users.query.filter_by(email=email_addr).first():
                errors.append("That email has already been used.")
        min_len = int(get_config("password_min_length", default=8))
        if len(password) < max(min_len, 1):
            errors.append("Password must be at least %d characters." % max(min_len, 1))
        elif len(password) > 128:
            errors.append("Pick a shorter password.")
        elif password != confirm:
            errors.append("The two passwords do not match.")

        college_id, new_college = None, None
        if college_sel == OTHER:
            if not TEXT_RE.match(other_college):
                errors.append("Type your college name (letters and digits only).")
            else:
                existing = _college_by_name(other_college)
                if existing and existing.approved:
                    college_id = existing.id
                else:
                    new_college = other_college
        elif college_sel.isdigit() and RegColleges.query.filter_by(id=int(college_sel), approved=True).first():
            college_id = int(college_sel)
        else:
            errors.append("Select your college.")
        if not TEXT_RE.match(branch):
            errors.append("Enter your branch (letters and digits only, for example CSE).")
        if not ROLL_RE.match(roll_no):
            errors.append("Roll number must be 3 to 30 letters or digits, no spaces or symbols.")

        if not errors:
            now = int(time.time())
            code = "%06d" % secrets.randbelow(1000000)
            from CTFd.utils.crypto import hash_password

            RegPending.query.filter_by(email=email_addr).delete()
            p = RegPending(
                token=secrets.token_urlsafe(32), email=email_addr, username=username, full_name=full_name,
                password_hash=hash_password(password), roll_no=roll_no, branch=branch,
                college_id=college_id, other_college=new_college,
                otp_hash=_otp_hash(_secret(), email_addr, code), otp_expires=now + OTP_TTL,
                tries=0, sends=1, last_sent=now, created=now,
            )
            db.session.add(p)
            db.session.commit()
            ok, why = _send_code(p, code)
            if not ok:
                db.session.delete(p)
                db.session.commit()
                print("[registration] could not send the code to %s: %s" % (email_addr, why), flush=True)
                errors.append("We could not send the verification e-mail right now. Please try again in a minute.")
            else:
                session["reg_pending"] = p.token
                return redirect(url_for("registration.verify"))
    return render_template(
        "register.html", errors=errors, form=form, colleges=approved_colleges(), other=OTHER,
    )


def _pending_from_session():
    token = session.get("reg_pending")
    return RegPending.query.filter_by(token=token).first() if token else None


reg_bp = Blueprint("registration", __name__)


@reg_bp.route("/register/verify", methods=["GET", "POST"])
@check_registration_visibility
@ratelimit_from_config(method="POST", config_key="RATELIMIT_REGISTER")
def verify():
    p = _pending_from_session()
    if p is None:
        return redirect(url_for("auth.register"))
    errors, infos = [], []
    now = int(time.time())
    if request.method == "POST":
        if request.form.get("action") == "resend":
            if now - p.last_sent < OTP_RESEND_WAIT:
                errors.append("Please wait %d seconds before asking for another code." % (OTP_RESEND_WAIT - (now - p.last_sent)))
            elif p.sends >= OTP_MAX_SENDS:
                errors.append("Too many codes requested. Please start the registration again.")
            else:
                code = "%06d" % secrets.randbelow(1000000)
                ok, why = _send_code(p, code)
                if ok:
                    p.otp_hash, p.otp_expires, p.tries, p.sends, p.last_sent = _otp_hash(_secret(), p.email, code), now + OTP_TTL, 0, p.sends + 1, now
                    db.session.commit()
                    infos.append("A new code has been sent.")
                else:
                    print("[registration] resend failed for %s: %s" % (p.email, why), flush=True)
                    errors.append("We could not send the e-mail right now. Please try again in a minute.")
        else:
            code = re.sub(r"\D", "", request.form.get("code", ""))
            if now > p.otp_expires:
                errors.append("This code has expired. Request a new one.")
            elif p.tries >= OTP_MAX_TRIES:
                errors.append("Too many wrong attempts. Request a new code.")
            elif not code or not hmac.compare_digest(_otp_hash(_secret(), p.email, code), p.otp_hash):
                p.tries += 1
                db.session.commit()
                errors.append("That code is not correct (%d attempts left)." % max(OTP_MAX_TRIES - p.tries, 0))
            else:
                user, why = _finalize(p)
                if user is None:
                    errors.append(why)
                else:
                    session.pop("reg_pending", None)
                    login_user(user)
                    return redirect(url_for("challenges.listing"))
    return render_template(
        "register_verify.html", errors=errors, infos=infos, email=p.email,
        wait=max(OTP_RESEND_WAIT - (now - p.last_sent), 0),
    )


def _finalize(p):
    """Create the real account from a verified pending registration."""
    if Users.query.filter_by(email=p.email).first():
        return None, "That email has already been used."
    if Users.query.filter_by(name=p.username).first():
        return None, "That username was taken while you were verifying. Please register again with another username."
    college_id = p.college_id
    try:
        if college_id is None:
            college = _college_by_name(p.other_college)
            if college is None:
                college = RegColleges(name=p.other_college, approved=False)
                db.session.add(college)
                db.session.flush()
            college_id = college.id
        user = Users(name=p.username, email=p.email, password="placeholder-replaced-below")
        user.verified = True
        db.session.add(user)
        db.session.flush()
        # store the hash made at sign-up (the Users model would hash a plain value again)
        db.session.execute(Users.__table__.update().where(Users.id == user.id).values(password=p.password_hash))
        db.session.add(RegProfiles(user_id=user.id, full_name=p.full_name, roll_no=p.roll_no, branch=p.branch, college_id=college_id))
        db.session.delete(p)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return None, "Could not finish registration. Please register again."
    user = Users.query.get(user.id)
    log("registrations", format="[{date}] {ip} - {name} registered (e-mail verified by OTP) with {email}", name=user.name, email=user.email)
    return user, ""


# ----------------------------------------------------------------------------- admin side
admin_bp = Blueprint("registration_admin", __name__)


def _clean_college(name):
    name = clean_upper(name)
    return name if TEXT_RE.match(name) else None


@admin_bp.route("/admin/colleges", methods=["GET", "POST"])
@admins_only
def colleges():
    msgs = []
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            added = 0
            for line in request.form.get("names", "").splitlines():
                n = _clean_college(line)
                if n and not _college_by_name(n):
                    db.session.add(RegColleges(name=n, approved=True))
                    added += 1
            db.session.commit()
            msgs.append("%d college(s) added." % added)
        else:
            c = RegColleges.query.get(int(request.form.get("id", 0) or 0))
            if c is None:
                abort(404)
            if action == "approve":
                c.approved = True
            elif action == "rename":
                n = _clean_college(request.form.get("name", ""))
                other = _college_by_name(n) if n else None
                if not n:
                    msgs.append("Invalid name.")
                elif other and other.id != c.id:
                    msgs.append("A college with that name already exists. Use Merge instead.")
                else:
                    c.name = n
            elif action == "merge":
                target = RegColleges.query.get(int(request.form.get("target", 0) or 0))
                if target and target.id != c.id:
                    RegProfiles.query.filter_by(college_id=c.id).update({"college_id": target.id})
                    db.session.delete(c)
                    msgs.append("Merged.")
            elif action == "delete":
                if RegProfiles.query.filter_by(college_id=c.id).count():
                    msgs.append("This college still has students. Merge it into another one instead.")
                else:
                    db.session.delete(c)
            db.session.commit()
    counts = dict(db.session.query(RegProfiles.college_id, db.func.count()).group_by(RegProfiles.college_id).all())
    rows = RegColleges.query.order_by(RegColleges.approved, RegColleges.name).all()
    return render_template(
        "admin/registration/colleges.html", rows=rows, counts=counts, msgs=msgs,
        pending=[r for r in rows if not r.approved], approved=[r for r in rows if r.approved],
    )


@admin_bp.route("/admin/students")
@admins_only
def students():
    q = request.args.get("q", "").strip()
    query = db.session.query(Users, RegProfiles, RegColleges).outerjoin(RegProfiles, RegProfiles.user_id == Users.id).outerjoin(
        RegColleges, RegColleges.id == RegProfiles.college_id).filter(Users.type == "user")
    if q:
        like = "%" + q.replace("%", "") + "%"
        query = query.filter(db.or_(Users.name.like(like), Users.email.like(like), RegProfiles.roll_no.like(like.upper()), RegProfiles.full_name.like(like)))
    rows = query.order_by(Users.id.desc()).limit(500).all()
    return render_template("admin/registration/students.html", rows=rows, q=q)


@admin_bp.route("/admin/students/export.csv")
@admins_only
def students_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["user_id", "full_name", "username", "email", "roll_no", "college", "branch"])
    rows = db.session.query(Users, RegProfiles, RegColleges).outerjoin(RegProfiles, RegProfiles.user_id == Users.id).outerjoin(
        RegColleges, RegColleges.id == RegProfiles.college_id).filter(Users.type == "user").order_by(Users.id).all()
    for u, p, c in rows:
        cells = [u.id, p.full_name if p else "", u.name, u.email, p.roll_no if p else "", c.name if c else "", p.branch if p else ""]
        w.writerow(["'" + str(x) if isinstance(x, str) and x[:1] in "=+-@" else x for x in cells])   # no spreadsheet formulas
    return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=students.csv"})


@admin_bp.route("/admin/students/<int:user_id>", methods=["GET", "POST"])
@admins_only
def student_edit(user_id):
    user = Users.query.get_or_404(user_id)
    prof = RegProfiles.query.get(user_id)
    errors = []
    if request.method == "POST":
        roll_no = clean_upper(request.form.get("roll_no")).replace(" ", "")
        branch = clean_upper(request.form.get("branch"))
        full_name = re.sub(r"\s+", " ", request.form.get("full_name", "").strip())
        college_id = request.form.get("college", "")
        if not ROLL_RE.match(roll_no):
            errors.append("Roll number: 3 to 30 letters or digits.")
        if not TEXT_RE.match(branch):
            errors.append("Branch: letters and digits only.")
        if not FULLNAME_RE.match(full_name):
            errors.append("Full name: letters only.")
        if not (college_id.isdigit() and RegColleges.query.get(int(college_id))):
            errors.append("Select a college.")
        if not errors:
            if prof is None:
                prof = RegProfiles(user_id=user_id)
                db.session.add(prof)
            prof.roll_no, prof.branch, prof.full_name, prof.college_id = roll_no, branch, full_name, int(college_id)
            db.session.commit()
            return redirect(url_for("registration_admin.students"))
    return render_template(
        "admin/registration/student_edit.html", user=user, prof=prof, errors=errors,
        colleges=RegColleges.query.order_by(RegColleges.name).all(),
    )


# ----------------------------------------------------------------------------- plugin entry
def load(app):
    app.db.create_all()
    app.view_functions["auth.register"] = register       # replaces the stock one-step sign-up
    app.register_blueprint(reg_bp)
    app.register_blueprint(admin_bp)
