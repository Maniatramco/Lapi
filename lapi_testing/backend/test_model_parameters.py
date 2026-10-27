"""WS12: typed per-stage model parameters, documented Lapi defaults, effective
settings, sample-prompt tests and versioned history. Cloud traffic is mocked."""
import io
import json
from types import SimpleNamespace
import httpx
import pytest
from lapi_app import core, ollama_provider as ollama, model_connections as connections
from lapi_app.lapi_models import parameters
from test_dataset_models import system, dataset
from test_model_registration import body, register, cloud_transport, select


# -- Resolution order and Lapi defaults ------------------------------------

def test_stage_fallback_order_is_stage_then_model_then_lapi_default():
    cfg = {'model_connection': {'protocol': 'ollama'}, 'model': 'qwen3:4b'}
    assert parameters.for_stage(cfg, 'tool_step') == {'temperature': 0, 'top_p': 0.8, 'top_k': 20, 'repeat_penalty': 1.1, 'seed': 42}
    cfg['extra_parameters'] = {'temperature': 0.6, 'top_k': 5}
    assert parameters.for_stage(cfg, 'tool_step')['temperature'] == 0.6
    cfg['stage_parameters'] = {'tool_step': {'temperature': 0.1}}
    detail = parameters.resolve(cfg, 'tool_step')
    assert detail['parameters']['temperature'] == 0.1 and detail['parameters']['top_k'] == 5
    assert detail['sources'] == {'temperature': 'stage', 'top_k': 'model', 'top_p': 'lapi_default', 'repeat_penalty': 'lapi_default', 'seed': 'lapi_default'}
    # Other stages fall back to the model value, never to another stage.
    assert parameters.for_stage(cfg, 'chat')['temperature'] == 0.6
    assert parameters.for_stage(cfg, 'optimize')['temperature'] == 0.6


def test_lapi_defaults_apply_only_when_a_field_is_on_default():
    base = {'model_connection': {'protocol': 'ollama'}}
    assert parameters.for_stage(base, 'chat')['temperature'] == 0
    assert parameters.for_stage(base, 'extraction')['temperature'] == 0.2
    assert parameters.for_stage(base, 'optimize')['temperature'] == 0.7
    # Admin value wins at any layer, including 0 and the highest allowed value.
    assert parameters.for_stage(base | {'extra_parameters': {'temperature': 2}}, 'tool_step')['temperature'] == 2
    assert parameters.for_stage(base | {'stage_parameters': {'extraction': {'temperature': 0}}}, 'extraction')['temperature'] == 0
    # "Use provider default" (null) sends nothing and stops the Lapi default.
    sent = parameters.for_stage(base | {'extra_parameters': {'seed': None}, 'stage_parameters': {'chat': {'temperature': None}}}, 'chat')
    assert 'temperature' not in sent and 'seed' not in sent and sent['top_p'] == 0.8
    # A stage null overrides a model value; a stage value overrides a model null.
    assert 'top_k' not in parameters.for_stage(base | {'extra_parameters': {'top_k': 9}, 'stage_parameters': {'chat': {'top_k': None}}}, 'chat')
    assert parameters.for_stage(base | {'extra_parameters': {'top_k': None}, 'stage_parameters': {'chat': {'top_k': 9}}}, 'chat')['top_k'] == 9


def test_openai_lapi_default_is_limited_to_gpt4o_tool_steps_and_ocr():
    connection = {'protocol': 'openai-compatible'}
    assert parameters.for_stage({'model_connection': connection, 'model': 'gpt-4o-mini'}, 'tool_step') == {'temperature': 0}
    assert parameters.for_stage({'model_connection': connection, 'model': 'gpt-4o-mini'}, 'chat') == {}
    assert parameters.for_stage({'model_connection': connection, 'model': 'gpt-5'}, 'tool_step') == {}
    assert parameters.for_stage({'model_connection': connection, 'model': 'gpt-4o'}, 'extraction', purpose='ocr') == {'temperature': 0.1}
    custom = {'model_connection': connection, 'model': 'gpt-4o', 'stage_parameters': {'extraction': {'temperature': 0.4}}}
    assert parameters.for_stage(custom, 'extraction', purpose='ocr') == {'temperature': 0.4}
    assert parameters.for_stage({'model_connection': {'protocol': 'anthropic'}}, 'tool_step') == {}


