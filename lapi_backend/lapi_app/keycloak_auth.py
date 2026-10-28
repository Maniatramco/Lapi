"""Keycloak sign-in: OpenID Connect authorization code flow with PKCE.

Set LAPI_KEYCLOAK_URL, LAPI_KEYCLOAK_REALM, LAPI_KEYCLOAK_CLIENT_ID and LAPI_PUBLIC_URL
to turn it on. A confidential client also needs its secret, from OCI Vault
(LAPI_KEYCLOAK_CLIENT_SECRET_OCID) or a mounted file (LAPI_KEYCLOAK_CLIENT_SECRET_FILE).

People sign in at Keycloak and Lapi opens its usual session. A Lapi account
('kc-<subject>') is created at the first sign-in; its role follows the Keycloak role
LAPI_KEYCLOAK_ADMIN_ROLE (default lapi-administrator) at every sign-in. Lapi's own
password sign-in stays only for local administrators: the break-glass account made
by create-admin.
"""
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from urllib.parse import urlencode
import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from . import core
from .relational import audit_as

log = logging.getLogger(__name__)
router = APIRouter()

PREFIX = 'kc-'
UNUSABLE_PASSWORD = '!keycloak'  # Never matches password_valid: no Lapi password.
FLOW_COOKIE = 'lapi_oidc'
FLOW_PATH = '/api/auth/keycloak'
FLOW_SECONDS = 600
SESSION_SECONDS = 43200
REQUIRED = ('LAPI_KEYCLOAK_URL', 'LAPI_KEYCLOAK_REALM', 'LAPI_KEYCLOAK_CLIENT_ID', 'LAPI_PUBLIC_URL')
_cache = {}
_process_key = Fernet.generate_key()


class SignInFailed(Exception):
    """`code` goes to the sign-in page; details stay in the server log."""
    def __init__(self, code, detail=''):
        super().__init__(detail or code)
        self.code = code


def enabled():
    return all(os.getenv(name, '').strip() for name in REQUIRED)


def managed(user_id):
    """True for accounts that sign in with Keycloak (they have no Lapi password)."""
    return isinstance(user_id, str) and user_id.startswith(PREFIX)


def _settings():
    return {'issuer': os.environ['LAPI_KEYCLOAK_URL'].strip().rstrip('/') + '/realms/' + os.environ['LAPI_KEYCLOAK_REALM'].strip(),
            'client_id': os.environ['LAPI_KEYCLOAK_CLIENT_ID'].strip(),
            'redirect_uri': os.environ['LAPI_PUBLIC_URL'].strip().rstrip('/') + FLOW_PATH + '/callback',
            'admin_role': os.getenv('LAPI_KEYCLOAK_ADMIN_ROLE', 'lapi-administrator').strip(),
            'auditor_role': os.getenv('LAPI_KEYCLOAK_AUDITOR_ROLE', 'lapi-auditor').strip()}


def _secure():
    return os.getenv('COOKIE_SECURE', 'false') == 'true'


def _http():
    return httpx.Client(timeout=10, trust_env=False, follow_redirects=False)


def _cached(name, key, seconds, load):
    hit = _cache.get(name)
    if hit and hit[0] == key and hit[1] > time.time():
        return hit[2]
    value = load()
    _cache[name] = (key, time.time() + seconds, value)
    return value


def _discovery():
    issuer = _settings()['issuer']
    def load():
        with _http() as client:
            response = client.get(issuer + '/.well-known/openid-configuration')
        response.raise_for_status()
        document = response.json()
        if document.get('issuer') != issuer:
            raise SignInFailed('unavailable', 'Keycloak reports issuer %r, expected %r; check LAPI_KEYCLOAK_URL and Keycloak\'s hostname.' % (document.get('issuer'), issuer))
        return document
    return _cached('discovery', issuer, 3600, load)


def _client_secret():
    secret_id = os.getenv('LAPI_KEYCLOAK_CLIENT_SECRET_OCID', '').strip()
    path = os.getenv('LAPI_KEYCLOAK_CLIENT_SECRET_FILE', '').strip()
    if secret_id:
        from .vault_master_key import read_secret
        return _cached('client_secret', secret_id, 300, lambda: read_secret(secret_id))
    if path:
        with open(path, encoding='utf-8') as handle:
            return handle.read().strip()
    return ''  # Public client: PKCE alone.


def _signing_key(token, document, refresh=False):
    kid = jwt.get_unverified_header(token).get('kid')
    def load():
        with _http() as client:
            response = client.get(document['jwks_uri'])
        response.raise_for_status()
        keys = [key for key in response.json().get('keys', []) if key.get('use', 'sig') == 'sig']
        return jwt.PyJWKSet.from_dict({'keys': keys})
    if refresh:
        _cache.pop('jwks', None)
    for key in _cached('jwks', document['jwks_uri'], 3600, load).keys:
        if key.key_id == kid:
            return key
    if not refresh:
        return _signing_key(token, document, True)  # Keycloak rotated its keys.
    raise SignInFailed('failed', 'No Keycloak signing key matches the token.')


