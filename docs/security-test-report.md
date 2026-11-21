# ZeroDayCTF security test report

Scope: the whole application running locally in Docker (nginx, app, MariaDB, Redis), tested on
21 Nov 2026 with 120+ automated and manual checks. Target was a local copy only.

## Fixed
| # | Finding | Severity | Fix |
|---|---------|----------|-----|
| 1 | No password policy: a 1-character password was accepted | Medium | Minimum 8 characters (register, reset, change) |
| 2 | No security headers (CSP, nosniff, X-Frame-Options, Referrer-Policy, Permissions-Policy) | Medium | Added on every response |
| 3 | Decompression-bomb image upload caused a server error (HTTP 500) | Medium | Pixel cap (25 MP), broad error handling |
| 4 | Uploaded "images" could carry appended HTML/script (polyglot) and EXIF/GPS data | Medium | Every screenshot is fully decoded and re-encoded |
| 5 | nginx disclosed its version; allowed 4 GB request bodies | Low | `server_tokens off`; 100 MB limit |
| 6 | API specification (`/api/v1/swagger.json`) was public | Low | Blocked at nginx |
| 7 | Redis had no password | Low | `requirepass` set; URL updated |
| 8 | MariaDB root account could log in from any host | Low | Root restricted to localhost |
| 9 | `.env` was world-readable | Low | `chmod 600` |
| 10 | Users and Scoreboard visible to anonymous visitors | Privacy | Set to logged-in only; links hidden |

## Verified safe
SQL injection (70 probes, error and time based) · stored/reflected XSS and template injection in names,
profile fields and writeups (player and admin views) · CSRF on forms and API · session fixation, logout
invalidation, cookie tampering · open redirects · login brute force (429) and flag brute force (429) ·
privilege escalation and mass assignment (`type=admin` etc.) · admin pages and admin API denied to normal
users and anonymous visitors · API tokens limited to their owner · hidden challenges not exposed · other
users' emails not exposed · concurrent flag submission race (exactly one solve) · hint double-unlock charged
once · submissions blocked before start and after end · writeup IDOR (view/delete another user's screenshot) ·
path traversal in file names and URLs · screenshot size/count/type limits · containers run as non-root ·
database and Redis not reachable from outside Docker.

## Open items / residual risk
* **Dependencies were not scanned.** Flask 2.2.5 / Werkzeug 2.2.3 are pinned by upstream; newer Werkzeug
  fixed several multipart-parsing DoS issues. Run a scanner (e.g. `pip-audit`) and plan an upgrade.
* **Email is not configured**, so accounts are not verified: duplicate or fake accounts cannot be ruled out
  technically. The "one account per person" rule must be enforced by the organizers.
* **Registration reveals whether a username exists** (information only).
* **CSP allows `unsafe-inline`/`unsafe-eval`** because the theme uses inline scripts and Alpine.js. It still
  blocks external scripts, framing, plugins and form hijacking, but is not a full XSS barrier.
* **Production only:** serve over HTTPS and set `SESSION_COOKIE_SECURE=true` (cookies are not `Secure` locally).
* **Not tested:** TLS configuration (needs the real domain), server/SSH hardening, load and DoS resilience,
  per-challenge lab isolation (labs are not built yet), backups.
* The admin spell-checker tries to download dictionaries from a public CDN; CSP blocks this on purpose.
