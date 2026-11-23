"""Simulate many ZeroDayCTF players to check capacity BEFORE the event.

Each simulated player registers, logs in, then keeps browsing for the test duration like a real
player: opens the challenge board, opens challenges, checks the scoreboard and live notifications,
and now and then submits a (wrong) flag.

Run it from a machine OTHER than the web server if you can (a second small EC2 instance is ideal), and
from a staging copy or before the real event; it creates accounts named "lt_<run>_<n>".
The event window must be OPEN while testing (Admin > Config > Time), otherwise challenge pages return 403.

    python3 scripts/loadtest.py --base https://www.zerodayctf.com --users 500 --duration 120
    # needs:  pip install requests      (already present inside the app container)

Remove the test accounts afterwards (inside the app container):
    ./deploy/compose.sh exec -T -e PYTHONPATH=/opt/CTFd ctfd python scripts/loadtest_cleanup.py

One generator machine handles roughly 1,000 simulated players; use several machines for more.
Make sure the rate limits in .env are raised (RATELIMIT_LOGIN / REGISTER / EVENTS) because every simulated
player shares one IP address, exactly like a college network.
"""
import argparse
import random
import re
import statistics
import threading
import time
from collections import defaultdict

import requests

NONCE_RE = re.compile(r"'csrfNonce': \"([0-9a-f]+)\"|name=\"nonce\"[^>]*value=\"([0-9a-f]+)\"")

lock = threading.Lock()
lat = defaultdict(list)        # endpoint -> list of seconds
codes = defaultdict(lambda: defaultdict(int))
errors = defaultdict(int)
stop_at = 0.0


def record(name, seconds, status):
    with lock:
        lat[name].append(seconds)
        codes[name][status] += 1


def timed(session, name, method, url, **kw):
    t = time.time()
    try:
        r = session.request(method, url, timeout=30, allow_redirects=kw.pop("allow_redirects", True), **kw)
        record(name, time.time() - t, r.status_code)
        return r
    except requests.RequestException as e:
        with lock:
            errors[type(e).__name__] += 1
        record(name, time.time() - t, "EXC")
        return None


def nonce_of(html):
    m = NONCE_RE.search(html or "")
    return (m.group(1) or m.group(2)) if m else None


def player(args, idx, run):
    name = "lt_%s_%d" % (run, idx)
    pw = "LoadTest!%s%d" % (run, idx)
    s = requests.Session()
    s.headers["User-Agent"] = "zerodayctf-loadtest"
    base = args.base.rstrip("/")
    time.sleep(random.random() * args.ramp)                        # spread the arrivals
    r = timed(s, "register page", "GET", base + "/register")
    n = nonce_of(r.text) if r else None
    r = timed(s, "register", "POST", base + "/register", data={"name": name, "email": name + "@loadtest.invalid", "password": pw, "nonce": n}, allow_redirects=False)
    if not r or r.status_code not in (302, 200):
        return
    if r.status_code == 200:                                          # registration failed (limit etc.): try login instead
        r = timed(s, "login page", "GET", base + "/login"); n = nonce_of(r.text) if r else None
        timed(s, "login", "POST", base + "/login", data={"name": name, "password": pw, "nonce": n}, allow_redirects=False)
    r = timed(s, "challenge board", "GET", base + "/challenges")
    n = nonce_of(r.text) if r else None
    r = timed(s, "api challenges", "GET", base + "/api/v1/challenges")
    try:
        ids = [c["id"] for c in r.json().get("data", [])] if r is not None and r.status_code == 200 else []
    except ValueError:
        ids = []
    while time.time() < stop_at:
        time.sleep(random.uniform(args.think_min, args.think_max))
        roll = random.random()
        if roll < 0.40 and ids:
            timed(s, "api challenge detail", "GET", base + "/api/v1/challenges/%d" % random.choice(ids))
        elif roll < 0.55:
            timed(s, "challenge board", "GET", base + "/challenges")
        elif roll < 0.70:
            timed(s, "api scoreboard", "GET", base + "/api/v1/scoreboard")
        elif roll < 0.80:
            timed(s, "api notifications", "HEAD", base + "/api/v1/notifications?since_id=0")
        elif roll < 0.88:
            timed(s, "server-time", "GET", base + "/server-time")
        elif roll < 0.95 and ids and n:
            timed(s, "flag attempt", "POST", base + "/api/v1/challenges/attempt", json={"challenge_id": random.choice(ids), "submission": "ZERODAY{wrong_%d}" % random.randint(1, 10 ** 6)}, headers={"CSRF-Token": n})
        else:
            timed(s, "public home", "GET", base + "/")


def pct(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(len(vals) * p / 100))] if vals else 0


def main():
    global stop_at
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost")
    ap.add_argument("--users", type=int, default=200)
    ap.add_argument("--duration", type=int, default=60, help="seconds of browsing after sign-up")
    ap.add_argument("--ramp", type=float, default=20, help="seconds over which players arrive")
    ap.add_argument("--think-min", type=float, default=1.0)
    ap.add_argument("--think-max", type=float, default=4.0)
    args = ap.parse_args()
    run = "%x" % int(time.time() % 100000)
    stop_at = time.time() + args.ramp + args.duration + 10
    print("Simulating %d players against %s for ~%ds (run id %s)" % (args.users, args.base, args.ramp + args.duration, run))
    t0 = time.time()
    threads = [threading.Thread(target=player, args=(args, i, run), daemon=True) for i in range(args.users)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    wall = time.time() - t0
    total = sum(len(v) for v in lat.values())
    print("\n%-24s %7s %8s %8s %8s %8s  %s" % ("request", "count", "p50 ms", "p95 ms", "p99 ms", "max ms", "status codes"))
    bad = 0
    for k in sorted(lat, key=lambda x: -len(lat[x])):
        v = lat[k]
        sc = ", ".join("%s:%d" % (c, n) for c, n in sorted(codes[k].items(), key=lambda x: str(x[0])))
        print("%-24s %7d %8.0f %8.0f %8.0f %8.0f  %s" % (k, len(v), pct(v, 50) * 1000, pct(v, 95) * 1000, pct(v, 99) * 1000, max(v) * 1000, sc))
        bad += sum(n for c, n in codes[k].items() if (c == "EXC" or (isinstance(c, int) and c >= 500)))
    allv = [x for v in lat.values() for x in v]
    rate = total / wall
    print("\n%d requests in %.0fs = %.0f requests/s | overall p95 %.0f ms | server errors/timeouts: %d (%.2f%%)" % (total, wall, rate, pct(allv, 95) * 1000, bad, 100.0 * bad / max(1, total)))
    if errors:
        print("client-side errors:", dict(errors))
    ok = bad / max(1, total) < 0.01 and pct(allv, 95) < 1.5
    print("RESULT:", "PASS (under 1% errors and p95 under 1.5 s)" if ok else "ATTENTION: look at the slowest endpoints and the server logs")
    print("Remember to delete the test accounts (scripts/loadtest_cleanup.py).")


if __name__ == "__main__":
    main()