def test_explicit_stage_wins_over_the_call_site_inference():
    assert parameters.current_stage('tool_step') == 'tool_step'
    with parameters.use_stage('optimize'):
        with parameters.default_stage('chat'):
            assert parameters.current_stage('tool_step') == 'optimize'
    with parameters.default_stage('extraction'):
        assert parameters.current_stage() == 'extraction'
    with pytest.raises(parameters.ParameterError):
        with parameters.use_stage('router'): pass


def test_effective_parameters_report_what_was_sent():
    parameters.clear_effective()
    sent = parameters.for_stage({'model_connection': {'protocol': 'ollama'}, 'stage_parameters': {'tool_step': {'temperature': 0.3}}}, 'tool_step')
    effective = parameters.effective()
    assert effective['parameters'] == sent and effective['stage'] == 'tool_step' and effective['protocol'] == 'ollama'
    assert effective['sources']['temperature'] == 'stage' and effective['sources']['seed'] == 'lapi_default'
    effective['parameters']['temperature'] = 9
    assert parameters.effective()['parameters']['temperature'] == 0.3


# -- Ranges and schema ------------------------------------------------------

@pytest.mark.parametrize('protocol,value,ok', [('ollama', 2, True), ('ollama', 2.01, False), ('openai-compatible', 1.5, True),
    ('bedrock', 1, True), ('bedrock', 1.5, False), ('vertex', 1.5, True), ('oci', -0.1, False)])
def test_temperature_ranges_keep_validation_including_bedrock(protocol, value, ok):
    if ok:
        assert parameters.validate_parameters({'temperature': value}, protocol, 'chat') == {'temperature': value}
        assert parameters.validate_stage_parameters({'tool_step': {'temperature': value}}, protocol, 'chat') == {'tool_step': {'temperature': value}}
    else:
        with pytest.raises(parameters.ParameterError):parameters.validate_parameters({'temperature': value}, protocol, 'chat')
        with pytest.raises(parameters.ParameterError):parameters.validate_stage_parameters({'tool_step': {'temperature': value}}, protocol, 'chat')


@pytest.mark.parametrize('stages', [{'router': {}}, {'chat': {'num_ctx': 4}}, {'chat': {'seed': 1.5}}, {'chat': {'top_p': 1.1}}, ['chat'], {'chat': {'stop': ['x' * 257]}}])
def test_invalid_stage_parameters_rejected(stages):
    with pytest.raises(parameters.ParameterError):
        parameters.validate_stage_parameters(stages, 'ollama', 'chat')


def test_null_means_provider_default_and_is_kept_only_for_storage():
    assert parameters.validate_parameters({'temperature': None, 'seed': 3}, 'ollama', 'chat') == {'seed': 3}
    assert parameters.validate_parameters({'temperature': None}, 'ollama', 'chat', keep_null=True) == {'temperature': None}
    assert parameters.validate_stage_parameters({'chat': {}, 'tool_step': {'seed': None}}, 'ollama', 'chat') == {'tool_step': {'seed': None}}
    with pytest.raises(parameters.ParameterError):
        parameters.validate_stage_parameters({'chat': {'keep_alive': '1m'}}, 'ollama', 'embedding')


