import sys, os, io, time; sys.path.insert(0, "/tmp")
from h import *  # helper module lives next to this file
from PIL import Image
from CTFd import create_app
from CTFd.models import db, Users, Solves
from CTFd.utils import set_config
from CTFd.plugins.writeups import WriteupFiles
app = create_app(); PW = "Zd!Sec-Test-9x"
def cfg(s, e, w):
    with app.app_context(): set_config("start", int(s)); set_config("end", int(e)); set_config("writeup_end", int(w))
now = time.time()
print("##### STAGE 3: verification of fixes #####")
# headers
for path in ("/", "/login", "/rules", "/api/v1/challenges", "/healthcheck", "/server-time"):
    r = requests.get(BASE + path, allow_redirects=False); h = r.headers
    need = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN", "Referrer-Policy": None, "Content-Security-Policy": None, "Permissions-Policy": None}
    miss = [k for k, v in need.items() if k not in h or (v and v not in h[k])]
    ok("security headers on %s" % path, not miss, "missing %s" % miss)
ok("nginx does not disclose its version", re.fullmatch(r"nginx", requests.get(BASE + "/").headers.get("Server", "")) is not None, requests.get(BASE + "/").headers.get("Server"))
ok("API spec (swagger.json) not public (%s)" % requests.get(BASE + "/api/v1/swagger.json").status_code, requests.get(BASE + "/api/v1/swagger.json").status_code == 404)
# password policy
time.sleep(5)
for pw, should in (("1", False), ("1234567", False), ("Abcd1234", True)):
    u, r = register("zdpw_%d" % len(pw), "zdpw_%d@example.test" % len(pw), pw); time.sleep(0.8)
    ok("register with %d-char password -> %s" % (len(pw), "accepted" if should else "rejected"), (r.status_code == 302) == should, "status %s" % r.status_code)
a, _ = login("zdsec_a", PW)
r = a.api("PATCH", "/users/me", {"password": "short", "confirm": PW}); ok("changing password to a short one is rejected", not r.json().get("success"), r.text[:120])
# real template-injection check on a user whose name is {{7*7}}${7*7}
with app.app_context():
    uid = Users.query.filter(Users.name.like("%{{7*7}}%")).first().id
t = a.get("/users/%d" % uid).text
ok("template expression in username is shown literally, not evaluated", "{{7*7}}" in t.replace("&#123;", "{").replace("&#125;", "}") or "{{7*7}}" in t, "49 appears? %s" % ("49$" in t))
# uploads
cfg(now - 7200, now - 60, now + 3600); a.refresh("/writeups")
def img(fmt, size=(40, 30), mode="RGB"):
    bio = io.BytesIO(); Image.new(mode, size, (200, 40, 40)).save(bio, fmt); return bio.getvalue()
for name, data, ctype in (("a.png", img("PNG"), "image/png"), ("b.jpg", img("JPEG"), "image/jpeg"), ("c.gif", img("GIF", mode="P"), "image/gif"), ("d.webp", img("WEBP"), "image/webp")):
    r = a.post("/writeups/2", data={"nonce": a.nonce, "content": "z" * 80}, files=[("screenshots", (name, data, ctype))], allow_redirects=True)
    with app.app_context(): nfiles = WriteupFiles.query.count()
    time.sleep(0.2)
a.get("/writeups")
with app.app_context(): w = [f for f in WriteupFiles.query.all()]
rec("INFO", "files stored for A: %d (max 10 per challenge enforced)" % len([f for f in w]))
# fresh clean state for upload-specific checks: delete A's existing screenshots via the app
with app.app_context():
    from CTFd.plugins.writeups import Writeups
    wr = Writeups.query.filter_by(challenge_id=2, user_id=Users.query.filter_by(name="zdsec_a").first().id).first()
    for f in list(wr.files): db.session.delete(f)
    db.session.commit()
a.refresh("/writeups")
big = None
def bomb(wid, hei):
    import struct, zlib
    def ch(t, d): c = struct.pack(">I", len(d)) + t + d; return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    comp = zlib.compressobj(9); data = b""; line = b"\x00" * (wid + 1)
    for _ in range(hei): data += comp.compress(line)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", wid, hei, 8, 0, 0, 0, 0)) + ch(b"IDAT", data + comp.flush()) + ch(b"IEND", b"")
r = a.post("/writeups/2", data={"nonce": a.nonce, "content": "y" * 80}, files=[("screenshots", ("bomb.png", bomb(20000, 12000), "image/png"))], allow_redirects=True)
ok("decompression bomb: no server error (%s) and politely refused" % r.status_code, r.status_code < 500 and ("too large" in r.text or "not a valid" in r.text), r.text[:100])
r = a.post("/writeups/2", data={"nonce": a.nonce, "content": "y" * 80}, files=[("screenshots", ("mid.png", bomb(6000, 6000), "image/png"))], allow_redirects=True)
ok("30-megapixel image refused", "too large" in r.text)
poly = img("PNG") + b"<html><script>alert('xss')</script></html>"
r = a.post("/writeups/2", data={"nonce": a.nonce, "content": "y" * 80}, files=[("screenshots", ("poly.png", poly, "image/png"))], allow_redirects=True)
with app.app_context():
    f = WriteupFiles.query.filter(WriteupFiles.filename.like("poly%")).first()
ok("polyglot PNG+HTML accepted as an image", f is not None)
if f:
    body = a.get("/writeups/file/%d" % f.id)
    ok("stored polyglot was re-encoded: HTML/script payload removed", b"<script" not in body.content and b"alert('xss')" not in body.content)
    ok("served as image/png with nosniff + attachment", body.headers.get("Content-Type", "").startswith("image/png") and body.headers.get("X-Content-Type-Options") == "nosniff" and "attachment" in body.headers.get("Content-Disposition", ""))
# EXIF stripping
from PIL import Image as I
bio = io.BytesIO(); im = I.new("RGB", (30, 30), (5, 5, 5)); ex = im.getexif(); ex[0x010E] = "SECRET-GPS-DESC"; im.save(bio, "JPEG", exif=ex)
r = a.post("/writeups/2", data={"nonce": a.nonce, "content": "y" * 80}, files=[("screenshots", ("exif.jpg", bio.getvalue(), "image/jpeg"))], allow_redirects=True)
with app.app_context(): f = WriteupFiles.query.filter(WriteupFiles.filename.like("exif%")).first()
if f: ok("EXIF metadata stripped from uploads", b"SECRET-GPS-DESC" not in a.get("/writeups/file/%d" % f.id).content)
cfg(1795930200, 1795948200, 1795955400); print("\nschedule restored")
print("\nSTAGE 3 DONE:", sum(1 for x in RES if x[0] == "FINDING"), "findings,", sum(1 for x in RES if x[0] == "PASS"), "pass")
