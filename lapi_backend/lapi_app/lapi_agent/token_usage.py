"""Provider-reported token usage: one record per model call, never an estimate.

Two independent collectors share the same call records:

* ``collect()`` gathers the calls of one Agent answer turn for ``summary()``
  (the per-answer token line). It never writes to the database.
* ``scope(owner=..., dataset_id=..., conversation_id=..., job_id=..., stage=...)``
  attributes every call made inside it to a user, dataset, conversation or job
  and persists them to ``lapi_token_usage`` when the outermost scope exits
  (or earlier through ``flush()``). Persistence is best effort: a database
  failure is logged and never fails the answer or the job.

Provider adapters call ``attempt()`` before a request and ``record()`` with the
provider response afterwards (or ``record()`` alone). ``pending()`` and
``report()`` let a facade open the call while a provider module reports the
response. ``stage('tool_step')`` labels the calls made inside it.

Counts are normalized so that totals never double count:

* ``input_tokens`` is every input token the provider processed, including cache
  reads and cache writes. OpenAI, Gemini/Vertex and OCI already include cached
  tokens in their prompt count; Claude and Bedrock report cache reads and writes
  separately, so they are added once here and kept in their own fields.
* ``output_tokens`` includes reasoning tokens. OpenAI and Claude already include
  them; Gemini/Vertex report ``thoughtsTokenCount`` separately.

A value the provider did not report stays ``None`` ("Not reported").
"""
import json
import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal, InvalidOperation

_calls = ContextVar('agent_token_usage', default=None)
_scope = ContextVar('lapi_token_usage_scope', default=None)
_stage = ContextVar('lapi_token_usage_stage', default=None)
_pending = ContextVar('lapi_token_usage_pending', default=None)

STAGES = ('prefetch_embedding', 'tool_step', 'final_answer', 'repair', 'optimize',
          'extraction', 'reindex', 'memory', 'chat', 'decisions')
EMBEDDING_STAGES = ('prefetch_embedding', 'reindex')
SCOPE_KEYS = ('owner_id', 'dataset_id', 'conversation_id', 'message_id', 'job_id')
COUNT_KEYS = ('input_tokens', 'cached_input_tokens', 'cache_write_tokens', 'output_tokens', 'reasoning_tokens')
MILLION = Decimal(1000000)
log = logging.getLogger(__name__)


class Scope:
    """Attribution for the calls made inside one ``scope()`` block."""
    def __init__(self, fields, rows, parent=None):
        self.fields = fields
        self.rows = rows
        self.parent = parent


def _clean_stage(value):
    return value if value in STAGES else None


@contextmanager
def collect():
    calls = []
    token = _calls.set(calls)
    try:
        yield calls
    finally:
        _calls.reset(token)


@contextmanager
def scope(*, owner=None, dataset_id=None, conversation_id=None, message_id=None, job_id=None, stage=None, persist=True):
    """Attribute calls made inside this block; the outermost scope persists them on exit.

    Nested scopes inherit and override the outer attribution and share its
    buffer, so a turn or job is written once, after it finishes (including
    when it fails: the tokens were spent either way).
    """
    parent = _scope.get()
    fields = dict(parent.fields) if parent else {key: None for key in SCOPE_KEYS + ('stage',)}
    given = {'owner_id': owner, 'dataset_id': dataset_id, 'conversation_id': conversation_id,
             'message_id': message_id, 'job_id': job_id, 'stage': _clean_stage(stage)}
    fields.update({key: value for key, value in given.items() if value not in (None, '')})
    current = Scope(fields, parent.rows if parent else [], parent)
    token = _scope.set(current)
    try:
        yield current
    finally:
        _scope.reset(token)
        if parent is None and persist:
            flush(current.rows)


@contextmanager
def stage(name):
    """Label the model calls made inside this block, e.g. ``stage('tool_step')``."""
    token = _stage.set(_clean_stage(name))
    try:
        yield
    finally:
        _stage.reset(token)


