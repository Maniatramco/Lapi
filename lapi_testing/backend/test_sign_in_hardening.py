"""Sessions (idle timeout, My sessions, sign out everywhere), sign-in limits per person and
per address, authenticator codes for password accounts, and Keycloak session re-checks and
back-channel logout."""
import time
from types import SimpleNamespace
from urllib.parse import parse_qs
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from lapi_app import core, keycloak_auth, main, relational, sessions, sign_in_limits, totp
from test_dataset_models import system
from test_user_management import accounts, login, OLD
from test_keycloak_auth import FakeKeycloak, ISSUER, CLIENT, keycloak, sign_in, me


def current_login(client):
    with core.Session() as session:
        return session.scalars(select(core.Login).order_by(core.Login.created_at.desc())).first()


def test_idle_sessions_end_and_activity_keeps_them_alive(accounts, monkeypatch):
    client = accounts
    login(client)
    row = current_login(client)
    assert row.last_seen and row.user_agent is not None
    with core.Session.begin() as session:
        session.get(core.Login, row.id).last_seen = time.time() - 120
    assert client.get('/api/auth/me').status_code == 200
    with core.Session() as session:
        assert session.get(core.Login, row.id).last_seen > time.time() - 10  # Activity recorded.
    with core.Session.begin() as session:
        session.get(core.Login, row.id).last_seen = time.time() - 31 * 60
    ended = client.get('/api/auth/me')
    assert ended.status_code == 401 and 'without activity' in ended.json()['detail']
    monkeypatch.setenv('LAPI_SESSION_IDLE_MINUTES', '60')
    assert client.get('/api/auth/me').status_code == 200


def test_my_sessions_list_and_sign_out(accounts):
    client = accounts
    login(client)
    with TestClient(main.app) as other:
        login(other)
        listed = client.get('/api/me/sessions').json()
        assert len(listed['sessions']) == 2 and listed['idle_minutes'] == 30
        assert sum(item['current'] for item in listed['sessions']) == 1
        assert all(len(item['id']) == 16 and 'csrf' not in item for item in listed['sessions'])
        assert client.post('/api/me/sessions/sign-out-others').json()['sessions_ended'] == 1
        assert other.get('/api/auth/me').status_code == 401
        login(other)
        mine = next(item for item in other.get('/api/me/sessions').json()['sessions'] if item['current'])
        assert other.delete('/api/me/sessions/' + mine['id']).json()['signed_out_this_browser'] is True
        assert other.get('/api/auth/me').status_code == 401
        assert client.delete('/api/me/sessions/zzzzzzzzzzzzzzzz').status_code == 404
    with TestClient(main.app) as colleague:
        login(colleague, 'Colleague')
        assert colleague.post('/api/users/administrator/sessions/sign-out').status_code == 403
        assert client.post('/api/users/colleague/sessions/sign-out').json()['sessions_ended'] == 1
        assert colleague.get('/api/auth/me').status_code == 401


def test_https_uses_the_host_prefixed_cookie(accounts, monkeypatch):
    monkeypatch.setenv('COOKIE_SECURE', 'true')
    client = accounts
    result = client.post('/api/auth/login', json={'username': 'Admin', 'password': OLD})
    cookie = result.headers['set-cookie']
    assert cookie.startswith('__Host-lapi_session=') and 'Secure' in cookie and 'Path=/' in cookie and 'Domain' not in cookie
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie


def test_failed_sign_ins_lock_the_username_and_then_the_address(accounts):
    client = accounts
    for _ in range(5):
        assert client.post('/api/auth/login', json={'username': 'Colleague', 'password': 'wrong password'}).status_code == 401
    locked = client.post('/api/auth/login', json={'username': 'Colleague', 'password': OLD})
    assert locked.status_code == 429 and 'Try again in' in locked.json()['detail']
    # Another person signing in from the same address is not locked out by it.
    assert client.post('/api/auth/login', json={'username': 'Admin', 'password': OLD}).status_code == 200
    with core.Session() as session:
        keys = [row.attempt_key for row in session.scalars(select(relational.SignInAttempt))]
    assert keys and all('colleague' not in key.lower() for key in keys)  # Hashed, never the username.
    for number in range(20):
        client.post('/api/auth/login', json={'username': f'nobody{number}', 'password': 'wrong password'})
    assert client.post('/api/auth/login', json={'username': 'Admin', 'password': OLD}).status_code == 429


