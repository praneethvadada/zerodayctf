#!/usr/bin/env python3
"""Print shell exports (DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME) parsed from DATABASE_URL in .env.
Usage:  eval "$(python3 deploy/dburl.py)"      (prints nothing when DATABASE_URL is not set)"""
import os
import shlex
import sys
from urllib.parse import unquote, urlparse

env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
url = ""
try:
    for line in open(env, encoding="utf-8"):
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"').strip("'")
except FileNotFoundError:
    pass
if not url:
    sys.exit(0)
u = urlparse(url)
for k, v in (("DB_HOST", u.hostname or ""), ("DB_PORT", str(u.port or 3306)), ("DB_USER", unquote(u.username or "")),
             ("DB_PASS", unquote(u.password or "")), ("DB_NAME", (u.path or "/ctfd").lstrip("/") or "ctfd")):
    print("export %s=%s" % (k, shlex.quote(v)))