def _verified(token, document, audience=None):
    key = _signing_key(token, document)
    return jwt.decode(token, key.key, algorithms=[key.algorithm_name], issuer=document['issuer'], audience=audience,
                      leeway=30, options={'verify_aud': audience is not None, 'require': ['exp', 'iat', 'iss', 'sub']})


def _roles(claims, client_id):
    realm = (claims.get('realm_access') or {}).get('roles') or []
    client = ((claims.get('resource_access') or {}).get(client_id) or {}).get('roles') or []
    return {role for role in list(realm) + list(client) if isinstance(role, str)}


def _cipher():
    from .vault_master_key import master_key
    key = master_key()
    return Fernet(key.encode()) if key else Fernet(_process_key)


def _safe_next(value):
    # Only paths on this site: never another host, so the redirect cannot be abused.
    return value if isinstance(value, str) and value.startswith('/') and not value.startswith(('//', '/\\')) and len(value) <= 500 else '/'


def _back_to_sign_in(code):
    response = RedirectResponse('/?sign_in_error=' + code, 302)
    response.delete_cookie(FLOW_COOKIE, path=FLOW_PATH)
    return response


RECHECK_SECONDS = 300
LOGOUT_EVENT = 'http://schemas.openid.net/event/backchannel-logout'
MFA_METHODS = {'otp', 'mfa', 'hwk', 'swk', 'sms', 'webauthn'}


def _require_admin_mfa():
    return os.getenv('LAPI_KEYCLOAK_REQUIRE_ADMIN_MFA', 'false') == 'true'


def _identity(tokens, document, settings, nonce=None, signing_in=True):
    """Who signed in, from Keycloak's tokens: subject, username, roles, groups, Keycloak
    session id, and the tokens Lapi keeps (encrypted) for re-checks and sign-out."""
    claims = _verified(tokens['id_token'], document, audience=settings['client_id'])
    if nonce is not None and not secrets.compare_digest(str(claims.get('nonce', '')), nonce):
        raise SignInFailed('failed', 'The ID token nonce does not match this sign-in.')
    audience = claims.get('aud')
    if (isinstance(audience, list) and len(audience) > 1 or 'azp' in claims) and claims.get('azp') != settings['client_id']:
        raise SignInFailed('failed', 'The ID token was issued to another client (azp).')
    roles = _roles(claims, settings['client_id'])
    # Group paths from Keycloak's "Group Membership" mapper (claim "groups") become teams.
    groups = set(claims.get('groups') or []) if isinstance(claims.get('groups'), list) else set()
    methods = set(claims.get('amr') or []) if isinstance(claims.get('amr'), list) else set()
    access = tokens.get('access_token') or ''
    if access.count('.') == 2:
        # Keycloak puts roles in the access token unless "Add to ID token" is on.
        try:
            granted = _verified(access, document)
            if granted.get('sub') == claims['sub'] and granted.get('azp') == settings['client_id']:
                roles |= _roles(granted, settings['client_id'])
                if isinstance(granted.get('groups'), list):
                    groups |= set(granted['groups'])
                if isinstance(granted.get('amr'), list):
                    methods |= set(granted['amr'])
        except jwt.PyJWTError:
            log.warning('Keycloak access token could not be verified; using roles from the ID token only.')
    administrator = settings['admin_role'] in roles
    if signing_in and administrator and _require_admin_mfa() and not methods & MFA_METHODS:
        raise SignInFailed('mfa_required', 'An administrator signed in without a second factor (amr %s).' % sorted(methods))
    return {'subject': claims['sub'], 'administrator': administrator,
            'auditor': settings['auditor_role'] in roles, 'groups': sorted(g for g in groups if isinstance(g, str)),
            'username': (claims.get('preferred_username') or claims.get('email') or claims['sub']).strip()[:120],
            'sid': str(claims.get('sid') or '')[:100] or None,
            'tokens': {'refresh': tokens.get('refresh_token') or '', 'id': tokens['id_token']}}


def _token_request(form):
    settings, document = _settings(), _discovery()
    form = form | {'client_id': settings['client_id']}
    secret = _client_secret()
    if secret:
        form['client_secret'] = secret
    with _http() as client:
        return client.post(document['token_endpoint'], data=form), secret


def _exchange(code, flow):
    settings, document = _settings(), _discovery()
    response, secret = _token_request({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': settings['redirect_uri'],
                                       'code_verifier': flow['verifier']})
    if response.status_code >= 300:
        from .lapi_models.connection import provider_reason
        raise SignInFailed('failed', 'Keycloak refused the code (HTTP %d): %s' % (response.status_code, provider_reason(response, {'secret': secret})))
    return _identity(response.json(), document, settings, nonce=flow['nonce'])


