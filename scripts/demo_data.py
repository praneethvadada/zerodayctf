"""Demo players and solves for previewing the scoreboard.

Run inside the app container:
    docker compose exec -T -e PYTHONPATH=/opt/CTFd -w /opt/CTFd ctfd python scripts/demo_data.py add
    docker compose exec -T -e PYTHONPATH=/opt/CTFd -w /opt/CTFd ctfd python scripts/demo_data.py remove

All demo accounts use the e-mail domain @demo.zerodayctf.invalid, so `remove`
deletes exactly those users (their solves and fails are removed with them).
"""
import datetime
import random
import secrets
import sys

from CTFd import create_app
from CTFd.models import Challenges, Fails, Solves, Users, db

DOMAIN = "@demo.zerodayctf.invalid"

# name -> challenge names they solve, in order (earlier = earlier in the event)
PLAYERS = {
    "r00tkit_riya": ["Welcome to ZeroDayCTF", "Caesar's Secret", "Base Camp", "XOR Gate", "Reverse the Strings", "Login Bypass", "Cookie Monster", "Hidden in Plain Sight", "Zero Day Quiz", "Trace the Handle", "Where Was This Taken?", "Buffer Overflow 101"],
    "n0va_karthik": ["Welcome to ZeroDayCTF", "Caesar's Secret", "Base Camp", "XOR Gate", "Reverse the Strings", "Login Bypass", "Zero Day Quiz", "Hidden in Plain Sight", "Cookie Monster"],
    "sudo_sneha": ["Welcome to ZeroDayCTF", "Caesar's Secret", "Base Camp", "Zero Day Quiz", "Reverse the Strings", "XOR Gate", "Login Bypass", "Where Was This Taken?"],
    "byte_bandit": ["Welcome to ZeroDayCTF", "Base Camp", "Caesar's Secret", "XOR Gate", "Zero Day Quiz", "Hidden in Plain Sight", "Trace the Handle"],
    "phantom_priya": ["Welcome to ZeroDayCTF", "Caesar's Secret", "Zero Day Quiz", "Reverse the Strings", "Login Bypass", "Cookie Monster"],
    "kernel_kabir": ["Welcome to ZeroDayCTF", "Base Camp", "Caesar's Secret", "XOR Gate", "Buffer Overflow 101"],
    "hexa_harsha": ["Welcome to ZeroDayCTF", "Caesar's Secret", "Base Camp", "Zero Day Quiz", "Reverse the Strings"],
    "null_nandini": ["Welcome to ZeroDayCTF", "Zero Day Quiz", "Caesar's Secret", "Base Camp"],
    "cipher_chetan": ["Welcome to ZeroDayCTF", "Caesar's Secret", "Base Camp"],
    "shell_shruti": ["Welcome to ZeroDayCTF", "Zero Day Quiz", "Caesar's Secret"],
    "packet_pranav": ["Welcome to ZeroDayCTF", "Zero Day Quiz"],
    "newbie_neha": ["Welcome to ZeroDayCTF"],
}


def add():
    rng = random.Random(7)
    now = datetime.datetime.utcnow()
    chals = {c.name: c for c in Challenges.query.all()}
    created = solves = 0
    for i, (name, solved) in enumerate(PLAYERS.items()):
        email = name + DOMAIN
        if Users.query.filter_by(email=email).first():
            continue
        user = Users(name=name, email=email, password=secrets.token_urlsafe(24), verified=True)
        db.session.add(user)
        db.session.flush()
        created += 1
        t = now - datetime.timedelta(minutes=rng.randint(240, 420) - i * 8)
        for cname in solved:
            ch = chals.get(cname)
            if ch is None:
                continue
            t += datetime.timedelta(minutes=rng.randint(6, 28))
            if t > now:
                t = now - datetime.timedelta(minutes=rng.randint(1, 5))
            # an occasional wrong attempt before the correct one
            if rng.random() < 0.35:
                db.session.add(Fails(user_id=user.id, challenge_id=ch.id, ip="203.0.113.%d" % (i + 10), provided="wrong_guess", date=t - datetime.timedelta(minutes=2)))
            db.session.add(Solves(user_id=user.id, challenge_id=ch.id, ip="203.0.113.%d" % (i + 10), provided="demo", date=t))
            solves += 1
    db.session.commit()
    print("demo users created:", created, "solves:", solves)


def remove():
    users = Users.query.filter(Users.email.like("%" + DOMAIN)).all()
    n = len(users)
    for u in users:
        db.session.delete(u)
    db.session.commit()
    print("demo users removed:", n)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("add", "remove"):
        sys.exit("usage: demo_data.py add|remove")
    app = create_app()
    with app.app_context():
        add() if mode == "add" else remove()
