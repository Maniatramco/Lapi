"""The HTTPS certificate folder survives deployments through the control store."""
import asyncio
import io
import tarfile
from lapi_app import core, tls_state


class Store:
    def __init__(self):self.objects={}
    def stat(self,key):return {'size':len(self.objects[key])} if key in self.objects else None
    def get(self,key):return self.objects[key]
    def put(self,key,data):self.objects[key]=data


def test_saved_certificate_comes_back_and_caddy_is_released(tmp_path,monkeypatch):
    store=Store();monkeypatch.setattr(core,'local_store',store)
    first=tmp_path/'first'
    cert=first/'caddy'/'certificates'/'acme'/'lapi.example'/'lapi.example.crt'
    cert.parent.mkdir(parents=True);cert.write_text('CERT')
    (first/'caddy'/'locks').mkdir();(first/'caddy'/'locks'/'issue.lock').write_text('busy')
    assert not tls_state.restore(first)  # Nothing saved yet: Caddy may start straight away.
    assert (first/tls_state.READY).exists()
    saved=tls_state.save(first,'')
    assert tls_state.KEY in store.objects
    names=tarfile.open(fileobj=io.BytesIO(store.objects[tls_state.KEY])).getnames()
    assert names==['caddy/certificates/acme/lapi.example/lapi.example.crt']
    before=store.objects[tls_state.KEY];store.objects.clear()
    assert tls_state.save(first,saved)==saved and store.objects=={}  # Unchanged: no upload.
    store.objects[tls_state.KEY]=before
    second=tmp_path/'second'
    assert tls_state.restore(second)
    assert (second/'caddy'/'certificates'/'acme'/'lapi.example'/'lapi.example.crt').read_text()=='CERT'
    assert (second/tls_state.READY).exists()


def test_unsafe_or_unreadable_state_still_lets_caddy_start(tmp_path,monkeypatch):
    store=Store();monkeypatch.setattr(core,'local_store',store)
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
        info=tarfile.TarInfo('../escape.txt');data=b'x';info.size=1;tar.addfile(info,io.BytesIO(data))
    store.objects[tls_state.KEY]=buffer.getvalue()
    root=tmp_path/'state'
    assert not tls_state.restore(root,attempts=2,wait=0)
    assert not (tmp_path/'escape.txt').exists() and (root/tls_state.READY).exists()
    class Down(Store):
        def stat(self,key):raise OSError('object storage unreachable')
    monkeypatch.setattr(core,'local_store',Down())
    other=tmp_path/'other'
    assert not tls_state.restore(other,attempts=2,wait=0) and (other/tls_state.READY).exists()


def test_directory_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv('LAPI_TLS_STATE_DIR',raising=False)
    assert tls_state.directory() is None
    monkeypatch.setenv('LAPI_TLS_STATE_DIR','/data/caddy')
    assert tls_state.directory().as_posix()=='/data/caddy'