def _saved_tokens(login_id):
    from . import sessions
    with core.Session() as session:
        row = session.get(core.Login, login_id)
        data = row.kc_tokens if row else None
    if not data:
        return None
    try:
        return json.loads(sessions.cipher().decrypt(data.encode()))
    except (InvalidToken, ValueError):
        return None


def id_token_of(login_id):
    return (_saved_tokens(login_id) or {}).get('id', '')


def recheck(login_id):
    """Ask Keycloak whether this session is still valid (refresh-token grant). A disabled or
    signed-out person, or an ended Keycloak session, ends the Lapi session; roles, the Auditor
    role and teams follow what Keycloak says now. If Keycloak cannot be reached the session
    continues and is checked again later."""
    from fastapi import HTTPException
    from . import sessions
    tokens, now = _saved_tokens(login_id), time.time()
    if not tokens or not tokens.get('refresh'):
        sessions.end(login_id)
        raise HTTPException(401, 'Sign in again with Keycloak.')
    try:
        response, _ = _token_request({'grant_type': 'refresh_token', 'refresh_token': tokens['refresh']})
    except (httpx.HTTPError, SignInFailed) as exc:
        log.warning('Keycloak could not be reached to re-check a session: %s', type(exc).__name__)
        sessions.touch_check(login_id, now)
        return
    if response.status_code in (400, 401):
        sessions.end(login_id)
        raise HTTPException(401, 'Your Keycloak session has ended. Sign in again.')
    if response.status_code >= 300:
        log.warning('Keycloak answered HTTP %d to a session re-check.', response.status_code)
        sessions.touch_check(login_id, now)
        return
    try:
        identity = _identity(response.json(), _discovery(), _settings(), signing_in=False)
    except (SignInFailed, jwt.PyJWTError, KeyError, ValueError) as exc:
        log.warning('Keycloak re-check returned tokens that could not be verified: %s', type(exc).__name__)
        sessions.end(login_id)
        raise HTTPException(401, 'Sign in again with Keycloak.')
    provision(identity)  # A role change signs the person out everywhere (provision).
    if not sessions.save_keycloak(login_id, identity['tokens'], now):
        raise HTTPException(401, 'Your access changed. Sign in again.')


@audit_as('keycloak')
def provision(identity):
    """Create or update the Lapi account for a Keycloak identity; returns its user ID."""
    user_id = PREFIX + identity['subject']
    if len(user_id) > 80 or not identity['username']:
        raise SignInFailed('failed', 'The Keycloak subject or username does not fit a Lapi account.')
    role = 'administrator' if identity['administrator'] else 'user'
    with core.document_lock('administrator-auth'):
        with core.Session.begin() as session:
            if session.scalar(select(core.User.id).where(core.User.username == identity['username'], core.User.id != user_id)):
                # Never merge with a local account by name: a matching name is not proof of the same person.
                raise SignInFailed('account_conflict', 'A local Lapi account already uses the username %r.' % identity['username'])
            user = session.get(core.User, user_id)
            if user is None:
                session.add(core.User(id=user_id, username=identity['username'], password_hash=UNUSABLE_PASSWORD, role=role))
                session.flush()
            else:
                user.username = identity['username']
                if user.role != role:
                    user.role = role
                    session.execute(delete(core.Login).where(core.Login.owner == user_id))
            # The Auditor role and team memberships follow Keycloak at every sign-in.
            from . import relational, teams
            auditor = session.get(relational.WorkspaceRole, user_id)
            if identity.get('auditor') and role != 'administrator' and auditor is None:
                session.add(relational.WorkspaceRole(user_id=user_id, role='auditor'))
            elif auditor is not None and (not identity.get('auditor') or role == 'administrator'):
                session.delete(auditor)
            teams.sync_keycloak_teams(session, user_id, identity.get('groups') or [])
    return user_id


def open_session(user_id, request=None, identity=None):
    from . import sessions
    keycloak = {'sid': identity.get('sid'), 'tokens': identity.get('tokens')} if identity else None
    return sessions.create(user_id, request, keycloak)[0]


def logout_url(id_token_hint=''):
    """Keycloak's end-session address, so signing out of Lapi also ends the Keycloak session.
    With the ID token as a hint Keycloak signs out straight away instead of asking."""
    try:
        endpoint = _discovery().get('end_session_endpoint')
    except Exception:
        return ''
    if not endpoint:
        return ''
    settings = _settings()
    query = {'client_id': settings['client_id'], 'post_logout_redirect_uri': os.environ['LAPI_PUBLIC_URL'].strip().rstrip('/') + '/'}
    if id_token_hint:
        query['id_token_hint'] = id_token_hint
    return endpoint + '?' + urlencode(query)


