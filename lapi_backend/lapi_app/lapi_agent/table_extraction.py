"""Row-by-row extraction from spreadsheets, understood by meaning and read from the stored tables.

When every document of an extraction is a spreadsheet, each field is matched to a column by meaning:
the dataset's model reads the fields and each sheet's meaning profile (columns, types, real values,
formulas, links between sheets) and proposes "Invoice number <- Reference No", "Vendor country <-
Vendors.Country via Counterparty". Every proposal is checked: the column must exist, its type must
fit the field, and a column on another sheet needs a proven link. Exact name matches are kept without
asking. The person can confirm or change the mapping in Quick start (column_mapping).

Values are then read exactly from the Parquet tables, one record per row, no model in between.
Fields that need judgment or live outside the columns (text on a receipt image, a comment) are read
by the model from each row's own context (cells, comments, image text), in batches that fit the
model; the whole sheet is never sent at once. Anything left empty is named in the notice.
"""
import io
import json
import math
import re
from .. import core, providers, spreadsheet, workbook
from ..merged_documents import embedded_schema

SCALARS = {'string', 'number', 'integer', 'boolean', 'null'}
MIN_SHARE = 0.5          # with no model help, at least half of the fields must be columns
MAX_AI_ROWS = 5_000
PROFILE_CHARS = 3_000
MAPPING = {'type': 'object', 'additionalProperties': False, 'required': ['fields'], 'properties': {'fields': {'type': 'array', 'items': {
    'type': 'object', 'additionalProperties': False, 'required': ['field', 'kind', 'sheet', 'column', 'confidence'], 'properties': {
        'field': {'type': 'string'}, 'kind': {'type': 'string', 'enum': ['column', 'row', 'whole', 'none']},
        'sheet': {'type': ['string', 'null']}, 'column': {'type': ['string', 'null']}, 'confidence': {'type': 'number'}}}}}}
MAP_SYSTEM = '''You match extraction fields to spreadsheet columns by MEANING, not by exact words.
You get the fields (key, label, description, type) and, per sheet, its meaning profile: columns with
types, real values or examples, formulas, and links between sheets. For each field answer one of:
- kind "column": the value of this field for a row IS a column (possibly on a linked sheet reached by a
  link listed in the profiles). Give the sheet and the exact column name as written in the profile.
  Example: "Invoice number" -> Reference No; "Vendor" -> Counterparty; "Vendor country" -> Vendors.Country.
- kind "row": the value is per row but not a column (it must be read from that row's comments, image
  text or notes, or needs a judgment about the row).
- kind "whole": the value is about the whole table (a total, a count, the largest...), not per row.
- kind "none": nothing in the workbook can give it.
Only use column names that appear in the profiles. Confidence is 0 to 1. Reply with JSON only.'''


def _words(text):
    return tuple(re.findall(r'[a-z0-9]+', str(text).lower()))


def _types(spec):
    kind = spec.get('type')
    return set(kind) if isinstance(kind, list) else {kind} if kind else set()


def flat_fields(schema):
    """{key: spec} when the prompt asks for one object of plain values, else None."""
    properties = schema.get('properties') if isinstance(schema, dict) and schema.get('type') == 'object' else None
    if not properties or any(not isinstance(spec, dict) or not _types(spec) or not _types(spec) <= SCALARS for spec in properties.values()):
        return None
    return properties


def _label(key, spec):
    description = str(spec.get('description', ''))
    return description.split(':', 1)[0] if ':' in description and 0 < len(description.split(':', 1)[0]) <= 60 else key.replace('_', ' ')


def _names(key, spec):
    """The field's key and the label written before ':' in its description ("Transaction ID: Extract ...")."""
    return {n for n in {_words(key.replace('_', ' ')), _words(_label(key, spec))} if n}


def _score(names, column):
    words = _words(column)
    if not words:
        return 0
    if words in names:
        return 3
    if any(set(words) <= set(n) for n in names):
        return 2 + len(words) / 10      # "Date" inside "Transaction date"; longer column names win
    return 0


def match(fields, columns):
    """{field key: column name} by words, each column used once, best scores first."""
    pairs = sorted(((_score(_names(key, spec), column), key, column) for key, spec in fields.items() for column in columns), reverse=True)
    mapping, used = {}, set()
    for score, key, column in pairs:
        if score and key not in mapping and column not in used:
            mapping[key] = column; used.add(column)
    return mapping


def _fits(spec, column_type):
    kinds = _types(spec) - {'null'}
    if kinds & {'number', 'integer'}:
        return column_type == 'number'
    if spec.get('format') == 'date':
        return column_type in ('date', 'text')
    return True


def sheets_of(document):
    """(tables manifest, profiles by sheet, links) saved at indexing."""
    saved = workbook.load(core.store, document.id) or {}
    return spreadsheet.tables(core.store, document.id), {p['sheet']: p for p in saved.get('profiles', [])}, saved.get('links', [])


