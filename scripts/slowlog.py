"""Show how long the server really took for every request type, from the nginx access log.

    ./deploy/compose.sh logs --no-log-prefix --since 10m nginx | python3 scripts/slowlog.py

Run it right after ./scripts/login_burst.py or scripts/loadtest.py (or after a busy moment of the real event). It lists,
per kind of request, the median / 95th / 99th percentile / slowest time and how many took longer than 2 seconds.
The times are measured by nginx on the server, so they exclude the students' own internet speed.
"""
import re, sys, statistics
rows = []
for line in sys.stdin:
    m = re.search(r'"(\w+) (\S+)[^"]*" (\d+) \d+ rt=([\d.]+)', line)
    if m: rows.append((m.group(1), m.group(2), int(m.group(3)), float(m.group(4))))
def grp(method, path):
    p = path.split("?")[0]
    if p.startswith("/login") and method == "POST": return "POST /login"
    if p.startswith("/login"): return "GET  /login (page)"
    if p.startswith("/challenges"): return "GET  /challenges (board page)"
    if p.startswith("/api/v1/challenges"): return "API  challenge list"
    if p.startswith("/api/v1/users/me"): return "API  users/me"
    if p.startswith("/api/v1/notifications"): return "API  notifications"
    return "other"
by = {}
for m, p, st, rt in rows: by.setdefault(grp(m, p), []).append((rt, st))
allrt = sorted(r[3] for r in rows)
print("%-30s %6s %8s %8s %8s %8s %8s" % ("request type (server-side time)", "count", "median", "p95", "p99", "max", ">2s"))
for k in sorted(by, key=lambda x: -len(by[x])):
    v = sorted(x[0] for x in by[k]); n = len(v)
    print("%-30s %6d %7.0fms %7.0fms %7.0fms %7.0fms %6d" % (k, n, v[n // 2] * 1000, v[int(n * .95) - 1] * 1000, v[int(n * .99) - 1] * 1000, v[-1] * 1000, sum(1 for x in v if x > 2)))
bad = sum(1 for r in rows if r[2] >= 500)
print("\nALL %d requests: median %.0f ms | p99 %.0f ms | slowest %.2f s | slower than 2 s: %d | HTTP 5xx: %d" % (len(allrt), allrt[len(allrt)//2]*1000, allrt[int(len(allrt)*.99)-1]*1000, allrt[-1], sum(1 for x in allrt if x > 2), bad))
