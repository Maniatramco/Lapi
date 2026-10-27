"""A failed registration test explains the provider's reason, never the credential;
normal model calls never show provider error text, which can echo private requests."""
import httpx
import pytest
from lapi_app.lapi_models import connection
from lapi_app.lapi_models.connection import ModelConnection, explaining_provider_errors, provider_reason
from lapi_app.lapi_models.validation import ConnectionError

KEY = 'sk-proj-' + 'A1b2C3d4' * 6


def reply(status, body):
    return httpx.Response(status, json=body)


def test_openai_reason_is_shown_on_one_line():
    body = {'error': {'message': "Unsupported value: 'temperature' does not support 0.2 with this model.\nOnly the default (1) value is supported.",
                      'type': 'invalid_request_error', 'param': 'temperature', 'code': 'unsupported_value'}}
    assert provider_reason(reply(400, body)) == ("Unsupported value: 'temperature' does not support 0.2 with this model. "
                                                 "Only the default (1) value is supported")


def test_keys_and_key_like_text_are_never_shown():
    body = {'error': {'message': f'Incorrect API key provided: {KEY}. Bearer {KEY} sk-abcdefghijklmnop'}}
    reason = provider_reason(reply(401, body), {'api_key': KEY})
    assert KEY not in reason and 'sk-abc' not in reason and 'Bearer sk' not in reason
    assert reason.startswith('Incorrect API key provided: [redacted]')


def test_other_formats_and_missing_reasons():
    assert provider_reason(reply(400, {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'max_tokens: too large'}})) == 'max_tokens: too large'
    assert provider_reason(reply(422, {'detail': 'Unknown model'})) == 'Unknown model'
    assert provider_reason(reply(500, {'error': {}})) == ''
    assert provider_reason(httpx.Response(502, text='<html>Bad gateway</html>')) == ''
    long = provider_reason(reply(400, {'error': {'message': 'x ' * 400}}))
    assert len(long) <= 301 and long.endswith('…')


def test_reason_only_while_testing_a_registration(monkeypatch):
    def handler(request):
        assert request.headers['authorization'] == 'Bearer ' + KEY
        return reply(400, {'error': {'message': "This model is only supported in v1/responses and not in v1/chat/completions."}})
    real = httpx.Client
    monkeypatch.setattr(connection.httpx, 'Client', lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    probe = ModelConnection.__new__(ModelConnection)
    probe.c = {'protocol': 'openai-compatible', 'auth_mode': 'api_key', 'endpoint': 'https://api.openai.com/v1'}
    probe.secret = {'api_key': KEY}
    probe.timeout = 5
    with explaining_provider_errors(), pytest.raises(ConnectionError) as error:
        probe.post('/chat/completions', {'model': 'gpt-6.1-terra'})
    message = str(error.value)
    assert message.startswith('Model request failed (HTTP 400): This model is only supported in v1/responses')
    assert KEY not in message
    with pytest.raises(ConnectionError) as error:
        probe.post('/chat/completions', {'model': 'gpt-6.1-terra'})
    assert str(error.value) == 'Model request failed (HTTP 400). Check credentials, model access, quota, and protocol.'
