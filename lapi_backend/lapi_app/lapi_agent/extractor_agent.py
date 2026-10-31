"""Durable LangGraph extractor: knowledge -> retrieve -> generate -> validate -> Parquet."""
import hashlib
import json
import time
from typing import TypedDict
from jsonschema import validate
from langgraph.graph import StateGraph, START, END
from langsmith import tracing_context
from .. import core, providers, workflow, extraction_retrieval, parquet_results, runtime_config
from .agent_checkpoints import ExternalCheckpointSaver
from . import table_extraction, extraction_repair


class State(TypedDict):
    selected: list[dict]
    diagnostics: dict
    records: dict
    result: dict
    evidence: list[dict]
    output: dict
    filled: list[str]


def run(jid, record, data, snapshot, documents, sources, check):
    indexes = {d.id: core.store.json('documents/' + d.id + '/index.json') for d in documents}
    data['index_versions'] = {key: {k: value.get(k) for k in
        ('index_generation', 'fingerprint', 'embedding_digest', 'indexed_at', 'dimensions')} for key, value in indexes.items()}
    signature = hashlib.sha256(json.dumps({'schema': data['schema'], 'prompt_version': data['template_version'],
        'indexes': data['index_versions'], 'execution': snapshot, 'pipeline': 2}, sort_keys=True).encode()).hexdigest()
    signature_ref = 'jobs/' + jid + '/extractor-signature.json'
    saver = ExternalCheckpointSaver(jid)
    try:
        if core.store.json(signature_ref)['signature'] != signature:
            saver.delete_thread(jid)
    except FileNotFoundError: pass
    core.store.put_json(signature_ref, {'signature': signature})

    def stage(name, status='running'):
        check(); workflow.transition(jid, name, status)

    # Spreadsheets whose columns are the requested fields: one record per row, read from the table.
    chosen = None if data.get('merge_records') else table_extraction.plan(data['schema'], documents, override=data.get('column_mapping'))
    if chosen:
        stage('retrieving'); stage('retrieving', 'completed'); stage('reranking', 'completed'); stage('generate')
        selection = data.get('model_selection') or {}
        result, evidence, notice = table_extraction.extract(data['schema'], chosen, sources, check,
            limits={'context': selection.get('context_limit'), 'output': selection.get('max_output_tokens')})
        data['column_plan'] = table_extraction.preview(chosen)
        data['schema'] = table_extraction.schema_for(data['schema'])
        stage('generate', 'completed'); stage('validate')
        validate(result, data['schema']); parquet_results.encoded(result); stage('validate', 'completed')
        stage('writing_output')
        output = parquet_results.persist(record.id, record.version, data | {'result': result, 'evidence': evidence})
        stage('writing_output', 'completed')
        data.update(result=result, evidence=evidence, table_rows=True, table_notice=notice,
                    retrieval={'method': 'spreadsheet rows', 'rows': len(result['records'])}, **output)
        return data

    def retrieve(state):
        stage('retrieving')
        groups = (data.get('merge') or {}).get('sources', []) if data.get('merge_records') else []
        selected = []; diagnostics = {}
        if groups:
            for source in groups:
                scoped = [c for c in sources if c.get('source_key') == source['key']] if data['merge'].get('document_id') else [c for c in sources if c['document_id'] == source['document_id']]
                chunks, detail = extraction_retrieval.retrieve(data['record_schema'], documents, snapshot, scoped, progress=lambda name: stage(name))
                selected.extend(dict(c, record_key=source['key']) for c in chunks); diagnostics[source['key']] = detail
        else:
            selected, diagnostics = extraction_retrieval.retrieve(data['schema'], documents, snapshot, sources, progress=lambda name: stage(name))
            selected, added = extraction_repair.cover_sources(selected, sources, runtime_config.get('LAPI_EXTRACTION_CHUNKS_PER_FIELD'))
            unread = extraction_repair.unread_sources(documents, sources, data.get('merge'))
            if added: diagnostics['sources_added'] = added
            if unread: diagnostics['sources_without_text'] = unread
        stage('retrieving', 'completed'); stage('reranking', 'completed')
        return {'selected': selected, 'diagnostics': diagnostics}

    def generate(state):
        stage('generate'); records = dict(state.get('records', {})); evidence = []
        def context(items):
            return '\n\n'.join(f'Document: {c.get("source_filename", c["document_name"])}; chunk {c["id"]}; page {c["page"]}\n{c["text"]}' for c in items)
        def call(text, schema, chunks):
            return providers.extract_with_evidence(text, schema, chunks)
        def complete(items, schema, scope):
            """Extract, retry invalid output once, then look again for fields left empty."""
            value, quotes = extraction_repair.generate_valid(call, context(items), schema, items)
            keys = extraction_repair.missing_fields(value, schema)
            if not keys: return value, quotes, []
            check()
            try:
                wider, _ = extraction_retrieval.retrieve(extraction_repair.subset_schema(schema, keys), documents, snapshot, scope, widen=2)
                return extraction_repair.fill_missing(call, value, quotes, schema, keys, context(wider), wider)
            except (providers.ProviderError, ValueError):
                return value, quotes, []  # The first result is valid; a failed second look must not lose it.
        filled = list(state.get('filled') or [])
        if data.get('merge_records') and data.get('merge'):
            manifest = data['merge']['sources']
            # Persist individual completed records outside the graph node too:
            # process death inside a multi-document node never loses prior work.
            checkpoint_ref = 'jobs/' + jid + '/records-' + signature + '.json'
            try: records.update(core.store.json(checkpoint_ref))
            except FileNotFoundError: pass
            output = []
            for n, source in enumerate(manifest):
                check(); key = source['key']; items = [c for c in state['selected'] if c.get('record_key') == key]
                if key not in records:
                    scope = [c for c in sources if c.get('source_key') == key] if data['merge'].get('document_id') else [c for c in sources if c['document_id'] == source['document_id']]
                    value, quotes, more = complete(items, data['record_schema'], scope)
                    validate(value, data['record_schema']); records[key] = {'fields': value, 'evidence': quotes}
                    filled += [source['name'] + ': ' + field for field in more]
                    core.store.put_json(checkpoint_ref, records)
                output.append({'source_filename': source['name'], 'source_key': key, 'fields': records[key]['fields']})
                evidence.extend(q | {'field': f'/records/{n}/fields' + q['field'], 'source_key': key, 'source_filename': source['name']} for q in records[key]['evidence'])
                data['record_progress'] = {'completed': n + 1, 'total': len(manifest), 'current_filename': source['name']}
                core.store.put_json(record.ref, data)
            result = {'records': output}
        else:
            result, evidence, filled = complete(state['selected'], data['schema'], sources)
        stage('generate', 'completed')
        return {'result': result, 'evidence': evidence, 'records': records, 'filled': filled}

    def validate_result(state):
        stage('validate'); validate(state['result'], data['schema'])
        parquet_results.encoded(state['result']); stage('validate', 'completed')
        return {}

    def persist(state):
        stage('writing_output')
        output = parquet_results.persist(record.id, record.version, data | {'result': state['result'], 'evidence': state['evidence']})
        stage('writing_output', 'completed'); return {'output': output}

    graph = StateGraph(State)
    for name, node in [('retrieving', retrieve), ('generate', generate), ('validate', validate_result), ('writing_output', persist)]: graph.add_node(name, node)
    graph.add_edge(START, 'retrieving'); graph.add_edge('retrieving', 'generate')
    graph.add_edge('generate', 'validate'); graph.add_edge('validate', 'writing_output'); graph.add_edge('writing_output', END)
    compiled = graph.compile(checkpointer=saver)
    config = {'configurable': {'thread_id': jid}, 'recursion_limit': 12}
    with tracing_context(enabled=False):
        previous = compiled.get_state(config)
        if previous.values and not previous.next:
            state = previous.values
        else:
            state = compiled.invoke(None if previous.values else {'records': {}}, config)
    # Verify persisted output even when replaying a completed graph after a crash.
    saved = parquet_results.load(data | state['output'])
    if parquet_results.encoded(saved['result']) != parquet_results.encoded(state['result']):
        raise ValueError('Recovered output differs from its validated checkpoint')
    data.update(result=state['result'], evidence=state['evidence'], retrieval=state['diagnostics'], filled_fields=state.get('filled') or [], **state['output'])
    return data
