"""Delete the accounts (and their submissions) created by scripts/loadtest.py.

    ./deploy/compose.sh exec -T -e PYTHONPATH=/opt/CTFd ctfd python scripts/loadtest_cleanup.py
Only accounts whose e-mail ends in @loadtest.invalid are removed.
"""
from CTFd import create_app
from CTFd.cache import clear_challenges, clear_standings
from CTFd.models import Submissions, Users, db

app = create_app()
with app.app_context():
    users = Users.query.filter(Users.email.like("%@loadtest.invalid")).all()
    ids = [u.id for u in users]
    if ids:
        Submissions.query.filter(Submissions.user_id.in_(ids)).delete(synchronize_session=False)
        for u in users:
            db.session.delete(u)
        db.session.commit()
    clear_standings()
    clear_challenges()
    print("removed %d load-test accounts" % len(ids))
