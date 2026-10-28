"""Keycloak sign-in (authorization code + PKCE) against a fake Keycloak that signs real
RS256 tokens. Lapi passwords remain only for local administrators (break-glass)."""
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import parse_qs, urlparse
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from lapi_app import core, keycloak_auth, main
from test_dataset_models import system
from test_user_management import accounts, login, body, OLD

ISSUER = 'https://sso.example.test/realms/lapi'
CLIENT = 'lapi-web'
SECRET = 'synthetic-keycloak-client-secret'


class FakeKeycloak:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.signer = self.key
        self.subject, self.username, self.roles = 'f3b0c442-98fc-4c3e-9a2b-1d2e3f405162', 'kc.admin', ['lapi-administrator']
        self.codes, self.nonce = {}, None

    def jwk(self, use='sig', kid='k1'):
        value = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return value | {'kid': kid, 'use': use, 'alg': 'RS256' if use == 'sig' else 'RSA-OAEP'}

    def sign(self, claims):
        return jwt.encode(claims, self.signer, algorithm='RS256', headers={'kid': 'k1'})

    def authorize(self, location):
        query = {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}
        assert location.startswith(ISSUER + '/protocol/openid-connect/auth?')
        assert query['code_challenge_method'] == 'S256' and query['client_id'] == CLIENT and 'openid' in query['scope'].split()
        code = secrets.token_urlsafe(16)
        self.codes[code] = query
        return code, query['state']

    def handle(self, request):
        path = request.url.path
        if path == '/realms/lapi/.well-known/openid-configuration':
            base = ISSUER + '/protocol/openid-connect'
            return httpx.Response(200, json={'issuer': ISSUER, 'authorization_endpoint': base + '/auth', 'token_endpoint': base + '/token',
                                             'jwks_uri': base + '/certs', 'end_session_endpoint': base + '/logout'})
        if path.endswith('/certs'):
            return httpx.Response(200, json={'keys': [self.jwk(), self.jwk('enc', 'k2')]})
        if path.endswith('/token'):
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            query = self.codes.pop(form.get('code'), None)
            if not query:
                return httpx.Response(400, json={'error': 'invalid_grant', 'error_description': 'Code not valid'})
            challenge = base64.urlsafe_b64encode(hashlib.sha256(form['code_verifier'].encode()).digest()).decode().rstrip('=')
            assert challenge == query['code_challenge'] and form['redirect_uri'] == query['redirect_uri']
            assert form['client_secret'] == SECRET
            now = int(time.time())
            common = {'iss': ISSUER, 'sub': self.subject, 'iat': now, 'exp': now + 300, 'azp': CLIENT}
            return httpx.Response(200, json={
                'id_token': self.sign(common | {'aud': CLIENT, 'nonce': self.nonce or query['nonce'], 'preferred_username': self.username}),
                'access_token': self.sign(common | {'aud': 'account', 'realm_access': {'roles': self.roles}}),
                'token_type': 'Bearer'})
        return httpx.Response(404)


@pytest.fixture
def keycloak(accounts, monkeypatch, tmp_path):
    fake = FakeKeycloak()
    secret = tmp_path / 'client-secret'
    secret.write_text(SECRET + '\n')
    monkeypatch.setenv('LAPI_KEYCLOAK_URL', 'https://sso.example.test/')
    monkeypatch.setenv('LAPI_KEYCLOAK_REALM', 'lapi')
    monkeypatch.setenv('LAPI_KEYCLOAK_CLIENT_ID', CLIENT)
    monkeypatch.setenv('LAPI_KEYCLOAK_CLIENT_SECRET_FILE', str(secret))
    monkeypatch.setenv('LAPI_PUBLIC_URL', 'http://testserver')
    monkeypatch.setattr(keycloak_auth, '_http', lambda: httpx.Client(transport=httpx.MockTransport(fake.handle)))
    monkeypatch.setattr(keycloak_auth, '_cache', {})
    return fake


def sign_in(client, kc, next='/'):
    start = client.get('/api/auth/keycloak/start', params={'next': next}, follow_redirects=False)
    assert start.status_code == 302
    code, state = kc.authorize(start.headers['location'])
    return client.get('/api/auth/keycloak/callback', params={'code': code, 'state': state}, follow_redirects=False)


def me(client):
    result = client.get('/api/auth/me')
    assert result.status_code == 200, result.text
    client.headers['X-CSRF-Token'] = result.json()['csrf_token']
    return result.json()['user']


