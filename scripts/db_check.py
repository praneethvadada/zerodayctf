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

import os
workers = int(os.environ.get("WORKERS", "1") or 1)
per = int(os.environ.get("SQLALCHEMY_POOL_SIZE", "6") or 6) + int(os.environ.get("SQLALCHEMY_MAX_OVERFLOW", "4") or 4)
with eng.connect() as c:
    limit = int(c.execute(text("select @@max_connections")).fetchone()[0])
need = workers * per
print("pool check:", workers, "workers x", per, "connections =", need, "possible connections vs database limit", limit)
print("           ", "OK" if need < limit * 0.8 else "WARNING: lower WORKERS / pool sizes or use a bigger database, otherwise bursts will fail with 'Too many connections'")
