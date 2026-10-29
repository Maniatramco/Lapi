"""Draft an extraction prompt from the document itself (Quick start).

People rarely know which fields to ask for or how to word an extraction prompt. This reads
the start of the chosen documents and asks the dataset's own extraction model for a short
list of fields (key, label, type, one-line instruction). People edit the list, or ask the
model to rewrite it ("add the due date, drop the address"); the result becomes an ordinary
Lapi prompt template (JSON Schema) and runs as an ordinary extraction.

Needs Editor on the dataset, and the same consent as extraction when that model is external.
"""
import json
import re
from typing import Literal
from fastapi import Depends, HTTPException
from jsonschema import ValidationError, validate
from pydantic import BaseModel, ConfigDict, Field
from . import core, providers
from . import dataset_access as access

FIELD_TYPES = {'text': 'string', 'number': 'number', 'date': 'string', 'yes_no': 'boolean', 'list': 'array'}
EXCERPT_CHARS = 8000
OUTPUT = {'type': 'object', 'additionalProperties': False, 'required': ['name', 'fields'], 'properties': {
    'name': {'type': 'string', 'minLength': 1, 'maxLength': 80},
    'instructions': {'type': 'string', 'maxLength': 600},
    'fields': {'type': 'array', 'minItems': 1, 'maxItems': 15, 'items': {
        'type': 'object', 'additionalProperties': False, 'required': ['key', 'label', 'type', 'description'], 'properties': {
            'key': {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,39}$'},
            'label': {'type': 'string', 'minLength': 1, 'maxLength': 60},
            'type': {'enum': list(FIELD_TYPES)},
            'description': {'type': 'string', 'minLength': 1, 'maxLength': 240}}}}}}
SYSTEM = '''You design extraction prompts for Lapi, a document AI tool used by business people.
Read the document excerpt and propose the fields someone would want pulled out of documents like it:
4 to 10 fields, the most useful first. For each field give a snake_case key, a short human label,
a type (text, number, date, yes_no or list) and a one-line description that says exactly what to
extract and in which format (dates as YYYY-MM-DD; amounts as plain numbers, with a separate currency
field when money appears; names exactly as written). Give the prompt a short name describing the
document kind (for example "Lease agreement fields") and one or two sentences of instructions
(what to do when a value is missing: return null). If the person asks for changes, apply them to the
current fields and keep the others unchanged. Reply with JSON only, matching this schema:
''' + json.dumps(OUTPUT)


class FieldInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(pattern=r'^[a-z][a-z0-9_]{0,39}$')
    label: str = Field(min_length=1, max_length=60)
    type: Literal['text', 'number', 'date', 'yes_no', 'list']
    description: str = Field(min_length=1, max_length=240)


class SuggestInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_id: str = Field(min_length=1)
    document_ids: list[str] = Field(min_length=1, max_length=5)
    request: str = Field(default='', max_length=1000)
    current: list[FieldInput] | None = Field(default=None, max_length=20)
    allow_external: bool = False


