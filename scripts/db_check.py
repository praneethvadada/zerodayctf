"""Verify the database connection from inside the app container (works for RDS and local MariaDB).
    ./deploy/compose.sh exec -T ctfd python scripts/db_check.py
"""
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from CTFd.config import Config

url = make_url(Config.DATABASE_URL)
print("host     :", url.host, "port:", url.port or 3306, "database:", url.database, "user:", url.username)
eng = create_engine(url)
with eng.connect() as c:
    one = lambda q: c.execute(text(q)).fetchone()
    print("server   :", one("select version()")[0])
    cipher = one("show status like 'Ssl_cipher'")
    print("TLS      :", (cipher[1] or "NOT ENCRYPTED") if cipher else "unknown")
    print("charset  :", one("select @@character_set_database")[0], "/", one("select @@collation_database")[0])
    print("max conn :", one("select @@max_connections")[0], "| in use now:", one("show status like 'Threads_connected'")[1])
    print("tables   :", one("select count(*) from information_schema.tables where table_schema = database()")[0])
    print("grants   :", [r[0] for r in c.execute(text("show grants for current_user()"))][:2])