def test_schema_per_provider_and_role():
    bedrock = parameters.supported_parameters('bedrock', 'chat', schema=True)
    fields = {f['key']: f for f in bedrock['fields']}
    assert set(fields) == {'temperature', 'topP', 'stopSequences'}
    assert {k: fields['temperature'][k] for k in ('type', 'min', 'max')} == {'type': 'number', 'min': 0, 'max': 1}
    assert fields['temperature']['help'] and 'default' in fields['temperature']
    assert [s['key'] for s in bedrock['stages']] == ['chat', 'tool_step', 'optimize']
    ollama_schema = parameters.parameter_schema('ollama', 'chat')
    temperature = next(f for f in ollama_schema['fields'] if f['key'] == 'temperature')
    assert temperature['max'] == 2 and temperature['default'] == 0.8
    tool = next(s for s in ollama_schema['stages'] if s['key'] == 'tool_step')
    assert tool['suggested']['temperature'] == 0 and tool['lapi_defaults']['temperature'] == 0 and tool['lapi_defaults']['seed'] == 42
    assert [s['key'] for s in parameters.parameter_schema('ollama', 'extraction')['stages']] == ['extraction']
    claude = parameters.parameter_schema('anthropic', 'chat')
    assert claude['accepts_overrides'] is False and claude['fields'] == [] and 'does not accept sampling overrides' in claude['notice']
    embedding = parameters.parameter_schema('ollama', 'embedding')
    assert [f['key'] for f in embedding['fields']] == ['keep_alive'] and embedding['stages'] == []
    assert parameters.parameter_schema('oci', 'chat', {'chat_format': 'cohere'})['fields'][-1]['key'] == 'stop_sequences'


def test_parameter_schema_route(system):
    result = system.api.get('/api/model-registrations/parameter-schema', params={'protocol': 'bedrock', 'category': 'chat'})
    assert result.status_code == 200
    assert next(f for f in result.json()['fields'] if f['key'] == 'temperature')['max'] == 1
    assert system.api.get('/api/model-registrations/parameter-schema', params={'protocol': 'unknown', 'category': 'chat'}).status_code == 422


# -- Values sent to each provider match the form ----------------------------

def test_ollama_adapter_sends_stage_values_and_documented_defaults(monkeypatch):
    cfg = {'context_limit': 16384, 'max_output_tokens': 256, 'extra_parameters': {'temperature': 0.5, 'keep_alive': '2m'},
        'stage_parameters': {'extraction': {'temperature': 0.05, 'seed': None}, 'chat': {'top_k': 7}}}
    monkeypatch.setattr(core, 'settings', lambda: cfg)
    sent = []
    def response(path, payload, timeout):
        sent.append(payload)
        return {'done': True, 'done_reason': 'stop', 'message': {'content': '{"status":"ready"}'}}
    monkeypatch.setattr(ollama, 'request', response)
    ollama.chat('qwen3:4b', 'Status?', [{'document_name': 'test', 'text': 'ready'}], [], 60)
    ollama.extract('qwen3:4b', 'ready', {'type': 'object', 'properties': {'status': {'type': 'string'}}}, 60)
    chat, extract = sent[0]['options'], sent[1]['options']
    assert chat['temperature'] == 0.5 and chat['top_k'] == 7 and chat['seed'] == 42 and chat['top_p'] == 0.8
    assert extract['temperature'] == 0.05 and 'seed' not in extract and extract['top_k'] == 20
    assert sent[0]['keep_alive'] == sent[1]['keep_alive'] == '2m' and 'keep_alive' not in chat
    # With nothing set, the documented Lapi defaults apply.
    cfg.update(extra_parameters={}, stage_parameters={})
    sent.clear()
    ollama.extract('qwen3:4b', 'ready', {'type': 'object', 'properties': {'status': {'type': 'string'}}}, 60)
    assert sent[0]['options']['temperature'] == 0.2 and sent[0]['options']['seed'] == 42 and 'keep_alive' not in sent[0]


