"""Select a dataset's cloud OCR model: its own OCR choice, the workspace OCR Default,
or (for datasets set up before OCR was a use) a vision-capable extraction model.
Never an embedding model."""
from urllib.parse import urlsplit
import re

PROVIDERS = ('gemini', 'openai')


def eligible(snapshot):
    """Extraction models that read images without an OCR test (the original rule)."""
    kind = provider(snapshot)
    return kind == 'gemini' or kind == 'openai' and bool(re.fullmatch(r'gpt-4o(?:-mini)?(?:-\d{4}-\d{2}-\d{2})?', snapshot['provider_model']))


def provider(snapshot):
    cfg = snapshot['settings']
    connection = cfg.get('model_connection') or {}
    if cfg.get('model_provider') != 'registered' or connection.get('protocol') != 'openai-compatible':
        return None
    host = urlsplit(connection.get('endpoint', '')).hostname
    if host == 'generativelanguage.googleapis.com' and snapshot['provider_model'].startswith('gemini-'):
        return 'gemini'
    if host == 'api.openai.com':
        return 'openai'
    return None


def tested(data):
    """The OCR image test passed for the registration's current connection version."""
    test = data.get('ocr_test') or {}
    return bool(test) and test.get('connection_profile_version') == data.get('connection_profile_version')


def ready(data, snapshot):
    """Can this registration read images for a dataset? Any OpenAI or Gemini model
    ticked for OCR whose image test passed, or a known vision extraction model."""
    if not provider(snapshot):
        return False
    uses = data.get('capabilities', [])
    return 'ocr' in uses and tested(data) or 'extraction' in uses and eligible(snapshot)


NOT_READY = ('The OCR model cannot read images yet. In Model Registration, tick OCR for it and pass Test connection '
             '(it reads a sample image), or choose gpt-4o, gpt-4o-mini or a Gemini model.')


def dataset_snapshot(dataset):
    from fastapi import HTTPException
    from .. import dataset_models as routing, workspace_defaults
    data = routing.dataset_config(dataset)
    selected = data.get('ocr_model_id')
    if selected == 'local':
        raise HTTPException(409, 'Select a cloud OCR model in Workspace Model Mapping. Local OCR is no longer selectable.')
    if not selected:
        selected = workspace_defaults.default_id('ocr')
    if selected:
        model = routing.model_record(selected)
        md = routing.model_data(model) if model and model.kind == 'model' else {}
        snapshot = routing.resolve_model(dataset, 'ocr' if 'ocr' in md.get('capabilities', []) else 'extraction', selected)
        if not ready(md, snapshot):
            raise HTTPException(409, NOT_READY)
        return snapshot
    try:
        snapshot = routing.resolve_model(dataset, 'extraction', None)
    except HTTPException:
        # A missing default is allowed for inspecting an embedding index; an
        # invalid saved extraction mapping must never select another OCR service.
        if data.get('default_extraction_model_id'):
            raise
        return None
    return snapshot if eligible(snapshot) else None


def adapter(name):
    if name == 'gemini':
        from .providers.lapi_gcp import ocr
    elif name == 'openai':
        from .providers.lapi_openai import ocr
    else:
        raise ValueError('Unsupported cloud OCR provider.')
    return ocr
