"""One spreadsheet row with everything connected to it: notes, attached items and linked rows.

Used by the agent's row_context tool and by the Row, Attached and Linked tabs of a citation.
"""
import io
import pyarrow.parquet as pq
from fastapi import HTTPException
from . import core, spreadsheet, workbook


def row_context(did, name, sheets, book, sheet='', row=0, item='', match=''):
    read = lambda entry: pq.read_table(io.BytesIO(core.store.get(entry['key']))).to_pylist()
    same = lambda value, wanted: spreadsheet._display(value).strip().lower() == wanted
    entry = next((s for s in sheets if s['name'].lower() == sheet.strip().lower()), sheets[0]) if sheet else sheets[0]
    found_item = next((i for i in book.get('items', []) if i['id'] == item), None) if item else None
    if item and not found_item:
        raise HTTPException(422, 'No item ' + repr(item) + ' in ' + repr(name) + '. Use workbook_map to list items.')
    if found_item:
        target = next((l for l in found_item.get('links', []) if l.get('row')), None)
        if not target:
            return {'document': name, 'item': {'id': found_item['id'], 'kind': found_item['kind'], 'where': workbook.where(found_item),
                                               'content': workbook.item_summary(found_item)}, 'row': None}
        entry = next((s for s in sheets if s['name'] == target['sheet']), entry); row = target['row']
    table = read(entry)
    if match and not row:
        wanted = match.strip().lower()
        for candidate in [entry] + [s for s in sheets if s is not entry]:
            rows = table if candidate is entry else read(candidate)
            hit = next((r for r in rows if any(same(v, wanted) for k, v in r.items() if k != '__row')), None)
            if hit:
                entry, table, row = candidate, rows, hit['__row']; break
        if not row:
            raise HTTPException(422, 'No row of ' + repr(name) + ' has a cell equal to ' + repr(match) + '. Use query_table with "contains" to search.')
    values = next((r for r in table if r.get('__row') == row), None)
    if values is None:
        raise HTTPException(422, 'Sheet ' + repr(entry['name']) + ' has no data row ' + str(row) + '.')
    saved = next((s for s in book.get('sheets', []) if s['name'] == entry['name']), {})
    attached = []
    for i in book.get('items', []):
        for l in i.get('links', []):
            if l['sheet'] == entry['name'] and l.get('row') == row:
                attached.append({'id': i['id'], 'kind': i['kind'], 'where': workbook.where(i), 'how': l['how'], 'strength': l['strength'],
                                 'content': workbook.item_summary(i)[:1500], **({'agrees': l['agrees']} if l.get('agrees') else {}),
                                 **({'differs': l['differs']} if l.get('differs') else {})})
    linked = []
    for link in book.get('links', []):
        if link.get('kind') == 'key' and link['from'] == entry['name']:
            key = spreadsheet._display(values.get(link['from_column'])).strip().lower()
            other = next((s for s in sheets if s['name'] == link['to']), None)
            if key and other:
                hit = next((r for r in read(other) if same(r.get(link['to_column']), key)), None)
                if hit:
                    linked.append({'sheet': other['name'], 'row': hit['__row'], 'through': link['from_column'] + ' = ' + link['to'] + '.' + link['to_column'],
                                   'strength': link['strength'], 'values': {k: spreadsheet._display(v) for k, v in hit.items() if k != '__row'}})
    return {'document': name, 'sheet': entry['name'], 'row': row,
            'values': {k: spreadsheet._display(v) for k, v in values.items() if k != '__row'},
            'notes': (saved.get('row_notes') or {}).get(str(row), []), 'attached': attached, 'linked_rows': linked}
