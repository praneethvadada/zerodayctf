import sys; sys.path.insert(0, "/tmp")
from h import *  # helper module lives next to this file
print("##### STAGE 1: authentication / session / authorization #####")
PW = "Zd!Sec-Test-9x"
# accounts
a, r = register("zdsec_a", "zdsec_a@example.test", PW); ok("register user A", r.status_code == 302, str(r.status_code))
b, r = register("zdsec_b", "zdsec_b@example.test", PW); ok("register user B", r.status_code == 302, str(r.status_code))
a.refresh(); b.refresh()
time.sleep(6)
# --- password policy
w, r = register("zdsec_weak", "zdsec_weak@example.test", "1")
ok("weak 1-character password rejected", r.status_code != 302, "accepted a 1-char password (no password policy)")
# --- user enumeration
x = U(); n = nonce_of(x.s.get(BASE + "/register").text)
r = x.s.post(BASE + "/register", data={"name": "zdsec_a", "email": "new@example.test", "password": PW, "nonce": n})
enum_name = "already" in r.text.lower() and "name" in r.text.lower()
rec("INFO" if enum_name else "PASS", "register reveals whether a username exists" if enum_name else "register does not reveal usernames")
time.sleep(1)
l1, r1 = login("zdsec_a", "wrong-password"); l2, r2 = login("no_such_user_zz", "wrong-password")
same = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", r1.text if r1.text else "")) 
t1 = u1 = None
a_msg = requests.post(BASE + "/login", data={"name": "zdsec_a", "password": "bad", "nonce": nonce_of(requests.get(BASE + "/login").text)}) 
# compare messages using one session each
def login_msg(name):
    s = requests.Session(); n = nonce_of(s.get(BASE + "/login").text)
    t = s.post(BASE + "/login", data={"name": name, "password": "bad-pass-zz", "nonce": n}).text
    m = re.search(r'alert[^>]*>\s*<[^>]*>\s*([^<]+)|role="alert">\s*([^<]+)', t, re.S); return (m.group(1) or m.group(2)).strip() if m else "?"
ok("login error message identical for real and fake users", login_msg("zdsec_a") == login_msg("no_such_user_zz"), "different messages enumerate users")
# --- rate limit
codes = []
s = requests.Session(); n = nonce_of(s.get(BASE + "/login").text)
for i in range(16):
    codes.append(s.post(BASE + "/login", data={"name": "zdsec_a", "password": "bad%d" % i, "nonce": n}).status_code)
ok("login brute force is rate limited (429)", 429 in codes, "codes=%s" % codes)
time.sleep(8)
# --- session fixation / logout / tamper
pre = requests.Session(); n = nonce_of(pre.get(BASE + "/login").text); before = pre.cookies.get("session")
r = pre.post(BASE + "/login", data={"name": "zdsec_a", "password": PW, "nonce": n}, allow_redirects=False)
ok("login succeeds", r.status_code == 302, str(r.status_code)); after = pre.cookies.get("session")
ok("session id changes on login (no fixation)", before != after)
old = after
pre.get(BASE + "/logout", allow_redirects=False)
chk = requests.get(BASE + "/settings", cookies={"session": old}, allow_redirects=False)
ok("old session cookie is dead after logout", chk.status_code in (302, 403), "status %s still logged in" % chk.status_code)
t = a.s.cookies.get("session"); bad = t[:-3] + ("AAA" if not t.endswith("AAA") else "BBB")
ok("tampered session cookie rejected", requests.get(BASE + "/settings", cookies={"session": bad}, allow_redirects=False).status_code in (302, 403))
# --- open redirect
s = requests.Session(); n = nonce_of(s.get(BASE + "/login").text)
for nxt in ("https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)"):
    time.sleep(0.6)
    r = s.post(BASE + "/login?next=" + nxt, data={"name": "zdsec_a", "password": PW, "nonce": n}, allow_redirects=False)
    loc = r.headers.get("Location", "")
    ok("no open redirect via next=%s" % nxt, "evil" not in loc and not loc.startswith("javascript"), "redirected to %s" % loc)
    s.get(BASE + "/logout"); n = nonce_of(s.get(BASE + "/login").text)
# --- CSRF
ok("API write without CSRF token rejected", a.api("PATCH", "/users/me", {"affiliation": "csrf"}, csrf=False).status_code in (400, 403))
ok("form POST without nonce rejected", a.post("/settings", data={"name": "zdsec_a"}).status_code in (400, 403))
# --- anonymous access
anon = U()
for p in ["/api/v1/challenges", "/api/v1/users", "/api/v1/scoreboard", "/api/v1/notifications", "/api/v1/pages", "/api/v1/statistics/users", "/api/v1/configs", "/api/v1/submissions", "/api/v1/flags", "/api/v1/files", "/api/v1/hints", "/api/v1/users/me", "/api/v1/tokens"]:
    r = anon.get(p); body = r.text[:200]
    ok("anonymous blocked: %s (%s)" % (p, r.status_code), r.status_code in (302, 401, 403), "returned data: %s" % body)