def test_agent_tool_steps_no_longer_override_admin_values(system, monkeypatch):
    from lapi_app.lapi_agent import agent_model
    cfg = {'model_provider': 'ollama', 'model': 'llama3.2', 'timeout': 30, 'context_limit': 32768, 'max_output_tokens': 256,
        'extra_parameters': {'temperature': 0.9, 'seed': 7}, 'stage_parameters': {'tool_step': {'temperature': 0.3}}}
    sent = []
    def response(path, payload, timeout):
        sent.append(payload)
        return {'done': True, 'done_reason': 'stop', 'message': {'content': 'Ready.'}}
    monkeypatch.setattr(ollama, 'request', response)
    tool = {'type': 'function', 'function': {'name': 'noop', 'description': 'x', 'parameters': {'type': 'object', 'properties': {}}}}
    with core.execution_context({'settings': cfg}):
        agent_model.complete([{'role': 'system', 'content': 'x'}, {'role': 'user', 'content': 'y'}], [tool])
        agent_model.complete([{'role': 'system', 'content': 'x'}, {'role': 'user', 'content': 'y'}], [])
    assert sent[0]['options']['temperature'] == 0.3 and sent[0]['options']['seed'] == 7
    assert sent[1]['options']['temperature'] == 0.9 and sent[1]['options']['seed'] == 7
    cfg.update(extra_parameters={}, stage_parameters={}); sent.clear()
    with core.execution_context({'settings': cfg}):
        agent_model.complete([{'role': 'system', 'content': 'x'}, {'role': 'user', 'content': 'y'}], [tool])
    assert sent[0]['options']['temperature'] == 0 and sent[0]['options']['seed'] == 42


@pytest.mark.parametrize('protocol', ['azure-openai', 'openai-compatible', 'bedrock', 'vertex', 'oci'])
def test_cloud_providers_receive_exactly_the_form_values_per_stage(system, monkeypatch, protocol):
    s = system; calls = []
    def handle(req):
        calls.append(json.loads(req.content))
        if protocol == 'vertex':
            return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'ready'}]}}]})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'ready'}}]})
    cloud_transport(monkeypatch, handle)
    class Bedrock:
        def converse(self, **payload):
            calls.append(payload); return {'stopReason': 'end_turn', 'output': {'message': {'content': [{'text': 'ready'}]}}}
    monkeypatch.setattr(connections.ModelConnection, 'bedrock', lambda self: Bedrock())
    class OCI:
        def chat(self, payload):
            import oci
            calls.append(oci.util.to_dict(payload))
            return SimpleNamespace(data=SimpleNamespace(chat_response=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=[SimpleNamespace(text='ready')]))])))
    monkeypatch.setattr(connections.ModelConnection, 'oci_client', lambda self: OCI())
    top = 'topP' if protocol in ('bedrock', 'vertex') else 'top_p'
    m = register(s, body('chat', protocol, extra_parameters={'temperature': 0.7, top: 0.9},
        stage_parameters={'optimize': {'temperature': 0.25}, 'chat': {top: None}}))
    assert m['stage_parameters'] == {'optimize': {'temperature': 0.25}, 'chat': {top: None}}
    snapshot = routing_snapshot(s, m)
    with core.execution_context(snapshot):
        adapter = connections.ModelConnection(core.settings())
        adapter.generate('instruction', 'test')
        with parameters.use_stage('optimize'):
            adapter.generate('instruction', 'test')
    def sent(payload):
        values = payload['inferenceConfig'] if protocol == 'bedrock' else payload['generationConfig'] if protocol == 'vertex' else payload['chat_request'] if protocol == 'oci' else payload
        return {k: values.get(k) for k in ('temperature', top)}
    assert sent(calls[0]) == {'temperature': 0.7, top: None}
    assert sent(calls[1]) == {'temperature': 0.25, top: 0.9}


def routing_snapshot(s, m):
    from lapi_app import dataset_models as routing
    profile = routing.owned(m['connection_profile_id'], s.owner, 'config_profile')
    return routing.profile_snapshot(profile)


def test_bedrock_registration_rejects_temperature_above_one(system):
    result = system.api.post('/api/model-registrations', json=body('chat', 'bedrock', stage_parameters={'tool_step': {'temperature': 1.2}}))
    assert result.status_code == 400 and 'temperature' in result.text
    assert system.api.post('/api/model-registrations', json=body('embedding', 'ollama', stage_parameters={'chat': {'temperature': 0.1}})).status_code == 400


def test_queued_extraction_is_pinned_to_its_stage_values(system):
    s = system; d = dataset(s)
    m = register(s, body('extraction', 'ollama', provider_model='qwen3:4b', stage_parameters={'extraction': {'temperature': 0.05}}))
    select(s, d, m, 'extraction')
    from lapi_app import dataset_models as routing
    snapshot = routing.execution_snapshot(routing.owned(d['id'], s.owner, 'knowledge_base'), 'extraction')
    assert snapshot['settings']['stage_parameters'] == {'extraction': {'temperature': 0.05}}
    assert parameters.for_stage(snapshot['settings'], 'extraction')['temperature'] == 0.05


