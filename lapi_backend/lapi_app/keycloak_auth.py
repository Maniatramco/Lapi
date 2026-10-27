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
            'admin_role': os.getenv('LAPI_KEYCLOAK_ADMIN_ROLE', 'lapi-administrator').strip()}


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


def _exchange(code, flow):
    settings, document = _settings(), _discovery()
    form = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': settings['redirect_uri'],
            'client_id': settings['client_id'], 'code_verifier': flow['verifier']}
    secret = _client_secret()
    if secret:
        form['client_secret'] = secret
    with _http() as client:
        response = client.post(document['token_endpoint'], data=form)
    if response.status_code >= 300:
        from .lapi_models.connection import provider_reason
        raise SignInFailed('failed', 'Keycloak refused the code (HTTP %d): %s' % (response.status_code, provider_reason(response, {'secret': secret})))
    tokens = response.json()
    claims = _verified(tokens['id_token'], document, audience=settings['client_id'])
    if not secrets.compare_digest(str(claims.get('nonce', '')), flow['nonce']):
        raise SignInFailed('failed', 'The ID token nonce does not match this sign-in.')
    roles = _roles(claims, settings['client_id'])
    access = tokens.get('access_token') or ''
    if access.count('.') == 2:
        # Keycloak puts roles in the access token unless "Add to ID token" is on.
        try:
            granted = _verified(access, document)
            if granted.get('sub') == claims['sub'] and granted.get('azp') == settings['client_id']:
                roles |= _roles(granted, settings['client_id'])
        except jwt.PyJWTError:
            log.warning('Keycloak access token could not be verified; using roles from the ID token only.')
    return {'subject': claims['sub'], 'administrator': settings['admin_role'] in roles,
            'username': (claims.get('preferred_username') or claims.get('email') or claims['sub']).strip()[:120]}


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
            else:
                user.username = identity['username']
                if user.role != role:
                    user.role = role
                    session.execute(delete(core.Login).where(core.Login.owner == user_id))
    return user_id


def open_session(user_id):
    token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    with core.Session.begin() as session:
        session.add(core.Login(id=hashlib.sha256(token.encode()).hexdigest(), owner=user_id,
                               expires=time.time() + SESSION_SECONDS, csrf=csrf))
    return token


def logout_url():
    """Keycloak's end-session address, so signing out of Lapi also ends the Keycloak session."""
    try:
        endpoint = _discovery().get('end_session_endpoint')
    except Exception:
        return ''
    if not endpoint:
        return ''
    settings = _settings()
    return endpoint + '?' + urlencode({'client_id': settings['client_id'],
                                       'post_logout_redirect_uri': os.environ['LAPI_PUBLIC_URL'].strip().rstrip('/') + '/'})


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
        user_id = provision(_exchange(code, flow))
    except SignInFailed as exc:
        log.warning('Keycloak sign-in failed: %s', exc)
        return _back_to_sign_in(exc.code)
    except (httpx.HTTPError, jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
        log.warning('Keycloak sign-in failed: %s', type(exc).__name__)
        return _back_to_sign_in('failed')
    response = RedirectResponse(flow['next'], 302)
    response.set_cookie('lapi_session', open_session(user_id), httponly=True, secure=_secure(), samesite='strict',
                        max_age=SESSION_SECONDS, path='/')
    response.delete_cookie(FLOW_COOKIE, path=FLOW_PATH)
    return response