# --- normal user vs admin surface
for p in ["/admin", "/admin/config", "/admin/users", "/admin/challenges", "/admin/submissions", "/admin/writeups", "/admin/export", "/admin/reset", "/admin/pages", "/admin/notifications", "/admin/statistics", "/admin/import"]:
    r = a.get(p); ok("user blocked from %s (%s)" % (p, r.status_code), r.status_code in (302, 403, 404), "reached admin page")
adm = [("POST", "/challenges", {"name": "x", "category": "x", "description": "x", "value": 1, "type": "standard", "state": "visible"}),
       ("DELETE", "/challenges/3", None), ("PATCH", "/challenges/3", {"value": 1}), ("GET", "/challenges/3/flags", None),
       ("POST", "/flags", {"challenge_id": 3, "content": "x", "type": "static"}), ("GET", "/configs", None), ("PATCH", "/configs", {"ctf_name": "hacked"}),
       ("GET", "/submissions", None), ("DELETE", "/users/1", None), ("PATCH", "/users/1", {"name": "pwned"}), ("POST", "/users", {"name": "x", "email": "x@x.io", "password": "x"}),
       ("POST", "/notifications", {"title": "x", "content": "x"}), ("POST", "/pages", {"title": "x", "route": "x", "content": "x"}),
       ("GET", "/exports/raw", None), ("GET", "/statistics/users", None), ("POST", "/files", None), ("DELETE", "/users/3", None), ("PATCH", "/users/3", {"type": "admin"})]
for m, p, body in adm:
    r = a.api(m, p, body); ok("user denied %s /api/v1%s (%s)" % (m, p, r.status_code), r.status_code in (400, 401, 403, 404, 405), "unexpected %s: %s" % (r.status_code, r.text[:120]))
# --- mass assignment / privilege escalation
me = a.api("GET", "/users/me").json()["data"]; uid = me["id"]
for body in ({"type": "admin"}, {"verified": True}, {"hidden": True}, {"banned": False}, {"id": 1}, {"email": "admin@trivonssn.com"}, {"password": "x", "confirm": ""}):
    r = a.api("PATCH", "/users/me", body)
now = a.api("GET", "/users/me").json()["data"]
ok("PATCH /users/me cannot make me admin", now.get("type") != "admin", str(now.get("type")))
ok("PATCH /users/me cannot change id", now["id"] == uid)
chk = a.get("/admin"); ok("still blocked from /admin after escalation attempts", chk.status_code in (302, 403))
# register-time escalation
z, r = register("zdsec_esc", "zdsec_esc@example.test", PW + "1") if False else (None, None)
# other user's data exposure
other = a.api("GET", "/users/%d" % 1)
d = other.json().get("data", {}) if other.status_code == 200 else {}
ok("other users' emails not exposed in API", "email" not in d or not d.get("email"), "email=%s" % d.get("email"))
lst = a.api("GET", "/users").json().get("data", [])
ok("user list does not expose emails", all("email" not in u for u in lst), "emails present")
ok("hidden challenge not visible (id 1)", a.api("GET", "/challenges/1").status_code in (403, 404))
ok("hidden challenge hidden in list", all(c["id"] != 1 for c in a.api("GET", "/challenges").json().get("data", [])) if a.api("GET", "/challenges").status_code == 200 else True)
# token handling
tk = a.api("POST", "/tokens", {"description": "t", "expiration": "2030-01-01"}).json().get("data", {}).get("value")
if tk:
    h = {"Authorization": "Token " + tk, "Content-Type": "application/json"}
    r = requests.get(BASE + "/api/v1/users/me", headers=h); ok("user API token works for own account", r.status_code == 200)
    r = requests.get(BASE + "/api/v1/configs", headers=h); ok("user API token cannot read admin configs", r.status_code in (401, 403), str(r.status_code))
    r = requests.post(BASE + "/api/v1/challenges", headers=h, json={"name": "x"}); ok("user API token cannot create challenges", r.status_code in (401, 403), str(r.status_code))
r = requests.get(BASE + "/api/v1/users/me", headers={"Authorization": "Token ctfd_" + "0" * 64}); ok("invalid token rejected", r.status_code in (401, 403))
print("\nSTAGE 1 DONE:", sum(1 for x in RES if x[0] == "FINDING"), "findings,", sum(1 for x in RES if x[0] == "PASS"), "pass")