def test_a_successful_sign_in_clears_only_that_username(accounts):
    client = accounts
    for _ in range(3):
        client.post('/api/auth/login', json={'username': 'Admin', 'password': 'wrong password'})
    assert client.post('/api/auth/login', json={'username': 'Admin', 'password': OLD}).status_code == 200
    with core.Session() as session:
        assert session.get(relational.SignInAttempt, sign_in_limits.key('user', 'Admin')) is None
        assert session.get(relational.SignInAttempt, sign_in_limits.key('ip', 'testclient')).failures == 3


def test_client_address_is_taken_from_the_proxy_only_on_this_instance():
    request = lambda peer, forwarded: SimpleNamespace(client=SimpleNamespace(host=peer), headers={'x-forwarded-for': forwarded})
    assert sessions.client_ip(request('127.0.0.1', '203.0.113.9')) == '203.0.113.9'
    assert sessions.client_ip(request('127.0.0.1', '1.2.3.4, 203.0.113.9')) == '203.0.113.9'
    assert sessions.client_ip(request('198.51.100.7', '203.0.113.9')) == '198.51.100.7'  # Not from the proxy: ignored.
    assert sessions.client_ip(request('127.0.0.1', 'not-an-ip')) == '127.0.0.1'


def test_authenticator_codes_protect_password_sign_in(accounts, monkeypatch):
    client = accounts
    login(client)
    assert client.post('/api/auth/totp/setup', json={'current_password': 'wrong'}).status_code == 400
    setup = client.post('/api/auth/totp/setup', json={'current_password': OLD}).json()
    assert setup['uri'].startswith('otpauth://totp/Lapi%3AAdmin?secret=' + setup['secret'])
    with core.Session() as session:
        assert setup['secret'] not in session.get(relational.UserTotp, 'administrator').secret  # Encrypted at rest.
    assert client.post('/api/auth/totp/confirm', json={'code': '000000' if totp.code_at(setup['secret'], int(time.time() // 30)) != '000000' else '111111'}).status_code == 400
    code = totp.code_at(setup['secret'], int(time.time() // 30))
    assert client.post('/api/auth/totp/confirm', json={'code': code}).json() == {'enabled': True}
    with TestClient(main.app) as other:
        needed = other.post('/api/auth/login', json={'username': 'Admin', 'password': OLD})
        assert needed.status_code == 401 and 'authenticator app' in needed.json()['detail']
        replay = other.post('/api/auth/login', json={'username': 'Admin', 'password': OLD, 'code': code})
        assert replay.status_code == 401  # The code used to confirm cannot be used again.
        monkeypatch.setattr(totp.time, 'time', lambda: time.time_ns() / 1e9 + 30)
        fresh = totp.code_at(setup['secret'], int((time.time_ns() / 1e9 + 30) // 30))
        signed_in = other.post('/api/auth/login', json={'username': 'Admin', 'password': OLD, 'code': fresh})
        assert signed_in.status_code == 200 and signed_in.json()['user']['mfa'] is True
    with TestClient(main.app) as colleague:
        login(colleague, 'Colleague')
        assert colleague.post('/api/users/administrator/totp/reset', json={'current_password': OLD}).status_code == 403
    assert client.post('/api/users/colleague/totp/reset', json={'current_password': OLD}).status_code == 404


class RefreshingKeycloak(FakeKeycloak):
    """Adds the refresh-token grant, a Keycloak session id and AMR to the fake Keycloak."""
    def __init__(self):
        super().__init__()
        self.sid, self.amr, self.revoked, self.refreshes = 'kc-session-1', ['pwd', 'otp'], False, 0

    def sign(self, claims):
        if 'nonce' in claims or claims.get('aud') == CLIENT:
            claims = claims | {'sid': self.sid, 'amr': self.amr}
        return super().sign(claims)

    def handle(self, request):
        if request.url.path.endswith('/token'):
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            if form.get('grant_type') == 'refresh_token':
                self.refreshes += 1
                if self.revoked:
                    return httpx.Response(400, json={'error': 'invalid_grant', 'error_description': 'Session not active'})
                now = int(time.time())
                common = {'iss': ISSUER, 'sub': self.subject, 'iat': now, 'exp': now + 300, 'azp': CLIENT}
                return httpx.Response(200, json={'id_token': self.sign(common | {'aud': CLIENT, 'preferred_username': self.username}),
                                                 'access_token': self.sign(common | {'aud': 'account', 'realm_access': {'roles': self.roles}}),
                                                 'refresh_token': 'refresh-' + str(self.refreshes)})
            response = super().handle(request)
            body = response.json()
            if 'id_token' in body:
                return httpx.Response(200, json=body | {'refresh_token': 'refresh-0'})
            return response
        return super().handle(request)


@pytest.fixture
def refreshing(keycloak, monkeypatch):
    fake = RefreshingKeycloak()
    monkeypatch.setattr(keycloak_auth, '_http', lambda: httpx.Client(transport=httpx.MockTransport(fake.handle)))
    return fake


def age_keycloak_check(client):
    with core.Session.begin() as session:
        for row in session.scalars(select(core.Login).where(core.Login.owner.startswith('kc-'))):
            row.kc_checked = time.time() - keycloak_auth.RECHECK_SECONDS - 1


def test_keycloak_rechecks_follow_roles_and_end_disabled_people(accounts, refreshing):
    client = accounts
    assert sign_in(client, refreshing).status_code == 302
    assert me(client)['is_admin']
    row = current_login(client)
    assert row.kc_sid == 'kc-session-1' and row.kc_tokens and 'refresh-0' not in row.kc_tokens  # Encrypted.
    out = client.post('/api/auth/logout').json()
    assert 'id_token_hint=' in out['logout_url']
    assert sign_in(client, refreshing).status_code == 302
    me(client)
    refreshing.roles = ['offline_access']  # Keycloak removed the administrator role.
    age_keycloak_check(client)
    changed = client.get('/api/auth/me')
    assert changed.status_code == 401 and refreshing.refreshes == 1
    assert sign_in(client, refreshing).status_code == 302
    assert not me(client)['is_admin']
    age_keycloak_check(client)
    assert client.get('/api/auth/me').status_code == 200 and refreshing.refreshes == 2
    refreshing.revoked = True  # Disabled or signed out in Keycloak.
    age_keycloak_check(client)
    ended = client.get('/api/auth/me')
    assert ended.status_code == 401 and 'Keycloak session has ended' in ended.json()['detail']


def test_keycloak_back_channel_logout_ends_the_matching_sessions(accounts, refreshing):
    client = accounts
    assert sign_in(client, refreshing).status_code == 302
    me(client)
    now = int(time.time())
    event = {'http://schemas.openid.net/event/backchannel-logout': {}}
    with TestClient(main.app) as keycloak_server:
        bad = keycloak_server.post('/api/auth/keycloak/backchannel-logout', data={'logout_token': 'not-a-token'})
        assert bad.status_code == 400
        with_nonce = refreshing.sign({'iss': ISSUER, 'aud': CLIENT, 'iat': now, 'jti': 'j1', 'sid': 'kc-session-1', 'events': event, 'nonce': 'x'})
        assert keycloak_server.post('/api/auth/keycloak/backchannel-logout', data={'logout_token': with_nonce}).status_code == 400
        assert client.get('/api/auth/me').status_code == 200
        token = refreshing.sign({'iss': ISSUER, 'aud': CLIENT, 'iat': now, 'jti': 'j2', 'sid': 'kc-session-1', 'events': event})
        assert keycloak_server.post('/api/auth/keycloak/backchannel-logout', data={'logout_token': token}).status_code == 200
    assert client.get('/api/auth/me').status_code == 401


def test_administrators_must_use_a_second_factor_when_required(accounts, refreshing, monkeypatch):
    monkeypatch.setenv('LAPI_KEYCLOAK_REQUIRE_ADMIN_MFA', 'true')
    refreshing.amr = ['pwd']
    result = sign_in(accounts, refreshing)
    assert result.status_code == 302 and 'sign_in_error=mfa_required' in result.headers['location']
    refreshing.amr = ['pwd', 'otp']
    assert sign_in(accounts, refreshing).headers['location'] == '/'
    assert me(accounts)['is_admin']
