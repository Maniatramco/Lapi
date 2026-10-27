"""Oracle configured through the environment gets its vector table at start-up."""
from types import SimpleNamespace
from sqlalchemy import create_engine
from lapi_app import core, oracle_vectors


def engine_named(name):
    return SimpleNamespace(dialect=SimpleNamespace(name=name))


def test_vector_table_is_prepared_only_for_oracle_database_and_search(monkeypatch):
    prepared = []
    monkeypatch.setattr(oracle_vectors, 'prepare', prepared.append)
    oracle = engine_named('oracle')
    monkeypatch.setattr(core, 'DEFAULTS', core.DEFAULTS | {'search_provider': 'oracle'})
    assert core.prepare_vectors(oracle) is True and prepared == [oracle]
    assert core.prepare_vectors(engine_named('sqlite')) is False
    monkeypatch.setattr(core, 'DEFAULTS', core.DEFAULTS | {'search_provider': 'qdrant'})
    assert core.prepare_vectors(oracle) is False
    assert prepared == [oracle]


def test_init_prepares_vectors_inside_the_schema_lock(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'control.db'))
    monkeypatch.setattr(core, 'DATA', tmp_path)
    monkeypatch.setattr(core, 'engine', engine)
    from lapi_app import database_control
    monkeypatch.setattr(database_control, 'active_engine', lambda: engine)
    calls = []
    monkeypatch.setattr(core, 'prepare_vectors', lambda e: calls.append(e))
    core.init()
    assert calls == [engine]
    engine.dispose()
