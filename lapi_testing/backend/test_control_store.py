"""Stateless containers: control state in Object Storage, only locks and caches on disk."""
import pytest
from lapi_app import core, main, storage_config, workspace_reset
from test_dataset_models import system, dataset, upload, template


class Bucket:
    """In-memory stand-in for an OCI bucket prefix: same interface, no local paths."""
    def __init__(self):self.objects = {}
    def path(self, key):raise RuntimeError('no local path')
    def put(self, key, data):
        assert isinstance(data, bytes);self.objects[key] = data
    def get(self, key):
        try:return self.objects[key]
        except KeyError:raise FileNotFoundError(key) from None
    def json(self, key):
        import json;return json.loads(self.get(key))
    def put_json(self, key, data):
        import json;self.put(key, json.dumps(data).encode())
    def delete(self, key):self.objects.pop(key, None)
    def stat(self, key):return {'size': len(self.objects[key])} if key in self.objects else None
    def list_prefix(self, prefix):
        assert prefix.endswith('/')
        return [{'key': k, 'size': len(v)} for k, v in sorted(self.objects.items()) if k.startswith(prefix)]


@pytest.fixture
def buckets(monkeypatch):
    control, documents = Bucket(), Bucket()
    # In production LAPI_CONTROL_STORE is read before any import; main.py also
    # binds local_store through `from .core import *`.
    monkeypatch.setattr(core, 'local_store', control)
    monkeypatch.setattr(main, 'local_store', control)
    monkeypatch.setattr(core, 'oci_storage', lambda cfg=None: documents)
    return control, documents


@pytest.fixture
def cloud(buckets, system, monkeypatch):
    monkeypatch.setattr(core, 'DEFAULTS', core.DEFAULTS | {'storage_provider': 'oci'})
    monkeypatch.setattr(main, 'DEFAULTS', core.DEFAULTS)
    return buckets, system


def disk_folders():
    return {p.name for p in core.DATA.iterdir()} - {'control.db'}


def test_control_state_and_documents_never_touch_the_container_disk(cloud):
    (control, documents), s = cloud
    d = dataset(s);doc = upload(s, d)['documents'][0];template(s)
    assert {k.split('/')[0] for k in control.objects} >= {'configuration', 'model', 'storage-routes'}
    assert 'documents/' + doc['id'] + '/original' in documents.objects
    # Only rebuildable state stays on the scratch disk.
    assert disk_folders() <= {'locks', 'object-cache', 'model-cache'}
    assert s.api.get('/api/documents/' + doc['id']).json()['status'] == 'ready'


def test_control_keys_route_to_the_control_store(buckets):
    control, _ = buckets
    assert storage_config.backend('configuration/settings.json') is control
    assert storage_config.backend('secrets/provider.enc') is control


def test_files_in_lists_direct_children_only(buckets):
    control, _ = buckets
    for key in ('storage-routes/a.json', 'storage-routes/deep/b.json', 'knowledge/k1/manifest.json',
                'knowledge/k1/extra.json', 'knowledge/manifest.json'):
        control.put(key, b'{}')
    assert core.files_in('storage-routes/', '*.json') == ['storage-routes/a.json']
    assert core.files_in('knowledge/', '*/manifest.json') == ['knowledge/k1/manifest.json']


def test_fresh_start_archives_and_restores_control_files_in_the_bucket(cloud):
    (control, documents), s = cloud
    d = dataset(s);doc = upload(s, d)['documents'][0]
    core.local_store.put('agent-state/old-thread/checkpoints.json', b'{"checkpoints":{}}')
    response = s.api.post('/api/workspace/reset', json={'confirmation': 'START FRESH'})
    assert response.status_code == 200, response.text
    archive = response.json()
    assert 'agent-state/old-thread/checkpoints.json' not in control.objects
    assert s.api.get('/api/datasets').json() == []
    assert [a['id'] for a in workspace_reset.archives()] == [archive['id']]
    restored = s.api.post('/api/workspace/archives/' + archive['id'] + '/restore', json={'confirmation': 'RESTORE'})
    assert restored.status_code == 200, restored.text
    assert control.get('agent-state/old-thread/checkpoints.json') == b'{"checkpoints":{}}'
    assert s.api.get('/api/datasets/' + d['id']).status_code == 200
    assert 'documents/' + doc['id'] + '/original' in documents.objects


def test_tampered_bucket_archive_is_refused(cloud):
    (control, _), s = cloud
    d = dataset(s);upload(s, d)
    core.local_store.put('executions/old.json', b'{"a":1}')
    receipt = s.api.post('/api/workspace/reset', json={'confirmation': 'START FRESH'}).json()
    control.put('workspace-archives/' + receipt['id'] + '/files/executions/old.json', b'changed')
    response = s.api.post('/api/workspace/archives/' + receipt['id'] + '/restore', json={'confirmation': 'RESTORE'})
    assert response.status_code == 400


def test_object_control_store_uses_the_configured_bucket_prefix(monkeypatch):
    created = {}
    class Adapter:
        def __init__(self, **kwargs):created.update(kwargs)
        def get(self, key):return b'{"ok": true}'
    from lapi_app import oci_adapters
    monkeypatch.setattr(oci_adapters, 'OCIStorageAdapter', Adapter)
    monkeypatch.setenv('LAPI_CONTROL_PREFIX', 'lapi-control')
    store = core.ObjectControlStore()
    assert created == {}
    assert store.json('configuration/settings.json') == {'ok': True}
    assert created == {'prefix': 'lapi-control'}
    with pytest.raises(RuntimeError):store.path('locks/x.lock')