# -- Test with these settings -----------------------------------------------

def test_connection_test_runs_sample_prompts_with_the_chosen_values(system, monkeypatch):
    requests = []
    def handle(req):
        payload = json.loads(req.content); requests.append(payload)
        if payload.get('tools'):
            message = {'content': '', 'tool_calls': [{'function': {'name': 'connection_status', 'arguments': {'status': 'ready'}}}]}
        else:
            message = {'content': 'Ready.'}
        return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'message': message})
    cloud_transport(monkeypatch, handle)
    value = body('chat', 'ollama', provider_model='llama3.2', extra_parameters={'temperature': 0.6},
        stage_parameters={'tool_step': {'temperature': 0.1, 'seed': None}}, test_stages=['chat'])
    result = system.api.post('/api/model-registrations/test', json=value)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['agent_tool_call_validated'] and data['samples'] == {'chat': 'Ready.'}
    assert len(requests) == 2
    assert requests[0]['options']['temperature'] == 0.1 and 'seed' not in requests[0]['options']
    assert requests[1]['options']['temperature'] == 0.6 and requests[1]['options']['seed'] == 42
    effective = data['effective_parameters']
    assert effective['tool_step']['parameters']['temperature'] == 0.1 and effective['tool_step']['sources']['seed'] == 'provider_default'
    assert effective['chat']['sources'] == effective['chat']['sources'] | {'temperature': 'model', 'seed': 'lapi_default'}
    # Without test_stages the probe stays one request, as before.
    requests.clear()
    assert system.api.post('/api/model-registrations/test', json=value | {'test_stages': None}).status_code == 200
    assert len(requests) == 1
    assert system.api.get('/api/models').json() == []


# -- Versioned history -------------------------------------------------------

def test_parameter_changes_are_versioned_with_author_and_time(system):
    s = system
    m = register(s, body(protocol='ollama', provider_model='qwen3:4b', extra_parameters={'temperature': 0.4}))
    assert m['parameter_version'] == 1 and m['parameters_updated']['author']['id'] == s.owner
    url = '/api/model-registrations/' + m['id']
    assert s.api.put(url, json=body(protocol='ollama', provider_model='qwen3:4b', name='Renamed')).status_code == 200
    changed = s.api.put(url, json=body(protocol='ollama', provider_model='qwen3:4b', extra_parameters={'temperature': None},
        stage_parameters={'tool_step': {'temperature': 0}}))
    assert changed.status_code == 200 and changed.json()['parameter_version'] == 2
    history = s.api.get(url + '/parameter-history').json()['history']
    assert [h['version'] for h in history] == [2, 1]
    assert history[1]['event'] == 'registered' and history[1]['parameters']['extra_parameters'] == {'temperature': 0.4}
    assert history[0]['event'] == 'changed' and history[0]['author']['id'] == s.owner and history[0]['at'] >= history[1]['at']
    assert {(c['scope'], c['key']): (c['from'], c['to']) for c in history[0]['changes']} == {
        ('model', 'temperature'): ({'mode': 'custom', 'value': 0.4}, {'mode': 'provider_default'}),
        ('tool_step', 'temperature'): ({'mode': 'default'}, {'mode': 'custom', 'value': 0})}
    assert history[0]['parameters'] == {'extra_parameters': {'temperature': None}, 'stage_parameters': {'tool_step': {'temperature': 0}}}
    assert 'parameter_history' not in s.api.get('/api/models').json()[0]
    # Omitting both fields keeps the saved values and adds no version.
    assert s.api.put(url, json=body(protocol='ollama', provider_model='qwen3:4b')).json()['stage_parameters'] == {'tool_step': {'temperature': 0}}
    assert len(s.api.get(url + '/parameter-history').json()['history']) == 2
    assert s.api.get('/api/model-registrations/missing/parameter-history').status_code == 404
