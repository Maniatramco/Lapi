"""Generic model registration; immutable connection versions, encrypted secrets."""
import copy
import json
import time
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, SecretStr
from .. import core, dataset_models as routing, providers
from .connection import ConnectionError, ModelConnection, explaining_provider_errors, validate_connection, validate_credentials
from . import parameters as model_parameters
from .parameters import validate_parameters, validate_stage_parameters
from .validation import temporary_credentials
from .catalog import choices
from .. import runtime_config


def probe_agent(cfg):
    from ..lapi_agent import agent_model
    schema = {'type': 'object', 'properties': {'status': {'type': 'string', 'enum': ['ready']}}, 'required': ['status'], 'additionalProperties': False}
    tool = {'type': 'function', 'function': {'name': 'connection_status', 'description': 'Report the synthetic connection status.', 'parameters': schema}}
    result = agent_model.complete([{'role': 'system', 'content': 'Use the connection_status function once, with status ready. Do not answer with text.'}, {'role': 'user', 'content': 'Test the synthetic connection status.'}], [tool])
    calls = result.get('calls') or []
    if len(calls) != 1 or calls[0].get('name') != 'connection_status' or calls[0].get('arguments') != {'status': 'ready'}:
        raise ConnectionError('This Chat model did not pass the function calling test. Choose a tool-capable model or use it for extraction instead.')
    return {'response_received': True, 'agent_tool_call_validated': True}


SAMPLE_PROMPTS = {
    'chat': 'In one short sentence, say that the connection test is ready.',
    'optimize': 'Rewrite this instruction to be clearer, in one sentence: say ready when the test passes.',
}


def sample_stage(cfg, stage):
    """One short sample prompt at a stage, sent with that stage's chosen values."""
    from ..lapi_agent import agent_model
    with model_parameters.use_stage(stage):
        result = agent_model.complete([{'role': 'system', 'content': 'Answer briefly in plain text. Do not call tools.'},
            {'role': 'user', 'content': SAMPLE_PROMPTS[stage]}], [])
    if not isinstance(result.get('text'), str) or not result['text'].strip():
        raise ConnectionError('The sample prompt returned no answer with these settings.')
    return result['text'].strip()[:400]


def effective_snapshot():
    value = model_parameters.effective()
    return {'parameters': value['parameters'], 'sources': value['sources']} if value else None


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    protocol: Literal['ollama', 'openai-compatible', 'azure-openai', 'anthropic', 'bedrock', 'vertex', 'oci']
    endpoint: str = Field(min_length=1, max_length=500)
    auth_mode: str = Field(max_length=40)
    region: str = Field(default='', max_length=64)
    project_id: str = Field(default='', max_length=128)
    workspace_id: str = Field(default='', max_length=128)
    compartment_id: str = Field(default='', max_length=200)
    profile: str = Field(default='DEFAULT', max_length=80)
    embedding_format: str = Field(default='titan', max_length=30)
    chat_format: str = Field(default='generic', max_length=30)
    chat_api: Literal['chat_completions', 'responses'] = 'chat_completions'
    dimensions: int | None = Field(default=None, ge=1, le=65536)
    structured_output: bool = True


class RegistrationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    category: Literal['embedding', 'chat', 'extraction']
    provider_model: str = Field(min_length=1, max_length=200)
    connection: ConnectionInput
    timeout: int = Field(default=runtime_config.get('LAPI_MODEL_REGISTRATION_TIMEOUT'), ge=5, le=1800)
    context_limit: int | None = Field(default=None, ge=1, le=2097152, strict=True)
    max_output_tokens: int | None = Field(default=None, ge=1, le=131072, strict=True)
    extra_parameters: dict | None = None
    # Per-stage values: {'chat'|'tool_step'|'extraction'|'optimize': {key: value}}.
    # A null value means "Use provider default"; an omitted key means "default".
    stage_parameters: dict[str, dict] | None = None
    # Connection test only: also run a sample prompt at these stages.
    test_stages: list[Literal['chat', 'tool_step', 'extraction', 'optimize']] | None = Field(default=None, max_length=4)
    enabled: bool = True
    credentials: dict[str, SecretStr] = Field(default_factory=dict, max_length=12)
    clear_credentials: bool = False
    existing_model_id: str | None = None
    allow_external: bool = False


def previous(r):
    md = routing.model_data(r)
    profile = routing.owned(md['connection_profile_id'], r.owner, 'config_profile')
    snapshot = routing.profile_snapshot(profile, md.get('connection_profile_version'))
    cfg = snapshot['settings']
    return md, profile, snapshot, cfg.get('embedding_connection' if md['capabilities'] == ['embedding'] else 'model_connection')


