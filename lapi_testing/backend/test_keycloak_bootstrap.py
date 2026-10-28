"""Hosted Keycloak: the api creates its Oracle user and hands it its secrets, without ever stopping Lapi."""
import logging
import os
import stat
from contextlib import contextmanager
from lapi_app import keycloak_bootstrap as kb

SECRETS = {'ocid.db': 'DbPassw0rdFromVault123', 'ocid.admin': 'AdminPassw0rdFromVault', 'ocid.client': 'client-secret-from-vault'}


class Result:
    def __init__(self, value):self.value = value
    def scalar(self):return self.value


class Connection:
    def __init__(self, engine):self.engine = engine
    def execute(self, statement, params=None):
        sql = str(statement)
        self.engine.statements.append((sql, params))
        if self.engine.fail_on and self.engine.fail_on in sql:
            raise RuntimeError(f'ORA-01031: insufficient privileges\n[SQL: {sql}]')
        return Result(1 if self.engine.exists else 0)


class Engine:
    def __init__(self, exists=False, dialect='oracle', fail_on=None):
        self.exists = exists;self.fail_on = fail_on;self.statements = []
        self.dialect = type('Dialect', (), {'name': dialect})()
    @contextmanager
    def begin(self):yield Connection(self)


def environment(monkeypatch, tmp_path):
    monkeypatch.setenv(kb.DB_SECRET_ENV, 'ocid.db')
    monkeypatch.setenv(kb.ADMIN_SECRET_ENV, 'ocid.admin')
    monkeypatch.setenv(kb.CLIENT_SECRET_ENV, 'ocid.client')
    locks = []
    @contextmanager
    def lock(name):
        locks.append(name);yield
    monkeypatch.setattr('lapi_app.core.document_lock', lock)
    return tmp_path / 'keycloak-secrets', locks


def test_directory_only_when_hosted(monkeypatch):
    monkeypatch.delenv(kb.DB_SECRET_ENV, raising=False)
    assert kb.directory() is None
    monkeypatch.setenv(kb.DB_SECRET_ENV, 'ocid.db')
    monkeypatch.delenv(kb.DIR_ENV, raising=False)
    assert kb.directory().as_posix() == '/data/keycloak-secrets'
    monkeypatch.setenv(kb.DIR_ENV, '/data/other')
    assert kb.directory().as_posix() == '/data/other'


def test_new_user_is_created_with_least_privilege_and_secrets_are_owner_only(monkeypatch, tmp_path):
    root, locks = environment(monkeypatch, tmp_path)
    modes = []
    chmod = os.chmod
    monkeypatch.setattr(kb.os, 'chmod', lambda path, mode: (modes.append((os.path.basename(path), mode)), chmod(path, mode)))
    engine = Engine(exists=False)
    assert kb.prepare(root, engine=engine, read_secret=SECRETS.__getitem__)
    assert locks == ['database-schema']
    sql = [statement for statement, _ in engine.statements]
    assert sql[0] == 'SELECT COUNT(*) FROM all_users WHERE username = :name' and engine.statements[0][1] == {'name': 'KEYCLOAK'}
    assert sql[1] == 'CREATE USER KEYCLOAK IDENTIFIED BY "DbPassw0rdFromVault123" DEFAULT TABLESPACE DATA QUOTA 2G ON DATA'
    assert sql[2] == 'GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE, CREATE VIEW, CREATE PROCEDURE, CREATE TRIGGER TO KEYCLOAK'
    assert len(sql) == 3 and not any('DBA' in s or 'ANY' in s for s in sql)
    assert (root / 'db-password').read_text() == 'DbPassw0rdFromVault123'
    assert (root / 'admin-password').read_text() == 'AdminPassw0rdFromVault'
    assert (root / 'client-secret').read_text() == 'client-secret-from-vault'
    assert (root / kb.READY).exists()
    assert {name for name, mode in modes if mode == 0o600} == {'db-password.tmp', 'admin-password.tmp', 'client-secret.tmp'}
    assert ('keycloak-secrets', 0o700) in modes
    if os.name != 'nt':
        for name in kb.FILES:
            assert stat.S_IMODE((root / name).stat().st_mode) == 0o600
    assert not list(root.glob('*.tmp'))


def test_existing_user_gets_the_vault_password_back(monkeypatch, tmp_path):
    root, _ = environment(monkeypatch, tmp_path)
    engine = Engine(exists=True)
    assert kb.prepare(root, engine=engine, read_secret=SECRETS.__getitem__)
    sql = [statement for statement, _ in engine.statements]
    assert sql[1:] == ['ALTER USER KEYCLOAK IDENTIFIED BY "DbPassw0rdFromVault123" ACCOUNT UNLOCK',
                       'ALTER USER KEYCLOAK QUOTA 2G ON DATA',
                       'GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE, CREATE VIEW, CREATE PROCEDURE, CREATE TRIGGER TO KEYCLOAK']
    assert (root / kb.READY).exists()


def test_database_failure_is_logged_without_the_password_and_keycloak_still_gets_its_files(monkeypatch, tmp_path, caplog):
    root, _ = environment(monkeypatch, tmp_path)
    caplog.set_level(logging.INFO, logger=kb.__name__)
    assert kb.prepare(root, engine=Engine(fail_on='CREATE USER'), read_secret=SECRETS.__getitem__)
    assert 'ORA-01031' in caplog.text
    assert not any(value in caplog.text for value in SECRETS.values())
    assert (root / kb.READY).exists()


def test_unreadable_vault_or_sqlite_never_raises(monkeypatch, tmp_path, caplog):
    root, _ = environment(monkeypatch, tmp_path)
    def broken(secret_id):raise RuntimeError('Vault down')
    assert not kb.prepare(root, engine=Engine(), read_secret=broken)
    assert not (root / kb.READY).exists()
    sqlite = Engine(dialect='sqlite')
    assert kb.prepare(root, engine=sqlite, read_secret=SECRETS.__getitem__)  # Files still written; DB step logged.
    assert sqlite.statements == [] and 'needs the Oracle database' in caplog.text
    monkeypatch.delenv(kb.CLIENT_SECRET_ENV)
    assert not kb.prepare(tmp_path / 'other', engine=Engine(), read_secret=SECRETS.__getitem__)
    quoted = dict(SECRETS, **{'ocid.db': 'bad"password'})
    monkeypatch.setenv(kb.CLIENT_SECRET_ENV, 'ocid.client')
    assert not kb.prepare(tmp_path / 'third', engine=Engine(), read_secret=quoted.__getitem__)
    assert 'bad"password' not in caplog.text


def test_unwritable_folder_is_logged_not_raised(monkeypatch, tmp_path, caplog):
    root, _ = environment(monkeypatch, tmp_path)
    blocker = tmp_path / 'file'
    blocker.write_text('x')
    assert not kb.prepare(blocker / 'secrets', engine=Engine(), read_secret=SECRETS.__getitem__)
    assert 'Could not hand Keycloak its secrets' in caplog.text