def annotate(**fields):
    """Set attribution learnt late (e.g. the saved conversation or message id) on every call of this scope."""
    current = _scope.get()
    if current is None:
        return
    values = {('owner_id' if key == 'owner' else key): value for key, value in fields.items()}
    values = {key: value for key, value in values.items() if key in SCOPE_KEYS and value not in (None, '')}
    current.fields.update(values)
    for row in current.rows:
        row.update(values)


def rows():
    """Calls recorded in the active scope (empty outside a scope)."""
    current = _scope.get()
    return list(current.rows) if current else []


def count(value):
    return value if type(value) is int and value >= 0 else None


def _identity(embedding):
    """Registered model id and provider model of the pinned execution, if any."""
    try:
        from .. import core
        execution = core._execution.get()
    except Exception:
        return None, None
    if not isinstance(execution, dict):
        return None, None
    settings = execution.get('settings') or {}
    if embedding:
        selected = execution if execution.get('capability') == 'embedding' else execution.get('embedding_execution')
        selected = selected if isinstance(selected, dict) else {}
        return selected.get('model_id'), selected.get('provider_model') or settings.get('embedding_model')
    if execution.get('capability') == 'embedding':
        return None, settings.get('model')
    return execution.get('model_id'), execution.get('provider_model') or settings.get('model')


def _resolve_stage(explicit, embedding, query, current):
    explicit = _clean_stage(explicit)
    if explicit:
        return explicit
    labelled = _stage.get()
    if embedding:
        if labelled in EMBEDDING_STAGES:
            return labelled
        return 'prefetch_embedding' if query else 'reindex'
    if labelled:
        return labelled
    if current is not None and current.fields.get('stage'):
        return current.fields['stage']
    return 'chat'


def _clean_parameters(parameters):
    if not isinstance(parameters, dict) or not parameters:
        return None
    clean = {}
    for key, value in parameters.items():
        if isinstance(key, str) and (value is None or isinstance(value, (bool, int, float, str))):
            clean[key[:64]] = value[:200] if isinstance(value, str) else value
    return clean or None


def _new_call(stage=None, embedding=False, query=False, model_id=None, provider_model=None, protocol=None, parameters=None, started=True):
    calls = _calls.get()
    current = _scope.get()
    if calls is None and current is None:
        return None
    pinned_id, pinned_model = _identity(embedding)
    call = {'input_tokens': None, 'output_tokens': None, 'cached_input_tokens': None,
            'cache_write_tokens': None, 'reasoning_tokens': None,
            'id': str(uuid.uuid4()), 'created_at': time.time(),
            'stage': _resolve_stage(stage, embedding, query, current),
            'model_id': model_id or pinned_id, 'provider_model': provider_model or pinned_model,
            'protocol': protocol, 'embedding': bool(embedding), 'parameters': _clean_parameters(parameters),
            'latency_ms': None, 'usage': None, 'reported': False,
            '_started': time.monotonic() if started else None}
    if current is not None:
        call.update({key: current.fields.get(key) for key in SCOPE_KEYS})
        current.rows.append(call)
    if calls is not None:
        calls.append(call)
    return call


def attempt(*, stage=None, embedding=False, query=False, model_id=None, provider_model=None, protocol=None, parameters=None):
    """Open one model call before the request; a call never recorded stays "Not reported"."""
    return _new_call(stage, embedding, query, model_id, provider_model, protocol, parameters)


def _numbers(value, depth=0):
    """Provider usage counters only: no content, prompts or identifiers."""
    if not isinstance(value, dict) or depth > 2:
        return None
    result = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            result[key[:64]] = item
        elif isinstance(item, dict):
            nested = _numbers(item, depth + 1)
            if nested:
                result[key[:64]] = nested
    return result or None


def _dict(value):
    return value if isinstance(value, dict) else {}


