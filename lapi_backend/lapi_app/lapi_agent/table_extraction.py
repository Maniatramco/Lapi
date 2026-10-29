"""Row-by-row extraction from spreadsheets, read from the stored table instead of the model.

When every document of an extraction is a spreadsheet and most of the requested fields are its
columns ("Transaction ID", "Amount", ...), each data row becomes one record with its values taken
exactly from the typed table Lapi saved at indexing (`spreadsheet.save`). No model call: it is exact,
does not depend on a context limit, and works for 2,000 rows as well as 20. Fields that match no
column stay empty and are named in the extraction's notice.
"""
import io
import math
import re
from .. import core, spreadsheet
from ..merged_documents import embedded_schema

SCALARS = {'string', 'number', 'integer', 'boolean', 'null'}
MIN_SHARE = 0.5     # at least half of the fields must be columns


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


def _names(key, spec):
    """The field's key and the label written before ':' in its description ("Transaction ID: Extract ...")."""
    names = {_words(key.replace('_', ' '))}
    label = str(spec.get('description', '')).split(':', 1)[0]
    if ':' in str(spec.get('description', '')) and 0 < len(label) <= 60:
        names.add(_words(label))
    return {n for n in names if n}


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
    """{field key: column name}, each column used once, best scores first."""
    pairs = sorted(((_score(_names(key, spec), column), key, column) for key, spec in fields.items() for column in columns), reverse=True)
    mapping, used = {}, set()
    for score, key, column in pairs:
        if score and key not in mapping and column not in used:
            mapping[key] = column; used.add(column)
    return mapping


def plan(schema, documents):
    """[{document, sheet entry, mapping}] when the extraction can be read from tables, else None."""
    fields = flat_fields(schema)
    if not fields or not documents:
        return None
    chosen = []
    for document in documents:
        if not spreadsheet.is_spreadsheet(document.name or ''):
            return None
        best = None
        for entry in spreadsheet.tables(core.store, document.id):
            mapping = match(fields, [c['name'] for c in entry['columns']])
            if not best or len(mapping) > len(best[1]):
                best = (entry, mapping)
        if not best or len(best[1]) < max(1, math.ceil(MIN_SHARE * len(fields))):
            return None
        chosen.append({'document': document, 'sheet': best[0], 'mapping': best[1]})
    return chosen


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


def extract(schema, chosen, sources, check=lambda: None):
    """(result, evidence, notice). Evidence is one quote per row from the row's search chunk."""
    import pyarrow.parquet as pq
    fields = flat_fields(schema)
    records, evidence, missing = [], [], set(fields)
    for item in chosen:
        document, entry, mapping = item['document'], item['sheet'], item['mapping']
        missing -= set(mapping)
        table = pq.read_table(io.BytesIO(core.store.get(entry['key']))).to_pylist()
        chunks = [c for c in sources if c['document_id'] == document.id and c.get('sheet') == entry['name'] and c.get('row_start')]
        for n, row in enumerate(table):
            if n % 500 == 0:
                check()
            number = row.get('__row')
            values = {key: _value(spec, row.get(mapping[key])) if key in mapping else None for key, spec in fields.items()}
            index = len(records)
            records.append({'source_filename': f'{document.name} · {entry["name"]} row {number}',
                            'source_key': f'{document.id}#{entry["index"]}:{number}', 'fields': values})
            quote = f'Row {number} · '
            chunk = next((c for c in chunks if c['row_start'] <= number <= c['row_end'] and quote in c['text']), None)
            if chunk:
                evidence.append({'field': f'/records/{index}/fields', 'chunk_id': chunk['id'], 'quote': quote.strip(' ·'),
                                 'document_id': document.id, 'document_name': document.name, 'page': chunk['page'],
                                 **{k: chunk[k] for k in ('section', 'sheet', 'row_start', 'row_end') if k in chunk}})
    used = ', '.join(sorted({f'{key} ← {column}' for item in chosen for key, column in item['mapping'].items()}))
    notice = f' Read row by row from the spreadsheet table ({len(records):,} rows; {used}).'
    if missing:
        notice += ' No column matched ' + ', '.join(sorted(missing)) + ': those fields are empty.'
    return {'records': records}, evidence, notice