def _names_a_row(key, spec, entry, profiles):
    """True when a word of the field's name or label is one of the row labels of a text column
    (the field asks for one row's value, so a column mapping would repeat it on every row)."""
    words = {w for name in _names(key, spec) for w in name if len(w) >= 4}
    profile = profiles.get(entry['name']) or {}
    for column in profile.get('columns', []):
        for value in column.get('values') or column.get('examples') or []:
            if isinstance(value, str) and _words(value) and set(_words(value)) <= words:
                return True
    return False


def _profile_text(entry, profiles):
    profile = profiles.get(entry['name'])
    if profile:
        return workbook.profile_text(profile)[:PROFILE_CHARS]
    return f'Sheet "{entry["name"]}": {entry["rows"]} rows. Columns: ' + ', '.join(f'{c["name"]} ({c["type"]})' for c in entry['columns'])


def ask_model(fields, tables, profiles, links):
    """The model's mapping proposal ({field: {...}}), or {} when no model can be asked."""
    request = {'fields': [{'key': k, 'label': _label(k, spec), 'description': spec.get('description', ''), 'type': sorted(_types(spec) - {'null'})} for k, spec in fields.items()],
               'sheets': [_profile_text(entry, profiles) for entry in tables],
               'links': [f'{l["from"]}.{l["from_column"]} refers to {l["to"]}.{l["to_column"]}' for l in links if l.get('kind') == 'key']}
    try:
        value = providers.plan(MAP_SYSTEM, json.dumps(request, ensure_ascii=False), MAPPING)
    except Exception:
        return {}
    return {item['field']: item for item in value.get('fields', []) if item['field'] in fields}


def _link(links, row_sheet, other):
    """The proven or likely key link from the row sheet to another sheet."""
    found = [l for l in links if l.get('kind') == 'key' and l['from'] == row_sheet and l['to'] == other]
    return max(found, key=lambda l: l['share']) if found else None


def propose(schema, documents, ask=ask_model, override=None):
    """Per document {document, sheet, mapping, row_fields, whole_fields, unmatched} or None when the
    extraction is not a row-by-row spreadsheet extraction."""
    fields = flat_fields(schema)
    if not fields or not documents:
        return None
    plans = []
    for document in documents:
        if not spreadsheet.is_spreadsheet(document.name or ''):
            return None
        tables, profiles, links = sheets_of(document)
        if not tables:
            return None
        by_name = {entry['name']: entry for entry in tables}
        columns = {entry['name']: {c['name']: c['type'] for c in entry['columns']} for entry in tables}
        words = {entry['name']: match(fields, list(columns[entry['name']])) for entry in tables}
        proposal = ask(fields, tables, profiles, links) if ask else {}
        chosen = {}
        for key, spec in fields.items():
            exact = next(((sheet, column) for sheet, mapped in words.items() for k, column in mapped.items()
                          if k == key and _score(_names(key, spec), column) == 3), None)
            wanted = (override or {}).get(key, ...)
            if wanted is None:
                continue                                       # the person chose "leave empty"
            if wanted is not ... and wanted.get('column') in columns.get(wanted.get('sheet'), {}):
                chosen[key] = {'sheet': wanted['sheet'], 'column': wanted['column'], 'how': 'chosen by you', 'confidence': 1.0}
            elif exact:
                chosen[key] = {'sheet': exact[0], 'column': exact[1], 'how': 'same name', 'confidence': 1.0}
            elif (p := proposal.get(key)) and p['kind'] == 'column' and p.get('column') in columns.get(p.get('sheet'), {}) \
                    and _fits(spec, columns[p['sheet']][p['column']]) and p['confidence'] >= 0.5:
                chosen[key] = {'sheet': p['sheet'], 'column': p['column'], 'how': 'by meaning', 'confidence': round(p['confidence'], 2)}
            else:
                sheet, column = next(((s, m[key]) for s, m in sorted(words.items(), key=lambda kv: -len(kv[1])) if key in m), (None, None))
                if column and _fits(spec, columns[sheet][column]):
                    chosen[key] = {'sheet': sheet, 'column': column, 'how': 'similar name', 'confidence': 0.6}
        counts = {}
        for item in chosen.values():
            counts[item['sheet']] = counts.get(item['sheet'], 0) + 1
        if not counts:
            return None
        row_sheet = max(counts, key=lambda s: (counts[s], by_name[s]['rows']))
        mapping = {}
        for key, item in chosen.items():
            if item['sheet'] == row_sheet:
                mapping[key] = item
            elif (link := _link(links, row_sheet, item['sheet'])):
                mapping[key] = item | {'via': {'column': link['from_column'], 'key': link['to_column'], 'strength': link['strength']}}
        row_fields = [k for k in fields if k not in mapping and (proposal.get(k) or {}).get('kind') == 'row']
        whole = [k for k in fields if k not in mapping and (proposal.get(k) or {}).get('kind') == 'whole']
        enough = len(mapping) >= max(1, math.ceil(MIN_SHARE * len(fields))) or (mapping and len(mapping) + len(row_fields) == len(fields))
        unmatched = [k for k in fields if k not in mapping and k not in row_fields and k not in whole]
        # Fields that name one row's value ("engineering_q1" when Engineering is a Department) or a
        # whole-table figure are not columns: such a prompt describes the workbook, not its rows.
        named_rows = [k for k in mapping if _names_a_row(k, fields[k], by_name[row_sheet], profiles)]
        if not override and (len(unmatched) * 3 > len(fields) or named_rows or len(whole) * 2 >= len(fields)):
            return None
        if not enough and not override:
            return None
        plans.append({'document': document, 'sheet': by_name[row_sheet], 'mapping': mapping, 'row_fields': row_fields, 'whole_fields': whole,
                      'unmatched': [k for k in fields if k not in mapping and k not in row_fields], 'columns': columns})
    return plans


