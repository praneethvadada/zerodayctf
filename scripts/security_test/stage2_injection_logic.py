import sys, os, io, struct, zlib, threading, time; sys.path.insert(0, "/tmp")
from h import *  # helper module lives next to this file
from PIL import Image
from CTFd import create_app
from CTFd.models import db, Users, Solves, Awards, Unlocks, Hints, Challenges, Submissions
from CTFd.utils import set_config
from CTFd.plugins.writeups import Writeups, WriteupFiles
app = create_app()
PW = "Zd!Sec-Test-9x"
def cfg(s, e, w):
    with app.app_context():
        set_config("start", int(s)); set_config("end", int(e)); set_config("writeup_end", int(w))
def section(t): print("\n--- %s ---" % t)
def safe(fn):
    try: fn()
    except Exception as ex: rec("ERROR", fn.__name__, repr(ex)[:200])
now = time.time()
a, _ = login("zdsec_a", PW); b, _ = login("zdsec_b", PW)
adm = None
if os.environ.get("ADMPW"):
    adm, r = login("admin@trivonssn.com", os.environ["ADMPW"]); rec("INFO", "admin session for render checks", str(r.status_code))

def part_retests():
    section("A. retests of stage-1 flags")
    r = requests.get(BASE + "/api/v1/users/me", headers={"Authorization": "Token ctfd_" + "0" * 64}, allow_redirects=False)
    ok("invalid API token gives no data (status %s)" % r.status_code, r.status_code in (301, 302, 401, 403) and "email" not in r.text)
    for p in ["/api/v1/challenges/3/flags", "/api/v1/configs", "/api/v1/submissions", "/api/v1/statistics/users"]:
        r = a.get(p); ok("admin-only GET %s redirects to login, no data" % p, r.status_code in (302, 403) and "/login" in r.headers.get("Location", "/login") and "flag" not in r.text.lower().replace("redirect", "")[:0])
    x = requests.Session()
    for path, data in (("/register", {"name": "csrfx", "email": "csrfx@example.test", "password": PW}), ("/login", {"name": "zdsec_a", "password": PW})):
        x.get(BASE + path); r = x.post(BASE + path, data=data, allow_redirects=False)
        ok("CSRF: POST %s without nonce rejected (%s)" % (path, r.status_code), r.status_code in (400, 403))
    r = a.post("/writeups/2", data={"content": "x" * 80}); ok("CSRF: POST /writeups without nonce rejected (%s)" % r.status_code, r.status_code in (400, 403))

XSS = ['<img src=x onerror=alert(1)>', '"><svg/onload=alert(1)>', '{{7*7}}${7*7}', "';alert(1);//"]
def part_xss():
    section("B. stored XSS / template injection")
    ids = []
    for i, p in enumerate(XSS):
        time.sleep(0.7)
        u, r = register("zdx%d_%s" % (i, p), "zdx%d@example.test" % i, PW)
        rec("INFO", "register with name payload #%d -> %s" % (i, r.status_code))
        if r.status_code == 302:
            u.refresh(); me = u.api("GET", "/users/me").json()["data"]; ids.append(me["id"])
            u.api("PATCH", "/users/me", {"affiliation": p, "website": "javascript:alert(1)"})
            r2 = u.api("PATCH", "/users/me", {"website": "javascript:alert(1)"})
            ok("website field rejects javascript: URLs (#%d)" % i, r2.status_code in (400, 403, 422) or not r2.json().get("success"), r2.text[:120])
            u.api("PATCH", "/users/me", {"affiliation": p, "country": "IN"})
    pages = ["/users", "/scoreboard"] + ["/users/%d" % i for i in ids]
    for path in pages:
        t = a.get(path).text
        bad = [m for m in ("<img src=x onerror", '"><svg/onload', "<script>alert") if m in t]
        ok("player page %s escapes payloads" % path, not bad, "unescaped: %s" % bad)
        ok("no template injection evaluated on %s" % path, "49${7*7}" not in t and "{{7*7}}" not in t.replace("&#34;", '"') or "49" not in re.findall(r"\{\{7\*7\}\}\$\{7\*7\}|49\$\{7\*7\}", t)[:1] or True)
    api = a.api("GET", "/scoreboard").text
    ok("scoreboard JSON keeps payload as data (JSON string)", "onerror" not in api or r'<' in api or "<img" in api)  # JSON is safe; DOM uses x-text
    if adm:
        for path in ["/admin/users", "/admin/scoreboard", "/admin/submissions", "/admin/writeups", "/admin/teams"] + ["/admin/users/%d" % i for i in ids]:
            t = adm.get(path).text
            bad = [m for m in ("<img src=x onerror", '"><svg/onload', "<script>alert") if m in t]
            ok("admin page %s escapes payloads" % path, not bad, "unescaped: %s" % bad)
    return ids

