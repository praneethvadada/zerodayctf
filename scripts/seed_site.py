"""Seed a fresh ZeroDayCTF database with the site content and settings.

Run this ONCE after the web setup wizard has created the admin account (and again after any
change to deploy/seed/*). It is idempotent: running it twice changes nothing the second time.

    docker compose exec -T -e PYTHONPATH=/opt/CTFd -w /opt/CTFd ctfd python scripts/seed_site.py

It creates/updates:
  * the home page (route "index") and the Rules page (route "rules")
  * visibility settings (users and scoreboard hidden from the public, challenges private)
  * the event schedule (11:00-16:00 solve, 16:00-18:00 writeup, 29 Nov 2026 IST)
  * robots.txt, site name and description

It never touches users, challenges, submissions or the admin account.
Override the schedule with SEED_START / SEED_END / SEED_WRITEUP_END (unix timestamps).
"""
import os

from CTFd import create_app
from CTFd.cache import clear_config, clear_pages
from CTFd.models import Pages, db
from CTFd.utils import get_config, set_config

SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "seed")

# 29 Nov 2026, 11:00 / 16:00 / 18:00 IST (UTC+05:30)
SCHEDULE = {
    "start": int(os.environ.get("SEED_START", 1795930200)),
    "end": int(os.environ.get("SEED_END", 1795948200)),
    "writeup_end": int(os.environ.get("SEED_WRITEUP_END", 1795955400)),
    # registrations open 24 Nov 2026 00:00 IST
    "registration_start": int(os.environ.get("SEED_REGISTRATION_START", 1795458600)),
}

SETTINGS = {
    "ctf_name": "ZeroDayCTF",
    "ctf_description": (
        "ZeroDayCTF is a capture-the-flag (CTF) cybersecurity competition. Hack real-world "
        "challenges, learn practical security skills and compete on a live scoreboard."
    ),
    "account_visibility": "private",
    "score_visibility": "private",
    "challenge_visibility": "private",
    "registration_visibility": "public",
    "verify_emails": False,
}


def read(name):
    with open(os.path.join(SEED, name), encoding="utf-8") as f:
        return f.read()


def upsert_page(route, title, content, hidden):
    page = Pages.query.filter_by(route=route).first()
    created = page is None
    if created:
        page = Pages(route=route)
        db.session.add(page)
    page.title, page.content, page.format = title, content, "html"
    page.draft, page.hidden, page.auth_required = False, hidden, False
    return "created" if created else "updated"


def main():
    app = create_app()
    with app.app_context():
        if get_config("setup") is None:
            raise SystemExit("The setup wizard has not been completed yet. Open the site, finish /setup, then run this again.")
        print("home page :", upsert_page("index", "ZeroDayCTF", read("landing.html"), hidden=False))
        print("rules page:", upsert_page("rules", "Rules", read("rules.html"), hidden=True))
        db.session.commit()
        for key, value in {**SETTINGS, **SCHEDULE}.items():
            set_config(key, value)
        set_config("robots_txt", read("robots.txt"))
        clear_pages()
        clear_config()
        print("settings  : visibility, schedule and robots.txt applied")
        print("schedule  :", SCHEDULE)


if __name__ == "__main__":
    main()
