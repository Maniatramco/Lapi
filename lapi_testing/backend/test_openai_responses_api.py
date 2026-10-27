"""Per-model API choice: OpenAI-compatible and Azure OpenAI models can use the
Responses API; every other provider keeps its single chat API."""
import json
import httpx
import pytest
from lapi_app import core, agent_model
from lapi_app.lapi_models.providers.lapi_openai import responses
from lapi_app.lapi_models.validation import ConnectionError, validate_connection
from test_dataset_models import system
from test_model_registration import body, register, routing, cloud_transport
from test_native_agent_providers import MESSAGES, TOOL


def snapshot(s, model):
    return routing.profile_snapshot(routing.owned(model['connection_profile_id'], s.owner, 'config_profile'), model['connection_profile_version'])


def answer(output, status='completed', **extra):
    return {'id': 'resp_1', 'model': 'gpt-6.1-terra', 'status': status, 'output': output,
            'usage': {'input_tokens': 12, 'output_tokens': 5, 'total_tokens': 17,
                      'input_tokens_details': {'cached_tokens': 4}, 'output_tokens_details': {'reasoning_tokens': 2}}, **extra}


def test_request_translates_messages_tools_limits_reasoning_and_format():
    payload = {'model': 'gpt-6.1-terra', 'max_completion_tokens': 300, 'reasoning_effort': 'high', 'tool_choice': 'required',
               'temperature': 1, 'seed': 42, 'stop': ['END'], 'frequency_penalty': 0.5, 'presence_penalty': 0.1, 'parallel_tool_calls': False,
               'messages': [{'role': 'system', 'content': 'Use the tool.'},
                            {'role': 'user', 'content': [{'type': 'text', 'text': 'Read this'}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AA', 'detail': 'high'}}]},
                            {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call_1', 'type': 'function', 'function': {'name': 'connection_status', 'arguments': {'status': 'ready'}}}]},
                            {'role': 'tool', 'tool_call_id': 'call_1', 'content': '{"ok": true}'}],
               'tools': [{'type': 'function', 'function': {'name': 'connection_status', 'description': 'Status', 'parameters': {'type': 'object'}, 'strict': True}}],
               'response_format': {'type': 'json_schema', 'json_schema': {'name': 'extraction', 'schema': {'type': 'object'}, 'strict': True}}}
    sent = responses.request(payload)
    assert sent['store'] is False and sent['max_output_tokens'] == 300 and sent['reasoning'] == {'effort': 'high'}
    assert sent['tool_choice'] == 'required' and sent['temperature'] == 1 and sent['parallel_tool_calls'] is False
    assert not {'seed', 'stop', 'frequency_penalty', 'presence_penalty', 'messages', 'response_format', 'reasoning_effort', 'max_completion_tokens'} & set(sent)
    assert sent['tools'] == [{'type': 'function', 'name': 'connection_status', 'description': 'Status', 'parameters': {'type': 'object'}, 'strict': True}]
    assert sent['text'] == {'format': {'type': 'json_schema', 'name': 'extraction', 'schema': {'type': 'object'}, 'strict': True}}
    assert sent['input'] == [
        {'role': 'system', 'content': 'Use the tool.'},
        {'role': 'user', 'content': [{'type': 'input_text', 'text': 'Read this'}, {'type': 'input_image', 'image_url': 'data:image/png;base64,AA', 'detail': 'high'}]},
        {'type': 'function_call', 'call_id': 'call_1', 'name': 'connection_status', 'arguments': '{"status": "ready"}'},
        {'type': 'function_call_output', 'call_id': 'call_1', 'output': '{"ok": true}'}]
    assert responses.request({'model': 'm', 'messages': [], 'tool_choice': {'type': 'function', 'function': {'name': 'f'}}})['tool_choice'] == {'type': 'function', 'name': 'f'}


def test_reply_becomes_a_chat_completions_answer():
    calls = responses.reply(answer([{'type': 'reasoning', 'summary': []},
                                    {'type': 'function_call', 'call_id': 'call_9', 'name': 'connection_status', 'arguments': '{"status":"ready"}'}]))
    choice = calls['choices'][0]
    assert choice['finish_reason'] == 'tool_calls' and choice['message']['content'] is None
    assert choice['message']['tool_calls'] == [{'id': 'call_9', 'type': 'function', 'function': {'name': 'connection_status', 'arguments': '{"status":"ready"}'}}]
    assert calls['usage'] == {'prompt_tokens': 12, 'completion_tokens': 5, 'total_tokens': 17,
                              'prompt_tokens_details': {'cached_tokens': 4}, 'completion_tokens_details': {'reasoning_tokens': 2}}
    text = responses.reply(answer([{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Three '}, {'type': 'output_text', 'text': 'contracts.'}]}]))
    assert text['choices'][0] == {'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'Three contracts.'}}
    assert responses.reply(answer([], status='incomplete'))['choices'][0]['finish_reason'] == 'length'
    assert responses.reply(answer([{'type': 'message', 'content': [{'type': 'refusal', 'refusal': 'No.'}]}]))['choices'][0]['finish_reason'] == 'content_filter'


@pytest.mark.parametrize('protocol', ['openai-compatible', 'azure-openai'])
def test_openai_style_connections_can_choose_either_api(protocol):
    connection = body('chat', protocol)['connection']
    assert validate_connection(connection, 'chat', 'gpt-6.1-terra')['chat_api'] == 'chat_completions'
    assert validate_connection(connection | {'chat_api': 'responses'}, 'chat', 'gpt-6.1-terra')['chat_api'] == 'responses'
    assert 'chat_api' not in validate_connection(connection | {'chat_api': 'responses'}, 'embedding', 'text-embedding-3-small')
    with pytest.raises(ConnectionError):
        validate_connection(connection | {'chat_api': 'assistants'}, 'chat', 'gpt-6.1-terra')


@pytest.mark.parametrize('protocol', ['anthropic', 'bedrock', 'vertex', 'oci'])
def test_single_api_providers_refuse_responses_and_store_nothing(protocol):
    connection = body('chat', protocol)['connection'] | ({'compartment_id': 'ocid1.compartment.oc1..synthetic'} if protocol == 'oci' else {})
    assert 'chat_api' not in validate_connection(connection | {'chat_api': 'chat_completions'}, 'chat', 'deployed-model')
    with pytest.raises(ConnectionError, match='one chat API'):
        validate_connection(connection | {'chat_api': 'responses'}, 'chat', 'deployed-model')


@pytest.mark.parametrize('chat_api,path', [('responses', '/v1/responses'), ('chat_completions', '/v1/chat/completions')])
def test_agent_tool_step_uses_the_chosen_api(system, monkeypatch, chat_api, path):
    value = body('chat', 'openai-compatible', max_output_tokens=256, context_limit=32768,
                 stage_parameters={'tool_step': {'reasoning_effort': 'high'}})
    value['connection']['chat_api'] = chat_api
    model = register(system, value)
    assert model['connection']['chat_api'] == chat_api
    snap = snapshot(system, model)
    snap['settings']['_agent_require_tool'] = True
    seen = []
    def handle(req):
        seen.append(req)
        assert req.url.path == path and req.headers['authorization'] == 'Bearer synthetic-secret'
        sent = json.loads(req.content)
        if chat_api == 'responses':
            assert sent['reasoning'] == {'effort': 'high'} and sent['tools'][0]['name'] and sent['store'] is False
            return httpx.Response(200, json=answer([{'type': 'function_call', 'call_id': 'call_1', 'name': sent['tools'][0]['name'],
                                                     'arguments': json.dumps({'status': 'ready'})}]))
        assert sent['reasoning_effort'] == 'high' and sent['tools'][0]['function']['name']
        return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None,
            'tool_calls': [{'id': 'call_1', 'type': 'function', 'function': {'name': sent['tools'][0]['function']['name'], 'arguments': json.dumps({'status': 'ready'})}}]}}],
            'usage': {'prompt_tokens': 12, 'completion_tokens': 5, 'total_tokens': 17}})
    cloud_transport(monkeypatch, handle)
    with core.execution_context(snap):
        result = agent_model.complete(MESSAGES, [TOOL])
    assert len(seen) == 1 and result['calls'][0]['name'] == 'connection_status' and result['calls'][0]['arguments'] == {'status': 'ready'}


def test_streamed_answers_with_responses_arrive_in_one_piece(system, monkeypatch):
    value = body('chat', 'openai-compatible', max_output_tokens=256, context_limit=32768)
    value['connection']['chat_api'] = 'responses'
    snap = snapshot(system, register(system, value))
    cloud_transport(monkeypatch, lambda req: httpx.Response(200, json=answer([{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Ready.'}]}])))
    tokens = []
    with core.execution_context(snap):
        result = agent_model.complete(MESSAGES, [], on_token=tokens.append)
    assert result['text'] == 'Ready.' and tokens == ['', 'Ready.']
