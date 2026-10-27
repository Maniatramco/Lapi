"""Operator-only first administrator creation: run in the API container, read stdin.

Replaces the public setup endpoint. It only succeeds while no account exists, so
an existing workspace is never taken over. Passwords are not accepted as
command-line arguments or printed.
"""
import json
import sys
from sqlalchemy import select
from . import core
from .relational import audit_as


@audit_as('operator')
def create_admin(username, password):
    if not isinstance(username, str) or not 1 <= len(username.strip()) <= 120 or username != username.strip():
        raise ValueError('Use a username of 1–120 characters without surrounding spaces.')
    if not isinstance(password, str) or not 12 <= len(password) <= 200:
        raise ValueError('Use a password of 12–200 characters.')
    with core.document_lock('bootstrap'):
        with core.Session.begin() as session:
            if session.scalar(select(core.User)):
                raise ValueError('An administrator is already configured; no account was changed.')
            session.add(core.User(id='administrator', username=username,
                                  password_hash=core.password_hash(password), role='administrator'))


def main():
    try:
        raw = sys.stdin.buffer.read(8193)
        if len(raw) > 8192:
            raise ValueError('Account input exceeds the size limit.')
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ValueError('Supply a JSON object containing username and password through stdin.') from None
        if not isinstance(value, dict) or set(value) != {'username', 'password'}:
            raise ValueError('Supply only username and password.')
        core.init()
        create_admin(value['username'], value['password'])
        print('Administrator created. Sign in through the application.')
        return 0
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print('Administrator creation failed. Check database readiness and retry.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
