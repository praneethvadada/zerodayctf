"""Test what happens when many students press "Login" in the same second.

Step 1, create N test accounts that share one known password (inside the app container):
    ./deploy/compose.sh exec -T -e PYTHONPATH=/opt/CTFd ctfd python scripts/login_burst.py create 1000
Step 2, fire all N login requests at the SAME INSTANT and measure how long the server takes to answer them all:
    ./deploy/compose.sh exec -T ctfd python scripts/login_burst.py fire 1000 --base http://nginx
Step 3, remove the test accounts:
    ./deploy/compose.sh exec -T -e PYTHONPATH=/opt/CTFd ctfd python scripts/loadtest_cleanup.py

All simulated students come from one IP address (like a college network), so RATELIMIT_LOGIN in .env decides
how many of them are let through; see deploy/README.md.
"""
import re
import statistics
import sys
import threading
import time
from collections import Counter

PASSWORD = "BurstTest!2026"


def create(n):
    from CTFd import create_app
    from CTFd.models import Users, db
    from CTFd.utils.crypto import hash_password

    app = create_app()
    with app.app_context():
        hashed = hash_password(PASSWORD)          # one hash, reused: creating 1000 hashes would take minutes
        existing = {u for (u,) in db.session.query(Users.name).filter(Users.name.like("bt\\_%")).all()}
        rows = [
            {"name": "bt_%d" % i, "email": "bt_%d@loadtest.invalid" % i, "password": hashed, "type": "user", "verified": True, "hidden": False, "banned": False}
            for i in range(n) if "bt_%d" % i not in existing
        ]
        if rows:
            db.session.execute(Users.__table__.insert(), rows)
            db.session.commit()
        print("test accounts ready: %d new (bt_0 .. bt_%d), password '%s'" % (len(rows), n - 1, PASSWORD))


def fire(n, base):
    import requests

    base = base.rstrip("/")
    nonce_re = re.compile(r'name="nonce"[^>]*value="([0-9a-f]+)"')
    sessions = [None] * n

    def prep(i):
        s = requests.Session()
        for _ in range(5):                      # the login page itself may be rate limited; retry quietly
            r = s.get(base + "/login", timeout=60)
            m = nonce_re.search(r.text)
            if m:
                sessions[i] = (s, m.group(1))
                return
            time.sleep(0.5)

    print("preparing %d browsers (each opens the login page first)..." % n)
    ts = [threading.Thread(target=prep, args=(i,)) for i in range(n)]
    for k in range(0, n, 100):
        batch = ts[k:k + 100]
        [t.start() for t in batch]
        [t.join() for t in batch]
    ready = [(i, x) for i, x in enumerate(sessions) if x]
    print("ready: %d" % len(ready))
    barrier = threading.Barrier(len(ready) + 1)
    results = []

    def go(i, s, nonce):
        barrier.wait()
        t = time.time()
        try:
            r = s.post(base + "/login", data={"name": "bt_%d" % i, "password": PASSWORD, "nonce": nonce}, allow_redirects=False, timeout=120)
            results.append((time.time() - t0, time.time() - t, r.status_code))
        except Exception as e:
            results.append((time.time() - t0, time.time() - t, type(e).__name__))

    t0 = 0
    ths = [threading.Thread(target=go, args=(i, s, nonce)) for i, (s, nonce) in ready]
    [t.start() for t in ths]
    time.sleep(1.0)
    t0 = time.time()
    barrier.wait()                              # every login is sent at this instant
    [t.join() for t in ths]
    total = time.time() - t0
    ok = [r for r in results if r[2] == 302]
    limited = [r for r in results if r[2] == 429]
    other = [r for r in results if r[2] not in (302, 429)]
    done = sorted(r[0] for r in ok)
    print("\n%d logins sent at the same instant" % len(results))
    print("  logged in successfully : %d" % len(ok))
    print("  refused (429 too many requests): %d" % len(limited))
    print("  other results          : %d %s" % (len(other), dict(Counter(r[2] for r in other)) if other else ""))
    if done:
        lat = sorted(r[1] for r in ok)
        pick = lambda p: done[min(len(done) - 1, int(len(done) * p))]
        print("  time until the 100th success: %.1f s | 50%% of successes done: %.1f s | 95%%: %.1f s | last: %.1f s" % (done[min(99, len(done) - 1)], pick(0.50), pick(0.95), done[-1]))
        print("  throughput while busy  : %.0f successful logins per second" % (len(ok) / max(done[-1], 0.001)))
        print("  one student's wait     : median %.1f s, 95th percentile %.1f s" % (statistics.median(lat), lat[int(len(lat) * 0.95) - 1]))
    print("  total time for the whole burst: %.1f s" % total)


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("create", "fire"):
        sys.exit(__doc__)
    n = int(sys.argv[2])
    if sys.argv[1] == "create":
        create(n)
    else:
        base = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "http://localhost"
        fire(n, base)
