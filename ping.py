"""
Script for checking that a database server is available.
Essentially a cross-platform, database agnostic mysqladmin.
"""

import sys
import time

from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url

from CTFd.config import Config

url = make_url(Config.DATABASE_URL)

# Ignore sqlite databases
if url.drivername.startswith("sqlite"):
    exit(0)

# Null out the database so raw_connection doesnt error if it doesnt exist
# CTFd will create the database if it doesnt exist
url = url._replace(database=None)

# Wait for the database server to be available
engine = create_engine(url)
print(f"Waiting for {url.host} to be ready")
# Errors that retrying cannot fix. Retrying them every second makes MariaDB/RDS block this server
# ("Host ... is blocked because of many connection errors"), so stop immediately with a clear message.
FATAL = {
    "CERTIFICATE_VERIFY_FAILED": "The TLS certificate of the database could not be verified. Check the CA bundle (see deploy/README.md, 'TLS verify failed').",
    "Access denied": "The database rejected the user name or password in DATABASE_URL.",
    "is blocked because of many connection errors": "The database has blocked this server after repeated failures. Unblock it (reboot RDS or FLUSH HOSTS) and fix the cause first.",
    "Name or service not known": "The database host name in DATABASE_URL cannot be resolved. Check the endpoint spelling.",
}
MAX_ATTEMPTS = 120  # about 2 minutes: enough for a database container to start

attempt = 0
while True:
    try:
        engine.raw_connection()
        break
    except Exception as e:
        attempt += 1
        print(e)
        for needle, advice in FATAL.items():
            if needle in str(e):
                print("\nSTOPPING: " + advice)
                sys.exit(1)
        if attempt >= MAX_ATTEMPTS:
            print("\nSTOPPING: the database did not become ready after %d attempts." % attempt)
            sys.exit(1)
        print("Waiting 1s for database connection (%d/%d)" % (attempt, MAX_ATTEMPTS))
        time.sleep(1)

print(f"{url.host} is ready")
time.sleep(1)