def plan(schema, documents, ask=ask_model, override=None):
    return propose(schema, documents, ask, override)


def _value(spec, value):
    """A table value in the field's JSON type; None when it cannot be one."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    kinds = _types(spec)
    if kinds & {'number', 'integer'}:
        number = spreadsheet._number(value)
        if number is not None:
            return int(number) if 'integer' in kinds and number.is_integer() else number
    if 'boolean' in kinds and isinstance(value, bool):
        return value
    if 'boolean' in kinds and isinstance(value, str) and value.strip().lower() in ('yes', 'no', 'true', 'false', 'y', 'n'):
        return value.strip().lower() in ('yes', 'true', 'y')
    if 'string' in kinds:
        text = spreadsheet._display(value)
        if spec.get('format') == 'date' and hasattr(value, 'date'):
            text = value.date().isoformat()
        return text or None
    return None


def schema_for(schema):
    """The result shape: one record per row, each with its row label, key and the prompt's fields."""
    return {'type': 'object', 'additionalProperties': False, '$defs': {'record': embedded_schema(schema)},
            'properties': {'records': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                'properties': {'source_filename': {'type': 'string'}, 'source_key': {'type': 'string'}, 'fields': {'$ref': '#/$defs/record'}},
                'required': ['source_filename', 'source_key', 'fields']}}}, 'required': ['records']}


def _table(entry):
    import pyarrow.parquet as pq
    return pq.read_table(io.BytesIO(core.store.get(entry['key']))).to_pylist()


def _row_text(row, columns, notes):
    cells = [f'{c}: {spreadsheet._display(row.get(c))}' for c in columns if not spreadsheet._empty(row.get(c))]
    return f'Row {row.get("__row")} · ' + ' · '.join(cells + list(notes or []))


def _read_rows(fields, todo, check, budget_chars, output_tokens):
    """Model-read values for fields that are not columns, from each row's own text, in batches."""
    keys = list(fields)
    per_row = max(40, 25 * len(keys))
    batch_rows = max(1, min(50, (output_tokens - 200) // per_row))
    values, evidence = {}, []
    batch, size = [], 0
    def run(batch):
        check()
        schema = {'type': 'object', 'additionalProperties': False, 'required': ['rows'], 'properties': {'rows': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['row', *keys], 'properties': {'row': {'type': 'integer'}, **fields}}}}}
        sources = [{'id': f'row-{n}', 'text': text, 'document_id': document_id, 'document_name': name, 'page': page} for n, text, document_id, name, page in batch]
        context = '\n'.join(f'{s["text"]}' for s in sources)
        data, quotes = providers.extract_with_evidence('Each line is one spreadsheet row. Return one entry per row, with its row number.\n' + context, schema, sources)
        rows = data.get('rows', [])
        for item in rows:
            values[item.get('row')] = {k: item.get(k) for k in keys}
        for quote in quotes:
            parts = quote.get('field', '').split('/')
            if len(parts) >= 4 and parts[1] == 'rows' and parts[2].isdigit() and int(parts[2]) < len(rows):
                evidence.append(quote | {'row': rows[int(parts[2])].get('row'), 'key': parts[3]})
    for item in todo:
        if batch and (size + len(item[1]) > budget_chars or len(batch) >= batch_rows):
            run(batch); batch, size = [], 0
        batch.append(item); size += len(item[1])
    if batch:
        run(batch)
    return values, evidence


