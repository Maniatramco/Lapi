"""PNG, JPG and WEBP images upload, are read with the dataset's cloud OCR model and indexed as one page."""
import io
import json

import pytest
from PIL import Image, ImageDraw
from lapi_app import core, file_formats, knowledge, ocr, worker, cloud_sources as cloud
from test_dataset_models import system, dataset
from test_ocr import cloud_vision, scan

OCR_TEXT = 'Alice Example\nInvoice total: 42.50'


def picture(kind='PNG', size=(320, 200), color='white', text='Invoice 42'):
    image = Image.new('RGB', size, color)
    if text:
        ImageDraw.Draw(image).text((20, 20), text, fill='black')
    out = io.BytesIO(); image.save(out, format=kind); return out.getvalue()


def send(s, d, name, raw, **data):
    return s.api.post('/api/documents/upload', data={'dataset_id': d['id'], 'allow_external': 'true'} | data, files=[('files', (name, raw, 'application/octet-stream'))])


def test_image_signatures_match_their_extension():
    assert file_formats.problem('scan.png', picture('PNG')) is None
    assert file_formats.problem('photo.jpg', picture('JPEG')) is None
    assert file_formats.problem('photo.jpeg', picture('JPEG')) is None
    assert file_formats.problem('shot.webp', picture('WEBP')) is None
    assert 'is a PNG image with a .jpg name. Rename it to .png' in file_formats.problem('photo.jpg', picture('PNG'))
    assert 'is a PNG image with a .pdf name. Rename it to .png' in file_formats.problem('scan.pdf', picture('PNG'))
    assert 'is a JPG image with a .docx name' in file_formats.problem('scan.docx', picture('JPEG'))
    assert 'only contains a web link' in file_formats.problem('scan.png', b'https://example.com/scan.png')
    assert 'is a PDF file with an image name' in file_formats.problem('scan.png', scan())
    assert 'not a real PNG image: it is plain text' in file_formats.problem('scan.png', b'Invoice 42')
    assert all(file_formats.supported(n) for n in ('a.PNG', 'b.jpg', 'c.JPEG', 'd.webp', 'e.pdf', 'f.docx', 'g.txt', 'h.json'))
    assert not any(file_formats.supported(n) for n in ('a.gif', 'b.heic', 'c.doc', 'noextension'))
    assert cloud.supported('scan.png') and not cloud.supported('scan.gif')


@pytest.mark.parametrize('name,kind', [('receipt.png', 'PNG'), ('receipt.jpg', 'JPEG'), ('receipt.webp', 'WEBP')])
def test_uploaded_image_is_read_with_cloud_ocr_and_searchable(system, cloud_vision, name, kind):
    d, requests = cloud_vision
    response = send(system, d, name, picture(kind))
    assert response.status_code == 200, response.text
    assert not requests  # No model call on the upload request itself.
    did = response.json()['documents'][0]['id']
    assert worker.run_once()
    doc = system.api.get('/api/documents/' + did).json()
    assert doc['status'] == 'ready', doc.get('error')
    assert doc['ocr']['ocr_page_count'] == 1
    pages = core.store.json('documents/' + did + '/parsed.json')['pages']
    assert pages[0]['page'] == 1 and pages[0]['text'] == OCR_TEXT and pages[0]['text_origin'] == 'ocr'
    assert pages[0]['ocr']['verified'] is False
    assert len([p for path, p in requests if path == '/chat/completions']) == 1
    knowledge.sync(system.owner, d['id'])
    hits = knowledge.search('Alice invoice total', system.owner, dataset_id=d['id'], source_types=['document_chunk'], limit=10)['matches']
    assert any('42.50' in h.get('text', '') for h in hits)
    source = system.api.get('/api/documents/' + did + '/source')
    assert source.status_code == 200 and source.headers['content-type'].startswith('image/')


