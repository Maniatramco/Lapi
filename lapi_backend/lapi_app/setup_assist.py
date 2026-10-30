"""Read one answer in the set-up chat with the overall Default chat model.

The chat is scripted, so it works without a model. With one, a typed or spoken answer is read
properly: "its mnai" becomes the name Mani, "yeah go on" is a yes, "the totals, who sent it and
when its due" becomes fields, and an answer that does not fit the question comes back as
"unclear" with a short, kind message asking again. The screen keeps its own rules as the fallback
whenever there is no model or it cannot be read.
"""
import json
from typing import Literal
from fastapi import Depends
from jsonschema import ValidationError, validate
from pydantic import BaseModel, ConfigDict, Field
from . import core, providers

Stage = Literal['help', 'name', 'team', 'team-name', 'choose', 'collection', 'type', 'interest', 'fields', 'change', 'documents', 'consent', 'results', 'done']
OUTPUT = {'type': 'object', 'additionalProperties': False, 'required': ['decision'], 'properties': {
    'decision': {'enum': ['yes', 'no', 'change', 'skip', 'answer', 'unclear']},
    'name': {'type': 'string', 'maxLength': 60},
    'pick': {'type': 'string', 'maxLength': 120},
    'fields': {'type': 'array', 'maxItems': 15, 'items': {'type': 'object', 'additionalProperties': False, 'required': ['label', 'type', 'description'], 'properties': {
        'label': {'type': 'string', 'minLength': 1, 'maxLength': 60}, 'type': {'enum': ['text', 'number', 'date', 'yes_no', 'list']}, 'description': {'type': 'string', 'minLength': 1, 'maxLength': 240}}}},
    'message': {'type': 'string', 'maxLength': 200}}}
STAGES = {
    'help': 'Lapi asked what it can do for the person and gave options: collection (make a collection), team (a team workspace), extract (pull data out of documents), email (reach a person for help or report a problem). Put the matching option word in "pick"; "unclear" with a message if none fits.',
    'name': 'Lapi asked what to call the person. Put their name, corrected for typos and capitalised, in "name" (first name, or first and last). Decision "answer". If no name is there, "unclear" with a kind message asking again.',
    'team': 'Lapi asked whether they also want a team workspace. Decision "yes" or "no"; "unclear" with a message if neither.',
    'team-name': 'Lapi asked what the team workspace should be called. Put a clean name in "pick" (fix typos, Title Case). Decision "answer".',
    'choose': 'Lapi asked which workspace to use and gave options. Put the matching option, exactly as listed, in "pick"; "unclear" with a message if none matches.',
    'collection': 'Lapi asked what the first collection should be called. Put a clean name in "pick" (fix typos, Title Case). Decision "answer".',
    'type': 'Lapi asked what kind of documents go in it. Put a short type in "pick", preferring one of the options when it fits (e.g. "invoices" -> "Finance"); "skip" if they decline.',
    'interest': 'Lapi asked what they want to pull out of their documents first. Turn it into 3 to 10 extraction fields: label, type (text, number, date, yes_no, list) and a one-line description of exactly what to extract and in which format. Decision "answer"; "skip" if they decline.',
    'fields': 'Lapi listed the fields it would pull out and asked to go with them or change them. "yes" to keep, "change" when they want changes (put the full changed list in "fields" when they say what to change), "unclear" otherwise.',
    'change': 'Lapi asked what to add or remove. Apply their words to the current fields and return the full new list in "fields". Decision "answer".',
    'documents': 'Lapi asked them to take a photo or choose files. Decision "skip" if they decline, else "unclear" with a message saying to tap one of the buttons.',
    'consent': 'Lapi asked permission to send their files to the AI services for reading. "yes" or "no"; "change" if they want to add more files first; "unclear" otherwise.',
}
SYSTEM = '''You help Lapi, a document AI tool, understand one answer in its set-up chat. People type or speak casually,
with typos and extra words. Read what they mean and reply with JSON only, matching this schema:
''' + json.dumps(OUTPUT) + '''
Only the fields the stage asks for. Never invent a name, option or field the person did not mean. Keep any message
to one short, kind sentence in plain English.'''


class InterpretInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stage: Stage
    answer: str = Field(min_length=1, max_length=400)
    options: list[str] = Field(default_factory=list, max_length=40)
    fields: list[str] = Field(default_factory=list, max_length=20)
    collection_type: str = Field(default='', max_length=60)
    name: str = Field(default='', max_length=60)


def chat_snapshot():
    """The overall Default chat model, pinned the way a collection's model is, or None."""
    from . import workspace_defaults, dataset_models as routing
    model_id = workspace_defaults.default_id('chat')
    model = routing.model_record(model_id) if model_id else None
    if not model or model.kind != 'model':
        return None
    data = routing.model_data(model)
    if data.get('archived') or not data.get('enabled', True) or 'chat' not in data.get('capabilities', []):
        return None
    profile = routing.owned(data['connection_profile_id'], model.owner, 'config_profile')
    snap = routing.profile_snapshot(profile, data.get('connection_profile_version'))
    snap.update(model_id=model.id, model_name=model.name, provider_model=data['provider_model'], capability='chat')
    snap['settings']['model'] = data['provider_model']; snap['settings']['oci_model'] = data['provider_model']
    snap['settings'].setdefault('context_limit', routing.runtime_config.get('LAPI_DEFAULT_MODEL_CONTEXT_TOKENS'))
    snap['settings'].setdefault('max_output_tokens', routing.runtime_config.get('LAPI_DEFAULT_MODEL_OUTPUT_TOKENS'))
    snap['settings'].setdefault('extra_parameters', {})
    cfg = core.settings().copy()
    cfg.update({k: snap['settings'][k] for k in routing.MODEL_KEYS if k in snap['settings']})
    snap['settings'] = cfg
    return snap


def parse(raw):
    text = (raw or '').strip()
    if '{' in text:
        text = text[text.index('{'):text.rindex('}') + 1]
    data = json.loads(text)
    validate(data, OUTPUT)
    return data


def install(app, auth):
    @app.post('/api/setup/interpret')
    def interpret(body: InterpretInput, actor=Depends(auth)):
        """What the person meant; {'decision': 'rules'} when the screen should use its own rules."""
        if body.stage not in STAGES:
            return {'decision': 'rules'}
        try:
            snapshot = chat_snapshot()
        except Exception:  # a misconfigured model never blocks set-up
            snapshot = None
        if snapshot is None:
            return {'decision': 'rules'}
        from .prompt_suggest import call_model
        ask = {'stage': body.stage, 'what_lapi_asked': STAGES[body.stage], 'answer': body.answer}
        if body.options: ask['options'] = body.options
        if body.fields: ask['current_fields'] = body.fields
        if body.collection_type: ask['collection_type'] = body.collection_type
        if body.name: ask['person'] = body.name
        messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps(ask, ensure_ascii=False)}]
        try:
            return parse(call_model(messages, snapshot, output=OUTPUT))
        except (providers.ProviderError, ValueError, ValidationError, Exception):
            return {'decision': 'rules'}
