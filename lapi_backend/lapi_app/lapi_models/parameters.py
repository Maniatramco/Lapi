"""Validated per-model inference settings; transport and prompt fields stay owned by Lapi.

Model Registration stores two layers of sampling values for Chat and Extraction
models, and Lapi keeps one documented table of its own defaults:

* ``stage_parameters[stage]`` -- values for one stage (``chat``, ``tool_step``,
  ``extraction`` or ``optimize``);
* ``extra_parameters`` -- model-wide values;
* ``LAPI_DEFAULTS`` -- documented Lapi defaults, used only for a field that the
  admin left on default.

``for_stage(cfg, stage)`` resolves a field in that order (stage, then model,
then the Lapi default) and returns exactly what is sent. A stored ``None``
means "Use provider default": nothing is sent for that field and the Lapi
default does not apply either. A value the admin sets always wins.
"""
import copy
import json
import math
import re
from contextlib import contextmanager
from contextvars import ContextVar
from .. import runtime_config


class ParameterError(ValueError):
    pass


STAGES = ('chat', 'tool_step', 'extraction', 'optimize')
STAGE_LABELS = {
    'chat': ('Chat answer', 'The answer the user reads, written from the gathered evidence.'),
    'tool_step': ('Tool steps', 'Steps where the model picks tools and their arguments.'),
    'extraction': ('Extraction', 'Structured extraction of template fields from documents.'),
    'optimize': ('Optimize', 'Rewriting prompts and instructions with /optimize.'),
}
# Stages shown for each registration category. The API accepts any stage for a
# Chat or Extraction model, so a legacy Chat + Extraction model keeps both.
CATEGORY_STAGES = {'chat': ('chat', 'tool_step', 'optimize'), 'extraction': ('extraction',), 'embedding': ()}
# Suggested starting values, shown in the form. They are never applied unless
# the admin chooses them.
SUGGESTED = {
    'chat': {'temperature': 0.2},
    'tool_step': {'temperature': 0, 'seed': 42},
    'extraction': {'temperature': 0},
    'optimize': {'temperature': 0.3},
}

_STOP = ('stop', 'stop_sequences', 'stopSequences')