def parse_usage(response, protocol, embedding=False):
    """Normalize one provider response's usage report (see the module docstring)."""
    data = _dict(response)
    cached = write = reasoning = None
    if protocol == 'ollama':
        raw = {key: data[key] for key in ('prompt_eval_count', 'eval_count') if key in data}
        input_tokens = count(data.get('prompt_eval_count'))
        output_tokens = count(data.get('eval_count'))
    elif protocol == 'bedrock':
        usage = _dict(data.get('usage'))
        raw = usage
        base = count(usage.get('inputTokens'))
        cached = count(usage.get('cacheReadInputTokens', 0))
        write = count(usage.get('cacheWriteInputTokens', 0))
        input_tokens = base + cached + write if None not in (base, cached, write) else None
        output_tokens = count(usage.get('outputTokens'))
    elif protocol == 'anthropic':
        usage = _dict(data.get('usage'))
        raw = usage
        base = count(usage.get('input_tokens'))
        cached = count(usage.get('cache_read_input_tokens', 0))
        write = count(usage.get('cache_creation_input_tokens', 0))
        input_tokens = base + cached + write if None not in (base, cached, write) else None
        output_tokens = count(usage.get('output_tokens'))
    elif protocol == 'vertex':
        usage = _dict(data.get('usageMetadata'))
        raw = usage
        input_tokens = count(usage.get('promptTokenCount'))
        tool_prompt = count(usage.get('toolUsePromptTokenCount', 0))
        if input_tokens is not None and tool_prompt is not None:
            input_tokens += tool_prompt
        cached = count(usage.get('cachedContentTokenCount', 0))
        candidates = count(usage.get('candidatesTokenCount'))
        thoughts = count(usage.get('thoughtsTokenCount', 0))
        reasoning = count(usage.get('thoughtsTokenCount')) if 'thoughtsTokenCount' in usage else None
        output_tokens = candidates + thoughts if candidates is not None and thoughts is not None else None
    else:
        usage = _dict(data.get('usage'))
        raw = usage
        input_tokens = count(usage.get('prompt_tokens', usage.get('input_tokens')))
        output_tokens = count(usage.get('completion_tokens', usage.get('output_tokens')))
        prompt_details = _dict(usage.get('prompt_tokens_details') or usage.get('input_tokens_details'))
        output_details = _dict(usage.get('completion_tokens_details') or usage.get('output_tokens_details'))
        cached = count(prompt_details.get('cached_tokens'))
        reasoning = count(output_details.get('reasoning_tokens'))
    if embedding and input_tokens is not None and output_tokens is None:
        output_tokens = 0
    return {'input_tokens': input_tokens, 'output_tokens': output_tokens, 'cached_input_tokens': cached,
            'cache_write_tokens': write, 'reasoning_tokens': reasoning, 'usage': _numbers(raw),
            'reported': input_tokens is not None and output_tokens is not None}


def record(response, protocol, call=None, *, stage=None, embedding=False, query=False, model_id=None,
           provider_model=None, parameters=None, latency_ms=None):
    """Record one provider response; ``call`` is the record opened by ``attempt()``."""
    if call is None:
        call = _new_call(stage, embedding, query, model_id, provider_model, protocol, parameters, started=False)
        if call is None:
            return None
    else:
        call['protocol'] = call.get('protocol') or protocol
        if parameters and not call.get('parameters'):
            call['parameters'] = _clean_parameters(parameters)
    call.update(parse_usage(response, protocol, embedding or call.get('embedding')))
    if count(latency_ms) is not None:
        call['latency_ms'] = latency_ms
    elif call.get('_started') is not None:
        call['latency_ms'] = max(0, round((time.monotonic() - call['_started']) * 1000))
    return call


@contextmanager
def pending(**fields):
    """Open a call that a provider module fills with ``report()``."""
    call = attempt(**fields)
    token = _pending.set({'call': call, 'filled': False, 'fields': fields})
    try:
        yield call
    finally:
        _pending.reset(token)


def report(response, protocol, **fields):
    """Fill the open ``pending()`` call, or record an additional call (one per provider request)."""
    slot = _pending.get()
    if slot is not None and slot['call'] is not None and not slot['filled']:
        slot['filled'] = True
        return record(response, protocol, slot['call'], **{k: v for k, v in fields.items() if k in ('parameters', 'latency_ms')})
    merged = dict(slot['fields']) if slot else {}
    merged.update(fields)
    merged.pop('protocol', None)
    return record(response, protocol, **{k: v for k, v in merged.items() if k in (
        'stage', 'embedding', 'query', 'model_id', 'provider_model', 'parameters', 'latency_ms')})