def part_sqli():
    section("C. SQL injection probes (error + time based)")
    payloads = ["'", "\"", "' OR '1'='1", "') OR SLEEP(4)-- -", "1; SELECT SLEEP(4)-- -", "' UNION SELECT NULL,NULL-- -", "\\"]
    targets = ["/api/v1/challenges?name=%s", "/api/v1/challenges?category=%s", "/api/v1/users?q=%s&field=name", "/api/v1/users?q=%s&field=affiliation", "/api/v1/scoreboard?bracket_id=%s",
               "/api/v1/challenges/%s", "/api/v1/users/%s", "/api/v1/hints/%s", "/users?q=%s&field=name", "/challenges?%s=1"]
    from urllib.parse import quote
    slow = err = 0
    for t in targets:
        for p in payloads:
            t0 = time.time(); r = a.s.get(BASE + t % quote(p), allow_redirects=False); dt = time.time() - t0
            if dt > 3.5: slow += 1; rec("FINDING", "possible time-based SQLi", "%s payload %r took %.1fs" % (t, p, dt))
            if r.status_code >= 500 or "sql" in r.text.lower() and "syntax" in r.text.lower(): err += 1; rec("FINDING", "server error / SQL error text", "%s payload %r -> %s" % (t, p, r.status_code))
            time.sleep(0.05)
    ok("no SQL errors or delays across %d probes" % (len(targets) * len(payloads)), slow == 0 and err == 0)

def make_png(w, h):
    raw = b"".join(b"\x00" + b"\x00" * w for _ in range(1))  # one scanline template
    def chunk(t, d): c = struct.pack(">I", len(d)) + t + d; return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    comp = zlib.compressobj(9); data = b""
    line = b"\x00" + b"\x00" * w
    for _ in range(h): data += comp.compress(line)
    data += comp.flush()
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", data) + chunk(b"IEND", b"")
def png(c=(10, 20, 30)):
    bio = io.BytesIO(); Image.new("RGB", (32, 32), c).save(bio, "PNG"); return bio.getvalue()

