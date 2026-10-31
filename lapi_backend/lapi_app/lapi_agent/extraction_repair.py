"""Second chances for one extraction: invalid output, empty fields, sources left out.

A repaired value is kept only when the model quotes it from a supplied chunk, so a
second pass can fill a field the first pass missed but cannot invent one. Each
repair runs at most once, and a field the documents do not contain stays empty.
"""
from jsonschema import ValidationError, validate


def source_of(chunk):
    return chunk.get('source_key') or chunk['document_id']


def cover_sources(selected, sources, per_source):
    """Add the first chunks of any source the ranking left out entirely.

    Ranking runs per field across all files, so one file can outrank another on every
    field and vanish from the model's input. Returns (chunks in source order, added keys)."""
    present = {source_of(c) for c in selected}
    chosen = {c['id'] for c in selected}
    counts = {}
    added = []
    for chunk in sources:
        key = source_of(chunk)
        if key in present or counts.get(key, 0) >= per_source: continue
        counts[key] = counts.get(key, 0) + 1
        chosen.add(chunk['id'])
        if key not in added: added.append(key)
    if not added: return selected, []
    return [c for c in sources if c['id'] in chosen], added


def unread_sources(documents, sources, merge=None):
    """Requested files with no text at all, which no retrieval can recover."""
    if merge and merge.get('document_id'):
        keys = {c.get('source_key') for c in sources}
        return [s['name'] for s in merge.get('sources', []) if s['key'] not in keys]
    ids = {c['document_id'] for c in sources}
    return [d.name for d in documents if d.id not in ids]


def generate_valid(call, text, schema, sources):
    """One extraction, retried once with the schema error when its output is invalid.
    A second invalid output raises, so the job fails instead of saving bad data."""
    value, quotes = call(text, schema, sources)
    try:
        validate(value, schema)
    except ValidationError as exc:
        where = '/'.join(str(p) for p in exc.absolute_path) or 'the top level'
        correction = ('Your previous answer did not match the required schema at ' + where + ': ' + exc.message[:300] +
                      '\nExtract again and follow the schema exactly.\n\n')
        value, quotes = call(correction + text, schema, sources)
        validate(value, schema)
    return value, quotes


def is_empty(value):
    return value is None or value == '' or value == [] or value == {}


def missing_fields(result, schema):
    if not isinstance(result, dict): return []
    return [key for key in schema.get('properties', {}) if is_empty(result.get(key))]


def subset_schema(schema, keys):
    return dict(schema, properties={k: schema['properties'][k] for k in keys},
                required=[k for k in schema.get('required', []) if k in keys])


def _pointer(key):
    return '/' + key.replace('~', '~0').replace('/', '~1')


def fill_missing(call, result, evidence, schema, keys, text, sources):
    """Ask once more for the empty fields. Returns (result, evidence, filled keys)."""
    value, quotes = call(text, subset_schema(schema, keys), sources)
    if not isinstance(value, dict): return result, evidence, []
    merged = dict(result)
    kept = []
    filled = []
    for key in keys:
        pointer = _pointer(key)
        support = [q for q in quotes if q.get('field') == pointer or str(q.get('field', '')).startswith(pointer + '/')]
        if is_empty(value.get(key)) or not support: continue
        merged[key] = value[key]
        kept += support
        filled.append(key)
    if not filled: return result, evidence, []
    try:
        validate(merged, schema)
    except ValidationError:
        return result, evidence, []
    return merged, list(evidence) + kept, filled