def test_sign_in_creates_the_account_with_the_keycloak_role(accounts, keycloak):
    client = accounts
    status = client.get('/api/auth/status').json()
    assert status['keycloak'] is True
    result = sign_in(client, keycloak, next='/?view=Users')
    assert result.status_code == 302 and result.headers['location'] == '/?view=Users'
    user = me(client)
    assert user['id'] == 'kc-' + keycloak.subject and user['username'] == 'kc.admin'
    assert user['is_admin'] and user['sign_in'] == 'keycloak'
    with core.Session() as session:
        account = session.get(core.User, user['id'])
        assert account.created_via == 'keycloak' and not core.password_valid('', account.password_hash)
    assert client.get('/api/users').status_code == 200
    out = client.post('/api/auth/logout').json()
    assert out['logout_url'].startswith(ISSUER + '/protocol/openid-connect/logout?client_id=lapi-web&post_logout_redirect_uri=')
    assert client.get('/api/auth/me').status_code == 401


def test_role_follows_keycloak_at_every_sign_in(accounts, keycloak):
    client = accounts
    keycloak.roles = ['offline_access']
    sign_in(client, keycloak)
    assert me(client)['is_admin'] is False
    assert client.get('/api/users').status_code == 403
    keycloak.roles = ['lapi-administrator']
    with TestClient(main.app) as second:
        sign_in(second, keycloak)
        assert me(second)['is_admin'] is True
    assert client.get('/api/auth/me').status_code == 401  # The role changed: older sessions end.


def test_only_local_administrators_keep_password_sign_in(accounts, keycloak):
    client = accounts
    refused = client.post('/api/auth/login', json={'username': 'Colleague', 'password': OLD})
    assert refused.status_code == 403 and refused.json()['detail'] == 'This account signs in with Keycloak.'
    assert login(client)['user']['is_admin']  # Break-glass administrator.
    assert client.post('/api/users', json=body(username='Someone')).status_code == 409


def test_keycloak_accounts_manage_passwords_and_roles_in_keycloak(accounts, keycloak):
    client = accounts
    keycloak.roles = []
    with TestClient(main.app) as person:
        sign_in(person, keycloak)
        kc_id = me(person)['id']
        assert person.post('/api/auth/password', json=body(current_password='x')).status_code == 409
    login(client)
    assert client.post('/api/users/' + kc_id + '/password', json=body(current_password=OLD)).status_code == 409
    assert 'Keycloak roles lapi-administrator' in client.patch('/api/users/' + kc_id + '/role', json={'role': 'administrator', 'current_password': OLD}).json()['detail']
    users = {row['id']: row for row in client.get('/api/users').json()}
    assert users[kc_id]['sign_in'] == 'keycloak' and users['colleague']['sign_in'] == 'password'


def test_keycloak_administrator_confirms_with_a_recent_sign_in(accounts, keycloak):
    client = accounts
    sign_in(client, keycloak)
    me(client)
    result = client.patch('/api/users/colleague/role', json={'role': 'administrator', 'current_password': 'keycloak-session'})
    assert result.status_code == 200
    with core.Session.begin() as session:
        for row in session.scalars(select(core.Login).where(core.Login.owner == 'kc-' + keycloak.subject)):
            row.created_at = time.time() - 3600
    result = client.patch('/api/users/colleague/role', json={'role': 'user', 'current_password': 'keycloak-session'})
    assert result.status_code == 401 and 'Sign in with Keycloak again' in result.json()['detail']


@pytest.mark.parametrize('problem,code', [('state', 'expired'), ('nonce', 'failed'), ('signature', 'failed'),
                                          ('replay', 'failed'), ('denied', 'denied'), ('conflict', 'account_conflict')])
def test_bad_sign_ins_open_no_session(accounts, keycloak, problem, code):
    client = accounts
    start = client.get('/api/auth/keycloak/start', follow_redirects=False)
    auth_code, state = keycloak.authorize(start.headers['location'])
    params = {'code': auth_code, 'state': state}
    if problem == 'state':
        params['state'] = 'forged'
    elif problem == 'nonce':
        keycloak.nonce = 'another-sign-in'
    elif problem == 'signature':
        keycloak.signer = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    elif problem == 'replay':
        keycloak.codes.clear()
    elif problem == 'denied':
        params = {'error': 'access_denied', 'state': state}
    elif problem == 'conflict':
        keycloak.username = 'Colleague'
    result = client.get('/api/auth/keycloak/callback', params=params, follow_redirects=False)
    assert result.status_code == 302 and result.headers['location'] == '/?sign_in_error=' + code
    assert 'lapi_session' not in client.cookies
    assert client.get('/api/auth/me').status_code == 401


def test_only_same_site_paths_are_followed_after_sign_in(accounts, keycloak):
    for target in ('//evil.example/', 'https://evil.example/', '/\\evil.example'):
        with TestClient(main.app) as client:
            assert sign_in(client, keycloak, next=target).headers['location'] == '/'


def test_sign_in_is_off_without_configuration(accounts, monkeypatch):
    monkeypatch.delenv('LAPI_KEYCLOAK_URL', raising=False)
    assert accounts.get('/api/auth/status').json()['keycloak'] is False
    assert accounts.get('/api/auth/keycloak/start', follow_redirects=False).status_code == 404
    assert login(accounts, 'Colleague')['user']['is_admin'] is False