def test_key(owner, body, cfg, secret):
    """Identity of a tested connection: same owner, model, settings and credentials."""
    import hashlib
    keys = routing.EMBED_KEYS if body.category == 'embedding' else routing.MODEL_KEYS
    identity = {'owner': owner, 'category': body.category, 'provider_model': body.provider_model.strip(),
                'settings': {k: cfg.get(k) for k in keys}, 'credentials': hashlib.sha256(json.dumps(secret, sort_keys=True).encode()).hexdigest()}
    return 'model/connection-tests/' + hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest() + '.json'


def passed_test(owner, body, cfg, secret):
    """A passing probe of exactly this configuration in the last day."""
    try: receipt = core.store.json(test_key(owner, body, cfg, secret))
    except (FileNotFoundError, ValueError): return None
    return receipt if time.time() - receipt.get('passed_at', 0) <= 86400 else None


def prepare(body, owner, existing=None):
    if not body.name.strip():
        raise HTTPException(400, 'Enter a model name.')
    try:
        c = validate_connection(body.connection.model_dump(), body.category, body.provider_model.strip())
        secret = {key: value.get_secret_value() for key, value in body.credentials.items()}
        if any(len(value) > 32768 for value in secret.values()):
            raise ConnectionError('Credential values are too large.')
        md = None
        if existing:
            md, profile, snapshot, old = previous(existing)
            if body.category not in md['capabilities']:
                raise ConnectionError('A registered model category cannot change. Register another model for the new category.')
            unchanged_destination = old and all(old.get(k) == c.get(k) for k in ('protocol', 'auth_mode', 'endpoint'))
            # Never reuse a saved key for a different endpoint or protocol implicitly.
            if not secret and not body.clear_credentials and unchanged_destination:
                ref = snapshot['secret_refs'].get('connection')
                if ref:
                    secret = json.loads(core.secret_cipher().decrypt(core.local_store.get(ref)).decode())
        if body.clear_credentials:
            secret = {}
        if body.enabled or secret:validate_credentials(c, secret)
        cfg = copy.deepcopy(core.settings())
        role = 'embedding' if body.category == 'embedding' else 'model'
        cfg[role + '_provider'] = 'ollama' if c['protocol'] == 'ollama' else 'registered'
        cfg['embedding_model' if role == 'embedding' else 'model'] = body.provider_model.strip()
        cfg[role + '_connection'] = c
        cfg['timeout'] = body.timeout
        old_cfg = snapshot['settings'] if existing else {}
        context_key = 'embedding_context_limit' if role == 'embedding' else 'context_limit'
        extra_key = 'embedding_extra_parameters' if role == 'embedding' else 'extra_parameters'
        cfg[context_key] = body.context_limit if body.context_limit is not None else old_cfg.get(context_key) or runtime_config.get('LAPI_DEFAULT_EMBEDDING_INPUT_TOKENS' if role == 'embedding' else 'LAPI_DEFAULT_MODEL_CONTEXT_TOKENS')
        params = body.extra_parameters if body.extra_parameters is not None else old_cfg.get(extra_key, {})
        stages = body.stage_parameters if body.stage_parameters is not None else old_cfg.get('stage_parameters') or {}
        try:
            cfg[extra_key] = validate_parameters(params, c['protocol'], body.category, c, keep_null=True)
            staged = validate_stage_parameters(stages, c['protocol'], body.category, c)
        except ValueError as exc:
            raise ConnectionError(str(exc)) from exc
        # Only stored when set, so older registrations keep an identical identity.
        cfg.pop('stage_parameters', None)
        if staged:
            cfg['stage_parameters'] = staged
        if role == 'embedding':
            if body.max_output_tokens is not None:
                raise ConnectionError('Embedding models return vectors; output tokens apply only to Chat and Extraction.')
        else:
            cfg['max_output_tokens'] = body.max_output_tokens if body.max_output_tokens is not None else old_cfg.get('max_output_tokens') or runtime_config.get('LAPI_DEFAULT_MODEL_OUTPUT_TOKENS')
            if cfg['max_output_tokens'] + runtime_config.get('LAPI_CONTEXT_HEADROOM_TOKENS') >= cfg['context_limit']:
                raise ConnectionError('Context tokens must exceed maximum output tokens plus '+str(runtime_config.get('LAPI_CONTEXT_HEADROOM_TOKENS'))+' tokens of headroom.')
        return cfg, secret, (md['capabilities'] if md else [body.category])
    except ConnectionError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(400, 'Saved credentials cannot be decrypted. Enter the credentials again.')


HISTORY_LIMIT = 50


def parameter_set(cfg, capabilities):
    embedding = capabilities == ['embedding']
    return {'extra_parameters': copy.deepcopy(cfg.get('embedding_extra_parameters' if embedding else 'extra_parameters') or {}),
        'stage_parameters': {} if embedding else copy.deepcopy(cfg.get('stage_parameters') or {})}


