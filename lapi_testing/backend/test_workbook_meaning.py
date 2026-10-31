"""Spreadsheet extraction by meaning: fields matched to columns by the model, every proposal checked,
columns on linked sheets, per-row reading for fields that are not columns, and the person's choice."""
import json
import pytest
from lapi_app import ocr, providers, worker
from test_dataset_models import system, dataset
from test_spreadsheets import upload_sheet
from test_workbook import RECEIPT_TEXT, rich_workbook

FIELDS = {'type': 'object', 'additionalProperties': False,
          'required': ['transaction_id', 'invoice_number', 'vendor_country', 'paid_value', 'dispute_note', 'total_spend'],
          'properties': {'transaction_id': {'type': ['string', 'null'], 'description': 'Transaction ID: as written.'},
                         'invoice_number': {'type': ['string', 'null'], 'description': 'Invoice number: the bill or invoice reference.'},
                         'vendor_country': {'type': ['string', 'null'], 'description': 'Vendor country: where the vendor is based.'},
                         'paid_value': {'type': ['number', 'null'], 'description': 'Paid value: what was paid, in dollars.'},
                         'dispute_note': {'type': ['string', 'null'], 'description': 'Dispute note: any dispute mentioned for the payment.'},
                         'total_spend': {'type': ['number', 'null'], 'description': 'Total spend across all transactions.'}}}


def model_mapping(instruction, text, schema):
    request = json.loads(text)
    assert 'Meaning profile of sheet "Vendors"' in ' '.join(request['sheets'])
    assert 'Transactions.Counterparty refers to Vendors.Name' in request['links']
    return {'fields': [
        {'field': 'invoice_number', 'kind': 'column', 'sheet': 'Transactions', 'column': 'Reference No', 'confidence': 0.93},
        {'field': 'vendor_country', 'kind': 'column', 'sheet': 'Vendors', 'column': 'Country', 'confidence': 0.9},
        {'field': 'paid_value', 'kind': 'column', 'sheet': 'Transactions', 'column': 'Status', 'confidence': 0.8},      # wrong type: rejected
        {'field': 'dispute_note', 'kind': 'row', 'sheet': None, 'column': None, 'confidence': 0.7},
        {'field': 'total_spend', 'kind': 'whole', 'sheet': None, 'column': None, 'confidence': 0.9},
        {'field': 'transaction_id', 'kind': 'column', 'sheet': 'Transactions', 'column': 'No Such Column', 'confidence': 0.99}]}


def rows_model(text, schema, sources):
    """Stands in for the model reading rows: finds the dispute in the row's own text."""
    rows = [{'row': int(s['id'].split('-')[1]), 'dispute_note': 'Disputed: driver charged twice' if 'Disputed' in s['text'] else None} for s in sources]
    quotes = [{'field': f'/rows/{i}/dispute_note', 'chunk_id': s['id'], 'quote': 'Disputed: driver charged twice',
               'document_id': s['document_id'], 'document_name': s['document_name'], 'page': s['page']}
              for i, s in enumerate(sources) if 'Disputed' in s['text']]
    return {'rows': rows}, quotes


@pytest.fixture
def indexed(system, monkeypatch):
    monkeypatch.setattr(ocr, 'read_image', lambda raw, **k: {'text': RECEIPT_TEXT, 'text_origin': 'ocr', 'ocr': {'model': 'test-vision', 'provider': 'ollama', 'verified': False}})
    monkeypatch.setattr(ocr, 'describe', lambda raw, **k: '')
    s = system; d = dataset(s)
    doc = upload_sheet(s, d, 'ledger.xlsx', rich_workbook()).json()['documents'][0]
    assert worker.run_once()
    monkeypatch.setattr(providers, 'plan', model_mapping)
    monkeypatch.setattr(providers, 'extract_with_evidence', rows_model)
    t = s.api.post('/api/templates', json={'name': 'Payments', 'schema': FIELDS, 'instructions': '', 'dataset_id': d['id']}).json()
    return s, d, doc, t


def test_fields_are_matched_by_meaning_checked_and_previewed(indexed):
    s, d, doc, t = indexed
    plan = s.api.post('/api/templates/table-plan', json={'dataset_id': d['id'], 'document_ids': [doc['id']], 'schema': FIELDS, 'allow_external': True}).json()
    assert plan['applies'] is True
    item = plan['documents'][0]
    assert item['sheet'] == 'Transactions' and item['rows'] == 6
    assert item['fields']['transaction_id'] == {'sheet': 'Transactions', 'column': 'Transaction ID', 'how': 'same name', 'confidence': 1.0}
    assert item['fields']['invoice_number']['column'] == 'Reference No' and item['fields']['invoice_number']['how'] == 'by meaning'
    assert item['fields']['vendor_country']['via'] == {'column': 'Counterparty', 'key': 'Name', 'strength': 'proven'}
    assert 'paid_value' not in item['fields'] and 'paid_value' in item['unmatched']           # Status is not a number
    assert item['row_fields'] == ['dispute_note'] and item['whole_fields'] == ['total_spend']
    assert {'sheet': 'Vendors', 'column': 'Country'} in item['columns']


def test_extraction_reads_columns_linked_sheets_and_row_context(indexed):
    s, d, doc, t = indexed
    e = s.api.post('/api/extractions', json={'document_ids': [doc['id']], 'template_id': t['id'], 'dataset_id': d['id'], 'allow_external': True}).json()
    assert worker.run_once()
    x = s.api.get('/api/extractions/' + e['id']).json()
    assert x['status'] == 'ready', x.get('error')
    records = [r['fields'] for r in x['result']['records']]
    assert records[1] == {'transaction_id': 'TXN-2', 'invoice_number': 'BILL-2025-0002', 'vendor_country': 'India', 'paid_value': None,
                          'dispute_note': 'Disputed: driver charged twice', 'total_spend': None}
    assert records[0]['vendor_country'] == 'Germany' and records[0]['dispute_note'] is None
    notice = x['evidence_notice']
    assert 'invoice_number ← Reference No (by meaning)' in notice and 'vendor_country ← Vendors.Country via Counterparty' in notice
    assert 'whole table' in notice and 'total_spend' in notice and 'No column matched paid_value' in notice
    assert any(q['field'] == '/records/1/fields/dispute_note' for q in x['evidence'])


def test_the_persons_mapping_wins(indexed):
    s, d, doc, t = indexed
    mapping = {'paid_value': {'sheet': 'Transactions', 'column': 'Amount (USD)'}, 'invoice_number': None}
    e = s.api.post('/api/extractions', json={'document_ids': [doc['id']], 'template_id': t['id'], 'dataset_id': d['id'],
                                             'allow_external': True, 'column_mapping': mapping}).json()
    assert worker.run_once()
    records = [r['fields'] for r in s.api.get('/api/extractions/' + e['id']).json()['result']['records']]
    assert records[2]['paid_value'] == pytest.approx(1078.55) and records[2]['invoice_number'] is None
