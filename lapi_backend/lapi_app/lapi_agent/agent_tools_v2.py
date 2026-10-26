"""Tool catalog v2 for the agentic chat loop (WS4a/WS4b).

Same tool names as the router catalog with backward-compatible arguments, but:
larger pages inside a byte budget (truncated + next_offset instead of errors),
name-or-ID arguments resolved server-side, a description on every parameter,
one retrieval stack (hybrid search + rerank over the unified index), a per-turn
read cache, one result envelope and citable catalog observations.

The router path keeps using agent_tools.Tools unchanged. Proposal tools only
prepare a confirmation card; nothing here executes processing or mutations.
"""
import json
import re
import statistics
import threading
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .. import core, dataset_models as routing
from .agent_tools import Tools, matches_result_filter

OBSERVATION_BYTES = 24000
PAGE = {'documents': 100, 'extractions': 50, 'records': 25, 'prompts': 100, 'datasets': 100}


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, default=str).encode('utf-8'))


def envelope(data, citations=None, next_offset=None, truncated=False, note=''):
    """One result shape for every tool: {data, citations, next_offset, truncated, note}."""
    out = {'data': data, 'citations': citations or [], 'next_offset': next_offset, 'truncated': bool(truncated)}
    if note: out['note'] = note
    return out


def fit_list(items, budget=OBSERVATION_BYTES - 2000):
    """Largest prefix of items within the byte budget (at least one item)."""
    kept = []; used = 2
    for item in items:
        size = _size(item) + 1
        if kept and used + size > budget: break
        kept.append(item); used += size
    return kept


class A(BaseModel):
    model_config = ConfigDict(extra='forbid')


DatasetArg = Field(default='', max_length=200, description='Dataset name or ID. Leave empty to use the dataset selected in chat.')


class ListArgs(A):
    name: str = Field(default='', max_length=200, description='Optional case-insensitive text the name must contain.')
    offset: int = Field(default=0, ge=0, le=100000, description='Start position; use next_offset from the previous page.')


class DatasetListArgs(ListArgs):
    dataset: str = DatasetArg


class DatasetArgs(A):
    dataset: str = DatasetArg


class StatusArgs(A):
    dataset: str = DatasetArg
    include_jobs: bool = Field(default=False, description='Also return recent job stages and errors.')


class HelpArgs(A):
    topic: Literal['overview', 'datasets', 'documents', 'extractions', 'prompts', 'models', 'agent', 'review', 'workspace_access'] = Field(
        default='overview', description='Product area to explain.')
    include_api: bool = Field(default=False, description='Include API endpoints; only for explicit developer questions.')


class PromptArgs(A):
    prompt: str = Field(default='', max_length=300, description='Prompt filename or ID. Empty uses the prompt selected in chat.')
    dataset: str = DatasetArg


class FindArgs(A):
    documents: list[str] = Field(default_factory=list, max_length=50, description='Optional document names or IDs to check coverage for.')
    name: str = Field(default='', max_length=200, description='Optional text the extraction name must contain.')
    offset: int = Field(default=0, ge=0, le=100000, description='Start position; use next_offset from the previous page.')
    dataset: str = DatasetArg


class ResultFilter(A):
    field: str = Field(min_length=1, max_length=200, description='Saved top-level field name.')
    operator: Literal['contains', 'not_contains', 'equals', 'gt', 'gte', 'lt', 'lte'] = Field(description='Comparison operator.')
    value: str | float | bool | None = Field(description='Value to compare with.')


class ReadArgs(A):
    extraction: str = Field(min_length=1, max_length=300, description='Extraction name or ID from find_extractions.')
    fields: list[str] = Field(default_factory=list, max_length=40, description='Top-level fields to return; empty returns all.')
    filters: list[ResultFilter] = Field(default_factory=list, max_length=5, description='Only records matching all conditions.')
    offset: int = Field(default=0, ge=0, le=100000, description='Record start position; use next_offset.')
    dataset: str = DatasetArg


class SearchArgs(A):
    query: str = Field(min_length=1, max_length=2000, description='What to look for, in natural language.')
    top_k: int = Field(default=8, ge=1, le=20, description='Number of passages to return (1-20).')
    documents: list[str] = Field(default_factory=list, max_length=50, description='Optional document names or IDs to search within.')
    dataset: str = DatasetArg


class KnowledgeArgs(A):
    query: str = Field(min_length=1, max_length=2000, description='What to look for, in natural language.')
    source_types: list[Literal['dataset', 'document', 'document_chunk', 'extraction', 'prompt', 'model', 'workflow', 'application']] = Field(
        default_factory=list, max_length=8, description='Limit to these source types; empty searches all.')
    top_k: int = Field(default=8, ge=1, le=20, description='Number of results (1-20).')
    scope: Literal['selected_dataset', 'accessible_datasets'] = Field(default='selected_dataset',
        description='accessible_datasets searches dataset/model metadata and Lapi guidance across datasets.')


class SectionArgs(A):
    document: str = Field(min_length=1, max_length=300, description='Document name or ID.')
    chunk_id: str = Field(default='', max_length=200, description='chunk_id of a search hit to expand around.')
    before: int = Field(default=1, ge=0, le=5, description='Neighbouring chunks before the hit.')
    after: int = Field(default=1, ge=0, le=5, description='Neighbouring chunks after the hit.')
    pages: list[int] = Field(default_factory=list, max_length=10, description='Alternatively, page numbers to read.')


class DescribeArgs(A):
    dataset: str = DatasetArg
    extraction: str = Field(default='', max_length=300, description='Optional extraction name or ID; empty describes all ready results.')