def test_large_photo_is_downscaled_and_rotated_before_ocr(monkeypatch):
    sent = []
    monkeypatch.setattr(ocr, 'config', lambda: {'enabled': True})
    monkeypatch.setattr(ocr, 'available', lambda cfg: cfg | {'digest': 'd', 'model': 'm', 'context': 1, 'output': 1, 'batch': 1, 'protocol': 3})
    monkeypatch.setattr(ocr, 'transcribe', lambda image, cfg: sent.append(Image.open(io.BytesIO(image)).size) or ('text', {'model': 'm'}))
    image = Image.new('RGB', (4000, 1000), 'white'); ImageDraw.Draw(image).text((10, 10), 'wide', fill='black')
    exif = image.getexif(); exif[0x0112] = 6  # Stored sideways: rotate 90 degrees to display upright.
    out = io.BytesIO(); image.save(out, format='JPEG', exif=exif)
    page = worker.parse_document('photo.jpg', out.getvalue())[0]
    assert sent == [(500, 2000)] and page['ocr']['render_width'] == 500 and page['page'] == 1


@pytest.mark.parametrize('raw,message', [
    (picture(text=''), 'The image is blank'),
    (b'\x89PNG\r\n\x1a\n' + b'\x00' * 64, 'could not be opened'),
])
def test_unreadable_images_fail_with_a_reason(monkeypatch, raw, message):
    monkeypatch.setattr(ocr, 'config', lambda: {'enabled': True})
    monkeypatch.setattr(ocr, 'available', lambda cfg: pytest.fail('OCR service contacted for an unreadable image'))
    with pytest.raises(ocr.OcrError, match=message):
        worker.parse_document('scan.png', raw)


def test_ocr_turned_off_names_the_setting(monkeypatch):
    monkeypatch.setattr(ocr, 'config', lambda: {'enabled': False})
    with pytest.raises(ocr.OcrError, match='LAPI_OCR_ENABLED=true'):
        worker.parse_document('scan.png', picture())


def test_dataset_without_an_ocr_model_explains_what_to_map(system):
    d = dataset(system)
    did = send(system, d, 'scan.png', picture()).json()['documents'][0]['id']
    worker.run_once()
    doc = system.api.get('/api/documents/' + did).json()
    assert doc['status'] == 'failed' and 'Select a cloud OCR model in Dataset Model Mapping' in doc['error']


def test_image_with_wrong_contents_is_refused_at_upload(system):
    d = dataset(system)
    response = send(system, d, 'scan.png', bytes(range(256)) * 4)
    assert response.status_code == 400 and 'contents are not in an image format' in response.json()['detail']
    # An image file that only holds a link is indexed as that text, without OCR.
    link = send(system, d, 'scan.png', b'https://portal.example.com/scan')
    assert link.status_code == 200, link.text
    assert worker.parse_document('scan.png', b'https://portal.example.com/scan')[0]['text'] == 'https://portal.example.com/scan'
    assert send(system, d, 'scan.gif', b'GIF89a').status_code == 400
    assert [doc['id'] for doc in system.api.get('/api/documents').json()] == [link.json()['documents'][0]['id']]


def test_image_can_be_merged_with_text(system, cloud_vision):
    d, requests = cloud_vision
    response = system.api.post('/api/documents/upload', data={'dataset_id': d['id'], 'merge_files': 'true', 'allow_external': 'true'},
                               files=[('files', ('notes.txt', b'Bob approves the invoice.', 'text/plain')), ('files', ('receipt.png', picture(), 'image/png'))])
    assert response.status_code == 200, response.text
    assert not requests
    did = response.json()['documents'][0]['id']
    assert worker.run_once()
    doc = system.api.get('/api/documents/' + did).json()
    assert doc['status'] == 'ready', doc.get('error')
    pages = core.store.json('documents/' + did + '/parsed.json')['pages']
    assert [(p['source_filename'], p['text']) for p in pages] == [('notes.txt', 'Bob approves the invoice.'), ('receipt.png', OCR_TEXT)]
