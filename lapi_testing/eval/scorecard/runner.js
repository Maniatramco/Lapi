// Scorecard runner. It runs in a signed-in Lapi browser tab and uses that session, so no
// password is handled. Load it with cases.json and the files, then call Scorecard.start.
(() => {
  const STORE = 'lapi-scorecard-v1';
  const CHAT_MODEL = 'gpt-4o';
  const RUNS = 3, PARALLEL = 3;
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const REFUSE = /couldn.?t|could not|cannot|can.?t|unable|sorry|not (?:explicitly |directly |specifically )?(?:found|available|provided|stated|mentioned|specified|listed|included|contain|mention)|no (?:information|evidence|record|mention|details|data)|does(?:n.?t| not)|do(?:n.?t| not) (?:explicitly |directly |specifically )?(?:have|provide|contain|mention|state|name|identify|list|include|specify)|isn.?t/i;

  const WORDS = { 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten', 12: 'twelve' };
  const state = JSON.parse(localStorage.getItem(STORE) || 'null') || { dataset: null, extraction: {}, agent: {}, log: [] };
  const save = () => { try { localStorage.setItem(STORE, JSON.stringify(state)); } catch (e) { state.log.push('save failed'); } };
  let csrf = '';

  async function api(path, options = {}) {
    const headers = { 'X-CSRF-Token': csrf };
    let body = options.body;
    if (body && !(body instanceof FormData)) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(body); }
    const response = await fetch('/api' + path, { method: options.method || (body ? 'POST' : 'GET'), headers, body });
    const text = await response.text();
    if (!response.ok) throw new Error(path + ' ' + response.status + ' ' + text.slice(0, 300));
    try { return JSON.parse(text); } catch (e) { return text; }
  }

  const clean = v => String(v == null ? '' : v).toLowerCase().replace(/\s+/g, ' ').trim();

  function dateForms(iso) {
    const [y, m, d] = iso.split('-').map(Number), name = MONTHS[m - 1], short = name.slice(0, 3);
    const dd = String(d).padStart(2, '0'), mm = String(m).padStart(2, '0');
    return [iso, `${d} ${name} ${y}`, `${dd} ${name} ${y}`, `${name} ${d}, ${y}`, `${name} ${d} ${y}`, `${d} ${short} ${y}`, `${short} ${d}, ${y}`, `${d}th ${name} ${y}`, `${d}st ${name} ${y}`, `${d}nd ${name} ${y}`, `${d}rd ${name} ${y}`, `${dd}/${mm}/${y}`, `${mm}/${dd}/${y}`, `${dd}-${mm}-${y}`, `${d} ${name}`, `${name} ${d}`].map(clean);
  }

  function numberIn(answer, want) {
    const text = String(answer).replace(/(\d),(?=\d)/g, '$1').replace(/\[\d+\]/g, ' ');
    if (WORDS[want] && new RegExp('\\b' + WORDS[want] + '\\b', 'i').test(text)) return true;
    const forms = [String(want), want.toFixed(2), want.toFixed(1)];
    if (forms.some(f => new RegExp('(^|[^\\d.])' + f.replace('.', '\\.') + '(?![\\d])').test(text))) return true;
    const lakh = text.match(/(\d+(?:\.\d+)?)\s*(lakh|crore)/gi) || [];
    return lakh.some(item => { const m = item.match(/([\d.]+)\s*(lakh|crore)/i); return Math.abs(parseFloat(m[1]) * (/crore/i.test(m[2]) ? 1e7 : 1e5) - want) < 0.5; });
  }

  function found(answer, item) {
    if (item.kind === 'number') return numberIn(answer, item.want);
    if (item.kind === 'date') { const low = clean(answer); return dateForms(item.want).some(f => low.includes(f)); }
    return clean(answer).includes(clean(item.want));
  }

  function fieldCorrect(got, field) {
    const empty = got === null || got === undefined || got === '' || (Array.isArray(got) && !got.length);
    if (field.kind === 'absent') return empty;
    if (empty) return false;
    if (field.kind === 'number') return Math.abs(Number(String(got).replace(/,/g, '')) - field.want) < 0.011 || numberIn(String(got), field.want);
    return found(String(got), field);
  }

  async function prepare(files, cases) {
    if (state.dataset) return;
    const spaces = await api('/workspaces');
    const list = Array.isArray(spaces) ? spaces : (spaces.workspaces || spaces.items || []);
    const home = list.find(w => /personal/i.test(w.audience || '')) || list[0];
    const made = await api('/datasets', { body: { name: 'QA Scorecard (safe to delete)', description: 'Made-up test files for the accuracy scorecard.', workspace_id: home.id, collection_type: 'Other' } });
    state.dataset = made.id; save();
    const wanted = files.filter(f => cases.files.includes(f.name));
    for (let i = 0; i < wanted.length; i += 4) {
      const form = new FormData();
      wanted.slice(i, i + 4).forEach(f => form.append('files', f));
      form.append('dataset_id', state.dataset); form.append('allow_external', 'true');
      await api('/documents/upload', { body: form });
    }
    state.log.push('uploaded ' + wanted.length); save();
  }

  async function waitForDocuments() {
    for (;;) {
      const docs = await api('/documents?dataset_id=' + state.dataset);
      state.documents = docs.map(d => ({ id: d.id, name: d.name, status: d.status, error: d.error })); save();
      if (docs.every(d => ['ready', 'failed'].includes(d.status))) return docs;
      await new Promise(r => setTimeout(r, 5000));
    }
  }

  async function extractions(cases, docs) {
    const jobs = {};
    for (const item of cases.extraction) {
      if (state.extraction[item.id] && state.extraction[item.id].done) continue;
      const doc = docs.find(d => d.name === item.file);
      if (!doc || doc.status !== 'ready') { state.extraction[item.id] = { done: true, status: 'document ' + (doc ? doc.status : 'missing'), error: doc && doc.error, rows: item.fields.map(f => ({ key: f.key, kind: f.kind, ok: false, want: f.want, got: null })) }; continue; }
      const properties = {};
      item.fields.forEach(f => { properties[f.key] = { type: [f.kind === 'number' ? 'number' : 'string', 'null'], description: f.desc + (f.kind === 'date' ? ' as YYYY-MM-DD' : '') + '. Null when the document does not state it.' }; });
      const template = await api('/templates', { body: { name: 'QA ' + item.id, dataset_id: state.dataset, schema: { type: 'object', properties, required: Object.keys(properties), additionalProperties: false } } });
      const job = await api('/extractions', { body: { document_ids: [doc.id], template_id: template.id, dataset_id: state.dataset, allow_external: true, display_name: 'QA ' + item.id, idempotency_key: 'scorecard-' + state.dataset + item.id } });
      jobs[item.id] = job.id;
    }
    const started = Date.now();
    while (Object.keys(jobs).length && Date.now() - started < 3600000) {
      for (const item of cases.extraction) {
        if (!jobs[item.id]) continue;
        const e = await api('/extractions/' + jobs[item.id]);
        if (['ready', 'completed', 'failed', 'cancelled'].includes(e.status)) {
          state.extraction[item.id] = { done: true, status: e.status, error: e.error, filled: e.filled_fields, retrieval: e.retrieval && { added: e.retrieval.sources_added, noText: e.retrieval.sources_without_text },
            rows: item.fields.map(f => { const got = e.result ? e.result[f.key] : null; return { key: f.key, kind: f.kind, ok: fieldCorrect(got, f), want: f.want, got }; }) };
          delete jobs[item.id]; save();
        }
      }
      await new Promise(r => setTimeout(r, 6000));
    }
    Object.keys(jobs).forEach(id => { state.extraction[id] = { done: true, status: 'timed out', rows: cases.extraction.find(x => x.id === id).fields.map(f => ({ key: f.key, kind: f.kind, ok: false, want: f.want, got: null })) }; });
    save();
  }

  async function oneTurn(item, run, model) {
    const started = Date.now();
    const record = { id: item.id, run, category: item.category, doc_type: item.doc_type };
    try {
      let conversation = '', message = null, plan = null;
      for (const text of item.turns) {
        plan = await api('/agent-v2/plans', { body: { text, planner_model_id: model, dataset_id: state.dataset, conversation_id: conversation, allow_external: true } });
        conversation = plan.conversation_id;
        const thread = await api('/conversations/' + conversation);
        message = thread.messages[thread.messages.length - 1];
      }
      const answer = (message && message.text) || '';
      record.answer = answer.slice(0, 1500);
      const route = (message && message.request_route) || {}, validation = route.validation || {};
      record.route = route.routing_mode; record.validation = validation.result; record.removed = validation.removed_sentences;
      record.support = validation.answer_support && validation.answer_support.status;
      record.tools = ((message && message.tool_trace) || []).map(o => o.tool);
      record.toolErrors = ((message && message.tool_trace) || []).filter(o => o.result && o.result.error).map(o => o.tool + ': ' + String(o.result.error).slice(0, 120));
      record.missing = item.must.filter(m => !found(answer, m)).map(m => m.want);
      if (item.refuse && !REFUSE.test(answer)) record.missing.push('a refusal');
      if (item.format === 'json') { try { JSON.parse(answer.replace(/```json|```/g, '').trim()); } catch (e) { record.missing.push('valid JSON'); } }
      if (item.format === 'three_bullets') { const count = answer.split('\n').filter(l => /^\s*(?:[-*•]|\d+[.)])\s/.test(l)).length; if (count !== 3) record.missing.push('3 bullets, got ' + count); }
      record.pass = !record.missing.length;
    } catch (e) { record.error = String(e).slice(0, 300); record.pass = false; }
    record.seconds = Math.round((Date.now() - started) / 1000);
    return record;
  }

  async function agents(cases) {
    const fresh = (await api('/datasets')).find(d => d.id === state.dataset);
    const model = (fresh.chat_choices || []).find(c => c.name === CHAT_MODEL) || (fresh.chat_choices || [])[0];
    const queue = [];
    for (let run = 1; run <= RUNS; run++) cases.agent.forEach(item => { if (!state.agent[item.id + '#' + run]) queue.push([item, run]); });
    await Promise.all(Array.from({ length: PARALLEL }, async () => {
      while (queue.length) {
        const [item, run] = queue.shift();
        state.agent[item.id + '#' + run] = await oneTurn(item, run, model.id);
        save();
      }
    }));
  }

  function pct(ok, total) { return total ? Math.round(ok * 1000 / total) / 10 + '% (' + ok + '/' + total + ')' : 'none'; }

  function summary() {
    const byType = {}; let ok = 0, total = 0; const wrongFields = [];
    Object.entries(state.extraction).forEach(([id, e]) => {
      const type = id.startsWith('inv_') ? 'text_pdf' : id.startsWith('contract') ? 'long_pdf' : id.startsWith('scan') ? 'scan' : id.startsWith('photo') ? 'photo' : id.startsWith('hand') ? 'handwriting' : id.startsWith('docx') ? 'word' : 'excel';
      byType[type] = byType[type] || [0, 0];
      e.rows.forEach(r => { byType[type][1]++; total++; if (r.ok) { byType[type][0]++; ok++; } else wrongFields.push({ doc: id, field: r.key, want: r.want, got: r.got }); });
    });
    const records = Object.values(state.agent), group = (key) => { const out = {}; records.forEach(r => { const k = key(r); if (!k) return; out[k] = out[k] || [0, 0]; out[k][1]++; if (r.pass) out[k][0]++; }); return Object.fromEntries(Object.entries(out).map(([k, v]) => [k, pct(v[0], v[1])])); };
    const failed = {};
    records.filter(r => !r.pass).forEach(r => { (failed[r.id] = failed[r.id] || []).push({ run: r.run, missing: r.missing, error: r.error, validation: r.validation, removed: r.removed, support: r.support, toolErrors: r.toolErrors, answer: (r.answer || '').slice(0, 200) }); });
    return { dataset: state.dataset, documents: state.documents && state.documents.filter(d => d.status !== 'ready'),
      extraction: { overall: pct(ok, total), byType: Object.fromEntries(Object.entries(byType).map(([k, v]) => [k, pct(v[0], v[1])])), filled: Object.entries(state.extraction).flatMap(([k, e]) => (e.filled || []).map(f => k + ':' + f)), statuses: Object.fromEntries(Object.entries(state.extraction).filter(([, e]) => !['ready', 'completed'].includes(e.status)).map(([k, e]) => [k, e.status + ' ' + (e.error || '')])), wrongFields },
      agent: { turns: records.length, overall: pct(records.filter(r => r.pass).length, records.length), byCategory: group(r => r.category), byFileType: group(r => r.doc_type), byRun: group(r => 'run' + r.run), routes: group(r => r.route || 'none'), medianSeconds: records.map(r => r.seconds).sort((a, b) => a - b)[records.length >> 1], supportStatus: group(r => r.support || 'none'), failed } };
  }

  // Re-score saved answers with the current rules, without using model quota, and drop
  // turns that never got an answer so the next start runs them again.
  function regrade(cases) {
    Object.entries(state.agent).forEach(([key, r]) => {
      const item = cases.agent.find(c => c.id === r.id);
      if (!item || r.error) { delete state.agent[key]; return; }
      const answer = r.answer || '';
      r.missing = item.must.filter(m => !found(answer, m)).map(m => m.want);
      if (item.refuse && !REFUSE.test(answer)) r.missing.push('a refusal');
      if (item.format === 'json') { try { JSON.parse(answer.replace(/```json|```/g, '').trim()); } catch (e) { r.missing.push('valid JSON'); } }
      if (item.format === 'three_bullets') { const count = answer.split('\n').filter(l => /^\s*(?:[-*\u2022]|\d+[.)])\s/.test(l)).length; if (count !== 3) r.missing.push('3 bullets, got ' + count); }
      r.pass = !r.missing.length;
    });
    save();
  }

  window.Scorecard = {
    state, summary, regrade, phase: 'idle',
    async start(files, cases) {
      const me = await api('/auth/me'); csrf = me.csrf_token;
      try {
        this.phase = 'upload'; await prepare(files, cases);
        this.phase = 'reading documents'; const docs = await waitForDocuments();
        this.phase = 'extraction'; await extractions(cases, docs);
        this.phase = 'agent'; await agents(cases);
        this.phase = 'done';
      } catch (e) { this.phase = 'stopped: ' + String(e).slice(0, 300); }
      save();
    },
  };
})();