class AggregateArgs(A):
    operation: Literal['count', 'sum', 'avg', 'min', 'max', 'distinct'] = Field(description='Aggregate to compute.')
    field: str = Field(default='', max_length=200, description='Field to aggregate; optional for count.')
    group_by: str = Field(default='', max_length=200, description='Optional field to group by.')
    filters: list[ResultFilter] = Field(default_factory=list, max_length=5, description='Only records matching all conditions.')
    extraction: str = Field(default='', max_length=300, description='Optional extraction name or ID; empty uses the latest result per document.')
    dataset: str = DatasetArg


class CompareArgs(A):
    items: list[str] = Field(min_length=2, max_length=10, description='2-10 extraction names/IDs or document names/IDs to compare.')
    fields: list[str] = Field(default_factory=list, max_length=30, description='Fields to align; empty uses the common fields.')
    dataset: str = DatasetArg


class PlanStep(A):
    text: str = Field(min_length=1, max_length=200, description='Short step description.')
    status: Literal['pending', 'running', 'done', 'skipped'] = Field(default='pending', description='Step status.')


class PlanArgs(A):
    steps: list[PlanStep] = Field(min_length=1, max_length=12, description='The full current plan.')


class SkillArgs(A):
    name: str = Field(min_length=1, max_length=80, description='Skill name from the skills index.')


class HistoryArgs(A):
    query: str = Field(min_length=1, max_length=500, description='What earlier conversation to find.')
    limit: int = Field(default=3, ge=1, le=10, description='Number of past turns to return.')


class WorkflowStatusArgs(A):
    workflow_id: str = Field(default='', max_length=100, description='Workflow ID; empty uses the latest in this conversation.')


class WorkflowArgs(A):
    operation: Literal['upload', 'extract', 'reextract', 'upload_extract'] = Field(description='Work to propose.')
    documents: list[str] = Field(default_factory=list, max_length=20, description='Document names or IDs; empty uses the selection.')
    prompt: str = Field(default='', max_length=300, description='Prompt filename or ID; empty uses the selected prompt.')


class RecoveryArgs(A):
    workflow_id: str = Field(max_length=100, description='Workflow ID from get_workflow_status.')
    action: Literal['retry', 'continue_ready', 'cancel'] = Field(description='Recovery to propose.')


class OnboardingArgs(A):
    name: str = Field(default='', max_length=200, description='Requested dataset name; empty if not given.')
    description: str = Field(default='', max_length=10000, description='Requested description; empty if not given.')


class InstructionArgs(A):
    instructions: str = Field(min_length=1, max_length=4000, description='The complete new dataset instructions (markdown).')
    summary: str = Field(default='', max_length=300, description='One line describing the change.')


CONTRACTS = {
    'list_datasets': (ListArgs, 'List datasets you can access (name, ID, active). Exact catalog.',
        {'name': ''}),
    'get_dataset_status': (StatusArgs, 'Exact document indexing counts and extraction status counts for a dataset; include_jobs adds recent job stages.',
        {}),
    'get_model_configuration': (DatasetArgs, 'Models mapped to a dataset and the workspace Default models, with limits and capabilities.',
        {}),
    'get_application_info': (HelpArgs, 'Built-in Lapi product guidance (screens, buttons, rules). Guidance, not live status.',
        {'topic': 'extractions'}),
    'list_prompts': (DatasetListArgs, 'Exact list of saved prompt templates (filename, ID, version) in a dataset.',
        {}),
    'read_prompt': (PromptArgs, 'Read a prompt template: field list, instructions and (possibly truncated) JSON schema.',
        {'prompt': 'resume_fields.json'}),
    'list_documents': (DatasetListArgs, 'Exact list of documents (filename, ID, status, pages) with document_count. Status describes indexing, not extraction.',
        {'name': '', 'offset': 0}),
    'find_extractions': (FindArgs, 'Saved extraction runs (name, ID, status, record count, field names), latest first, plus documents not yet covered.',
        {'documents': ['invoice_march.pdf']}),
    'read_extraction_results': (ReadArgs, 'Read saved records of one extraction, up to 25 per page; request only needed fields.',
        {'extraction': 'Resumes batch 1', 'fields': ['full_name', 'skills']}),
    'search_documents': (SearchArgs, 'Hybrid search with reranking over original document text; returns passages with citation numbers and chunk_id.',
        {'query': 'termination notice period', 'top_k': 6}),
    'search_knowledge': (KnowledgeArgs, 'Hybrid search with reranking across all knowledge: documents, saved results, prompts, models, workflows and Lapi guidance. Ranked, not a complete list.',
        {'query': 'python experience', 'source_types': ['extraction']}),
    'read_document_section': (SectionArgs, 'Expand a search hit to neighbouring chunks, or read whole pages of a document.',
        {'document': 'contract.pdf', 'chunk_id': 'c12', 'before': 1, 'after': 2}),
    'describe_results': (DescribeArgs, 'Saved field names, types and fill rate for a dataset or one extraction.',
        {}),
    'aggregate_results': (AggregateArgs, 'Exact count, sum, avg, min, max or distinct values over saved fields, optionally grouped and filtered. Use for any number or count.',
        {'operation': 'count', 'group_by': 'city', 'filters': [{'field': 'years_python', 'operator': 'gt', 'value': 5}]}),
    'compare_records': (CompareArgs, 'Aligned field table for 2-10 extractions or documents.',
        {'items': ['invoice_a.pdf', 'invoice_b.pdf'], 'fields': ['total', 'due_date']}),
    'get_workflow_status': (WorkflowStatusArgs, 'Progress and failures of a workflow in this conversation.',
        {}),
    'get_dataset_onboarding_status': (ListArgs, 'Your dataset onboarding workflows: steps, errors, models, documents and results.',
        {}),
    'update_plan': (PlanArgs, 'Show the user a short checklist for a several-part request and update it as you go.',
        {'steps': [{'text': 'Find invoices over 5,000', 'status': 'running'}, {'text': 'Compare due dates', 'status': 'pending'}]}),
    'load_skill': (SkillArgs, 'Load a skill playbook from the skills index; its instructions apply for the rest of this turn.',
        {'name': 'candidate-shortlist'}),
    'list_skills': (A, 'The skills (playbooks) you can load, with what each is for.', {}),
    'read_dataset_instructions': (DatasetArgs, "The dataset owner's current answer instructions for a dataset, with version.", {}),
    'search_my_history': (HistoryArgs, 'Find your own earlier questions and answer summaries. Recall is not evidence; re-read facts.',
        {'query': 'invoice totals last week'}),
    'prepare_workflow': (WorkflowArgs, 'Propose upload, extract or re-extract. Does not run it; the user confirms in a card.',
        {'operation': 'extract'}),
    'prepare_recovery': (RecoveryArgs, 'Propose retry, continue_ready or cancel for a failed workflow. The user confirms.',
        {'workflow_id': 'abc', 'action': 'retry'}),
    'prepare_dataset_onboarding': (OnboardingArgs, 'Propose a new dataset onboarding form (admins). The user confirms.',
        {'name': 'Invoices 2026'}),
    'propose_instruction_update': (InstructionArgs, "Propose new dataset instructions as a before/after card. Only when the user's own message asks for it; nothing is saved until they press Save.",
        {'instructions': 'Answer in short bullet points.', 'summary': 'Prefer bullet answers'}),
}
PROPOSALS = {'prepare_workflow', 'prepare_recovery', 'prepare_dataset_onboarding', 'propose_instruction_update'}
READS = set(CONTRACTS) - PROPOSALS - {'update_plan', 'load_skill'}


