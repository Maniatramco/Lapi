"""A .pdf or .docx that only holds text (such as a saved link) is indexed as that text; one that
is really something else is refused with a reason, not a generic failure."""
import io
import zipfile

import pytest
from docx import Document
from pypdf import PdfWriter
from lapi_app import file_formats, worker, cloud_sources as cloud
from test_dataset_models import system, dataset, post

LINK = b'https://trmx.example.com/Candidate/Todo/ProfileDownload.asp?id=abc&EmailTemplate=true'
GENERIC = 'Processing failed; inspect service health and retry'
JUNK = bytes(range(256)) * 4  # Neither the named format nor text.


def pdf():
    writer = PdfWriter(); writer.add_blank_page(width=200, height=200)
    out = io.BytesIO(); writer.write(out); return out.getvalue()


def docx():
    document = Document(); document.add_paragraph('Offer letter for Priya Menon.')
    out = io.BytesIO(); document.save(out); return out.getvalue()


def archive(**entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        for name, value in entries.items():
            z.writestr(name, value)
    return out.getvalue()


def test_real_documents_pass():
    assert file_formats.problem('offer.pdf', pdf()) is None
    assert file_formats.problem('offer.pdf', b'\r\n  ' + pdf()) is None  # junk before the header is tolerated
    assert file_formats.problem('offer.docx', docx()) is None
    assert file_formats.problem('notes.txt', LINK) is None and file_formats.problem('data.json', b'{}') is None


@pytest.mark.parametrize('name,raw,expected', [
    ('hcl offer.pdf', LINK, 'only contains a web link'),
    ('hcl offer.pdf', b'\n' + LINK + b'\n', 'only contains a web link'),
    ('page.pdf', b'<!doctype html><html><body>Sign in</body></html>', 'web page'),
    ('renamed.pdf', docx(), 'renamed to .pdf'),
    ('notes.pdf', b'Offer letter text typed into a file.', 'plain text'),
    ('binary.pdf', bytes(range(256)) * 4, 'contents are not in PDF format'),
    ('renamed.docx', pdf(), 'Rename it to .pdf'),
    ('old.docx', file_formats.OLE + b'\x00' * 600, 'older Word (.doc)'),
    ('link.docx', LINK, 'only contains a web link'),
    ('other.docx', archive(**{'data.csv': 'a,b'}), 'different kind of ZIP archive'),
    ('broken.docx', b'PK\x03\x04' + b'\x00' * 40, 'damaged'),
], ids=lambda value: value if isinstance(value, str) else 'raw')
def test_wrong_contents_are_named(name, raw, expected):
    message = file_formats.problem(name, raw)
    assert message and expected in message and name in message
    with pytest.raises(ValueError, match='"' + name.replace('.', r'\.') + '"'):
        file_formats.check(name, raw)


def test_a_link_saved_as_pdf_is_indexed_as_its_text_and_never_followed(system, monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, 'get', lambda *a, **k: pytest.fail('A link inside a document was fetched'))
    s = system; d = dataset(s)
    assert file_formats.plain_text('hcl offer.pdf', LINK) == LINK.decode()
    response = s.api.post('/api/documents/upload', files={'files': ('hcl offer.pdf', LINK, 'application/pdf')}, data={'dataset_id': d['id'], 'allow_external': 'true'})
    assert response.status_code == 200, response.text
    did = response.json()['documents'][0]['id']
    assert worker.run_once()
    doc = s.api.get('/api/documents/' + did).json()
    assert doc['status'] == 'ready', doc.get('error')
    assert s.api.get('/api/documents/' + did + '/preview').json()['text'] == LINK.decode()
    source = s.api.get('/api/documents/' + did + '/source')
    assert source.status_code == 200 and source.headers['content-type'].startswith('text/plain') and source.content == LINK
    assert s.api.get('/api/documents/' + did + '/page-image').status_code == 415


def test_upload_refuses_a_pdf_that_is_neither_pdf_nor_text(system):
    s = system; d = dataset(s)
    response = s.api.post('/api/documents/upload', files={'files': ('offer.pdf', JUNK, 'application/pdf')}, data={'dataset_id': d['id'], 'allow_external': 'true'})
    assert response.status_code == 400 and 'contents are not in PDF format' in response.json()['detail']
    assert s.api.get('/api/documents').json() == [] and s.api.get('/api/jobs').json() == []
    ok = s.api.post('/api/documents/upload', files={'files': ('offer.docx', docx(), 'application/octet-stream')}, data={'dataset_id': d['id'], 'allow_external': 'true'})
    assert ok.status_code == 200, ok.text


def stored(s, d, monkeypatch, name, raw):
    """A document saved before this check existed: skip the upload check, then index it."""
    with monkeypatch.context() as patch:
        patch.setattr(file_formats, 'problem', lambda name, raw: None)
        document = post(s, '/api/documents/upload', files={'files': (name, raw, 'application/pdf')}, data={'dataset_id': d['id'], 'allow_external': 'true'})['documents'][0]
    worker.run_once()
    return s.api.get('/api/documents/' + document['id']).json()


def test_indexing_an_already_stored_bad_file_says_why(system, monkeypatch):
    s = system; d = dataset(s)
    doc = stored(s, d, monkeypatch, 'offer.pdf', JUNK)
    assert doc['status'] == 'failed' and 'contents are not in PDF format' in doc['error'] and doc['error'] != GENERIC


def test_indexing_a_damaged_pdf_says_it_is_damaged(system, monkeypatch):
    s = system; d = dataset(s)
    doc = stored(s, d, monkeypatch, 'cut.pdf', b'%PDF-1.7\n' + b'\x00garbage' * 20)
    assert doc['status'] == 'failed' and 'damaged and cannot be opened as a PDF' in doc['error']


def test_connector_import_indexes_a_text_pdf_and_reports_an_unreadable_one(system, monkeypatch):
    from test_source_connections import connection, selections
    files = {'f1': ('hcl offer.pdf', LINK), 'f2': ('broken.pdf', JUNK)}
    class Adapter:
        def browse(self, folder='', cursor=''):
            return [{'id': id, 'name': name, 'folder': False, 'supported': True, 'size': len(raw), 'revision': 'r1'} for id, (name, raw) in files.items()], ''
        def fetch(self, item, limit):
            return item['name'], files[item['id']][1], {'remote_id': item['id'], 'revision': 'r1', 'original_url': 'https://drive.google.com/file/d/' + item['id'] + '/view'}
    monkeypatch.setattr(cloud, 'adapter', lambda cfg, secret: Adapter())
    s = system; d = dataset(s); c = connection(s, d)
    tokens = [item['selection'] for item in selections(s, c)['items']]
    results = post(s, '/api/source-connections/' + c['id'] + '/import', {'selections': tokens, 'publish_to_dataset': True, 'allow_external': True})['results']
    assert results[0]['status'] == 'imported'
    assert results[1]['status'] == 'failed' and 'contents are not in PDF format' in results[1]['message']
    assert worker.run_once()
    assert s.api.get('/api/documents/' + results[0]['document_id']).json()['status'] == 'ready'