def extract(schema, plans, sources, check=lambda: None, limits=None):
    """(result, evidence, notice)."""
    fields = flat_fields(schema)
    limits = limits or {}
    records, evidence, notes = [], [], []
    for item in plans:
        document, entry, mapping = item['document'], item['sheet'], item['mapping']
        table = _table(entry)
        saved = workbook.load(core.store, document.id) or {}
        row_notes = next((s.get('row_notes', {}) for s in saved.get('sheets', []) if s['name'] == entry['name']), {})
        lookups = {}
        for key, m in mapping.items():
            if m.get('via') and m['sheet'] not in lookups:
                other = next((e for e in spreadsheet.tables(core.store, document.id) if e['name'] == m['sheet']), None)
                rows = _table(other) if other else []
                lookups[m['sheet']] = {}
                for row in rows:
                    value = row.get(m['via']['key'])
                    if not spreadsheet._empty(value):
                        lookups[m['sheet']].setdefault(spreadsheet._display(value).strip().lower(), row)
        chunks = [c for c in sources if c['document_id'] == document.id and c.get('sheet') == entry['name'] and c.get('row_start')]
        start = len(records)
        for n, row in enumerate(table):
            if n % 500 == 0:
                check()
            number = row.get('__row')
            values = {}
            for key, spec in fields.items():
                m = mapping.get(key)
                if not m:
                    values[key] = None
                elif m.get('via'):
                    linked = lookups[m['sheet']].get(spreadsheet._display(row.get(m['via']['column'])).strip().lower())
                    values[key] = _value(spec, linked.get(m['column'])) if linked else None
                else:
                    values[key] = _value(spec, row.get(m['column']))
            records.append({'source_filename': f'{document.name} · {entry["name"]} row {number}',
                            'source_key': f'{document.id}#{entry["index"]}:{number}', 'fields': values})
            quote = f'Row {number} · '
            chunk = next((c for c in chunks if c['row_start'] <= number <= c['row_end'] and quote in c['text']), None)
            if chunk:
                evidence.append({'field': f'/records/{len(records) - 1}/fields', 'chunk_id': chunk['id'], 'quote': quote.strip(' ·'),
                                 'document_id': document.id, 'document_name': document.name, 'page': chunk['page'],
                                 **{k: chunk[k] for k in ('section', 'sheet', 'row_start', 'row_end') if k in chunk}})
        if item['row_fields']:
            specs = {k: fields[k] for k in item['row_fields']}
            todo = [(row.get('__row'), _row_text(row, [c['name'] for c in entry['columns']], row_notes.get(str(row.get('__row')))), document.id, document.name, entry['index'])
                    for row in table[:MAX_AI_ROWS]]
            budget = max(4_000, int((limits.get('context') or 32_768) * 1.6))
            values, quotes = _read_rows(specs, todo, check, budget, limits.get('output') or 4_096)
            position = {records[i]['source_key']: i for i in range(start, len(records))}
            for i, row in enumerate(table[:MAX_AI_ROWS]):
                found = values.get(row.get('__row')) or {}
                for key in item['row_fields']:
                    records[start + i]['fields'][key] = found.get(key)
            for quote in quotes:
                index = position.get(f'{document.id}#{entry["index"]}:{quote["row"]}')
                if index is not None:
                    evidence.append({k: v for k, v in quote.items() if k not in ('row', 'key')} | {'field': f'/records/{index}/fields/{quote["key"]}'})
            if len(table) > MAX_AI_ROWS:
                notes.append(f'{", ".join(item["row_fields"])} were read by the model for the first {MAX_AI_ROWS:,} rows only.')
        used = '; '.join(f'{k} ← ' + (f'{m["sheet"]}.{m["column"]} via {m["via"]["column"]}' if m.get('via') else m['column']) + f' ({m["how"]})' for k, m in mapping.items())
        notes.insert(0, f'Read row by row from sheet "{entry["name"]}" of {document.name} ({len(table):,} rows; {used}).')
        if item['row_fields']:
            notes.append(f'Read by the model from each row\'s cells, comments and images: {", ".join(item["row_fields"])}.')
        if item['whole_fields']:
            notes.append(f'About the whole table, not one row, so left empty here (ask in chat for exact totals): {", ".join(item["whole_fields"])}.')
        missing = [k for k in item['unmatched'] if k not in item['whole_fields']]
        if missing:
            notes.append('No column matched ' + ', '.join(missing) + ': those fields are empty.')
    return {'records': records}, evidence, ' ' + ' '.join(notes)


def preview(plans):
    """The mapping as the person sees it before extracting."""
    out = []
    for item in plans:
        out.append({'document_id': item['document'].id, 'name': item['document'].name, 'sheet': item['sheet']['name'], 'rows': item['sheet']['rows'],
                    'fields': {k: {key: v for key, v in m.items()} for k, m in item['mapping'].items()},
                    'row_fields': item['row_fields'], 'whole_fields': item['whole_fields'], 'unmatched': item['unmatched'],
                    'columns': [{'sheet': s, 'column': c} for s, cols in item['columns'].items() for c in cols]})
    return out