def definitions(allowed=None):
    """Function contracts with parameter descriptions and one example call each."""
    out = []
    for name, (model, description, example) in CONTRACTS.items():
        if allowed is not None and name not in allowed: continue
        schema = model.model_json_schema(); defs = schema.pop('$defs', {})

        def inline(value):
            if isinstance(value, list): return [inline(v) for v in value]
            if not isinstance(value, dict): return value
            if '$ref' in value: return inline(defs[value['$ref'].rsplit('/', 1)[-1]])
            return {k: inline(v) for k, v in value.items() if k != 'title'}
        schema = inline(schema); schema.pop('title', None)
        text = description + (' Example: ' + json.dumps(example, ensure_ascii=False) if example else '')
        out.append({'type': 'function', 'function': {'name': name, 'description': text, 'parameters': schema}})
    return out


def _norm(value):
    return ' '.join(str(value or '').split()).casefold()


class AgentTools(Tools):
    """Tools for the agentic loop. Every read rechecks access; proposals only prepare."""
    agentic = True

    def __init__(self, owner, body, conversation_id, main, on_plan=None, skills=None):
        super().__init__(owner, body, conversation_id, main)
        self._cache = {}; self.plan = []; self.on_plan = on_plan; self.lock = threading.RLock()
        self.skills = skills  # WS5 library, optional
        self.loaded_skills = []; self.instruction_proposal = None
        self._selected_dataset = body.dataset_id; self._selected_documents = list(body.document_ids)

    # ------------------------------------------------------------ helpers
    def json(self, ref):
        """Per-turn read cache for stored JSON (extraction files, templates)."""
        if ref not in self._cache: self._cache[ref] = core.store.json(ref)
        return self._cache[ref]

    def rows(self, kind):
        key = ('rows', kind)
        if key not in self._cache: self._cache[key] = list(routing.rows(self.owner, kind))
        return self._cache[key]

    def use_dataset(self, value):
        """Resolve a dataset name or ID against access and scope this call to it."""
        if not value:
            self.body.dataset_id = self._selected_dataset; self.body.document_ids = list(self._selected_documents)
            return self.dataset() if self.body.dataset_id else None
        found = [r for r in self.rows('knowledge_base') if r.id == value or _norm(r.name) == _norm(value)]
        if not found:
            found = [r for r in self.rows('knowledge_base') if _norm(value) in _norm(r.name)]
        if len(found) != 1:
            names = ', '.join(r.name for r in self.rows('knowledge_base')[:20])
            raise HTTPException(404 if not found else 409, ('No accessible dataset matches ' if not found else 'Several datasets match ') + repr(value) + '. Available: ' + names)
        self.body.dataset_id = found[0].id
        # The chat document filter only applies to the dataset it was chosen in.
        self.body.document_ids = list(self._selected_documents) if found[0].id == self._selected_dataset else []
        return found[0]

    def resolve_documents(self, values):
        if not values: return None
        docs = self.documents(); ids = []
        for value in values:
            match = [d for d in docs if d.id == value or _norm(d.name) == _norm(value)] or [d for d in docs if _norm(value) in _norm(d.name)]
            if len(match) != 1:
                raise HTTPException(404 if not match else 409, ('No document named ' if not match else 'Several documents match ') + repr(value) + ' in this scope.')
            ids.append(match[0].id)
        return list(dict.fromkeys(ids))

    def resolve_extraction(self, value):
        records = [r for r in self.rows('extraction') if r.parent_id == self.body.dataset_id]
        match = [r for r in records if r.id == value or _norm(r.name) == _norm(value)]
        if not match:
            match = [r for r in records if _norm(value) in _norm(r.name)]
            if len(match) > 1:  # prefer the latest of identically named runs
                match = sorted(match, key=lambda r: r.updated_at or 0, reverse=True)[:1] if len({_norm(r.name) for r in match}) == 1 else match
        if len(match) != 1:
            raise HTTPException(404 if not match else 409, ('No saved extraction matches ' if not match else 'Several extractions match ') + repr(value) + '. Use find_extractions for exact names.')
        return match[0]

    def resolve_prompt(self, value):
        prompts = [r for r in self.rows('template') if r.parent_id in ('', self.body.dataset_id)]
        if not value:
            if not self.body.template_id: return None
            value = self.body.template_id
        match = [r for r in prompts if r.id == value or _norm(r.name) == _norm(value)
                 or _norm(self.json(r.ref).get('source_filename')) == _norm(value)]
        if len(match) != 1:
            raise HTTPException(404 if not match else 409, 'No single prompt template matches ' + repr(value) + '. Use list_prompts.')
        return match[0]

    def cite(self, *args, **kwargs):
        with self.lock: return self._cite_locked(*args, **kwargs)

    def _cite_locked(self, label, text, **extra):
        """Register a citable source (catalog facts or computed tables) for this turn."""
        key = extra.pop('key', None) or ('catalog:' + label + ':' + str(len(text)))
        existing = next((s for s in self.sources if s.get('chunk_id') == key), None)
        if existing: return existing['index']
        source = {'kind': extra.pop('kind', 'knowledge'), 'index': len(self.sources) + 1, 'chunk_id': key,
                  'document_name': label, 'text': text, **extra}
        self.sources.append(source)
        return source['index']

    def extraction_items(self, record):
        from ..parquet_results import load
        value = load(self.json(record.ref))
        original = value.get('result')
        items = original['records'] if isinstance(original, dict) and isinstance(original.get('records'), list) else [{'fields': original}]
        return value, [(item.get('fields', item) if isinstance(item, dict) else item, item) for item in items]

    def latest_records(self, extraction=''):
        """Records from the latest ready, visible extraction per covered document."""
        if extraction:
            record = self.resolve_extraction(extraction)
            value = self.json(record.ref)
            if not self.visible(value): raise HTTPException(422, 'This result includes files outside the selected document filter.')
            if record.status != 'ready': raise HTTPException(409, 'That extraction is ' + record.status + ', not ready.')
            chosen = [record]
        else:
            allowed = {d.id for d in self.documents()}; covered = set(); chosen = []
            ready = sorted([r for r in self.rows('extraction') if r.parent_id == self.body.dataset_id and r.status == 'ready'],
                           key=lambda r: r.updated_at or 0, reverse=True)
            for record in ready:
                value = self.json(record.ref)
                sources = set(value.get('document_ids', [])) | {s.get('document_id') for s in (value.get('merge') or {}).get('sources', [])}
                if (value.get('merge') or {}).get('document_id'): sources.add(value['merge']['document_id'])
                sources = {s for s in sources if s}
                if not sources & allowed or not self.visible(value) or sources <= covered: continue
                covered |= sources; chosen.append(record)
        out = []
        for record in chosen:
            value, items = self.extraction_items(record)
            for i, (fields, raw) in enumerate(items):
                if isinstance(fields, dict):
                    out.append({'record': record, 'value': value, 'index': i, 'fields': fields,
                                'source_filename': raw.get('source_filename') if isinstance(raw, dict) else None})
        return out

    def record_source(self, *args, **kwargs):
        with self.lock: return self._record_source_locked(*args, **kwargs)

    def _record_source_locked(self, entry, fields=None):
        record = entry['record']; data = entry['fields']
        if fields: data = {k: v for k, v in data.items() if k in fields}
        label = data.get('full_name') or data.get('name') or entry['source_filename'] or record.name
        key = f'extraction:{record.id}:v{record.version}:record:{entry["index"]}' + (':' + ','.join(sorted(fields)) if fields else '')
        index = self.cite(str(entry['source_filename'] or record.name), json.dumps(data, ensure_ascii=False, default=str), key=key,
                          kind='extraction', extraction_id=record.id, dataset_id=record.parent_id, version=record.version,
                          record_index=entry['index'], review_status=entry['value'].get('review_status', 'unreviewed'),
                          record_label=label if isinstance(label, str) else None, field_projection=fields or [])
        if not any(a['extraction_id'] == record.id for a in self.review_actions):
            self.review_actions.append({'extraction_id': record.id, 'name': record.name, 'version': record.version,
                                        'label': 'Review result', 'fields': fields or []})
        return index

    # ------------------------------------------------------------ dispatch
    def run(self, name, arguments):
        if name not in CONTRACTS: raise ValueError('Unknown tool. Choose a defined tool.')
        if self.loaded_skills:
            allowed = set.intersection(*[set(s.get('allowed_tools') or CONTRACTS) for s in self.loaded_skills])
            if name not in allowed | {'update_plan', 'load_skill', 'list_skills'}:
                return envelope(None, note='The loaded skill does not allow ' + name + '. Allowed: ' + ', '.join(sorted(allowed)))
        values = CONTRACTS[name][0].model_validate(arguments).model_dump()
        dataset = values.pop('dataset', None) if 'dataset' in values else None
        try:
            if dataset is not None: self.use_dataset(dataset)
            result = getattr(self, 'v2_' + name)(**values)
        finally:
            self.body.dataset_id = self._selected_dataset; self.body.document_ids = list(self._selected_documents)
        if _size(result) > OBSERVATION_BYTES:
            result = dict(result, truncated=True, note=(result.get('note', '') + ' Result trimmed to the observation budget; page or narrow the request.').strip())
            text = json.dumps(result['data'], ensure_ascii=False, default=str)[:OBSERVATION_BYTES - 2000]
            result['data'] = {'partial_json': text}
        return result

    # ------------------------------------------------------------ catalog reads
    def v2_list_datasets(self, name='', offset=0):
        items = [{'name': r.name, 'id': r.id, 'active': routing.dataset_config(r).get('active', True)}
                 for r in self.rows('knowledge_base') if _norm(name) in _norm(r.name)]
        page = fit_list(items[offset:offset + PAGE['datasets']]); nxt = offset + len(page)
        data = {'dataset_count': len(items), 'datasets': page}
        n = self.cite('Dataset list', json.dumps(data, ensure_ascii=False), key=f'catalog:datasets:{name}:{offset}')
        return envelope(data, [n], nxt if nxt < len(items) else None)

    def v2_list_documents(self, name='', offset=0):
        dataset = self.dataset(); docs = self.documents()
        items = [{'name': d.name, 'id': d.id, 'status': d.status, 'version': d.version, 'size': d.size}
                 for d in docs if _norm(name) in _norm(d.name)]
        page = fit_list(items[offset:offset + PAGE['documents']]); nxt = offset + len(page)
        data = {'dataset': dataset.name, 'scope': 'selected_documents' if self.body.document_ids else 'dataset',
                'document_count': len(items), 'documents': page}
        n = self.cite('Document list · ' + dataset.name, json.dumps(data, ensure_ascii=False), key=f'catalog:documents:{dataset.id}:{name}:{offset}')
        return envelope(data, [n], nxt if nxt < len(items) else None,
                        note='Document status describes indexing, not extraction.')

    def v2_list_prompts(self, name='', offset=0):
        dataset = self.dataset()
        items = [{'name': self.json(r.ref).get('source_filename') or r.name, 'id': r.id, 'version': r.version}
                 for r in self.rows('template') if r.parent_id in ('', dataset.id)]
        items = [p for p in items if _norm(name) in _norm(p['name'])]
        page = fit_list(items[offset:offset + PAGE['prompts']]); nxt = offset + len(page)
        data = {'dataset': dataset.name, 'prompt_count': len(items), 'prompts': page}
        n = self.cite('Prompt list · ' + dataset.name, json.dumps(data, ensure_ascii=False), key=f'catalog:prompts:{dataset.id}:{name}:{offset}')
        return envelope(data, [n], nxt if nxt < len(items) else None)

    def v2_get_dataset_status(self, include_jobs=False):
        state = self.get_dataset_status()
        data = {k: state[k] for k in ('dataset', 'scope', 'document_count', 'document_status_counts', 'extraction_status_counts', 'active_job_count')}
        if include_jobs: data['recent_jobs'] = state['recent_jobs']
        n = self.cite('Dataset status · ' + state['dataset']['name'], json.dumps(data, ensure_ascii=False, default=str),
                      key=f'catalog:status:{state["dataset"]["id"]}:{include_jobs}')
        return envelope(data, [n])

    def v2_get_model_configuration(self):
        data = self.get_model_configuration()
        try:
            from .. import dataset_models
            defaults = getattr(dataset_models, 'workspace_defaults', None)
            if callable(defaults): data['workspace_defaults'] = defaults()
        except Exception:  # Defaults are informational; mapping data stays authoritative.
            pass
        n = self.cite('Model configuration · ' + data['dataset']['name'], json.dumps(data, ensure_ascii=False, default=str),
                      key=f'catalog:models:{data["dataset"]["id"]}')
        return envelope(data, [n])

    def v2_get_application_info(self, topic='overview', include_api=False):
        data = self.get_application_info(topic, include_api)
        n = self.cite('Lapi guide · ' + topic, json.dumps(data['user_guide'], ensure_ascii=False), key=f'guide:{topic}', kind='knowledge')
        return envelope(data, [n])

    def v2_read_prompt(self, prompt=''):
        self.dataset(); record = self.resolve_prompt(prompt)
        if record is None: return envelope(None, note='No prompt selected. Call list_prompts and name one.')
        value = self.json(record.ref); schema = value.get('schema', {}) or {}
        props = schema.get('properties') or {}
        fields = [{'name': k, 'type': (v or {}).get('type'), 'description': (v or {}).get('description', '')[:300]} for k, v in props.items()]
        text = json.dumps(schema, ensure_ascii=False); truncated = len(text) > 12000
        data = {'name': value.get('source_filename') or record.name, 'id': record.id, 'version': record.version,
                'instructions': (value.get('instruction') or value.get('instructions') or '')[:3000], 'fields': fields,
                'schema': json.loads(text) if not truncated else text[:12000]}
        n = self.cite('Prompt · ' + data['name'], json.dumps({'name': data['name'], 'version': data['version'], 'fields': fields,
                      'instructions': data['instructions']}, ensure_ascii=False), key=f'prompt:{record.id}:v{record.version}', kind='knowledge')
        return envelope(data, [n], truncated=truncated, note='Schema truncated; the field list is complete.' if truncated else '')

    def v2_find_extractions(self, documents=None, name='', offset=0):
        ids = self.resolve_documents(documents)
        result = self._find(ids, name)
        page = fit_list(result['extractions'][offset:offset + PAGE['extractions']]); nxt = offset + len(page)
        names = {d.id: d.name for d in self.documents()}
        data = {'extraction_count': result['total'], 'extractions': page,
                'documents_without_ready_results': [names.get(i, i) for i in result['missing_document_ids']][:100]}
        n = self.cite('Saved extraction runs', json.dumps(data, ensure_ascii=False, default=str), key=f'catalog:extractions:{self.body.dataset_id}:{name}:{offset}:{ids}')
        return envelope(data, [n], nxt if nxt < result['total'] else None)

    def _find(self, document_ids, name):
        allowed = {d.id for d in self.documents(document_ids)}; found = []
        records = sorted([r for r in self.rows('extraction') if r.parent_id == self.body.dataset_id],
                         key=lambda r: r.updated_at or 0, reverse=True)
        for record in records:
            if _norm(name) not in _norm(record.name): continue
            value = self.json(record.ref)
            coverage = set(value.get('document_ids', [])) | {s.get('document_id') for s in (value.get('merge') or {}).get('sources', [])}
            if (value.get('merge') or {}).get('document_id'): coverage.add(value['merge']['document_id'])
            if not coverage & allowed or (self.body.document_ids and not self.visible(value)): continue
            result = value.get('result')
            records_ = result.get('records') if isinstance(result, dict) and isinstance(result.get('records'), list) else None
            fields = list((records_[0] or {}).get('fields', {})) if records_ else list(result or {}) if isinstance(result, dict) else []
            found.append({'name': record.name, 'id': record.id, 'status': record.status, 'version': record.version,
                          'record_count': len(records_) if records_ is not None else (1 if record.status == 'ready' else 0),
                          'field_names': fields[:60], 'review_status': value.get('review_status', 'unreviewed'),
                          'source_ids': sorted(i for i in coverage if i), 'error': record.error or None})
        ready = {i for e in found if e['status'] == 'ready' for i in e['source_ids']}
        return {'extractions': found, 'total': len(found), 'missing_document_ids': sorted(allowed - ready)}

    # ------------------------------------------------------------ result reads
    def v2_read_extraction_results(self, extraction, fields=None, filters=None, offset=0):
        self.dataset(); record = self.resolve_extraction(extraction)
        value = self.json(record.ref)
        if not self.visible(value): raise HTTPException(422, 'This merged result includes files outside the selected document filter.')
        if record.status != 'ready': return envelope({'name': record.name, 'status': record.status, 'error': record.error})
        value, items = self.extraction_items(record)
        available = list(dict.fromkeys(k for f, _ in items if isinstance(f, dict) for k in f))
        unknown = sorted((set(fields or []) | {f['field'] for f in filters or []}) - set(available))
        if unknown:
            return envelope({'available_fields': available}, note='Unknown fields: ' + ', '.join(unknown) + '. Use available_fields.')
        selected = [i for i, (f, _) in enumerate(items) if isinstance(f, dict) and all(matches_result_filter(f, c) for c in filters or [])]
        page = []; citations = []; used = 2
        for i in selected[offset:offset + PAGE['records']]:
            f, raw = items[i]
            data = {k: v for k, v in f.items() if not fields or k in fields}
            entry = {'record': record, 'value': value, 'index': i, 'fields': f,
                     'source_filename': raw.get('source_filename') if isinstance(raw, dict) else None}
            row = {'record': i, 'source_filename': entry['source_filename'], 'fields': data}
            size = _size(row) + 1
            if page and used + size > OBSERVATION_BYTES - 3000: break
            row['citation'] = self.record_source(entry, fields or None); citations.append(row['citation'])
            page.append(row); used += size
        nxt = offset + len(page); self.observed_results = True
        data = {'extraction': record.name, 'id': record.id, 'version': record.version,
                'review_status': value.get('review_status', 'unreviewed'), 'matching_records': len(selected),
                'total_records': len(items), 'records': page, 'available_fields': available}
        return envelope(data, citations, nxt if nxt < len(selected) else None,
                        truncated=nxt < len(selected), note='Saved values are unverified until reviewed.')

    def v2_describe_results(self, extraction=''):
        self.dataset(); rows = self.latest_records(extraction); stats = {}
        for row in rows:
            for k, v in row['fields'].items():
                s = stats.setdefault(k, {'field': k, 'types': set(), 'filled': 0})
                if v not in (None, '', [], {}): s['filled'] += 1
                s['types'].add('list' if isinstance(v, list) else 'number' if isinstance(v, (int, float)) and not isinstance(v, bool) else
                               'boolean' if isinstance(v, bool) else 'object' if isinstance(v, dict) else 'null' if v is None else 'text')
        fields = [{'field': s['field'], 'types': sorted(s['types']), 'fill_rate': round(s['filled'] / len(rows), 3) if rows else 0}
                  for s in stats.values()]
        data = {'records': len(rows), 'extractions': len({r['record'].id for r in rows}), 'fields': fields}
        n = self.cite('Saved field summary', json.dumps(data, ensure_ascii=False), key=f'describe:{self.body.dataset_id}:{extraction}')
        return envelope(data, [n])

    def v2_aggregate_results(self, operation, field='', group_by='', filters=None, extraction=''):
        self.dataset(); rows = [r for r in self.latest_records(extraction)
                                if all(matches_result_filter(r['fields'], c) for c in filters or [])]
        if operation != 'count' and not field: raise HTTPException(422, 'Choose the field to aggregate.')
        known = {k for r in self.latest_records(extraction) for k in r['fields']}
        for name in (field, group_by):
            if name and name not in known: raise HTTPException(422, 'Unknown field ' + repr(name) + '. Use describe_results.')

        def keyof(value):
            if isinstance(value, list): return [str(v) for v in value] or ['(none)']
            return ['(none)' if value in (None, '') else str(value)]

        groups = {}
        for r in rows:
            for key in (keyof(r['fields'].get(group_by)) if group_by else ['all']):
                groups.setdefault(key, []).append(r)
        table = []
        for key, members in sorted(groups.items()):
            values = [m['fields'].get(field) for m in members] if field else []
            numbers = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if operation == 'count':
                result = len(members) if not field else sum(1 for v in values if v not in (None, '', []))
            elif operation == 'distinct':
                flat = [str(x) for v in values for x in (v if isinstance(v, list) else [v]) if x not in (None, '')]
                result = sorted(set(flat))[:200]
            elif not numbers: result = None
            else:
                result = {'sum': sum(numbers), 'avg': statistics.fmean(numbers), 'min': min(numbers), 'max': max(numbers)}[operation]
                if isinstance(result, float): result = round(result, 4)
            table.append({'group': key, operation: result, 'records': len(members), 'numeric_values': len(numbers) if field else None})
        data = {'operation': operation, 'field': field or None, 'group_by': group_by or None, 'filters': filters or [],
                'records_considered': len(rows), 'scope': 'latest ready result per document' if not extraction else extraction, 'result': table}
        n = self.cite('Computed ' + operation + (' of ' + field if field else '') + (' by ' + group_by if group_by else ''),
                      json.dumps(data, ensure_ascii=False, default=str), key=f'aggregate:{json.dumps(data["filters"])}:{operation}:{field}:{group_by}:{extraction}')
        return envelope(data, [n], note='Exact over saved values in scope; saved values are unverified until reviewed.')

    def v2_compare_records(self, items, fields=None):
        self.dataset(); columns = []
        docs = {d.id: d for d in self.documents()}
        rows = self.latest_records()
        for item in items:
            try:
                record = self.resolve_extraction(item); picked = [r for r in self.latest_records(record.id)]
            except HTTPException:
                ids = self.resolve_documents([item]); picked = []
                for r in rows:
                    value = r['value']
                    if set(value.get('document_ids', [])) & set(ids) or (value.get('merge') or {}).get('document_id') in ids:
                        if r['source_filename'] in (None, docs[ids[0]].name) or len(value.get('document_ids', [])) == 1: picked.append(r)
            if not picked: raise HTTPException(404, 'No saved result found for ' + repr(item) + '.')
            for r in picked[:3]: columns.append((item, r))
        common = fields or [k for k in columns[0][1]['fields'] if all(k in r['fields'] for _, r in columns)][:20]
        table = []
        for item, r in columns:
            row = {'item': item, 'citation': self.record_source(r, common or None)}
            row.update({k: r['fields'].get(k) for k in common}); table.append(row)
        return envelope({'fields': common, 'rows': table}, [r['citation'] for r in table])

    # ------------------------------------------------------------ retrieval
    def _view(self, document_ids=None):
        from .chat_knowledge import PublishedKnowledge
        return PublishedKnowledge(self.owner, self.body.dataset_id, document_ids if document_ids is not None else self.body.document_ids)

    def _hits(self, view, query, types, top_k):
        from .chat_knowledge import assemble
        self.main.external_check(self.body.allow_external, True, view.snapshot['settings'])
        points = view.search(query, types, limit=top_k, require_rerank=True)
        return assemble(points), getattr(view, 'search_diagnostics', {})

    def _source(self, *args, **kwargs):
        with self.lock: return self._source_locked(*args, **kwargs)

    def _source_locked(self, r, view):
        existing = next((s for s in self.sources if s.get('knowledge_id') == r['knowledge_id']), None)
        if existing: return existing['index']
        kind = 'document' if r['source_type'] == 'document_chunk' else 'extraction' if r['source_type'] == 'extraction' else 'knowledge'
        src = {'kind': kind, 'index': len(self.sources) + 1, 'knowledge_id': r['knowledge_id'], 'chunk_id': r.get('chunk_id') or r['knowledge_id'],
               'document_name': r['title'], 'text': r['text'], 'source_type': r['source_type'], 'page': r.get('page'),
               'version': r.get('source_version'), 'knowledge_collection': view.snapshot['knowledge_collection'],
               'source_url': '/api/knowledge/published-sources/' + r['knowledge_id'] + '?collection=' + view.snapshot['knowledge_collection'] + '&dataset_id=' + view.dataset_id}
        if len(r.get('document_ids', [])) == 1: src['document_id'] = r['document_ids'][0]
        if kind == 'extraction':
            src['extraction_id'] = r.get('extraction_id') or r['entity_id'].split(':')[0]
            src['record_index'] = r.get('record_index'); src['review_status'] = r.get('review_status')
            if not any(a['extraction_id'] == src['extraction_id'] for a in self.review_actions):
                self.review_actions.append({'extraction_id': src['extraction_id'], 'name': r['title'], 'version': r.get('source_version'), 'label': 'Review result'})
        self.sources.append(src)
        return src['index']

    def v2_search_documents(self, query, top_k=8, documents=None):
        self.dataset(); ids = self.resolve_documents(documents)
        view = self._view(ids); hits, diagnostics = self._hits(view, query, ['document_chunk'], top_k)
        rows = [{'citation': self._source(r, view), 'document': r['title'], 'page': r.get('page'), 'chunk_id': r.get('chunk_id'),
                 'text': r['text'][:2400], **({'ocr_notice': 'AI OCR transcription; verify against the original.'} if r.get('ocr') else {})} for r in hits]
        rows = fit_list(rows)
        return envelope({'passages': rows, 'retrieval': {k: diagnostics.get(k) for k in ('mode', 'reranker_enabled', 'returned_entities')}},
                        [r['citation'] for r in rows], note='Ranked passages, not a complete list.')

    def v2_search_knowledge(self, query, source_types=None, top_k=8, scope='selected_dataset'):
        types = source_types or ['dataset', 'document', 'document_chunk', 'extraction', 'prompt', 'model', 'workflow', 'application']
        if scope == 'accessible_datasets' or not self.body.dataset_id:
            types = [t for t in types if t in ('dataset', 'model', 'application')] or ['application']
            dataset_id, document_ids = self.body.dataset_id, self.body.document_ids
            self.body.dataset_id, self.body.document_ids = '', []
            try: view = self._view([])
            finally: self.body.dataset_id, self.body.document_ids = dataset_id, document_ids
        else:
            view = self._view()
        hits, diagnostics = self._hits(view, query, types, top_k)
        rows = fit_list([{'citation': self._source(r, view), 'type': r['source_type'], 'title': r['title'], 'page': r.get('page'),
                          'chunk_id': r.get('chunk_id'), 'text': r['text'][:2400]} for r in hits])
        return envelope({'results': rows, 'retrieval': {k: diagnostics.get(k) for k in ('mode', 'reranker_enabled', 'returned_entities')}},
                        [r['citation'] for r in rows], note='Ranked results, not a complete list or count.')

    def v2_read_document_section(self, document, chunk_id='', before=1, after=1, pages=None):
        self.dataset(); ids = self.resolve_documents([document]); doc = next(d for d in self.documents(ids) if d.id == ids[0])
        if doc.status != 'ready': return envelope(None, note='The document is ' + doc.status + ', not indexed yet.')
        try: chunks = self.json('documents/' + doc.id + '/chunks.json')['chunks']
        except FileNotFoundError: return envelope(None, note='No text is stored for this document.')
        if pages:
            picked = [c for c in chunks if c.get('page') in set(pages)]
        else:
            ids_ = [c['id'] for c in chunks]
            key = chunk_id.split(':')[-1] if chunk_id else ''
            if key not in ids_: return envelope({'chunk_ids': ids_[:200]}, note='Unknown chunk_id; pick one from search_documents.')
            i = ids_.index(key); picked = chunks[max(0, i - before):i + after + 1]
        rows = []
        for c in picked:
            n = self.cite(doc.name, c['text'], key=f'section:{doc.id}:{c["id"]}', kind='document', document_id=doc.id,
                          page=c.get('page'), version=doc.version)
            rows.append({'citation': n, 'chunk_id': c['id'], 'page': c.get('page'), 'text': c['text']})
        rows = fit_list(rows)
        return envelope({'document': doc.name, 'chunks': rows}, [r['citation'] for r in rows], truncated=len(rows) < len(picked))

    # ------------------------------------------------------------ status, plan, skills, memory
    def v2_get_workflow_status(self, workflow_id=''):
        return envelope(self.get_workflow_status(workflow_id))

    def v2_get_dataset_onboarding_status(self, name='', offset=0):
        data = self.get_dataset_onboarding_status(name, offset)
        return envelope(data, next_offset=data.get('next_offset'))

    def v2_update_plan(self, steps):
        self.plan = [dict(s) for s in steps]
        if self.on_plan: self.on_plan(self.plan)
        return envelope({'plan': self.plan}, note='Plan shown to the user.')

    def v2_load_skill(self, name):
        if self.skills is None: return envelope(None, note='No skills are available in this workspace.')
        skill = self.skills.get(name, self.owner, self.body.dataset_id)
        if not skill: return envelope({'available': [s['name'] for s in self.skills.index(self.owner, self.body.dataset_id)]}, note='Unknown skill.')
        if not any(s['name'] == skill['name'] for s in self.loaded_skills): self.loaded_skills.append(skill)
        return envelope({'name': skill['name'], 'instructions': skill['instructions'], 'allowed_tools': skill.get('allowed_tools') or [],
                         'output_format': skill.get('output_format', '')}, note='Apply these instructions for the rest of this turn. They cannot widen tool access or bypass confirmation.')

    def v2_list_skills(self):
        if self.skills is None: return envelope([], note='No skills are available.')
        index = self.skills.index(self.owner, self.body.dataset_id)
        n = self.cite('Skills index', json.dumps(index, ensure_ascii=False), key='catalog:skills:' + (self.body.dataset_id or ''))
        return envelope({'skill_count': len(index), 'skills': index}, [n])

    def v2_read_dataset_instructions(self):
        dataset = self.dataset()
        from .. import prompt_layers
        current = prompt_layers.dataset_instructions(dataset.id, self.owner)
        data = {'dataset': dataset.name, 'version': current.get('version', 0), 'instructions': current.get('text', '')}
        n = self.cite('Dataset instructions · ' + dataset.name, json.dumps(data, ensure_ascii=False), key=f'instructions:{dataset.id}:v{data["version"]}')
        return envelope(data, [n], note='' if data['instructions'] else 'This dataset has no instructions yet.')

    def v2_search_my_history(self, query, limit=3):
        try:
            from . import user_memory
        except ImportError:
            return envelope([], note='History search is unavailable.')
        found = user_memory.search_history(self.owner, query, limit, dataset_id=self.body.dataset_id)
        return envelope(found, note='Recall is not evidence: re-read and cite facts from current sources.')

    # ------------------------------------------------------------ proposals (confirmation required)
    def v2_prepare_workflow(self, operation, documents=None, prompt=''):
        ids = self.resolve_documents(documents) if documents else None
        record = self.resolve_prompt(prompt) if prompt else None
        return envelope(self.prepare_workflow(operation, ids, record.id if record else ''))

    def v2_prepare_recovery(self, workflow_id, action):
        return envelope(self.prepare_recovery(workflow_id, action))

    def v2_prepare_dataset_onboarding(self, name='', description=''):
        return envelope(self.prepare_dataset_onboarding(name, description))

    def v2_propose_instruction_update(self, instructions, summary=''):
        if not self.body.dataset_id: raise HTTPException(422, 'Select a dataset to change its instructions.')
        try:
            from .. import prompt_layers
            current = prompt_layers.dataset_instructions(self.body.dataset_id, self.owner)
            warnings = prompt_layers.weakening_warnings(instructions)
        except ImportError:
            current, warnings = {'text': '', 'version': 0}, []
        self.instruction_proposal = {'dataset_id': self.body.dataset_id, 'before': current.get('text', ''), 'after': instructions,
                                     'current_version': current.get('version', 0), 'summary': summary, 'warnings': warnings}
        return envelope({'proposed': True, 'executed': False}, note='A before/after card is shown; nothing is saved until the user presses Save.')