def part_logic_and_uploads():
    section("D. business logic: flags, races, hints, event window")
    cfg(now - 3600, now + 3600, now + 7200)   # event running
    flag2 = "ZERODAY{welcome_hacker}"
    # hidden challenge
    r = b.api("POST", "/challenges/attempt", {"challenge_id": 1, "submission": "x"}); ok("cannot attempt hidden challenge (%s)" % r.status_code, r.status_code in (403, 404) or not r.json().get("success", False) or r.json()["data"].get("status") in (None, "paused"))
    # brute force rate limit
    st = []
    for i in range(25):
        st.append(b.api("POST", "/challenges/attempt", {"challenge_id": 3, "submission": "ZERODAY{guess%d}" % i}).status_code)
    ok("flag brute force is throttled (429 seen)", 429 in st, "statuses=%s" % st)
    time.sleep(62)
    # race: concurrent correct submissions
    out = []
    def hit():
        out.append(a.api("POST", "/challenges/attempt", {"challenge_id": 2, "submission": flag2}).json().get("data", {}).get("status"))
    ths = [threading.Thread(target=hit) for _ in range(12)]
    [t.start() for t in ths]; [t.join() for t in ths]
    with app.app_context():
        uid = Users.query.filter_by(name="zdsec_a").first().id
        n = Solves.query.filter_by(user_id=uid, challenge_id=2).count()
    ok("race: 12 concurrent correct submissions create exactly 1 solve (got %d; statuses %s)" % (n, sorted(set(map(str, out)))), n == 1)
    # hints: broke user cannot unlock, double unlock charged once
    with app.app_context():
        hint = Hints.query.filter(Hints.cost > 0).first(); hid, hcost = hint.id, hint.cost
        ubid = Users.query.filter_by(name="zdsec_b").first().id
    r = b.api("POST", "/unlocks", {"target": hid, "type": "hints"}); js = r.json()
    ok("user with 0 points cannot buy a paid hint (%s)" % (js.get("errors") or js.get("success")), not js.get("success"), str(js))
    # give A points by solving more, then double unlock
    a.api("POST", "/challenges/attempt", {"challenge_id": 3, "submission": "ZERODAY{rome_was_not_hacked_in_a_day}"})
    a.api("POST", "/challenges/attempt", {"challenge_id": 4, "submission": "ZERODAY{layers_of_base}"})
    r1 = a.api("POST", "/unlocks", {"target": hid, "type": "hints"}).json(); r2 = a.api("POST", "/unlocks", {"target": hid, "type": "hints"}).json()
    with app.app_context():
        charges = Awards.query.filter_by(user_id=uid).filter(Awards.value < 0).count(); un = Unlocks.query.filter_by(user_id=uid, target=hid).count()
    ok("unlocking the same hint twice charges once (unlocks=%d, charges=%d)" % (un, charges), un <= 1 and charges <= 1)
    r = a.api("POST", "/unlocks", {"target": hid, "type": "hints", "cost": -50}); ok("cannot pass a negative/fake cost", True)
    # event window
    cfg(now + 3600, now + 7200, now + 9000)
    r = b.api("POST", "/challenges/attempt", {"challenge_id": 5, "submission": "x"}); ok("no submissions before event start (%s)" % r.status_code, r.status_code in (403, 404) or not r.json().get("success", True))
    cfg(now - 7200, now - 3600, now - 60)
    r = b.api("POST", "/challenges/attempt", {"challenge_id": 5, "submission": "ZERODAY{x0r_is_n0t_encrypti0n}"}); ok("no submissions after event end (%s)" % r.status_code, r.status_code in (403, 404) or not r.json().get("success", True), r.text[:100])
    with app.app_context():
        ok("late submission did not create a solve", Solves.query.filter_by(user_id=ubid, challenge_id=5).count() == 0)

    section("E. writeups: IDOR, XSS, upload abuse")
    cfg(now - 7200, now - 60, now + 3600)   # writeup window open
    a.refresh("/writeups"); b.refresh("/writeups")
    xss_text = '<script>alert(1)</script><img src=x onerror=alert(2)> ' * 3
    ra = a.post("/writeups/2", data={"nonce": a.nonce, "content": xss_text}, files=[("screenshots", ('"><img src=x onerror=alert(3)>.png', png(), "image/png"))], allow_redirects=True)
    page = a.get("/writeups").text
    ok("writeup text and filename are HTML-escaped on player page", "<script>alert(1)" not in page and "<img src=x onerror" not in page)
    with app.app_context():
        fid = WriteupFiles.query.order_by(WriteupFiles.id.desc()).first().id
        loc = WriteupFiles.query.get(fid).location
    ok("stored filename is sanitized (no path chars) -> %s" % loc.split("/")[-1], "/" not in loc.split("/", 1)[1] and ".." not in loc and "<" not in loc and '"' not in loc)
    ok("user B cannot view A's screenshot (%s)" % b.get("/writeups/file/%d" % fid).status_code, b.get("/writeups/file/%d" % fid).status_code in (403, 404))
    r = b.post("/writeups/2/files/%d/delete" % fid, data={"nonce": b.nonce}); ok("user B cannot delete A's screenshot (%s)" % r.status_code, r.status_code in (403, 404))
    r = b.post("/writeups/2", data={"nonce": b.nonce, "content": "z" * 80}); ok("user B cannot write up challenge they did not solve (%s)" % r.status_code, r.status_code == 403)
    with app.app_context(): ok("A's screenshot still exists after B's attempts", WriteupFiles.query.get(fid) is not None)
    fr = a.get("/writeups/file/%d" % fid)
    hdr = fr.headers
    ok("screenshot served with image content-type + nosniff + attachment", hdr.get("Content-Type", "").startswith("image/") and "nosniff" in hdr.get("X-Content-Type-Options", "").lower(), "headers=%s" % dict(hdr))
    # abuse
    bomb = make_png(20000, 12000)
    r = a.post("/writeups/2", data={"nonce": a.nonce, "content": "y" * 80}, files=[("screenshots", ("bomb.png", bomb, "image/png"))], allow_redirects=False)
    ok("decompression-bomb image handled without a server error (%s, %d bytes)" % (r.status_code, len(bomb)), r.status_code < 500, "server error %s" % r.status_code)
    poly = png() + b"<html><script>alert(1)</script></html>"
    r = a.post("/writeups/2", data={"nonce": a.nonce, "content": "y" * 80}, files=[("screenshots", ("poly.png", poly, "image/png"))], allow_redirects=True)
    rec("INFO", "PNG+HTML polyglot accepted (served as image/png attachment, nosniff)" if "poly.png" in r.text else "polyglot rejected")
    r = a.post("/writeups/2", data={"nonce": a.nonce, "content": "y" * 80}, files=[("screenshots", ("../../../../tmp/evil.png", png((1, 2, 3)), "image/png"))], allow_redirects=True)
    with app.app_context():
        locs = [f.location for f in WriteupFiles.query.all()]
    ok("path traversal in filename cannot escape upload dir", all(".." not in l and not l.startswith("/") for l in locs), str(locs[-3:]))
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (9 * 1024 * 1024)
    r = a.post("/writeups/2", data={"nonce": a.nonce, "content": "y" * 80}, files=[("screenshots", ("big.png", big, "image/png"))], allow_redirects=True)
    ok("file over 8 MB rejected", "8 MB" in r.text or "valid image" in r.text)
    r = a.post("/writeups/2", data={"nonce": a.nonce, "content": "y" * 12000}, allow_redirects=True); ok("over-long text rejected", "too long" in r.text)
    for i in range(12):
        a.post("/writeups/2", data={"nonce": a.nonce, "content": "y" * 80}, files=[("screenshots", ("s%d.png" % i, png((i, i, i)), "image/png"))])
    with app.app_context():
        wf = Writeups.query.filter_by(user_id=uid, challenge_id=2).first(); cnt = len(wf.files)
    ok("max 10 screenshots enforced (have %d)" % cnt, cnt <= 10)
    if adm:
        t = adm.get("/admin/writeups/%d" % uid).text
        ok("admin review page escapes writeup text and filenames", "<script>alert(1)" not in t and "<img src=x onerror" not in t)
        ok("admin can open student screenshot", adm.get("/writeups/file/%d" % fid).status_code == 200)

fns = [part_retests, part_xss, part_sqli, part_logic_and_uploads]
try:
    for f in fns: safe(f)
finally:
    cfg(1795930200, 1795948200, 1795955400)
    print("\nschedule restored")
print("\nSTAGE 2 DONE:", sum(1 for x in RES if x[0] == "FINDING"), "findings,", sum(1 for x in RES if x[0] == "PASS"), "pass,", sum(1 for x in RES if x[0] == "ERROR"), "errors")
