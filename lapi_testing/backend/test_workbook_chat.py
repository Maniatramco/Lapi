"""Chat over a connected workbook: the agent sees what each sheet means, joins linked sheets for exact
numbers, and starts from an image or a value to reach everything connected to it."""
import json
from lapi_app import knowledge, ocr, worker
from test_dataset_models import system, dataset
from test_spreadsheets import upload_sheet
from test_agentic_chat import scripted, agentic, tool
from test_agent_workspace import plan
from test_workbook import RECEIPT_TEXT, rich_workbook


def outputs(seen, name):
    return [json.loads(m['content']) for m in seen[-1]['messages'] if m.get('role') == 'tool' and m.get('tool_name') == name]


def setup(s, monkeypatch, receipt=RECEIPT_TEXT):
    monkeypatch.setattr(ocr, 'read_image', lambda raw, **k: {'text': receipt, 'text_origin': 'ocr', 'ocr': {'model': 'test-vision', 'provider': 'ollama', 'verified': False}})
    monkeypatch.setattr(ocr, 'describe', lambda raw, **k: 'A taxi receipt.')
    d = dataset(s)
    upload_sheet(s, d, 'ledger.xlsx', rich_workbook())
    assert worker.run_once(); knowledge.sync(s.owner, d['id']); agentic(monkeypatch)
    return d


def test_the_agent_understands_the_workbook_and_joins_linked_sheets(system, monkeypatch):
    s = system; d = setup(s, monkeypatch)
    seen = scripted(monkeypatch,
        tool('workbook_map', document='ledger.xlsx'),
        tool('query_table', document='ledger.xlsx', sheet='Transactions', join={'sheet': 'Vendors', 'on': 'Counterparty', 'key': 'Name'},
             filters=[{'column': 'Vendors.Country', 'op': '=', 'value': 'India'}, {'column': 'Status', 'op': 'in', 'value': ['Pending', 'Overdue']}],
             metrics=[{'op': 'sum', 'column': 'Amount (USD)'}, {'op': 'count'}]),
        *[{'text': 'Unpaid spend with vendors in India is 8,245.37 USD across 2 transactions.', 'calls': []}] * 3)
    plan(s, d, text='How much do we still owe vendors based in India?')
    mapped = outputs(seen, 'workbook_map')[0]['data']
    assert any('Status: text with values: Paid, Overdue, Pending' in line for sheet in mapped['sheets'] for line in sheet.split('\n'))
    assert any(l['kind'] == 'key' and l['from_column'] == 'Counterparty' and l['to_column'] == 'Name' for l in mapped['links'])
    assert any(e['cell'] == 'B3' and e['label'] == 'Total USD' for e in mapped['calculated_cells'])
    assert any(i['kind'] == 'image' and i['where'] == 'Transactions!I3' for i in mapped['items'])
    result = outputs(seen, 'query_table')[0]
    assert result['data']['rows'] == [[8245.37, 2]]
    assert result['data']['join'] == {'on': 'Transactions.Counterparty = Vendors.Name', 'matched_rows': 6, 'unmatched_rows': 0}
    assert 'Say this join in the answer' in result['note']


def test_a_question_about_the_receipt_reaches_its_row_and_linked_vendor(system, monkeypatch):
    s = system; d = setup(s, monkeypatch)
    seen = scripted(monkeypatch,
        tool('row_context', document='ledger.xlsx', item='image-1'),
        tool('row_context', document='ledger.xlsx', match='INV-2025-0003'),
        *[{'text': 'The receipt belongs to TXN-2 (RideNow Cabs, India) and matches its amount.', 'calls': []}] * 3)
    plan(s, d, text='Which transaction is the taxi receipt for, and does it match?')
    by_image, by_value = [o['data'] for o in outputs(seen, 'row_context')]
    assert (by_image['sheet'], by_image['row'], by_image['values']['Transaction ID']) == ('Transactions', 3, 'TXN-2')
    receipt = next(a for a in by_image['attached'] if a['kind'] == 'image')
    assert 'BILL-2025-0002' in receipt['content'] and receipt['agrees'] == ['Amount', 'Amount (USD)']
    assert 'note on Status: Disputed: driver charged twice (Priya)' in by_image['notes']
    assert by_image['linked_rows'][0]['values']['Country'] == 'India' and by_image['linked_rows'][0]['through'] == 'Counterparty = Vendors.Name'
    assert by_value['row'] == 4 and by_value['values']['Amount (USD)'] == '1078.55'


def test_a_receipt_that_disagrees_is_shown_to_the_agent(system, monkeypatch):
    s = system; d = setup(s, monkeypatch, receipt='RideNow Cabs BILL-2025-0002 Total 254.37')
    seen = scripted(monkeypatch, tool('row_context', document='ledger.xlsx', item='image-1'),
                    *[{'text': 'The receipt shows 254.37 but the row says 245.37.', 'calls': []}] * 3)
    plan(s, d, text='Does the receipt match the transaction?')
    receipt = next(a for a in outputs(seen, 'row_context')[0]['data']['attached'] if a['kind'] == 'image')
    assert receipt['differs']['item'] == [254.37] and receipt['differs']['row']['Amount'] == 245.37
