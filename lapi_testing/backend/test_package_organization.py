"""Import compatibility and provider dispatch protect saved model integrations."""
import importlib
import pytest
from lapi_app.lapi_models import provider_registry
from lapi_app.lapi_models.validation import ConnectionError


@pytest.mark.parametrize('old,new',[
    ('agent_graph','lapi_agent.agent_graph'),
    ('agent_model','lapi_agent.agent_model'),
    ('agent_workspace','lapi_agent.agent_workspace'),
    ('chat_agent','lapi_agent.chat_agent'),
    ('token_usage','lapi_agent.token_usage'),
    ('model_connections','lapi_models.connection'),
    ('model_registration','lapi_models.registration'),
    ('model_parameters','lapi_models.parameters'),
    ('ollama_provider','lapi_models.providers.lapi_local.ollama'),
    ('oci_models','lapi_models.providers.lapi_oci.enterprise'),
])
def test_legacy_imports_resolve_to_the_same_module(old,new):
    assert importlib.import_module('lapi_app.'+old) is importlib.import_module('lapi_app.'+new)


@pytest.mark.parametrize('protocol,endpoint,suffix',[
    ('openai-compatible','https://api.openai.com/v1','lapi_openai.adapter'),
    ('openai-compatible','https://generativelanguage.googleapis.com/v1beta/openai','lapi_gcp.gemini'),
    ('anthropic','https://api.anthropic.com/v1','lapi_anthropic.native'),
    ('azure-openai','https://example.openai.azure.com/openai/v1','lapi_azure.adapter'),
    ('vertex','https://aiplatform.googleapis.com','lapi_gcp.vertex'),
    ('bedrock','https://bedrock-runtime.us-east-1.amazonaws.com','lapi_aws.bedrock'),
    ('oci','https://inference.generativeai.us-chicago-1.oci.oraclecloud.com','lapi_oci.native'),
])
def test_provider_selection_is_explicit_and_does_not_load_cloud_sdks(monkeypatch,protocol,endpoint,suffix):
    import builtins
    original=builtins.__import__
    def restricted(name,*args,**kwargs):
        if name.split('.')[0] in ('boto3','google','oci'):
            raise AssertionError('Provider selection attempted to load '+name)
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',restricted)
    selected=provider_registry.provider({'protocol':protocol,'endpoint':endpoint})
    assert selected.__name__.endswith(suffix)
    assert callable(selected.generate) and callable(selected.embed)


def test_unknown_protocol_cannot_become_an_import_path():
    with pytest.raises(ConnectionError,match='supported connection protocol'):
        provider_registry.provider({'protocol':'os.system','endpoint':'https://example.com'})


def test_legacy_registry_cli_still_exposes_the_operator_command():
    import subprocess,sys
    result=subprocess.run([sys.executable,'-m','lapi_app.model_registry','--help'],
                          capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert '--embedding' in result.stdout and '--apply' in result.stdout
