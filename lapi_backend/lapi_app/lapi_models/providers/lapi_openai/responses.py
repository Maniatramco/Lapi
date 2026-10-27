"""OpenAI Responses API (/v1/responses), chosen per model in Model Registration.

Lapi builds Chat Completions payloads and reads Chat Completions replies
everywhere. For a connection whose chat_api is 'responses', `request()` turns
the payload into a Responses request and `reply()` turns the answer back, so
tool steps, chat, extraction and OCR keep their existing code. Responses accepts
function tools together with reasoning, which some models refuse on Chat
Completions. Requests are sent with store=false: OpenAI keeps no copy.
"""
import json

CHAT_APIS = ('chat_completions', 'responses')
RESPONSES_PROTOCOLS = ('openai-compatible', 'azure-openai')
# Chat Completions fields that have no Responses equivalent; they are not sent.
UNSUPPORTED = ('seed', 'stop', 'frequency_penalty', 'presence_penalty', 'n', 'logprobs', 'top_logprobs', 'stream_options')
PASSED = ('temperature', 'top_p', 'parallel_tool_calls', 'prompt_cache_key', 'user', 'metadata', 'stream')


def uses_responses(connection):
    c = getattr(connection, 'c', connection) or {}
    return c.get('protocol') in RESPONSES_PROTOCOLS and c.get('chat_api') == 'responses'


def _text(content):
    if isinstance(content, list):
        return ''.join(part.get('text', '') for part in content if isinstance(part, dict))
    return content or ''


def _parts(content):
    """Chat content parts (text, image_url) as Responses input parts."""
    if not isinstance(content, list):
        return content or ''
    parts = []
    for part in content:
        kind = part.get('type')
        if kind == 'text':
            parts.append({'type': 'input_text', 'text': part.get('text', '')})
        elif kind == 'image_url':
            image = part.get('image_url') or {}
            value = {'type': 'input_image', 'image_url': image.get('url', '') if isinstance(image, dict) else image}
            if isinstance(image, dict) and image.get('detail'):
                value['detail'] = image['detail']
            parts.append(value)
    return parts


def _tool(tool):
    function = tool.get('function') or {}
    return {'type': 'function', 'name': function['name'], 'description': function.get('description', ''),
            'parameters': function.get('parameters') or {'type': 'object', 'properties': {}},
            'strict': bool(function.get('strict', False))}


def request(payload):
    """A Chat Completions payload as a Responses request."""
    body = {'model': payload['model'], 'input': [], 'store': False}
    for message in payload.get('messages') or []:
        role = message.get('role')
        if role == 'tool':
            body['input'].append({'type': 'function_call_output', 'call_id': message['tool_call_id'],
                                  'output': _text(message.get('content'))})
        elif role == 'assistant':
            text = _text(message.get('content'))
            if text:
                body['input'].append({'role': 'assistant', 'content': text})
            for call in message.get('tool_calls') or []:
                arguments = call['function']['arguments']
                body['input'].append({'type': 'function_call', 'call_id': call['id'], 'name': call['function']['name'],
                                      'arguments': arguments if isinstance(arguments, str) else json.dumps(arguments)})
        else:
            body['input'].append({'role': role, 'content': _parts(message.get('content'))})
    if payload.get('tools'):
        body['tools'] = [_tool(tool) for tool in payload['tools']]
    choice = payload.get('tool_choice')
    if isinstance(choice, dict) and choice.get('type') == 'function':
        body['tool_choice'] = {'type': 'function', 'name': choice['function']['name']}
    elif choice is not None:
        body['tool_choice'] = choice
    limit = payload.get('max_completion_tokens', payload.get('max_tokens'))
    if limit is not None:
        body['max_output_tokens'] = limit
    if payload.get('reasoning_effort'):
        body['reasoning'] = {'effort': payload['reasoning_effort']}
    response_format = payload.get('response_format') or {}
    if response_format.get('type') == 'json_schema':
        schema = response_format['json_schema']
        body['text'] = {'format': {'type': 'json_schema', 'name': schema.get('name', 'response'),
                                   'schema': schema['schema'], 'strict': bool(schema.get('strict', False))}}
    elif response_format.get('type') == 'json_object':
        body['text'] = {'format': {'type': 'json_object'}}
    body.update({key: payload[key] for key in PASSED if key in payload})
    return body


def reply(data):
    """A Responses answer in the Chat Completions shape Lapi reads."""
    if not isinstance(data, dict):
        raise ValueError('Invalid Responses API answer')
    text, calls, refused = [], [], False
    for item in data.get('output') or []:
        kind = item.get('type')
        if kind == 'message':
            for part in item.get('content') or []:
                if part.get('type') == 'output_text':
                    text.append(part.get('text', ''))
                elif part.get('type') == 'refusal':
                    refused = True
        elif kind == 'function_call':
            calls.append({'id': item.get('call_id') or item.get('id'), 'type': 'function',
                          'function': {'name': item['name'], 'arguments': item.get('arguments') or '{}'}})
    status = data.get('status')
    if status == 'incomplete':
        finish = 'length'
    elif refused:
        finish = 'content_filter'
    elif calls:
        finish = 'tool_calls'
    elif status in (None, 'completed'):
        finish = 'stop'
    else:
        finish = status
    message = {'role': 'assistant', 'content': ''.join(text) or None}
    if calls:
        message['tool_calls'] = calls
    usage = data.get('usage') or {}
    converted = {'prompt_tokens': usage.get('input_tokens', 0), 'completion_tokens': usage.get('output_tokens', 0),
                 'total_tokens': usage.get('total_tokens', usage.get('input_tokens', 0) + usage.get('output_tokens', 0))}
    cached = (usage.get('input_tokens_details') or {}).get('cached_tokens')
    reasoning = (usage.get('output_tokens_details') or {}).get('reasoning_tokens')
    if cached is not None:
        converted['prompt_tokens_details'] = {'cached_tokens': cached}
    if reasoning is not None:
        converted['completion_tokens_details'] = {'reasoning_tokens': reasoning}
    return {'id': data.get('id'), 'model': data.get('model'), 'usage': converted,
            'choices': [{'index': 0, 'finish_reason': finish, 'message': message}]}
