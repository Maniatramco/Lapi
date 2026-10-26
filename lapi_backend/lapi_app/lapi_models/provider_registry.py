"""Fixed provider dispatch; saved protocol IDs and endpoints remain stable."""
from importlib import import_module
from urllib.parse import urlsplit

REGISTRY = {
    'ollama': ('lapi_local.native', ('none',)),
    'openai-compatible': ('lapi_openai.adapter', ('api_key', 'bearer_token')),
    'azure-openai': ('lapi_azure.adapter', ('api_key', 'bearer_token')),
    'anthropic': ('lapi_anthropic.native', ('api_key',)),
    'bedrock': ('lapi_aws.bedrock', ('aws_keys', 'server_identity')),
    'vertex': ('lapi_gcp.vertex', ('service_account', 'server_identity', 'bearer_token')),
    'oci': ('lapi_oci.native', ('oci_credentials', 'server_identity', 'config_profile')),
}
PROTOCOLS = tuple(REGISTRY)
AUTH_MODES = {name: value[1] for name, value in REGISTRY.items()}


def provider(connection):
    from .validation import ConnectionError
    protocol = connection['protocol']
    if protocol not in REGISTRY:
        raise ConnectionError('Choose a supported connection protocol.')
    module = REGISTRY[protocol][0]
    if protocol == 'openai-compatible' and urlsplit(connection['endpoint']).hostname == 'generativelanguage.googleapis.com':
        module = 'lapi_gcp.gemini'
    return import_module('.providers.' + module, __package__)
