import re, time, json, requests
BASE = "http://nginx"
RES = []
def rec(level, title, detail=""):
    RES.append((level, title, detail)); print("%-8s %s%s" % (level, title, ("  -> " + detail) if detail else ""))
def ok(title, cond, detail_if_fail=""):
    rec("PASS" if cond else "FINDING", title, "" if cond else detail_if_fail)
def nonce_of(html):
    m = re.search(r"'csrfNonce': \"([0-9a-f]+)\"", html) or re.search(r'name="nonce"[^>]*value="([0-9a-f]+)"', html)
    return m.group(1) if m else None
class U:
    def __init__(self):
        self.s = requests.Session(); self.s.headers["User-Agent"] = "zd-sec-test"
        self.nonce = None
    def refresh(self, path="/challenges"):
        r = self.s.get(BASE + path, allow_redirects=True); self.nonce = nonce_of(r.text) or self.nonce; return r
    def get(self, p, **k): return self.s.get(BASE + p, allow_redirects=k.pop("allow_redirects", False), **k)
    def post(self, p, **k):
        k.setdefault("allow_redirects", False); return self.s.post(BASE + p, **k)
    def api(self, method, p, body=None, csrf=True, **k):
        h = k.pop("headers", {}); 
        if csrf and self.nonce: h["CSRF-Token"] = self.nonce
        return self.s.request(method, BASE + "/api/v1" + p, json=body, headers=h, allow_redirects=False, **k)
def register(name, email, pw):
    u = U(); r = u.s.get(BASE + "/register"); n = nonce_of(r.text)
    r = u.s.post(BASE + "/register", data={"name": name, "email": email, "password": pw, "nonce": n}, allow_redirects=False)
    return u, r
def login(name, pw):
    u = U(); r = u.s.get(BASE + "/login"); n = nonce_of(r.text)
    r = u.s.post(BASE + "/login", data={"name": name, "password": pw, "nonce": n}, allow_redirects=False)
    u.refresh(); return u, r
