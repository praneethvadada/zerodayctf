# ZerodayCTF

**ZerodayCTF** is a Capture The Flag (CTF) platform hosted at **[zerodayctf.com](https://zerodayctf.com)**.

> Logo and final branding: coming soon.

## What is ZerodayCTF?

ZerodayCTF is a self-hosted CTF platform where players solve security challenges, submit flags, and compete on a live scoreboard, either individually or in teams. Organizers manage everything (challenges, users, scoring, content, schedule) from a built-in admin panel.

## Features

**For players**
- Register and log in as an individual, or create and join teams
- Browse challenges by category, download files, unlock hints
- Submit flags with brute-force protection and attempt limits
- Live scoreboard, score graphs, and public profile pages
- Notifications from organizers (real-time)
- Rate and review challenges after solving them

**For organizers (admin panel)**
- Challenge management: standard and dynamic-scoring challenges, static and regex flags, hints, tags, topics, file uploads, prerequisites, hidden challenges, attempt limits
- Users, teams, and brackets management (hide, ban, verify, edit)
- Audiences and modules to control which groups can see which content
- Submissions review (correct, incorrect, and all), scoreboard control and score freezing
- Statistics dashboard
- Custom pages (Markdown), notifications, and legal pages (Terms of Service, Privacy)
- Full configuration: user or team mode, registration rules, visibility, start and end times, theme, logo, email, localization
- Import and export of CTF data, and CSV import and export
- Plugin and theme system for extensions

## Tech stack

- Python 3.11, Flask, SQLAlchemy
- MariaDB (production) or SQLite (development)
- Redis cache
- Gunicorn (gevent) behind Nginx
- Docker and Docker Compose

## Run with Docker

```bash
docker compose up --build
```

Then open <http://localhost> and complete the first-run setup (event name, admin account, mode, schedule).

> **Before going to production**, change the database passwords in `docker-compose.yml`, set a fixed `SECRET_KEY`, and serve the site over HTTPS.

## Run for development

```bash
pip install -r requirements.txt
python serve.py
```

Settings live in `CTFd/config.ini`. Any value can also be given as an environment variable.

## Project layout

| Path | Purpose |
| --- | --- |
| `CTFd/` | Application code (routes, models, API, admin) |
| `CTFd/themes/core` | Player-facing theme |
| `CTFd/themes/admin` | Admin panel theme |
| `CTFd/plugins/` | Challenge types and flag types |
| `migrations/` | Database migrations |
| `conf/nginx` | Nginx reverse-proxy config |
| `tests/` | Test suite |

## Credits and license

ZerodayCTF is built on the open-source [CTFd](https://github.com/CTFd/CTFd) framework and is distributed under the Apache License 2.0. See [LICENSE](LICENSE). CTFd is a trademark of its respective owners; the original logo and "Powered by CTFd" attribution will be replaced during our UI update.