class TablePlanInput(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
    dataset_id: str = Field(min_length=1)
    document_ids: list[str] = Field(min_length=1, max_length=20)
    schema_: dict = Field(alias='schema')
    column_mapping: dict[str, dict[str, str] | None] | None = Field(default=None, max_length=100)
    allow_external: bool = False


def excerpt(document_ids):
    """The start of each document's extracted text, within one budget."""
    parts, budget = [], EXCERPT_CHARS
    for document_id in document_ids:
        try:
            pages = core.store.json(f'documents/{document_id}/parsed.json').get('pages') or []
        except FileNotFoundError:
            continue
        text = '\n'.join(str(page.get('text') or '') for page in pages).strip()
        from . import workbook
        if (book := workbook.load(core.store, document_id)):
            # A workbook: what each sheet means (all its columns and values), then its first rows.
            text = '\n\n'.join(workbook.profile_text(p) for p in book.get('profiles', [])) + '\n\n' + text
        if not text:
            continue
        piece = text[:max(500, budget // max(1, len(document_ids)))]
        parts.append(piece)
        budget -= len(piece)
        if budget <= 0:
            break
    return '\n\n---\n\n'.join(parts)[:EXCERPT_CHARS]


def to_schema(fields):
    """The editable field list as the JSON Schema Lapi templates use."""
    properties = {}
    for field in fields:
        kind = FIELD_TYPES[field['type']]
        node = {'type': [kind, 'null'], 'description': f"{field['label']}: {field['description']}"}
        if field['type'] == 'date':
            node['format'] = 'date'
        if kind == 'array':
            node = {'type': ['array', 'null'], 'items': {'type': 'string'}, 'description': node['description']}
        properties[field['key']] = node
    # Strict extraction: every field is required and nullable, so a missing value is null.
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}


def call_model(messages, snapshot, output=OUTPUT):
    """One reply from the dataset's extraction model (the same provider extraction uses)."""
    settings = snapshot['settings']
    protocol = (settings.get('model_connection') or {}).get('protocol') if settings['model_provider'] == 'registered' else settings['model_provider']
    with core.execution_context(snapshot):
        if protocol == 'ollama':
            from . import ollama_provider
            payload = {'model': ollama_provider.local_model_name(settings['model']), 'messages': messages,
                       'stream': False, 'think': False, 'format': output, 'options': {'temperature': 0}}
            try:
                result = ollama_provider.request('/api/chat', payload, settings['timeout'])
            except ollama_provider.OllamaError as error:
                raise providers.ProviderError(str(error)) from error
            return result.get('message', {}).get('content', '')
        from .lapi_agent import agent_model
        return agent_model.complete(messages, []).get('text', '')


def parse(raw):
    text = (raw or '').strip()
    fenced = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.S)
    if fenced:
        text = fenced.group(1)
    elif '{' in text:
        text = text[text.index('{'):text.rindex('}') + 1]
    data = json.loads(text)
    validate(data, OUTPUT)
    seen, fields = set(), []
    for field in data['fields']:
        if field['key'] not in seen:
            seen.add(field['key'])
            fields.append(field)
    return {'name': data['name'].strip(), 'instructions': (data.get('instructions') or '').strip(), 'fields': fields}


def install(app, auth):
    @app.post('/api/templates/suggest')
    def suggest(body: SuggestInput, owner=Depends(auth)):
        from .main import external_check
        from . import dataset_models as routing
        dataset = access.get_record(body.dataset_id, owner, 'knowledge_base', level='editor')
        for document_id in body.document_ids:
            document = access.get_record(document_id, owner, 'document')
            if document.parent_id != dataset.id:
                raise HTTPException(400, 'Choose documents from this dataset.')
            if document.status != 'ready':
                raise HTTPException(409, 'Wait until the documents are read, then try again.')
        text = excerpt(body.document_ids)
        if not text:
            raise HTTPException(409, 'No text could be read from these documents, so no fields can be suggested.')
        snapshot = routing.execution_snapshot(dataset, 'extraction')
        external_check(body.allow_external, cfg=snapshot['settings'])
        ask = {'document_excerpt': text}
        if body.current:
            ask['current_fields'] = [field.model_dump() for field in body.current]
        if body.request.strip():
            ask['requested_changes'] = body.request.strip()
        messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps(ask, ensure_ascii=False)}]
        try:
            raw = call_model(messages, snapshot)
        except providers.ProviderError as exc:
            raise HTTPException(502, f'The extraction model could not suggest fields: {exc}')
        try:
            result = parse(raw)
        except (ValueError, ValidationError):
            raise HTTPException(502, 'The extraction model\'s suggestion could not be read. Try again.')
        return result | {'schema': to_schema(result['fields'])}

    @app.post('/api/templates/table-plan')
    def table_plan(body: TablePlanInput, owner=Depends(auth)):
        """How each field will be read from spreadsheet columns, for the person to confirm."""
        from .main import external_check
        from . import dataset_models as routing
        from .lapi_agent import table_extraction
        dataset = access.get_record(body.dataset_id, owner, 'knowledge_base', level='editor')
        documents = []
        for document_id in body.document_ids:
            document = access.get_record(document_id, owner, 'document')
            if document.parent_id != dataset.id:
                raise HTTPException(400, 'Choose documents from this dataset.')
            if document.status != 'ready':
                raise HTTPException(409, 'Wait until the documents are read, then try again.')
            documents.append(document)
        snapshot = routing.execution_snapshot(dataset, 'extraction')
        external_check(body.allow_external, cfg=snapshot['settings'])
        with core.execution_context(snapshot):
            plans = table_extraction.propose(body.schema_, documents, override=body.column_mapping)
        return {'applies': bool(plans), 'documents': table_extraction.preview(plans) if plans else []}
