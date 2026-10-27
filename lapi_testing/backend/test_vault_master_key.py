import base64
from types import SimpleNamespace
import pytest
from cryptography.fernet import Fernet
from lapi_app import core, vault_master_key as vault


class FakeSecrets:
    def __init__(self, value):
        self.value, self.calls = value, 0
    def get_secret_bundle(self, secret_id):
        self.calls += 1
        if self.value is None:
            raise RuntimeError('ServiceError 404 for ' + secret_id)
        content = base64.b64encode(self.value.encode()).decode()
        return SimpleNamespace(data=SimpleNamespace(secret_bundle_content=SimpleNamespace(content=content)))


class FakeVaults:
    def __init__(self):
        self.details = None
    def create_secret(self, details):
        self.details = details
        return SimpleNamespace(data=SimpleNamespace(id='ocid1.vaultsecret.oc1..created'))


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for name in ('LAPI_MASTER_KEY', 'MASTER_KEY', vault.SECRET_ENV):
        monkeypatch.delenv(name, raising=False)
    vault._cached.clear()
    yield
    vault._cached.clear()


def test_without_vault_the_environment_key_is_used(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv('LAPI_MASTER_KEY', key)
    assert vault.master_key() == key


def test_vault_key_is_read_once_and_used_by_the_credential_cipher(monkeypatch):
    key = Fernet.generate_key().decode()
    fake = FakeSecrets(key)
    monkeypatch.setenv(vault.SECRET_ENV, 'ocid1.vaultsecret.oc1..master')
    monkeypatch.setattr(vault, '_client', lambda service, **_: fake)
    token = core.secret_cipher().encrypt(b'model-api-key')
    assert Fernet(key.encode()).decrypt(token) == b'model-api-key'
    core.secret_cipher()
    assert fake.calls == 1


def test_vault_and_environment_key_together_are_refused(monkeypatch):
    monkeypatch.setenv(vault.SECRET_ENV, 'ocid1.vaultsecret.oc1..master')
    monkeypatch.setenv('LAPI_MASTER_KEY', Fernet.generate_key().decode())
    with pytest.raises(vault.MasterKeyUnavailable, match='not both'):
        vault.master_key(client=FakeSecrets(Fernet.generate_key().decode()))


def test_unreadable_or_invalid_vault_secret_gives_a_safe_error(monkeypatch):
    monkeypatch.setenv(vault.SECRET_ENV, 'ocid1.vaultsecret.oc1..master')
    with pytest.raises(vault.MasterKeyUnavailable, match='could not be read') as error:
        vault.master_key(client=FakeSecrets(None))
    assert '404' not in str(error.value)
    with pytest.raises(vault.MasterKeyUnavailable, match='valid master key'):
        vault.master_key(client=FakeSecrets('not-a-fernet-key'))


def test_store_creates_a_base64_secret_and_rejects_bad_keys():
    key = Fernet.generate_key().decode()
    fake = FakeVaults()
    assert vault.store('ocid1.compartment', 'ocid1.vault', 'ocid1.key', 'lapi-master-key', key, client=fake) == 'ocid1.vaultsecret.oc1..created'
    assert base64.b64decode(fake.details.secret_content.content).decode() == key
    assert (fake.details.vault_id, fake.details.key_id, fake.details.secret_name) == ('ocid1.vault', 'ocid1.key', 'lapi-master-key')
    with pytest.raises(vault.MasterKeyUnavailable):
        vault.store('c', 'v', 'k', 'n', 'short', client=FakeVaults())


def test_autonomous_database_url_uses_dsn_and_vault_password(monkeypatch):
    from lapi_app.database import database_url
    monkeypatch.setattr(vault, '_client', lambda service, **_: FakeSecrets('Db-password-from-vault-1'))
    dsn = '(description=(address=(protocol=tcps)(port=1522)(host=abc.adb.ap-mumbai-1.oraclecloud.com))(connect_data=(service_name=x_low.adb.oraclecloud.com)))'
    url = database_url(None, {'DATABASE_PROVIDER': 'oracle', 'ORACLE_USER': 'LAPI', 'ORACLE_DSN': dsn,
                              'ORACLE_PASSWORD_SECRET_OCID': 'ocid1.vaultsecret.oc1..db'})
    assert (url.drivername, url.username, url.password, url.host, url.query['dsn']) == ('oracle+oracledb', 'LAPI', 'Db-password-from-vault-1', None, dsn)
    from sqlalchemy.dialects.oracle.oracledb import OracleDialect_oracledb
    args, kwargs = OracleDialect_oracledb().create_connect_args(url)
    assert kwargs['dsn'] == dsn and kwargs['password'] == 'Db-password-from-vault-1'
