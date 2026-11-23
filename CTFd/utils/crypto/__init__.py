import hashlib
import os

from passlib.hash import bcrypt_sha256

from CTFd.utils import string_types


def _hash_rounds():
    """bcrypt cost factor for NEW password hashes (each +1 doubles the time). Default 12 (upstream).

    PASSWORD_HASH_ROUNDS=10 makes a login about 4x cheaper, which matters when hundreds of players log in at the same
    moment. Never goes below 10 (the OWASP minimum). Existing hashes keep their own cost and keep working.
    """
    try:
        rounds = int(os.environ.get("PASSWORD_HASH_ROUNDS", "12"))
    except ValueError:
        rounds = 12
    return min(14, max(10, rounds))


def hash_password(plaintext):
    return bcrypt_sha256.using(rounds=_hash_rounds()).hash(str(plaintext))


def verify_password(plaintext, ciphertext):
    return bcrypt_sha256.verify(plaintext, ciphertext)


def sha256(p):
    if isinstance(p, string_types):
        p = p.encode("utf-8")
    return hashlib.sha256(p).hexdigest()