# One spec per wire key: type, range, provider default (when the provider
# documents one) and one line of help. Ranges are the validation ranges.
FIELD_SPECS = {
    'temperature': {'label': 'Temperature', 'type': 'number', 'min': 0, 'max': 2, 'step': 0.05,
        'help': 'Randomness of the output. Lower is more focused and repeatable.'},
    'top_p': {'label': 'Top P', 'type': 'number', 'min': 0, 'max': 1, 'step': 0.05,
        'help': 'Nucleus sampling: keep the most likely tokens up to this total probability.'},
    'topP': {'label': 'Top P', 'type': 'number', 'min': 0, 'max': 1, 'step': 0.05,
        'help': 'Nucleus sampling: keep the most likely tokens up to this total probability.'},
    'min_p': {'label': 'Min P', 'type': 'number', 'min': 0, 'max': 1, 'step': 0.01,
        'help': 'Drop tokens less likely than this fraction of the most likely token.'},
    'top_k': {'label': 'Top K', 'type': 'integer', 'min': 0, 'max': 4096, 'step': 1,
        'help': 'Sample only from this many most likely tokens. 0 turns the limit off.'},
    'topK': {'label': 'Top K', 'type': 'integer', 'min': 0, 'max': 4096, 'step': 1,
        'help': 'Sample only from this many most likely tokens.'},
    'repeat_penalty': {'label': 'Repeat penalty', 'type': 'number', 'min': 0, 'max': 2, 'step': 0.05,
        'help': 'Penalty for repeating recent tokens. 1 means no penalty.'},
    'repeat_last_n': {'label': 'Repeat window', 'type': 'integer', 'min': 0, 'max': 4096, 'step': 1,
        'help': 'How many recent tokens the repeat penalty looks back over.'},
    'frequency_penalty': {'label': 'Frequency penalty', 'type': 'number', 'min': -2, 'max': 2, 'step': 0.1,
        'help': 'Positive values discourage tokens that already appeared often.'},
    'presence_penalty': {'label': 'Presence penalty', 'type': 'number', 'min': -2, 'max': 2, 'step': 0.1,
        'help': 'Positive values encourage new topics.'},
    'frequencyPenalty': {'label': 'Frequency penalty', 'type': 'number', 'min': -2, 'max': 2, 'step': 0.1,
        'help': 'Positive values discourage tokens that already appeared often.'},
    'presencePenalty': {'label': 'Presence penalty', 'type': 'number', 'min': -2, 'max': 2, 'step': 0.1,
        'help': 'Positive values encourage new topics.'},
    'seed': {'label': 'Seed', 'type': 'integer', 'min': 0, 'max': 2147483647, 'step': 1,
        'help': 'Fixed seed for more repeatable sampling, where the model supports it.'},
    'stop': {'label': 'Stop sequences', 'type': 'string_list', 'max_items': 16, 'max_length': 256,
        'help': 'Generation stops at any of these strings. One per line.'},
    'stop_sequences': {'label': 'Stop sequences', 'type': 'string_list', 'max_items': 16, 'max_length': 256,
        'help': 'Generation stops at any of these strings. One per line.'},
    'stopSequences': {'label': 'Stop sequences', 'type': 'string_list', 'max_items': 16, 'max_length': 256,
        'help': 'Generation stops at any of these strings. One per line.'},
    'reasoning_effort': {'label': 'Reasoning effort', 'type': 'select', 'options': ['none', 'minimal', 'low', 'medium', 'high'],
        'help': 'Reasoning models only: how much the model thinks before answering.'},
    'keep_alive': {'label': 'Keep loaded', 'type': 'duration', 'pattern': r'(?:0|[0-9]{1,3}(?:ms|s|m|h))',
        'help': 'How long Ollama keeps the model in memory after a request, for example 5m. 0 unloads at once.'},
    'normalize': {'label': 'Normalize vectors', 'type': 'boolean',
        'help': 'Ask Bedrock Titan to return unit-length vectors.'},
    'encoding_format': {'label': 'Encoding format', 'type': 'select', 'options': ['float'],
        'help': 'Vector encoding returned by the service. Lapi reads float vectors.'},
}

# Documented provider defaults (what the provider uses when nothing is sent).
# None means the provider sets it per model.
PROVIDER_DEFAULTS = {
    'ollama': {'temperature': 0.8, 'top_p': 0.9, 'top_k': 40, 'min_p': 0.0, 'repeat_penalty': 1.1, 'repeat_last_n': 64, 'keep_alive': '5m'},
    'openai-compatible': {'temperature': 1, 'top_p': 1, 'frequency_penalty': 0, 'presence_penalty': 0},
    'azure-openai': {'temperature': 1, 'top_p': 1, 'frequency_penalty': 0, 'presence_penalty': 0},
}

# Documented Lapi defaults. These replace values that used to be hard-coded in
# the Agent, chat, Ollama and OCR code. They are sent only for a field left on
# default; the admin's stage or model value always wins, and "Use provider
# default" (None) removes them. '*' applies to every stage of that protocol.
LAPI_DEFAULTS = {
    'ollama': {
        # Former Ollama adapter sampling (0.7 / 0.8 / 20, repeat 1.1, seed 42).
        '*': {'temperature': 0.7, 'top_p': 0.8, 'top_k': 20, 'repeat_penalty': 1.1, 'seed': 42},
        # Former temperature 0 and seed 42 in agent_model and chat_agent.
        'chat': {'temperature': 0},
        'tool_step': {'temperature': 0},
        # Former extraction temperature 0.2 in the Ollama adapter.
        'extraction': {'temperature': 0.2},
    },
    'openai-compatible': {
        # Former GPT-4o strict tool-choice temperature 0 in agent_model.
        'tool_step': {'temperature': 0, '_models': ('gpt-4o',)},
    },
    'azure-openai': {
        'tool_step': {'temperature': 0, '_models': ('gpt-4o',)},
    },
}
# Page transcription (OCR) runs at the Extraction stage with these Lapi
# defaults (former hard-coded OCR temperature 0.1).
OCR_DEFAULTS = {'temperature': 0.1}
# Local Ollama OCR is configured by LAPI_OCR_* runtime settings, not by a
# registered model, so these are its fixed documented request options.
OLLAMA_OCR_OPTIONS = {'temperature': 0.1, 'repeat_penalty': 1.1, 'seed': 42}

