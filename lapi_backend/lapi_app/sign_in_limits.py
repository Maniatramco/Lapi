"""Failed sign-in limits, per person and per address, kept in the database.

5 wrong passwords for one username within 15 minutes lock that username for 15 minutes;
20 failures from one address lock that address. A successful sign-in clears the username's
count (not the address's), so one person's success cannot unlock an attacker. Counts survive
restarts and are shared by every api process. Keycloak sign-ins have Keycloak's own lockout.
"""
import hashlib
import math
import time
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from . import core, relational

WINDOW = 900
LOCK = 900
LIMITS = {'user': 5, 'ip': 20}


def key(kind, value):
    # Hashed: the table never holds usernames or addresses in clear.
    return kind + ':' + hashlib.sha256(str(value).strip().lower().encode()).hexdigest()[:64]


def keys(username, ip):
    return [key('user', username), key('ip', ip)]


def check(attempt_keys, now=None):
    now = now or time.time()
    with core.Session() as session:
        for attempt_key in attempt_keys:
            row = session.get(relational.SignInAttempt, attempt_key)
            if row and row.locked_until and row.locked_until > now:
                minutes = max(1, math.ceil((row.locked_until - now) / 60))
                raise HTTPException(429, f'Too many failed sign-ins. Try again in {minutes} minute{"s" if minutes != 1 else ""}.')


def fail(attempt_keys, now=None):
    now = now or time.time()
    for attempt_key in attempt_keys:
        limit = LIMITS[attempt_key.split(':', 1)[0]]
        for _ in (0, 1):  # A concurrent first failure may insert the same key: retry once.
            try:
                with core.Session.begin() as session:
                    row = session.get(relational.SignInAttempt, attempt_key, with_for_update=True)
                    if row is None:
                        row = relational.SignInAttempt(attempt_key=attempt_key, failures=0, window_start=now)
                        session.add(row)
                    if now - (row.window_start or now) > WINDOW:
                        row.failures, row.window_start = 0, now
                    row.failures = (row.failures or 0) + 1
                    if row.failures >= limit:
                        row.locked_until, row.failures, row.window_start = now + LOCK, 0, now
                break
            except IntegrityError:
                continue


def succeed(username):
    with core.Session.begin() as session:
        row = session.get(relational.SignInAttempt, key('user', username))
        if row:
            session.delete(row)
