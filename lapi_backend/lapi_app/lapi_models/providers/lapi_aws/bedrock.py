from ...validation import ConnectionError
from ....lapi_agent import token_usage
import json
from .agent import payload as agent_payload, complete as agent_complete, mark_cache

def client(connection):
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise ConnectionError('Install lapi_backend/requirements-models.txt for native cloud protocols.')
    kwargs = {}
    if connection.c['auth_mode'] == 'aws_keys':
        kwargs = {'aws_access_key_id': connection.secret['access_key_id'], 'aws_secret_access_key': connection.secret['secret_access_key']}
        if connection.secret.get('session_token'):
            kwargs['aws_session_token'] = connection.secret['session_token']
    return boto3.client('bedrock-runtime', region_name=connection.c['region'], endpoint_url=connection.c['endpoint'],
        config=Config(connect_timeout=min(10, connection.timeout), read_timeout=connection.timeout, retries={'total_max_attempts': 1}, proxies={}), **kwargs)


def generate(connection, instruction, text, schema, output_tokens, extra):
    data = connection.bedrock().converse(modelId=connection.model, system=[{'text': instruction}], messages=[{'role': 'user', 'content': [{'text': text}]}], inferenceConfig={'maxTokens': output_tokens, **extra})
    token_usage.report(data, 'bedrock')
    if data.get('stopReason') != 'end_turn':
        raise ConnectionError('Model returned an incomplete or refused response.')
    result = '\n'.join(x['text'] for x in data['output']['message']['content'] if 'text' in x)
    return result


def report_embedding(response, data, query):
    # Titan returns inputTextTokenCount; every InvokeModel response carries the
    # billed input count in X-Amzn-Bedrock-Input-Token-Count.
    tokens = data.get('inputTextTokenCount') if isinstance(data, dict) else None
    if not isinstance(tokens, int) or isinstance(tokens, bool):
        try:
            headers = response['ResponseMetadata']['HTTPHeaders']
            raw = str(headers.get('x-amzn-bedrock-input-token-count', ''))
        except Exception:
            raw = ''
        tokens = int(raw) if raw.isdecimal() else None
    token_usage.report({'usage': {'inputTokens': tokens, 'outputTokens': 0}} if tokens is not None else {}, 'bedrock', embedding=True, query=query)


def embed(connection, texts, query, dim, extra):
    client = connection.bedrock()
    fmt = connection.c['embedding_format']
    if fmt == 'titan':
        vectors = []
        for text in texts:
            payload = {'inputText': text, **extra, **({'dimensions': dim} if dim else {})}
            response = client.invoke_model(modelId=connection.model, body=json.dumps(payload), contentType='application/json', accept='application/json')
            data = json.loads(response['body'].read())
            report_embedding(response, data, query)
            vectors.append(data['embedding'])
    else:
        payload = {'texts': texts, 'input_type': 'search_query' if query else 'search_document', 'truncate': 'NONE'}
        if fmt == 'cohere-v4':
            payload['embedding_types'] = ['float']
            if dim:
                payload['output_dimension'] = dim
        response = client.invoke_model(modelId=connection.model, body=json.dumps(payload), contentType='application/json', accept='application/json')
        data = json.loads(response['body'].read())
        report_embedding(response, data, query)
        vectors = data['embeddings']['float'] if isinstance(data['embeddings'], dict) else data['embeddings']
    return vectors