NO_OVERRIDES = {
    'anthropic': 'Direct Claude does not accept sampling overrides; the model uses its own settings.',
}

_stage = ContextVar('lapi_parameter_stage', default=None)
_effective = ContextVar('lapi_effective_parameters', default=None)


def supported_parameters(protocol, category, connection=None, schema=False):
    """Keys accepted for this provider and role; with schema=True, the form schema."""
    if schema:
        return parameter_schema(protocol, category, connection)
    if category == 'embedding':
        if protocol == 'ollama': return ('keep_alive',)
        if protocol in ('openai-compatible', 'azure-openai'): return ('encoding_format',)
        if protocol == 'bedrock' and (connection or {}).get('embedding_format', 'titan') == 'titan': return ('normalize',)
        return ()
    return {
        'ollama': ('temperature', 'top_p', 'top_k', 'min_p', 'repeat_penalty', 'repeat_last_n', 'seed', 'stop', 'keep_alive'),
        'openai-compatible': ('temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'seed', 'stop', 'reasoning_effort'),
        'azure-openai': ('temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'seed', 'stop', 'reasoning_effort'),
        'anthropic': (),  # Messages API 2026-10-21 removes sampling overrides.
        'bedrock': ('temperature', 'topP', 'stopSequences'),
        'vertex': ('temperature', 'topP', 'topK', 'stopSequences', 'seed', 'presencePenalty', 'frequencyPenalty'),
        'oci': ('temperature', 'top_p', 'top_k', 'frequency_penalty', 'presence_penalty', 'seed', 'stop') if (connection or {}).get('chat_format') != 'cohere' else ('temperature', 'top_p', 'top_k', 'frequency_penalty', 'presence_penalty', 'seed', 'stop_sequences'),
    }.get(protocol, ())


def field_spec(key, protocol):
    spec = copy.deepcopy(FIELD_SPECS[key])
    if key == 'temperature' and protocol == 'bedrock':
        spec['max'] = 1
    return spec


def lapi_defaults(protocol, stage, model=None, purpose=None):
    """Documented Lapi defaults for one protocol and stage (before any admin value)."""
    table = LAPI_DEFAULTS.get(protocol, {})
    values = {}
    for layer in (table.get('*', {}), table.get(stage, {})):
        models = layer.get('_models')
        if models and not str(model or '').startswith(models):
            continue
        values.update({k: v for k, v in layer.items() if not k.startswith('_')})
    if purpose == 'ocr':
        values.update(OCR_DEFAULTS)
    allowed = supported_parameters(protocol, 'extraction' if stage == 'extraction' else 'chat')
    return {k: v for k, v in values.items() if k in allowed}


def parameter_schema(protocol, category, connection=None, model=None):
    """Form schema for one provider and role: fields, stages and their defaults."""
    keys = supported_parameters(protocol, category, connection)
    provider_defaults = PROVIDER_DEFAULTS.get(protocol, {})
    fields = []
    for key in keys:
        spec = field_spec(key, protocol) | {'key': key}
        spec['default'] = provider_defaults.get(key)
        spec['default_note'] = 'Provider default: ' + json.dumps(provider_defaults[key]) if key in provider_defaults else 'Provider default: set by the model.'
        fields.append(spec)
    stages = []
    for stage in CATEGORY_STAGES.get(category, ()):
        label, description = STAGE_LABELS[stage]
        stages.append({'key': stage, 'label': label, 'help': description,
            'lapi_defaults': lapi_defaults(protocol, stage, model),
            'suggested': {k: v for k, v in SUGGESTED[stage].items() if k in keys}})
    notice = None
    if not keys:
        notice = NO_OVERRIDES.get(protocol) or ('This provider has no additional embedding parameters. Use the token and dimensions fields.' if category == 'embedding' else 'This provider accepts no sampling overrides.')
    return {'protocol': protocol, 'category': category, 'accepts_overrides': bool(keys), 'notice': notice,
        'fields': fields, 'stages': stages,
        'model_lapi_defaults': {} if category == 'embedding' else lapi_defaults(protocol, 'extraction' if category == 'extraction' else 'chat', model),
        'order': ['stage', 'model', 'lapi_default', 'provider_default']}


def _valid(key, value, protocol):
    spec = field_spec(key, protocol)
    kind = spec['type']
    if kind == 'string_list':
        return isinstance(value, list) and len(value) <= spec['max_items'] and all(isinstance(v, str) and 0 < len(v) <= spec['max_length'] for v in value)
    if kind == 'duration':
        return isinstance(value, str) and bool(re.fullmatch(spec['pattern'], value))
    if kind == 'boolean':
        return isinstance(value, bool)
    if kind == 'select':
        return value in spec['options']
    valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if kind == 'integer':
        valid = valid and isinstance(value, int)
    return valid and spec['min'] <= value <= spec['max']


def validate_parameters(parameters, protocol, category, connection=None, keep_null=False):
    """Validate one layer of values. None means "Use provider default".

    Returned values are safe to send; None entries are dropped unless
    keep_null=True (registration storage keeps them so the choice persists).
    """
    if not isinstance(parameters, dict) or len(parameters) > 20:
        raise ParameterError('Extra parameters must be a JSON object with at most 20 entries.')
    allowed = supported_parameters(protocol, category, connection)
    # Do not interpolate submitted names or values into errors (could contain credentials).
    if any(key not in allowed for key in parameters):
        raise ParameterError('Unsupported extra parameter for this model. Supported keys: ' + (', '.join(allowed) or 'none; use the token and dimensions fields') + '.')
    for key, value in parameters.items():
        if value is not None and not _valid(key, value, protocol):
            raise ParameterError('Invalid value for extra parameter ' + key + '. Check its type and supported range.')
    return {k: copy.deepcopy(v) for k, v in parameters.items() if keep_null or v is not None}


def validate_stage_parameters(stages, protocol, category, connection=None):
    """Validate per-stage values ({stage: {key: value}}); empty stages are dropped."""
    if stages is None:
        return {}
    if not isinstance(stages, dict) or any(stage not in STAGES for stage in stages):
        raise ParameterError('Stage parameters must use the stages chat, tool_step, extraction or optimize.')
    if category == 'embedding' and any(stages.values()):
        raise ParameterError('Embedding models have no stages; use the model-wide parameters.')
    result = {}
    for stage, values in stages.items():
        checked = validate_parameters(values or {}, protocol, 'extraction' if stage == 'extraction' else 'chat', connection, keep_null=True)
        if checked:
            result[stage] = checked
    return result


@contextmanager
def use_stage(stage):
    """Run model calls in this block with one stage's parameters.

    The agent loop wraps a call in ``with parameters.use_stage('tool_step'):``
    to choose the stage explicitly; it wins over the stage a call site infers.
    """
    if stage not in STAGES:
        raise ParameterError('Unknown parameter stage.')
    token = _stage.set(stage)
    try:
        yield stage
    finally:
        _stage.reset(token)


@contextmanager
def default_stage(stage):
    """Set the stage a call site infers, unless an outer block chose one."""
    if _stage.get() is not None:
        yield _stage.get()
        return
    with use_stage(stage):
        yield stage


def current_stage(inferred='chat'):
    return _stage.get() or inferred


def resolve(cfg, stage, protocol=None, connection=None, purpose=None):
    """Effective parameters for a stage plus where each value came from.

    Order per field: stage value, model-wide value, documented Lapi default.
    None at the stage or model layer means "Use provider default" and stops
    the fallback, so nothing is sent for that field.
    """
    if stage not in STAGES:
        raise ParameterError('Unknown parameter stage.')
    cfg = cfg or {}
    connection = connection if connection is not None else (cfg.get('model_connection') or {})
    protocol = protocol or connection.get('protocol') or cfg.get('model_provider')
    category = 'extraction' if stage == 'extraction' else 'chat'
    allowed = supported_parameters(protocol, category, connection)
    model_wide = validate_parameters(cfg.get('extra_parameters') or {}, protocol, category, connection, keep_null=True)
    staged = validate_parameters((cfg.get('stage_parameters') or {}).get(stage) or {}, protocol, category, connection, keep_null=True)
    defaults = lapi_defaults(protocol, stage, cfg.get('model'), purpose)
    values, sources = {}, {}
    for key in allowed:
        for layer, source in ((staged, 'stage'), (model_wide, 'model'), (defaults, 'lapi_default')):
            if key in layer:
                if layer[key] is None:
                    sources[key] = 'provider_default'
                else:
                    values[key] = copy.deepcopy(layer[key]); sources[key] = source
                break
    return {'stage': stage, 'protocol': protocol, 'parameters': values, 'sources': sources}


def for_stage(cfg, stage, protocol=None, connection=None, purpose=None, record=True):
    """Validated parameters to send for one stage (stage -> model -> Lapi default).

    This is the function model call sites and the agent loop use. The result is
    also stored as the current call's effective parameters (see effective()).
    """
    detail = resolve(cfg, stage, protocol, connection, purpose)
    if record:
        _effective.set(copy.deepcopy(detail))
    return copy.deepcopy(detail['parameters'])


def record_effective(detail):
    _effective.set(copy.deepcopy(detail))


def effective():
    """Parameters actually sent by the latest model call in this context.

    ``{'stage', 'protocol', 'parameters', 'sources'}`` or None. The token-usage
    recorder reads this right after a call to store the settings it used.
    """
    value = _effective.get()
    return copy.deepcopy(value) if value is not None else None


def clear_effective():
    _effective.set(None)


def parameter_changes(old, new):
    """Field-level changes between two {'extra_parameters', 'stage_parameters'} sets."""
    changes = []
    def layer(values, scope):
        return {(scope, k): v for k, v in (values or {}).items()}
    before = layer(old.get('extra_parameters'), 'model')
    after = layer(new.get('extra_parameters'), 'model')
    for stage in STAGES:
        before |= layer((old.get('stage_parameters') or {}).get(stage), stage)
        after |= layer((new.get('stage_parameters') or {}).get(stage), stage)
    for scope, key in sorted(set(before) | set(after)):
        if before.get((scope, key), '__default__') != after.get((scope, key), '__default__'):
            changes.append({'scope': scope, 'key': key,
                'from': before.get((scope, key), '__default__'), 'to': after.get((scope, key), '__default__')})
    for change in changes:
        for side in ('from', 'to'):
            if change[side] == '__default__':
                change[side] = {'mode': 'default'}
            elif change[side] is None:
                change[side] = {'mode': 'provider_default'}
            else:
                change[side] = {'mode': 'custom', 'value': change[side]}
    return changes


def check_budget(cfg, contents, embedding=False, output_tokens=None):
    limit = cfg.get('embedding_context_limit' if embedding else 'context_limit')
    if limit is None: return
    reserved = 0 if embedding else (output_tokens if output_tokens is not None else cfg.get('max_output_tokens', runtime_config.get('LAPI_DEFAULT_MODEL_OUTPUT_TOKENS'))) + runtime_config.get('LAPI_CONTEXT_HEADROOM_TOKENS')
    # Conservative UTF-8 estimate, not a provider-specific tokenizer. Never truncate input.
    needed = (len(json.dumps(contents, ensure_ascii=False).encode('utf-8')) + 1) // 2 + reserved
    if needed > limit:
        label = 'embedding input' if embedding else 'context'
        raise ParameterError(f'Selected content exceeds this model\'s {label} budget ({limit:,} tokens). Estimated requirement: {needed:,} tokens. Choose a smaller scope or change the token limit in Model Registration.')
