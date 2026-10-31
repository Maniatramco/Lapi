"""Sign-in sessions: the cookie, idle and absolute timeouts, and "My sessions".

A session ends 12 hours after sign-in, or after LAPI_SESSION_IDLE_MINUTES (default 30)
without a request. Each person can see their sessions (when, from which address and
browser) and sign any of them out; administrators can sign a person out everywhere.
With HTTPS the cookie is named __Host-lapi_session: the browser then only sends it over
HTTPS, to this exact host and path /.
"""
import hashlib
import ipaddress
import json
import logging
import os
import secrets
import time
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from . import core

log = logging.getLogger(__name__)
ABSOLUTE_SECONDS = 43200
_process_key = None
TOUCH_SECONDS = 60  # Record activity at most once a minute per session.
PLAIN_COOKIE = 'lapi_session'
SECURE_COOKIE = '__Host-lapi_session'


def secure():
    return os.getenv('COOKIE_SECURE', 'false') == 'true'


def idle_seconds():
    try:
        return max(5, int(os.getenv('LAPI_SESSION_IDLE_MINUTES', '30'))) * 60
    except ValueError:
        return 1800


def cookie_name():
    return SECURE_COOKIE if secure() else PLAIN_COOKIE


def token_from(request):
    return request.cookies.get(cookie_name(), '') or request.cookies.get(PLAIN_COOKIE, '')


def set_cookie(response, token):
    response.set_cookie(cookie_name(), token, httponly=True, secure=secure(), samesite='strict', max_age=ABSOLUTE_SECONDS, path='/')


def clear_cookie(response):
    for name in {cookie_name(), PLAIN_COOKIE}:
        response.delete_cookie(name, path='/', secure=name == SECURE_COOKIE, httponly=True, samesite='strict')


def session_id(token):
    return hashlib.sha256(token.encode()).hexdigest()


def client_ip(request):
    """The person's address. Requests reach the api through Caddy and the web server on this
    instance; Caddy replaces X-Forwarded-For with the address it saw (from the load balancer's
    PROXY header), so the last entry is trusted only when the request came from this instance."""
    peer = request.client.host if request.client else ''
    try:
        local = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        local = False
    forwarded = request.headers.get('x-forwarded-for', '')
    if local and forwarded:
        candidate = forwarded.split(',')[-1].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    return peer or 'unknown'


def cipher():
    """Keycloak tokens are encrypted with the master key; without one (local tests) with a
    key that lives only as long as this process, so tokens never sit in the database in clear."""
    global _process_key
    from cryptography.fernet import Fernet
    try:
        return core.secret_cipher()
    except ValueError:
        _process_key = _process_key or Fernet.generate_key()
        return Fernet(_process_key)


def create(user_id, request=None, keycloak=None):
    """Open a session; returns (token, csrf). keycloak: {'sid', 'tokens'} for Keycloak sign-ins."""
    token, csrf, now = secrets.token_urlsafe(40), secrets.token_urlsafe(32), time.time()
    tokens = None
    if keycloak and keycloak.get('tokens'):
        tokens = cipher().encrypt(json.dumps(keycloak['tokens']).encode()).decode()
    with core.Session.begin() as session:
        session.add(core.Login(id=session_id(token), owner=user_id, expires=now + ABSOLUTE_SECONDS, csrf=csrf, last_seen=now,
                               user_agent=(request.headers.get('user-agent', '')[:200] if request else None),
                               client_ip=(client_ip(request)[:64] if request else None),
                               kc_sid=(keycloak or {}).get('sid'), kc_tokens=tokens, kc_checked=now if tokens else None))
    return token, csrf


def check(login, now=None):
    """Raise 401 if the session has ended; returns whether its activity should be recorded."""
    now = now or time.time()
    if not login or login.expires < now:
        raise HTTPException(401, 'Session expired')
    last = login.last_seen or login.created_at or now
    if now - last > idle_seconds():
        raise HTTPException(401, 'Signed out after %d minutes without activity. Sign in again.' % (idle_seconds() // 60))
    return now - last >= TOUCH_SECONDS


def touch(login_id, now=None):
    with core.Session.begin() as session:
        row = session.get(core.Login, login_id)
        if row:
            row.last_seen = now or time.time()


def touch_check(login_id, now=None):
    """Keycloak could not answer: check this session again after the next interval."""
    with core.Session.begin() as session:
        row = session.get(core.Login, login_id)
        if row:
            row.kc_checked = now or time.time()


def save_keycloak(login_id, tokens, now=None):
    """Store refreshed Keycloak tokens; False if the session no longer exists."""
    encrypted = cipher().encrypt(json.dumps(tokens).encode()).decode()
    with core.Session.begin() as session:
        row = session.get(core.Login, login_id)
        if not row:
            return False
        row.kc_tokens, row.kc_checked = encrypted, now or time.time()
        return True


def end(login_id):
    with core.Session.begin() as session:
        session.execute(delete(core.Login).where(core.Login.id == login_id))


def end_all(user_id, keep=None):
    with core.Session.begin() as session:
        query = delete(core.Login).where(core.Login.owner == user_id)
        if keep:
            query = query.where(core.Login.id != keep)
        return session.execute(query).rowcount or 0


def public(row, current):
    return {'id': row.id[:16], 'current': row.id == current, 'created_at': row.created_at, 'last_seen': row.last_seen or row.created_at,
            'expires_at': row.expires, 'client_ip': row.client_ip or '', 'user_agent': row.user_agent or '',
            'sign_in': 'keycloak' if row.kc_tokens or row.kc_sid else 'password'}


def install(app, auth):
    from .dataset_access import require_admin

    @app.get('/api/me/sessions')
    def my_sessions(request: Request, owner=Depends(auth)):
        current = session_id(token_from(request))
        with core.Session() as session:
            rows = list(session.scalars(select(core.Login).where(core.Login.owner == owner, core.Login.expires > time.time()).order_by(core.Login.created_at.desc())))
        return {'sessions': [public(row, current) for row in rows], 'idle_minutes': idle_seconds() // 60}

    @app.delete('/api/me/sessions/{short_id}')
    def end_my_session(short_id: str, request: Request, response: Response, owner=Depends(auth)):
        if len(short_id) != 16 or not all(c in '0123456789abcdef' for c in short_id):
            raise HTTPException(404, 'Session not found.')
        with core.Session.begin() as session:
            row = session.scalar(select(core.Login).where(core.Login.owner == owner, core.Login.id.startswith(short_id)))
            if not row:
                raise HTTPException(404, 'Session not found.')
            current = row.id == session_id(token_from(request))
            session.delete(row)
        if current:
            clear_cookie(response)
        return {'ok': True, 'signed_out_this_browser': current}

    @app.post('/api/me/sessions/sign-out-others')
    def end_my_other_sessions(request: Request, owner=Depends(auth)):
        return {'ok': True, 'sessions_ended': end_all(owner, keep=session_id(token_from(request)))}

    @app.post('/api/users/{user_id}/sessions/sign-out')
    def end_user_sessions(user_id: str, owner=Depends(auth)):
        require_admin(owner)
        with core.Session() as session:
            if not session.get(core.User, user_id):
                raise HTTPException(404, 'User not found.')
        ended = end_all(user_id)
        log.warning('Administrator %s signed out every session of %s (%d).', owner, user_id, ended)
        return {'ok': True, 'sessions_ended': ended}