def recently_signed_in(user_id, seconds=600):
    """Keycloak accounts have no Lapi password to re-enter; a fresh sign-in confirms instead."""
    with core.Session() as session:
        latest = session.scalar(select(core.Login.created_at).where(core.Login.owner == user_id).order_by(core.Login.created_at.desc()).limit(1))
    return bool(latest and latest >= time.time() - seconds)


@router.get(FLOW_PATH + '/start')
def start(next: str = '/'):
    if not enabled():
        raise HTTPException(404, 'Keycloak sign-in is not configured.')
    try:
        document = _discovery()
    except Exception as exc:
        log.warning('Keycloak is unavailable: %s', exc)
        return _back_to_sign_in('unavailable')
    settings = _settings()
    verifier = secrets.token_urlsafe(64)
    flow = {'state': secrets.token_urlsafe(32), 'nonce': secrets.token_urlsafe(32), 'verifier': verifier, 'next': _safe_next(next)}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    query = {'response_type': 'code', 'client_id': settings['client_id'], 'redirect_uri': settings['redirect_uri'],
             'scope': 'openid profile email', 'state': flow['state'], 'nonce': flow['nonce'],
             'code_challenge': challenge, 'code_challenge_method': 'S256'}
    response = RedirectResponse(document['authorization_endpoint'] + '?' + urlencode(query), 302)
    # Lax, not Strict: the browser must send it when Keycloak redirects back.
    response.set_cookie(FLOW_COOKIE, _cipher().encrypt(json.dumps(flow).encode()).decode(), max_age=FLOW_SECONDS,
                        httponly=True, secure=_secure(), samesite='lax', path=FLOW_PATH)
    return response


@router.get(FLOW_PATH + '/callback')
def callback(request: Request, code: str = '', state: str = '', error: str = ''):
    if not enabled():
        raise HTTPException(404, 'Keycloak sign-in is not configured.')
    try:
        flow = json.loads(_cipher().decrypt(request.cookies.get(FLOW_COOKIE, '').encode(), ttl=FLOW_SECONDS))
    except (InvalidToken, ValueError):
        flow = None
    if not flow or not state or not secrets.compare_digest(state, flow['state']):
        return _back_to_sign_in('expired')
    if error or not code:
        return _back_to_sign_in('denied' if error == 'access_denied' else 'failed')
    try:
        identity = _exchange(code, flow)
        user_id = provision(identity)
    except SignInFailed as exc:
        log.warning('Keycloak sign-in failed: %s', exc)
        return _back_to_sign_in(exc.code)
    except (httpx.HTTPError, jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
        log.warning('Keycloak sign-in failed: %s', type(exc).__name__)
        return _back_to_sign_in('failed')
    response = RedirectResponse(flow['next'], 302)
    from . import sessions
    sessions.set_cookie(response, open_session(user_id, request, identity))
    response.delete_cookie(FLOW_COOKIE, path=FLOW_PATH)
    return response


@router.post(FLOW_PATH + '/backchannel-logout')
async def backchannel_logout(request: Request):
    """Keycloak calls this when a Keycloak session ends (sign-out elsewhere, an administrator
    signing someone out, session expiry): the matching Lapi sessions end at once."""
    from fastapi.responses import JSONResponse
    from sqlalchemy import or_
    if not enabled():
        raise HTTPException(404, 'Keycloak sign-in is not configured.')
    form = await request.form()
    token = str(form.get('logout_token') or '')
    try:
        settings, document = _settings(), _discovery()
        key = _signing_key(token, document)
        claims = jwt.decode(token, key.key, algorithms=[key.algorithm_name], issuer=document['issuer'], audience=settings['client_id'],
                            leeway=30, options={'require': ['iat', 'iss', 'aud']})
    except Exception as exc:
        log.warning('Rejected a Keycloak logout token: %s', type(exc).__name__)
        return JSONResponse({'error': 'invalid_request'}, 400)
    if LOGOUT_EVENT not in (claims.get('events') or {}) or 'nonce' in claims or not (claims.get('sid') or claims.get('sub')):
        return JSONResponse({'error': 'invalid_request'}, 400)
    conditions = []
    if claims.get('sid'):
        conditions.append(core.Login.kc_sid == str(claims['sid']))
    if claims.get('sub') and not claims.get('sid'):
        conditions.append(core.Login.owner == PREFIX + str(claims['sub']))
    with core.Session.begin() as session:
        ended = session.execute(delete(core.Login).where(or_(*conditions))).rowcount or 0
    log.info('Keycloak back-channel logout ended %d Lapi session(s).', ended)
    return JSONResponse({}, 200)
