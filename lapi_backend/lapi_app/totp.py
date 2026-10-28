"""Authenticator-app codes (TOTP, RFC 6238) for password accounts.

With Keycloak, people use Keycloak's own MFA; Lapi passwords remain only for break-glass
administrators, and this adds a second factor to them. A person sets it up from My password
(scan the key into Google Authenticator, Microsoft Authenticator, 1Password …, then confirm a
code); from then on that account cannot sign in with its password alone. Each code works once.
An administrator can reset a colleague's authenticator when a phone is lost.
"""
import base64
import hashlib
import hmac
import logging
import secrets
import struct
import time
from urllib.parse import quote
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from . import core, relational

log = logging.getLogger(__name__)
STEP, DIGITS, DRIFT = 30, 6, 1


class CodeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    code: str = Field(pattern=r'^\d{6}$')


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    current_password: SecretStr = Field(min_length=1, max_length=200)


class DisableInput(PasswordInput):
    code: str = Field(pattern=r'^\d{6}$')


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def code_at(secret, step):
    key = base64.b32decode(secret + '=' * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack('>Q', step), hashlib.sha1).digest()
    offset = digest[-1] & 15
    value = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def matching_step(secret, code, now=None, after=None):
    """The time step the code belongs to (±30 seconds of clock drift), or None. Steps at or
    before `after` are refused, so a code cannot be replayed."""
    if not (isinstance(code, str) and len(code) == DIGITS and code.isdigit()):
        return None
    current = int((now or time.time()) // STEP)
    for step in range(current - DRIFT, current + DRIFT + 1):
        if (after is None or step > after) and hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def _secret(row):
    return core.secret_cipher().decrypt(row.secret.encode()).decode()


def enabled(user_id, session=None):
    if session is None:
        with core.Session() as active:
            return enabled(user_id, active)
    row = session.get(relational.UserTotp, user_id)
    return bool(row and row.enabled)


def verify(session, user_id, code):
    """Check and consume a code for an account with an authenticator (inside the caller's transaction)."""
    row = session.get(relational.UserTotp, user_id, with_for_update=True)
    if not row or not row.enabled:
        return False
    step = matching_step(_secret(row), code, after=row.last_step)
    if step is None:
        return False
    row.last_step = step
    return True


def install(app, auth):
    from .user_management import verify_password
    from .dataset_access import require_admin

    def password_account(owner):
        from . import keycloak_auth
        if keycloak_auth.managed(owner):
            raise HTTPException(409, 'You sign in with Keycloak: set up your authenticator app in Keycloak.')

    @app.get('/api/auth/totp')
    def status(owner=Depends(auth)):
        with core.Session() as session:
            row = session.get(relational.UserTotp, owner)
        return {'enabled': bool(row and row.enabled), 'pending': bool(row and not row.enabled)}

    @app.post('/api/auth/totp/setup')
    def setup(body: PasswordInput, owner=Depends(auth)):
        password_account(owner)
        with core.document_lock('administrator-auth'), core.Session.begin() as session:
            user = session.get(core.User, owner)
            verify_password(user, body.current_password.get_secret_value())
            row = session.get(relational.UserTotp, owner)
            if row and row.enabled:
                raise HTTPException(409, 'An authenticator is already set up. Turn it off first to replace it.')
            secret = new_secret()
            encrypted = core.secret_cipher().encrypt(secret.encode()).decode()
            if row:
                row.secret, row.last_step = encrypted, None
            else:
                session.add(relational.UserTotp(user_id=owner, secret=encrypted, enabled=False))
            label = quote('Lapi:' + user.username)
        return {'secret': secret, 'uri': f'otpauth://totp/{label}?secret={secret}&issuer=Lapi&digits={DIGITS}&period={STEP}'}

    @app.post('/api/auth/totp/confirm')
    def confirm(body: CodeInput, owner=Depends(auth)):
        password_account(owner)
        with core.Session.begin() as session:
            row = session.get(relational.UserTotp, owner, with_for_update=True)
            if not row or row.enabled:
                raise HTTPException(409, 'Start the authenticator setup first.')
            step = matching_step(_secret(row), body.code)
            if step is None:
                raise HTTPException(400, 'That code does not match. Check the time on your phone and try the next code.')
            row.enabled, row.last_step = True, step
        log.warning('Authenticator app turned on for %s.', owner)
        return {'enabled': True}

    @app.post('/api/auth/totp/disable')
    def disable(body: DisableInput, owner=Depends(auth)):
        password_account(owner)
        with core.document_lock('administrator-auth'), core.Session.begin() as session:
            verify_password(session.get(core.User, owner), body.current_password.get_secret_value())
            if not verify(session, owner, body.code):
                raise HTTPException(400, 'That code does not match.')
            session.delete(session.get(relational.UserTotp, owner))
        log.warning('Authenticator app turned off for %s.', owner)
        return {'enabled': False}

    @app.post('/api/users/{user_id}/totp/reset')
    def reset(user_id: str, body: PasswordInput, owner=Depends(auth)):
        require_admin(owner)
        if user_id == owner:
            raise HTTPException(400, 'Turn off your own authenticator from My password.')
        with core.document_lock('administrator-auth'), core.Session.begin() as session:
            verify_password(session.get(core.User, owner), body.current_password.get_secret_value())
            row = session.get(relational.UserTotp, user_id)
            if not row:
                raise HTTPException(404, 'This account has no authenticator.')
            session.delete(row)
            from sqlalchemy import delete
            session.execute(delete(core.Login).where(core.Login.owner == user_id))
        log.warning('Administrator %s reset the authenticator of %s.', owner, user_id)
        return {'ok': True, 'sessions_revoked': True}