def author(owner):
    from .. import dataset_access as access
    actor = access.request_actor.get() or owner
    with core.Session() as session:
        user = session.get(core.User, actor)
        return {'id': actor, 'username': user.username if user else None}


def parameter_history_entry(existing, cfg, capabilities, owner, model_version, now):
    """Carry the parameter history forward and append one entry per change.

    Each entry records the author, time, the full parameter set after the
    change and the field-level changes, so the model detail can show who
    changed what and when. Unchanged saves add nothing.
    """
    history, before = [], {}
    if existing:
        data = routing.model_data(existing)
        history = copy.deepcopy(data.get('parameter_history') or [])
        before = parameter_set(previous(existing)[2]['settings'], data['capabilities'])
    after = parameter_set(cfg, capabilities)
    changes = model_parameters.parameter_changes(before, after)
    if existing and not changes:
        return history
    history.append({'version': (history[-1]['version'] + 1) if history else 1, 'model_version': model_version,
        'at': now, 'author': author(owner), 'event': 'changed' if existing else 'registered',
        'parameters': after, 'changes': changes})
    return history[-HISTORY_LIMIT:]


def save(body, owner, existing=None):
    cfg, secret, capabilities = prepare(body, owner, existing)
    from .registry import equivalent
    if existing and routing.model_data(existing).get('archived'):
        raise HTTPException(409,'This registration is archived. Edit its replacement model instead.')
    if existing and not body.enabled:
        from .. import workspace_defaults
        workspace_defaults.guard_disable(existing.id)
    duplicate=equivalent(owner,cfg,body.provider_model.strip(),capabilities,existing.id if existing else None) if not secret else None
    if duplicate:
        raise HTTPException(409,'An equivalent model is already registered as '+duplicate.name+'. Use Model Mapping or edit that registration.')
    model_id = existing.id if existing else core.uid()
    profile = previous(existing)[1] if existing and previous(existing)[3] else None
    profile_id = profile.id if profile else core.uid()
    version = profile.version + 1 if profile else 1
    ref = f'configuration/profiles/{profile_id}/v{version}.json'
    data = {'settings': cfg, 'api_key_configured': False, 'oci_api_key_configured': False,
        'connection_credentials_configured': bool(secret), 'saved_at': time.time(), 'registration_model_id': model_id}
    if secret:
        try:
            encrypted = core.secret_cipher().encrypt(json.dumps(secret).encode())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        core.local_store.put(f'secrets/profiles/{profile_id}/v{version}/connection.enc', encrypted)
    core.local_store.put_json(ref, data)
    model_version = existing.version + 1 if existing else 1
    model_ref = f'model/{model_id}/v{model_version}.json'
    tested = passed_test(owner, body, cfg, secret)
    now = time.time()
    history = parameter_history_entry(existing, cfg, capabilities, owner, model_version, now)
    core.store.put_json(model_ref, {'name': body.name.strip(), 'provider_model': body.provider_model.strip(),
        'connection_profile_id': profile_id, 'connection_profile_version': version, 'capabilities': capabilities, 'enabled': body.enabled,
        'parameter_history': history,
        # Only a version whose connection test passed can become a workspace Default.
        **({'connection_test': {'connection_profile_version': version, 'passed_at': tested['passed_at']}} if tested else {})})
    with core.Session.begin() as session:
        if profile:
            p = session.get(core.Record, profile.id)
            p.version = version; p.ref = ref; p.updated_at = now
        else:
            session.add(core.Record(id=profile_id, kind='config_profile', owner=owner, name=body.name.strip()+' connection', ref=ref, created_at=now, updated_at=now))
        if existing:
            r = session.get(core.Record, model_id)
            r.name = body.name.strip(); r.ref = model_ref; r.version = model_version; r.updated_at = now
        else:
            r = core.Record(id=model_id, kind='model', owner=owner, name=body.name.strip(), ref=model_ref, created_at=now, updated_at=now)
            session.add(r)
    return routing.model_public(r)