# ---------------------------------------------------------------- prices

def decimal(value):
    if value in (None, ''):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def price_public(version):
    """Price version as a dict of decimal strings (per 1M tokens)."""
    if version is None:
        return None
    return {'id': version.id, 'model_id': version.model_id, 'currency': version.currency,
            'input_price': version.input_price, 'cached_input_price': version.cached_input_price,
            'cache_write_price': version.cache_write_price, 'output_price': version.output_price,
            'reasoning_price': version.reasoning_price, 'effective_at': version.effective_at,
            'created_at': version.created_at, 'created_by': version.created_by}


def price_in_force(versions, at):
    """The version an admin had entered and made effective by time ``at``."""
    eligible = [v for v in versions if v.effective_at <= at and (v.created_at or 0) <= at]
    return max(eligible, key=lambda v: (v.effective_at, v.created_at or 0), default=None)


def call_cost(call, price):
    """(status, amount, currency) for one call; amount is an unrounded Decimal.

    cost = uncached input x input price + cache reads x cached price
         + cache writes x cache-write price + output x output price
         + reasoning x (reasoning price, else output price)
    Input and output are normalized totals, so cached input and reasoning are
    subtracted once before pricing and never counted twice. A cached or
    cache-write price that was not entered falls back to the input price.
    """
    if call.get('input_tokens') is None or call.get('output_tokens') is None:
        return 'not_reported', None, None
    if not price:
        return 'price_not_set', None, None
    input_price, output_price = decimal(price.get('input_price')), decimal(price.get('output_price'))
    if input_price is None or output_price is None:
        return 'price_not_set', None, None
    cached_price = decimal(price.get('cached_input_price'))
    write_price = decimal(price.get('cache_write_price'))
    reasoning_price = decimal(price.get('reasoning_price'))
    cached = call.get('cached_input_tokens') or 0
    write = call.get('cache_write_tokens') or 0
    reasoning = call.get('reasoning_tokens') or 0
    uncached = max(call['input_tokens'] - cached - write, 0)
    plain_output = max(call['output_tokens'] - reasoning, 0)
    amount = (Decimal(uncached) * input_price
              + Decimal(cached) * (cached_price if cached_price is not None else input_price)
              + Decimal(write) * (write_price if write_price is not None else input_price)
              + Decimal(plain_output) * output_price
              + Decimal(reasoning) * (reasoning_price if reasoning_price is not None else output_price)) / MILLION
    return 'priced', amount, price.get('currency')


def amount_text(amount):
    """Exact decimal text without exponent; rounding is for display only."""
    text = format(amount.normalize(), 'f') if amount else '0'
    return text


def attach_prices(calls):
    """Pin the price version in force at each call's time (one query per batch)."""
    pending_calls = [c for c in calls if c.get('model_id') and '_price' not in c]
    if not pending_calls:
        return
    try:
        from sqlalchemy import select
        from .. import core
        from ..usage_tables import ModelPrice
        ids = sorted({c['model_id'] for c in pending_calls})
        with core.Session() as session:
            versions = list(session.scalars(select(ModelPrice).where(ModelPrice.model_id.in_(ids))))
        by_model = {}
        for version in versions:
            by_model.setdefault(version.model_id, []).append(version)
        for call in pending_calls:
            version = price_in_force(by_model.get(call['model_id'], []), call.get('created_at') or time.time())
            call['price_version_id'] = version.id if version else None
            call['_price'] = price_public(version)
    except Exception as exc:  # Prices are display data; never fail an answer.
        log.warning('Token prices could not be read (%s)', type(exc).__name__)


