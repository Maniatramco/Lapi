"""OpenAI Decisions API (POST /v1/decisions): typed answers instead of generated text.

A Decisions request carries shared evidence (`input`) and 1-400 questions. Each question
is a predicate (probability that a statement is true), a choice (one of the supplied
values, with probabilities and a confidence) or a score. Any question may come back as a
refusal. Lapi uses it only to judge, never to write: whether an answer's cited sentences
are supported by their sources, whether a Dashboard chat question needs knowledge, and
which option a set-up chat answer means.

Decisions is a model use of its own in Model Registration, for OpenAI (api.openai.com)
connections only, with its own workspace Default. Without that Default every caller keeps
its previous behaviour. A failed or refused decision is reported as such; callers never
treat it as a passed check.
"""
from urllib.parse import urlsplit

from .. import core, runtime_config

USE = 'decisions'
DEFAULT_MODEL = 'gpt-6-luna'
PROVIDERS = 'Decisions works with OpenAI connections (api.openai.com) only. Untick Decisions for other providers.'
ALONE = 'Decisions is registered on its own. Save Chat, Extraction and OCR as one model, and Decisions as another.'


class DecisionsError(Exception):
    """The Decisions request could not be made or its answer could not be read."""


def openai_connection(cfg):
    """True for a registered OpenAI-compatible connection to api.openai.com."""
    connection = (cfg or {}).get('model_connection') or {}
    return (cfg.get('model_provider') == 'registered' and connection.get('protocol') == 'openai-compatible'
            and urlsplit(connection.get('endpoint', '')).hostname == 'api.openai.com')


def percent(name):
    return runtime_config.get(name) / 100


def snapshot():
    """The workspace Decisions Default, pinned like a collection's model, or None when unset,
    disabled, archived, untested or no longer an OpenAI connection."""
    from .. import workspace_defaults, dataset_models as routing
    model_id = workspace_defaults.default_id(USE)
    model = routing.model_record(model_id) if model_id else None
    if not model or model.kind != 'model':
        return None
    data = routing.model_data(model)
    if data.get('archived') or not data.get('enabled', True) or USE not in data.get('capabilities', []):
        return None
    if not workspace_defaults.verified(model):
        return None
    profile = routing.owned(data['connection_profile_id'], model.owner, 'config_profile')
    snap = routing.profile_snapshot(profile, data.get('connection_profile_version'))
    if not openai_connection(snap['settings']):
        return None
    snap.update(model_id=model.id, model_name=model.name, provider_model=data['provider_model'], capability=USE)
    snap['settings']['model'] = data['provider_model']
    cfg = core.settings().copy()
    cfg.update({k: snap['settings'][k] for k in routing.MODEL_KEYS if k in snap['settings']})
    snap['settings'] = cfg
    return snap


def _answers(data, questions):
    answers = data.get('answers') if isinstance(data, dict) else None
    if not isinstance(answers, list) or len(answers) != len(questions):
        raise DecisionsError('The Decisions API returned an answer Lapi could not read.')
    out = []
    for question, answer in zip(questions, answers):
        if not isinstance(answer, dict) or answer.get('type') not in ('predicate', 'choice', 'score', 'refusal'):
            raise DecisionsError('The Decisions API returned an answer Lapi could not read.')
        if answer['type'] != 'refusal' and answer['type'] != question['type']:
            raise DecisionsError('The Decisions API answered a different question type.')
        if answer['type'] == 'predicate' and not isinstance(answer.get('probability'), (int, float)):
            raise DecisionsError('The Decisions API returned a predicate without a probability.')
        if answer['type'] == 'choice':
            allowed = [c['value'] for c in question['choices']]
            if answer.get('choice') not in allowed or not isinstance(answer.get('confidence'), (int, float)):
                raise DecisionsError('The Decisions API returned a choice that was not offered.')
        out.append(answer)
    return out


def ask(snap, evidence, questions, cfg=None):
    """Send one Decisions request with the pinned connection; answers come back in question order."""
    from .connection import ModelConnection, ConnectionError
    from ..lapi_agent import token_usage
    if not questions:
        return []
    settings = dict(cfg or snap['settings'])
    settings['timeout'] = min(settings.get('timeout') or 60, runtime_config.get('LAPI_DECISIONS_TIMEOUT'))
    if not openai_connection(settings):
        raise DecisionsError(PROVIDERS)
    body = {'model': snap.get('provider_model') or settings['model'], 'input': evidence, 'questions': questions}
    try:
        with core.execution_context(dict(snap, settings=settings)):
            adapter = ModelConnection(core.settings())
            call = token_usage.attempt(stage='decisions', protocol='openai-compatible')
            data = adapter.post('/decisions', body)
            token_usage.record(data, 'openai-compatible', call)
    except (ConnectionError, ValueError, KeyError) as exc:
        raise DecisionsError(str(exc) or 'The Decisions API could not be reached.') from exc
    return _answers(data, questions)


PROBE_INPUT = 'Lapi connection test. The test code printed on this page is 4827.'


def probe(cfg, provider_model):
    """Two known predicates through the same path as chat: one true, one false."""
    if not openai_connection(cfg):
        from .connection import ConnectionError
        raise ConnectionError(PROVIDERS)
    questions = [{'type': 'predicate', 'name': 'code_4827', 'instructions': 'Is the test code printed on this page 4827?'},
                 {'type': 'predicate', 'name': 'code_1234', 'instructions': 'Is the test code printed on this page 1234?'}]
    snap = {'settings': cfg, 'secret_refs': {}, 'provider_model': provider_model, 'capability': USE}
    try:
        true, false = ask(snap, PROBE_INPUT, questions, cfg)
    except DecisionsError as exc:
        from .connection import ConnectionError
        raise ConnectionError('The Decisions test could not run: ' + str(exc)) from None
    if true['type'] != 'predicate' or false['type'] != 'predicate' or true['probability'] < 0.5 or false['probability'] >= 0.5:
        from .connection import ConnectionError
        raise ConnectionError('The model answered the Decisions test incorrectly, so it cannot be used for Decisions. '
                              'Use ' + DEFAULT_MODEL + ' with an OpenAI connection.')
    return {'decisions_validated': True}