def install_routes(app, auth):
    @app.get('/api/model-providers')
    def provider_choices(owner=Depends(auth)):
        return choices()

    @app.get('/api/model-registrations/parameter-schema')
    def parameter_schema(protocol: str, category: Literal['embedding', 'chat', 'extraction'], chat_format: str = 'generic',
            embedding_format: str = 'titan', model: str = '', owner=Depends(auth)):
        if protocol not in ConnectionInput.model_fields['protocol'].annotation.__args__:
            raise HTTPException(422, 'Unknown model protocol.')
        return model_parameters.parameter_schema(protocol, category, {'chat_format': chat_format[:30], 'embedding_format': embedding_format[:30]}, model[:200])

    @app.get('/api/model-registrations/{id}/parameter-history')
    def parameter_history(id: str, owner=Depends(auth)):
        record = routing.owned(id, owner, 'model')
        data = routing.model_data(record)
        return {'model_id': record.id, 'name': record.name, 'history': list(reversed(data.get('parameter_history') or []))}
    @app.post('/api/model-registrations')
    def register(body: RegistrationInput, owner=Depends(auth)):
        with core.document_lock('model-registration-'+owner):
            return save(body, owner)

    @app.put('/api/model-registrations/{id}')
    def revise(id: str, body: RegistrationInput, owner=Depends(auth)):
        with core.document_lock('model-registration-'+owner):
            with core.document_lock('model-'+id):
                return save(body, owner, routing.owned(id, owner, 'model'))

    @app.post('/api/model-registrations/test')
    def test(body: RegistrationInput, owner=Depends(auth)):
        existing = routing.owned(body.existing_model_id, owner, 'model') if body.existing_model_id else None
        cfg, secret, capabilities = prepare(body, owner, existing)
        if body.connection.protocol != 'ollama' and not body.allow_external:
            raise HTTPException(400, 'Allow the synthetic test request to be sent to this external model first.')
        try:
            core.enforce_local_only(cfg)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        # The probe uses the same adapter and validation as execution. No document data
        # or test credentials are persisted, and the configured timeout remains bounded.
        started = time.monotonic()
        snapshot = {'settings': dict(cfg, _agent_require_tool=True), 'secret_refs': {}, 'capability': body.category}
        effective = {}
        model_parameters.clear_effective()
        with core.execution_context(snapshot), temporary_credentials(secret), explaining_provider_errors():
            try:
                if body.category == 'chat':
                    with model_parameters.use_stage('tool_step'):
                        result = probe_agent(snapshot['settings'])
                    effective['tool_step'] = effective_snapshot()
                    # "Test with these settings": one short sample prompt per
                    # requested answer stage, sent with that stage's values.
                    samples = {}
                    for stage in [s for s in ('chat', 'optimize') if s in (body.test_stages or [])]:
                        model_parameters.clear_effective()
                        with core.execution_context({'settings': dict(cfg), 'secret_refs': {}, 'capability': 'chat'}):
                            samples[stage] = sample_stage(cfg, stage)
                        effective[stage] = effective_snapshot()
                    if samples:
                        result['samples'] = samples
                elif body.connection.protocol == 'ollama':
                    from ..ollama_provider import embed, chat, extract
                    if body.category == 'embedding':
                        vectors = embed(body.provider_model, ['Lapi connection test.'], body.timeout)
                        result = {'dimensions': len(vectors[0])}
                    elif body.category == 'extraction':
                        extract(body.provider_model, 'Return the word ready.', {'type': 'object', 'properties': {'status': {'type': 'string'}}, 'required': ['status'], 'additionalProperties': False}, body.timeout)
                        result = {'schema_validated': True}
                    else:
                        chat(body.provider_model, 'What is the status?', [{'document_name': 'Connection test', 'text': 'The status is ready.'}], [], body.timeout)
                        result = {'response_received': True}
                else:
                    adapter = ModelConnection(cfg, embedding=body.category=='embedding', credentials_override=secret)
                    if body.category == 'embedding':
                        vectors = adapter.embed(['Lapi connection test.'])
                        result = {'dimensions': len(vectors[0])}
                    elif body.category == 'extraction':
                        adapter.generate('Return JSON.', 'The status is ready.', {'type': 'object', 'properties': {'status': {'type': 'string'}}, 'required': ['status'], 'additionalProperties': False})
                        result = {'schema_validated': True}
                    else:
                        adapter.generate('Give a brief answer.', 'Say ready.')
                        result = {'response_received': True}
                core.store.put_json(test_key(owner, body, cfg, secret), {'passed_at': time.time(), 'category': body.category})
                if body.category == 'extraction':
                    effective['extraction'] = effective_snapshot()
                elif body.category == 'chat' and 'chat' not in effective and body.connection.protocol == 'ollama' and 'response_received' in result and not result.get('agent_tool_call_validated'):
                    effective['chat'] = effective_snapshot()
                return {'ok': True, 'category': body.category, 'elapsed_ms': round((time.monotonic()-started)*1000), **result,
                    **({'effective_parameters': {k: v for k, v in effective.items() if v is not None}} if body.category != 'embedding' else {})}
            except (ConnectionError, providers.ProviderError) as exc:
                raise HTTPException(400, str(exc)) from exc
            except Exception:
                raise HTTPException(400, 'Connection test failed. Check the endpoint, model, credentials, and service availability.')
