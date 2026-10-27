"""Operator-only first administrator creation: run in the API container, read stdin.

Replaces the public setup endpoint. It only succeeds while no account exists, so
an existing workspace is never taken over. Passwords are not accepted as
command-line arguments or printed.
"""
import json
import os
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


def ensure_from_environment():
    """Create the first administrator at start-up on hosts without a shell (Container Instances).

    Uses LAPI_FIRST_ADMIN_USERNAME and the OCI Vault secret in
    LAPI_FIRST_ADMIN_PASSWORD_SECRET_OCID. Does nothing once any account exists.
    """
    username = os.getenv('LAPI_FIRST_ADMIN_USERNAME', '').strip()
    secret_id = os.getenv('LAPI_FIRST_ADMIN_PASSWORD_SECRET_OCID', '').strip()
    if not username or not secret_id:
        return False
    with core.Session() as session:
        if session.scalar(select(core.User)):
            return False
    from .vault_master_key import read_secret
    try:
        create_admin(username, read_secret(secret_id))
    except ValueError as error:
        if 'already configured' in str(error):
            return False  # The worker or another start created it first.
        raise
    return True


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