def cost_summary(items):
    """Totals per currency (never added across currencies) and excluded call counts."""
    totals, priced, unpriced, unreported = {}, 0, 0, 0
    for status, amount, currency in items:
        if status == 'priced':
            priced += 1
            totals[currency] = totals.get(currency, Decimal(0)) + amount
        elif status == 'price_not_set':
            unpriced += 1
        else:
            unreported += 1
    calls = priced + unpriced + unreported
    status = ('no_model_calls' if not calls else 'not_reported' if unreported == calls
              else 'price_not_set' if not priced else 'complete' if priced == calls else 'partial')
    return {'approximate': True, 'status': status,
            'totals': [{'currency': key, 'amount': amount_text(value)} for key, value in sorted(totals.items())],
            'priced_calls': priced, 'price_not_set_calls': unpriced, 'not_reported_calls': unreported,
            'excluded_calls': unpriced + unreported}


def _step(call):
    status, amount, currency = call_cost(call, call.get('_price'))
    return {'stage': call.get('stage') or 'chat', 'model_id': call.get('model_id'),
            'provider_model': call.get('provider_model'), 'protocol': call.get('protocol'),
            'embedding': bool(call.get('embedding')),
            **{key: call.get(key) for key in COUNT_KEYS},
            'latency_ms': call.get('latency_ms'),
            'reported': call.get('input_tokens') is not None and call.get('output_tokens') is not None,
            'parameters': call.get('parameters'), 'price_version_id': call.get('price_version_id'),
            'cost': {'status': status, 'amount': amount_text(amount) if amount is not None else None, 'currency': currency}}


def summary(calls):
    def total(key):
        values = [call[key] for call in calls if call.get(key) is not None]
        return sum(values) if values else (0 if not calls else None)
    reported = sum(call['input_tokens'] is not None and call['output_tokens'] is not None for call in calls)
    attach_prices(calls)
    steps = [_step(call) for call in calls]
    costs = [(step['cost']['status'], decimal(step['cost']['amount']), step['cost']['currency']) for step in steps]
    return {'scope': 'answer_turn', 'input_tokens': total('input_tokens'),
            'output_tokens': total('output_tokens'), 'model_calls': len(calls),
            'reported_calls': reported, 'complete': reported == len(calls),
            'source': 'provider' if calls else 'no_model_calls',
            'cached_input_tokens': total('cached_input_tokens'), 'cache_write_tokens': total('cache_write_tokens'),
            'reasoning_tokens': total('reasoning_tokens'),
            'not_reported_calls': len(calls) - reported,
            'steps': steps, 'cost': cost_summary(costs)}


# ---------------------------------------------------------------- persistence

def _row(call):
    from ..usage_tables import TokenUsage
    def text(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:8000] if value else None
    return TokenUsage(
        id=call.get('id') or str(uuid.uuid4()), created_at=call.get('created_at') or time.time(),
        owner_id=call.get('owner_id'), dataset_id=call.get('dataset_id') or None,
        conversation_id=call.get('conversation_id'), message_id=call.get('message_id'), job_id=call.get('job_id'),
        model_id=call.get('model_id'), provider_model=(call.get('provider_model') or None) and str(call['provider_model'])[:250],
        protocol=(call.get('protocol') or None) and str(call['protocol'])[:40], stage=call.get('stage') or 'chat',
        **{key: call.get(key) for key in COUNT_KEYS}, latency_ms=call.get('latency_ms'),
        reported=call.get('input_tokens') is not None and call.get('output_tokens') is not None,
        parameters_json=text(call.get('parameters')), usage_json=text(call.get('usage')),
        price_version_id=call.get('price_version_id'))


def flush(calls=None):
    """Persist calls not yet saved; returns how many were written. Never raises."""
    if calls is None:
        current = _scope.get()
        calls = current.rows if current else []
    todo = [call for call in calls if not call.get('_persisted')]
    if not todo:
        return 0
    try:
        from .. import core
        attach_prices(todo)
        with core.Session.begin() as session:
            for call in todo:
                session.add(_row(call))
        for call in todo:
            call['_persisted'] = True
        return len(todo)
    except Exception as exc:  # Accounting must never fail an answer or a job.
        log.warning('Token usage could not be saved (%s)', type(exc).__name__)
        return 0
