"use client";
import {ActionButton} from "./action-button";
import { useEffect, useState } from "react";
import { Check, Layers, Search, X, Pencil, Coins } from "lucide-react";
import { ModelPrices } from "./model-prices";
import "./model-configuration.css";
import { type ParameterSchema, type ParameterValues, type StageValues, cleanStages, formatValue, parseModelParameters, schemaPath, sourceLabel, supportedModelParameters, testStages, valuesError } from "./model-parameters";
import { ParameterForm, ParameterHistory } from "./model-parameter-form";
import "./knowledge-index-banner.css";
import { SummaryTiles } from "./summary-tiles";

type Entity = Record<string, any>;
type Api = (path: string, method?: string, body?: unknown) => Promise<any>;
type ProviderChoice = {id: string; name: string; protocol: string; endpoint: string; region: string; auth_modes: string[]; categories: string[]};
function providerId(connection: Entity) {
  if (connection.protocol !== "openai-compatible") return connection.protocol;
  try { const host = new URL(connection.endpoint).hostname; return host === "generativelanguage.googleapis.com" ? "gemini" : host === "api.openai.com" ? "openai" : "openai-compatible"; } catch { return "openai-compatible"; }
}
const authOptions: Record<string, [string, string][]> = {
  anthropic: [["api_key", "API key"]],
  ollama: [["none", "No credentials · local service"]],
  "openai-compatible": [["api_key", "API key"], ["bearer_token", "Bearer token"]],
  "azure-openai": [["api_key", "API key"], ["bearer_token", "Bearer token"]],
  bedrock: [["aws_keys", "Access keys"], ["server_identity", "Server / workload identity"]],
  vertex: [["service_account", "Service account JSON"], ["server_identity", "Server / workload identity"], ["bearer_token", "Bearer token"]],
  oci: [["oci_credentials", "API signing credentials"], ["server_identity", "Resource principal"], ["config_profile", "Server credential profile"]],
};
const endpointHints: Record<string, string> = {
  anthropic: "https://api.anthropic.com/v1",
  ollama: "http://127.0.0.1:11435", "openai-compatible": "https://your-service.example.com/v1",
  "azure-openai": "https://your-resource.openai.azure.com/openai/v1",
  bedrock: "https://bedrock-runtime.us-east-1.amazonaws.com",
  vertex: "https://us-central1-aiplatform.googleapis.com", oci: "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
};
const credentialFields: Record<string, [string, string, boolean?][]> = {
  api_key: [["api_key", "API key"]], bearer_token: [["token", "Bearer token"]],
  aws_keys: [["access_key_id", "Access key ID"], ["secret_access_key", "Secret access key"], ["session_token", "Session token (optional)"]],
  service_account: [["service_account", "Service account JSON", true]],
  oci_credentials: [["tenancy", "Tenancy OCID"], ["user", "User OCID"], ["fingerprint", "Key fingerprint"], ["key_content", "Private key (PEM)", true], ["pass_phrase", "Key passphrase (optional)"]],
};

const ROLE_KEYS: Record<string, string> = { chat: "chat_model_id", extraction: "extraction_model_id", embedding: "embedding_model_id", ocr: "ocr_model_id" };
const ROLE_LABELS: Record<string, string> = { chat: "Chat", extraction: "Extraction", embedding: "Embedding", ocr: "OCR" };
const INDEX_CONFIRMATION = "I understand the knowledge index will be deleted and rebuilt";
/** Registrations need a passing connection test for their saved version. */
function connectionTested(model: Entity) {
  return !model.connection || model.connection_test?.connection_profile_version === model.connection_profile_version;
}

/** Chat APIs each provider offers. OpenAI-compatible and Azure OpenAI let the admin choose. */
const CHAT_APIS: Record<string, { value: string; label: string }[]> = {
  "openai-compatible": [{ value: "chat_completions", label: "Chat Completions (/chat/completions)" }, { value: "responses", label: "Responses (/responses)" }],
  "azure-openai": [{ value: "chat_completions", label: "Chat Completions (/chat/completions)" }, { value: "responses", label: "Responses (/responses)" }],
  anthropic: [{ value: "chat_completions", label: "Messages API" }],
  bedrock: [{ value: "chat_completions", label: "Converse API" }],
  vertex: [{ value: "chat_completions", label: "generateContent" }],
  oci: [{ value: "chat_completions", label: "OCI Generative AI chat" }],
  ollama: [{ value: "chat_completions", label: "Ollama chat (/api/chat)" }],
};

const USES: [string, string][] = [["chat", "Chat"], ["extraction", "Extraction"], ["ocr", "OCR"], ["embedding", "Embedding"]];
/** The use the connection test and parameter fields follow; Chat first, Embedding only on its own. */
const primaryUse = (uses: string[]) => uses.includes("chat") ? "chat" : uses.includes("extraction") ? "extraction" : uses.includes("ocr") ? "ocr" : "embedding";
/** OCR runs at the Extraction stage with Extraction's parameters. */
const parameterCategory = (category: string) => category === "ocr" ? "extraction" : category;
const companionName = (name: string) => `${name.trim().slice(0, 108)} (embedding)`;
/** The form keeps `uses` locally; the API takes `capabilities`. */
const withoutUses = ({ uses, ...rest }: Entity) => rest;

export function ModelRegistration({ models, settings, api, run, busy, onSaved, onMapping, onDefaultsChanged }: {
  models: Entity[]; settings: Entity; api: Api; run: (fn: () => Promise<void>) => Promise<void>;
  busy: boolean; onSaved: (model: Entity) => void; onMapping: () => void; onDefaultsChanged?: () => void;
}) {
  const defaults = settings.model_defaults;
  const blank = (): Entity => ({ name: "", category: "chat", uses: ["chat"], provider_model: "", timeout: defaults?.timeout, context_limit: defaults?.context_limit, max_output_tokens: defaults?.max_output_tokens, enabled: true,
    credentials: {}, clear_credentials: false, allow_external: false,
    connection: { protocol: "ollama", endpoint: settings.ollama_endpoint || endpointHints.ollama, auth_mode: "none", region: "", project_id: "", workspace_id: "", compartment_id: "", profile: "DEFAULT", embedding_format: "titan", chat_format: "generic", chat_api: "chat_completions", dimensions: null, structured_output: true } });
  const [form, setForm] = useState<Entity>(blank);
  const [editing, setEditing] = useState<Entity | null>(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [prices, setPrices] = useState<Entity | null>(null);
  const [test, setTest] = useState<Entity | null>(null);
  const [testing, setTesting] = useState(false);
  const [providerChoices, setProviderChoices] = useState<ProviderChoice[]>([]);
  const [providerChoice, setProviderChoice] = useState("ollama");
  const [providerError, setProviderError] = useState("");
  useEffect(() => { let active = true; api("/model-providers").then(value => { if (active) setProviderChoices(value); }).catch(() => { if (active) setProviderError("Provider choices could not load. Reload this screen to retry."); }); return () => { active = false; }; }, [api]);
  const [workspaceDefaults, setWorkspaceDefaults] = useState<Entity | null>(null);
  const [rebuild, setRebuild] = useState<Entity | null>(null);
  const [rebuildAck, setRebuildAck] = useState(false);
  const [rebuildExternal, setRebuildExternal] = useState(false);
  useEffect(() => { let active = true; api("/workspace/defaults").then(value => { if (active) setWorkspaceDefaults(value); }).catch(() => { if (active) setWorkspaceDefaults(null); }); return () => { active = false; }; }, [api, models]);
  const isDefault = (model: Entity, role: string) => !!workspaceDefaults && workspaceDefaults[ROLE_KEYS[role]] === model.id;
  const applyDefault = (model: Entity, role: string, confirmed = false, allowExternal = false) => run(async () => {
    const value = await api(`/model-registrations/${model.id}/default`, "PUT", { role, acknowledge_index_rebuild: confirmed, allow_external: allowExternal });
    setWorkspaceDefaults(value); setRebuild(null); onDefaultsChanged?.();
  });
  const chooseDefault = (model: Entity, role: string) => {
    // Changing the embedding Default deletes the one knowledge index: confirm first.
    if (role === "embedding" && (workspaceDefaults?.embedding_model_id || workspaceDefaults?.impact?.documents)) {
      setRebuild(model); setRebuildAck(false); setRebuildExternal(false); return;
    }
    applyDefault(model, role);
  };
  const rebuildRemote = !!rebuild && (rebuild.connection?.protocol || rebuild.provider) !== "ollama";
  const [extraText, setExtraText] = useState("{}");
  const [extraOpen, setExtraOpen] = useState(false);
  const [schema, setSchema] = useState<ParameterSchema | null>(null);
  const [schemaError, setSchemaError] = useState("");
  const [stageValues, setStageValues] = useState<StageValues>({});
  const [scope, setScope] = useState("model");
  const [history, setHistory] = useState<any[] | null>(null);
  const [historyError, setHistoryError] = useState("");
  const paramCategory = parameterCategory(form.category);
  const schemaKey = schemaPath(form.connection.protocol, paramCategory, form.connection, form.provider_model.trim());
  useEffect(() => {
    if (!open) return;
    let active = true; setSchemaError("");
    api(schemaKey).then(value => { if (active && value && Array.isArray(value.fields)) setSchema(value); else if (active) setSchemaError("Parameter settings could not load. Use Advanced JSON or reload this screen."); })
      .catch(() => { if (active) setSchemaError("Parameter settings could not load. Use Advanced JSON or reload this screen."); });
    return () => { active = false; };
  }, [api, open, schemaKey]);
  const resetParameters = () => { setExtraText("{}"); setStageValues({}); setScope("model"); };
  const change = (key: string, value: any) => { setForm(current => ({ ...current, [key]: value, ...(key === "category" ? { context_limit: value === "embedding" ? defaults?.embedding_context_limit : defaults?.context_limit } : {}) })); if (key === "category") resetParameters(); setTest(null); };
  const uses: string[] = form.uses || [form.category];
  // Embedding alongside Chat/Extraction is saved as a second, embedding-only registration.
  const companion = !editing && uses.includes("embedding") && uses.length > 1;
  const toggleUse = (use: string, on: boolean) => {
    const next = USES.map(([value]) => value).filter(value => value === use ? on : uses.includes(value));
    if (!next.length) return;
    if (primaryUse(next) !== form.category) change("category", primaryUse(next));
    setForm(current => ({ ...current, uses: next, category: primaryUse(next) }));
    setTest(null);
  };
  const connectionChange = (key: string, value: any) => {
    setForm(current => ({ ...current, connection: { ...current.connection, [key]: value },
      ...(["protocol", "endpoint", "auth_mode"].includes(key) ? { credentials: {}, allow_external: false } : {}) }));
    setTest(null);
    if (["protocol", "embedding_format", "chat_format"].includes(key)) resetParameters();
  };
  const start = (model?: Entity) => {
    if (!defaults) return;
    const initial = blank();
    if (model) {
      initial.name = model.name; initial.provider_model = model.provider_model;
      initial.uses = [...model.capabilities]; initial.category = primaryUse(model.capabilities); initial.enabled = model.enabled; initial.timeout = model.timeout || defaults.timeout; initial.context_limit = model.context_limit || (initial.category === "embedding" ? defaults.embedding_context_limit : defaults.context_limit); initial.max_output_tokens = model.max_output_tokens || defaults.max_output_tokens;
      if (model.connection) initial.connection = { ...initial.connection, ...model.connection };
      else if (model.provider !== "ollama") {
        initial.connection = { ...initial.connection, protocol: "openai-compatible", auth_mode: "api_key", endpoint: "" };
      }
    }
    setEditing(model || null); setForm(initial); setExtraText(JSON.stringify(model?.extra_parameters || {}, null, 2)); setExtraOpen(false); setStageValues(model?.stage_parameters || {}); setScope("model"); setSchema(null); setHistory(null); setHistoryError(""); setTest(null); setOpen(true);
    setProviderChoice(providerId(initial.connection));
  };
  const close = () => { setOpen(false); setEditing(null); setForm(blank()); setTest(null); };
  const native = ["bedrock", "vertex", "oci"].includes(form.connection.protocol);
  const remote = form.connection.protocol !== "ollama";
  const visible = models.filter(m => `${m.name} ${m.provider_model} ${m.capabilities.join(" ")}`.toLowerCase().includes(search.toLowerCase()));
  const retainedCredentials = editing?.credential_configured && editing?.connection && ["endpoint", "protocol", "auth_mode"].every(key => editing.connection[key] === form.connection[key]);
  const categories = providerChoices.find(p => p.id === providerChoice)?.categories || ["embedding", "chat", "extraction"];
  const activeSchema = schema && schema.protocol === form.connection.protocol && schema.category === paramCategory ? schema : null;
  const supported = activeSchema ? activeSchema.fields.map(f => f.key) : supportedModelParameters(form.connection.protocol, paramCategory, form.connection);
  let parameterError = "";
  let modelValues: ParameterValues = {};
  try { modelValues = parseModelParameters(extraText, supported) as ParameterValues; } catch (error) { parameterError = (error as Error).message; }
  const stagesSent = form.category === "embedding" ? {} : cleanStages(activeSchema, stageValues);
  parameterError = parameterError || valuesError(activeSchema, modelValues) || Object.values(stagesSent).map(values => valuesError(activeSchema, values)).find(Boolean) || "";
  const setModelValues = (values: ParameterValues) => { setExtraText(JSON.stringify(values, null, 2)); setTest(null); };
  const setStages = (values: StageValues) => { setStageValues(values); setTest(null); };
  const loadHistory = () => { if (!editing || history) return; setHistoryError(""); api(`/model-registrations/${editing.id}/parameter-history`).then(value => setHistory(Array.isArray(value?.history) ? value.history : [])).catch(() => setHistoryError("Parameter history could not load.")); };
  // A provider with one chat API always sends its default, whatever was chosen before switching.
  const chatApi = (CHAT_APIS[form.connection.protocol] || []).some(api => api.value === form.connection.chat_api) ? form.connection.chat_api : "chat_completions";
  const payload = () => ({ ...withoutUses(form), capabilities: form.category === "embedding" ? ["embedding"] : uses.filter(u => u !== "embedding"), connection: { ...form.connection, chat_api: chatApi }, max_output_tokens: form.category === "embedding" ? null : form.max_output_tokens, extra_parameters: parseModelParameters(extraText, supported), stage_parameters: stagesSent, existing_model_id: editing?.id || null });
  const testPayload = () => ({ ...payload(), test_stages: form.category === "ocr" ? [] : testStages(form.category, modelValues, stagesSent) });
  // Built the same way for its test and its save, so the passed test counts for Defaults.
  const companionPayload = () => ({ ...withoutUses(form), name: companionName(form.name), category: "embedding", capabilities: ["embedding"],
    connection: { ...form.connection, chat_api: "chat_completions" }, context_limit: defaults?.embedding_context_limit, max_output_tokens: null,
    extra_parameters: {}, stage_parameters: {}, existing_model_id: null });
  /** Test every ticked use: the main one, Extraction alongside Chat, and the embedding registration. */
  const testAll = async () => {
    const result = await api("/model-registrations/test", "POST", testPayload());
    if (form.category === "chat" && uses.includes("extraction")) {
      const extraction = await api("/model-registrations/test", "POST", { ...payload(), category: "extraction", test_stages: [] });
      result.schema_validated = extraction.schema_validated;
    }
    // OCR is proven by reading a sample image, whichever use leads the test.
    if (form.category !== "ocr" && uses.includes("ocr")) result.ocr_validated = (await api("/model-registrations/test", "POST", { ...payload(), category: "ocr", test_stages: [] })).ocr_validated;
    if (companion) result.dimensions = (await api("/model-registrations/test", "POST", companionPayload())).dimensions;
    result.passed_uses = uses;
    return result;
  };
  const stageLabel = (key: string) => activeSchema?.stages.find(s => s.key === key)?.label || (key === "tool_step" ? "Tool steps" : key === "extraction" ? "Extraction" : key === "optimize" ? "Optimize" : "Chat answer");

  return <div className="model-registration">
    {settings.local_only && <div className="notice"><Layers size={17} /><div>This deployment runs in local-only mode. You can register cloud connections, but testing and applying them require cloud use to be enabled by the deployment administrator.</div></div>}
    {!open && !!models.length && <SummaryTiles label="Registered model summary" tiles={[
      { label: "Registered", value: models.length, detail: `${models.filter(m => m.enabled).length} enabled`, tone: "" },
      { label: "Chat & extraction", value: models.filter(m => (m.capabilities || [m.category]).some((c: string) => c === "chat" || c === "extraction")).length, detail: "answer and extract", tone: "info" },
      { label: "Embedding", value: models.filter(m => (m.capabilities || [m.category]).includes("embedding")).length, detail: "index knowledge", tone: "ok" },
      { label: "Disabled", value: models.filter(m => !m.enabled).length, detail: "not offered for new work", tone: "warn" },
    ]}/>}
    {!open ? <section className="panel registration-directory">
      <div className="panel-head"><span className="pill">{models.length} models</span><ActionButton className="btn primary" disabled={busy || !defaults} onClick={() => start()} label="Register model" action="add" showLabel/></div>
      {!!models.length && <label className="registration-search"><Search size={16} aria-hidden="true" /><input type="search" aria-label="Search registered models" value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e=>{if(e.key==='Escape')setSearch('');}} placeholder="Search models or categories" />{search&&<button className="btn icon" type="button" title="Clear search" aria-label="Clear model search" onClick={()=>setSearch('')}><X size={14}/></button>}</label>}
      {!!models.length && <div className="registration-table" role="region" aria-label="Registered models table" tabIndex={0}>
        <table aria-label="Registered models"><thead><tr><th scope="col">Model</th><th scope="col">Category</th><th scope="col" title="One overall Default per role. Collections may override Chat, Extraction and OCR; the Embedding Default builds the one knowledge index.">Default</th><th scope="col">Provider</th><th scope="col">Endpoint</th><th scope="col" className="registration-tokens" title="Configured input limit for embeddings; total context limit for chat and extraction">Input / context</th><th scope="col" className="registration-tokens" title="Configured maximum output tokens">Output</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
          <tbody>{visible.map(m=><tr key={m.id}>
            <th scope="row"><div className="registration-model-cell"><Layers size={16} aria-hidden="true"/><div><strong>{m.name}</strong><small>{m.provider_model}</small>{(()=>{const count=Object.keys(m.extra_parameters||{}).length+Object.values(m.stage_parameters||{}).reduce((n:number,v:any)=>n+Object.keys(v||{}).length,0);return count>0&&<small>{count} parameter{count===1?'':'s'} set{m.parameter_version?` · v${m.parameter_version}`:''}</small>;})()}</div></div></th>
            <td><div className="model-chips">{m.capabilities.map((cap:string)=><span className="model-chip" key={cap}>{ROLE_LABELS[cap]||cap}</span>)}{m.capabilities.filter((cap:string)=>isDefault(m,cap)).map((cap:string)=><span className="model-chip is-default" key={'default-'+cap} title={`Collection ${ROLE_LABELS[cap]} Default`}>{m.capabilities.length>1?`${ROLE_LABELS[cap]} default`:'Default'}</span>)}</div></td>
            <td><div className="model-default-cell">{m.capabilities.map((cap:string)=>{const current=isDefault(m,cap);const tested=connectionTested(m)&&(cap!=='ocr'||m.ocr_eligible===true);return <label className="check" key={cap} title={current?`Collection ${ROLE_LABELS[cap]} Default. Choose another model to change it.`:!m.enabled?'Enable this model to make it a Default.':!tested?(cap==='ocr'?'Test this model with OCR ticked (it reads a sample image), then save, before making it the OCR Default.':'Test and save this connection before making it a Default.'):`Make ${m.name} the collection ${ROLE_LABELS[cap]} Default`}><input type="checkbox" aria-label={`${ROLE_LABELS[cap]} Default: ${m.name}`} checked={current} disabled={busy||current||!workspaceDefaults||!m.enabled||!tested} onChange={()=>chooseDefault(m,cap)}/>{m.capabilities.length>1?ROLE_LABELS[cap]:'Default'}</label>;})}</div></td>
            <td>{providerChoices.find(p=>p.id===providerId(m.connection||{protocol:m.provider}))?.name||m.provider}</td>
            <td><span className="registration-endpoint" title={m.connection?.endpoint||'No endpoint configured'}>{m.connection?.endpoint||'—'}</span></td>
            <td className="registration-tokens" title={m.capabilities[0]==='embedding'?'Input tokens':'Context tokens'}>{m.context_limit?.toLocaleString()||'—'}</td>
            <td className="registration-tokens" title={m.capabilities[0]==='embedding'?'Not applicable to embeddings':'Maximum output tokens'}>{m.capabilities[0]==='embedding'?'—':m.max_output_tokens?.toLocaleString()||'—'}</td>
            <td><span className={`pill ${m.enabled?'green':'amber'}`}>{m.enabled?'Enabled':'Disabled'}</span></td>
            <td><button className="btn icon registration-edit" disabled={busy || !defaults} title={`Edit ${m.name}`} aria-label={`Edit ${m.name}`} onClick={()=>start(m)}><Pencil size={15}/></button><button className="btn icon registration-edit" title={`Prices for ${m.name}`} aria-label={`Prices for ${m.name}`} aria-pressed={prices?.id===m.id} onClick={()=>setPrices(prices?.id===m.id?null:m)}><Coins size={15}/></button></td>
          </tr>)}{!visible.length&&<tr><td colSpan={9} className="registration-table-empty">No models match your search.</td></tr>}</tbody>
        </table>
      </div>}
      {!models.length && <div className="empty"><Layers size={30} /><h3>Start with your models</h3><p>Register an Embedding, Chat, Extraction and OCR model, test each connection, and mark one Default per role. The Embedding Default builds the one knowledge index for every collection.</p></div>}
      <div className="registration-footer"><ActionButton className="btn" onClick={onMapping} label="Open Model Mapping" action="mapping"/></div>
    </section> : null}
    {!open && prices && models.some(m => m.id === prices.id) && <ModelPrices key={prices.id} model={prices} api={api} onClose={() => setPrices(null)} />}
    {open && <section className="panel registration-form-panel">
      <form onSubmit={e => { e.preventDefault(); if (!test) return; run(async () => { const saved = await api(`/model-registrations${editing ? "/" + editing.id : ""}`, editing ? "PUT" : "POST", payload()); onSaved(saved); if (companion) onSaved(await api("/model-registrations", "POST", companionPayload())); close(); }); }}>
        <div className="panel-head"><h2>{editing ? "Edit model" : "Register model"}</h2><button title="Cancel model registration" className="btn icon" type="button" aria-label="Cancel model registration" disabled={busy} onClick={close}><X size={16} /></button></div>
        {form.connection.protocol === "anthropic" && <div className="notice"><Layers size={17} /><div>Direct Claude for Agent and Collection Knowledge Chat. After testing and saving, enable it in Model Mapping, Save & Apply, then select it in chat. Keep your existing Embedding and Extraction models.</div></div>}
        <fieldset disabled={busy}>
          <div className="registration-fields">
            <div className="field"><label htmlFor="registration-name">Name</label><input id="registration-name" autoFocus value={form.name} onChange={e => change("name", e.target.value)} required maxLength={120} placeholder="e.g. Document extraction" /></div>
            <fieldset className="field registration-uses"><legend>Use for</legend><div className="row wrap">{USES.filter(([value]) => categories.includes(value)).map(([value, label]) => {
              const locked = !!editing && (value === "embedding" || editing.capabilities.includes("embedding"));
              return <label className="check" key={value} title={locked ? "An Embedding model and a Chat, Extraction or OCR model are separate registrations; register another model instead." : value === "ocr" ? "OCR reads text from images and scanned pages. Test connection sends a small sample image to check the model can read it." : undefined}>
                <input type="checkbox" checked={uses.includes(value)} disabled={locked} onChange={e => toggleUse(value, e.target.checked)} />{label}</label>; })}</div>
              <small>{companion ? `Saves two registrations of ${form.provider_model.trim() || "this model"}: ${uses.filter((u: string) => u !== "embedding").map((u: string) => ROLE_LABELS[u]).join(" and ")}, and “${companionName(form.name || "Model")}” for Embedding with default embedding settings (edit it after saving).` : uses.length > 1 ? `One registration used for ${uses.length === 2 ? "both" : "all of them"}. Each role can be a overall Default separately.` : "Tick more than one to use the same model for several roles."}</small></fieldset>
            <div className="field"><label htmlFor="registration-protocol">Provider</label><select id="registration-protocol" value={providerChoice} disabled={!providerChoices.length} onChange={e => { const choice = providerChoices.find(p => p.id === e.target.value); if (!choice) return; setProviderChoice(choice.id); resetParameters(); const protocol = choice.protocol; const kept = (current: Entity) => { const uses = (current.uses || [current.category]).filter((u: string) => choice.categories.includes(u)); return uses.length ? uses : [choice.categories[0]]; }; setForm(current => ({ ...current, uses: kept(current), category: primaryUse(kept(current)), context_limit: primaryUse(kept(current)) === current.category ? current.context_limit : primaryUse(kept(current)) === "embedding" ? defaults?.embedding_context_limit : defaults?.context_limit, provider_model: "", credentials: {}, clear_credentials: false, allow_external: false, connection: { ...blank().connection, protocol, region: choice.region, endpoint: protocol === "ollama" ? settings.ollama_endpoint || choice.endpoint : choice.endpoint, auth_mode: choice.auth_modes[0] } })); setTest(null); }}>{providerChoices.length ? providerChoices.map(p => <option key={p.id} value={p.id} disabled={!!editing && !p.categories.includes(form.category)}>{p.name}</option>) : <option value="ollama">Loading providers…</option>}</select>{providerError && <small role="alert">{providerError}</small>}</div>
            <div className="field"><label htmlFor="registration-model">Model / deployment ID</label><input id="registration-model" value={form.provider_model} onChange={e => change("provider_model", e.target.value)} required maxLength={200} placeholder={form.connection.protocol === "azure-openai" ? "Deployment name" : "Model ID"} /></div>
            <div className="field registration-full"><label htmlFor="registration-endpoint">Endpoint</label><input id="registration-endpoint" type="url" value={form.connection.endpoint} onChange={e => connectionChange("endpoint", e.target.value)} required maxLength={500} placeholder={endpointHints[form.connection.protocol]} /><small>{form.connection.protocol === "anthropic" ? "Direct Claude uses this official endpoint. Enter the exact model ID supplied with your API access." : "Use the service base URL. Custom gateway hosts must be approved in the deployment."}</small></div>
            {form.connection.protocol === "anthropic" && <div className="field registration-full"><label htmlFor="registration-workspace">Anthropic workspace ID (optional)</label><input id="registration-workspace" value={form.connection.workspace_id} onChange={e => connectionChange("workspace_id", e.target.value)} maxLength={128} placeholder="wrkspc_…" /><small>Required only when your API key is not scoped to one workspace. Ask your API administrator if needed.</small></div>}
            {native && <div className="field"><label htmlFor="registration-region">Region / location</label><input id="registration-region" value={form.connection.region} onChange={e => connectionChange("region", e.target.value)} required placeholder="e.g. us-east-1" /></div>}
            {form.connection.protocol === "vertex" && <div className="field"><label htmlFor="registration-project">Project ID</label><input id="registration-project" value={form.connection.project_id} onChange={e => connectionChange("project_id", e.target.value)} required /></div>}
            {form.connection.protocol === "oci" && <div className="field"><label htmlFor="registration-compartment">Compartment OCID</label><input id="registration-compartment" value={form.connection.compartment_id} onChange={e => connectionChange("compartment_id", e.target.value)} required /></div>}
            <div className="field"><label htmlFor="registration-auth">Authentication</label><select id="registration-auth" value={form.connection.auth_mode} onChange={e => connectionChange("auth_mode", e.target.value)}>{authOptions[form.connection.protocol].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
            <div className="field"><label htmlFor="registration-timeout">Timeout (seconds)</label><input id="registration-timeout" type="number" min={defaults?.timeout_min} max={defaults?.timeout_max} value={form.timeout} onChange={e => change("timeout", Number(e.target.value))} required /><small>{form.connection.protocol === "anthropic" ? "Time allowed for each Claude response. Longer answers may need a higher limit." : "Detailed local extraction on CPU may need 1,200 seconds. This is a limit, not an estimated completion time."}</small></div>
            <div className="field"><label htmlFor="registration-context-limit">{form.category === "embedding" ? "Input token limit" : "Context token limit"}</label><input id="registration-context-limit" type="number" min={1} max={defaults?.context_max} step={1} value={form.context_limit} onChange={e => change("context_limit", Number(e.target.value))} aria-describedby="registration-context-help" required /><small id="registration-context-help">{form.category === "embedding" ? "Maximum input per text chunk or query. No output tokens; embeddings return vectors." : `Total input and output budget, including instructions and history. Keep ${defaults?.headroom_tokens} tokens of headroom beyond the output limit.`} Lapi uses a conservative text estimate. Set this within the model’s supported capacity.</small></div>
            {form.category !== "embedding" && <div className="field"><label htmlFor="registration-output-limit">Maximum output tokens</label><input id="registration-output-limit" type="number" min={1} max={defaults?.output_max} step={1} value={form.max_output_tokens} onChange={e => change("max_output_tokens", Number(e.target.value))} required /><small>Maximum tokens generated per answer or extraction. Default: {defaults?.max_output_tokens?.toLocaleString()}. Larger limits can take longer and use more memory or provider credits.</small></div>}
            {form.connection.auth_mode === "config_profile" && <div className="field"><label htmlFor="registration-profile">Server credential profile</label><input id="registration-profile" value={form.connection.profile} onChange={e => connectionChange("profile", e.target.value)} required /></div>}
          </div>
          {!!credentialFields[form.connection.auth_mode]?.length && <div className="registration-credentials"><h3>Credentials</h3><p className="muted small">{retainedCredentials ? "Leave all credential fields empty to retain the saved credentials. Enter the complete set to replace them." : "Enter credentials for this endpoint. They are never returned to the browser."}</p><div className="registration-fields">
            {credentialFields[form.connection.auth_mode].map(([key, label, multiline]) => <div className={`field ${multiline ? "registration-full" : ""}`} key={key}><label htmlFor={`credential-${key}`}>{label}</label>{multiline ? <textarea id={`credential-${key}`} rows={4} value={form.credentials[key] || ""} spellCheck={false} autoComplete="off" onChange={e => change("credentials", { ...form.credentials, [key]: e.target.value })} /> : <input id={`credential-${key}`} type="password" autoComplete="new-password" value={form.credentials[key] || ""} onChange={e => change("credentials", { ...form.credentials, [key]: e.target.value })} />}</div>)}
          </div>{!!editing && <label className="check"><input type="checkbox" checked={form.clear_credentials} onChange={e => change("clear_credentials", e.target.checked)} />Remove saved credentials (disable the model first)</label>}</div>}
          {form.connection.auth_mode === "server_identity" && <p className="muted small">The API and worker hosts must have an identity permitted to invoke this model.</p>}
          {form.category === "embedding" && <div className="registration-fields registration-options">
            <div className="field"><label htmlFor="registration-dimensions">Output dimensions (optional)</label><input id="registration-dimensions" type="number" min={1} max={65536} value={form.connection.dimensions || ""} onChange={e => connectionChange("dimensions", e.target.value ? Number(e.target.value) : null)} /><small>Leave empty for the model’s default dimensions.</small></div>
            {form.connection.protocol === "bedrock" && <div className="field"><label htmlFor="registration-embedding-format">Embedding request format</label><select id="registration-embedding-format" value={form.connection.embedding_format} onChange={e => connectionChange("embedding_format", e.target.value)}><option value="titan">Titan Text</option><option value="cohere-v3">Cohere Embed v3</option><option value="cohere-v4">Cohere Embed v4</option></select></div>}
          </div>}
          {form.category !== "embedding" && (() => {
            const apis = CHAT_APIS[form.connection.protocol] || CHAT_APIS["openai-compatible"];
            const value = apis.some(api => api.value === form.connection.chat_api) ? form.connection.chat_api : "chat_completions";
            return <div className="field"><label htmlFor="registration-chat-api">API</label>
              <select id="registration-chat-api" value={value} disabled={apis.length < 2} aria-describedby="registration-chat-api-help"
                onChange={e => connectionChange("chat_api", e.target.value)}>
                {apis.map(api => <option key={api.value} value={api.value}>{api.label}</option>)}
              </select>
              <small id="registration-chat-api-help">{apis.length < 2 ? "The only chat API this provider offers."
                : value === "responses" ? "Supports function tools together with reasoning. Seed, stop and frequency/presence penalties are not sent. Answers are not streamed; OpenAI keeps no copy (store: false)."
                : "The widely supported default. Some reasoning models refuse function tools with reasoning here; choose Responses for them."}</small>
            </div>;
          })()}
          {form.category !== "embedding" && form.connection.protocol === "oci" && <div className="field"><label htmlFor="registration-chat-format">Chat request format</label><select id="registration-chat-format" value={form.connection.chat_format} onChange={e => connectionChange("chat_format", e.target.value)}><option value="generic">Generic</option><option value="cohere">Cohere</option></select></div>}
          {form.category === "extraction" && ["openai-compatible", "azure-openai"].includes(form.connection.protocol) && <label className="check"><input type="checkbox" checked={form.connection.structured_output} onChange={e => connectionChange("structured_output", e.target.checked)} />Request native JSON schema output <span className="muted small">All extraction responses are validated against the template.</span></label>}
          {form.category !== "embedding" || supported.length ? <section className="registration-parameters" aria-labelledby="registration-parameters-title">
            <h3 id="registration-parameters-title">Model parameters</h3>
            <ParameterForm schema={activeSchema} loading={!activeSchema && !schemaError} error={schemaError} model={modelValues} stages={stageValues} scope={scope} onScope={setScope} onModel={setModelValues} onStages={setStages} />
          <details className="registration-options registration-extra" open={extraOpen} onToggle={e => setExtraOpen(e.currentTarget.open)}><summary>Advanced: model-wide parameters as JSON</summary><div className="field"><label htmlFor="registration-extra-parameters">Extra parameters (JSON)</label><small id="registration-parameter-help">{supported.length ? `Supported keys: ${supported.join(", ")}.` : "This adapter has no additional parameters. Use the token limit and dimensions fields."} Leave empty to use defaults; null means use the provider default. The form above edits the same values. Use only options supported by your deployed model. These values are visible to collection users; keep credentials in Authentication.</small><textarea id="registration-extra-parameters" rows={4} spellCheck={false} value={extraText} onChange={e => { setExtraText(e.target.value); setTest(null); }} aria-invalid={!!parameterError} aria-describedby="registration-parameter-help registration-parameter-error" placeholder={form.connection.protocol === "anthropic" ? "{}" : form.category === "embedding" ? '{"keep_alive": "5m"}' : '{"temperature": 0.2}'} />{parameterError && <small id="registration-parameter-error" role="alert">{parameterError}</small>}</div></details>
          </section> : null}
          {!!editing && form.category !== "embedding" && <details className="registration-options registration-history" onToggle={e => { if (e.currentTarget.open) loadHistory(); }}><summary>Parameter history{editing.parameters_updated?.at ? ` · last changed ${new Date(editing.parameters_updated.at * 1000).toLocaleDateString()}${editing.parameters_updated.author?.username ? " by " + editing.parameters_updated.author.username : ""}` : ""}</summary><ParameterHistory history={history} error={historyError} /></details>}
          <div className="registration-options"><label className="check"><input type="checkbox" checked={form.enabled} onChange={e => change("enabled", e.target.checked)} />Enabled for collection mapping</label></div>
          {remote && <label className="check registration-test-consent"><input type="checkbox" checked={form.allow_external} onChange={e => change("allow_external", e.target.checked)} />Allow a small synthetic test request to this external model. Provider usage may be billed.</label>}
        </fieldset>
        {test && <div className="notice" role="status"><Check size={17} /><div>Connection passed in {(test.elapsed_ms / 1000).toFixed(2)}s{test.passed_uses?.length > 1 ? ` for ${test.passed_uses.map((u: string) => USES.find(([v]) => v === u)?.[1]).join(", ")}` : ""}.{test.dimensions && ` Embedding dimensions: ${test.dimensions}.`}{test.schema_validated && " Extraction schema validated."}{test.ocr_validated && " OCR read the sample image."}{test.agent_tool_call_validated && " Agent function calling validated."}
          {!!test.effective_parameters && Object.keys(test.effective_parameters).length > 0 && <ul className="registration-test-effective" aria-label="Settings sent in the test">{Object.entries(test.effective_parameters as Record<string, { parameters: ParameterValues; sources: Record<string, keyof typeof sourceLabel> }>).map(([stage, value]) => <li key={stage}><strong>{stageLabel(stage)}:</strong> {Object.keys(value.parameters).length ? Object.entries(value.parameters).map(([key, v]) => `${key} ${formatValue(v)} (${sourceLabel[value.sources[key]] || "set"})`).join(", ") : "no sampling parameters sent (provider defaults)"}{test.samples?.[stage] && <span className="muted"> · sample answer: “{test.samples[stage]}”</span>}</li>)}</ul>}</div></div>}
        <div className="registration-actions"><button className="btn" type="button" disabled={busy || !!parameterError || !form.name.trim() || !form.provider_model.trim() || !form.connection.endpoint || remote && (!form.allow_external || settings.local_only)} onClick={e => { if (!e.currentTarget.form?.reportValidity()) return; setTest(null); setTesting(true); run(async () => { try { setTest(await testAll()); } finally { setTesting(false); } }); }}>{testing ? "Testing connection…" : "Test Connection"}</button><div className="row wrap"><button className="btn" type="button" disabled={busy} onClick={close}>Cancel</button><ActionButton className="btn primary" disabled={busy || !!parameterError || !test} label="Save Model" action="save"/></div></div>
        <p className="muted small">Test the connection before saving. The test sends a sample prompt with the parameter values above and lists what was sent. Chat tests verify Agent function calling, plus one short sample answer when you change answer-stage values. OCR tests send a small sample image and check its text is read back. New chat and extraction runs use the latest saved connection. Editing the Default embedding model requires re-applying it as Default, which deletes the knowledge index and reindexes every document. Work already queued keeps its saved version.</p>
      </form>
    </section>}
    {rebuild && <div className="modal-bg"><section className="modal index-rebuild-dialog" role="dialog" aria-modal="true" aria-labelledby="index-rebuild-title">
      <h2 id="index-rebuild-title">Rebuild the knowledge index with {rebuild.name}?</h2>
      <p>{rebuild.name} becomes the overall Default embedding model. The current knowledge index is deleted now and rebuilt in the background. There is no rollback.</p>
      <ul>
        <li>{(workspaceDefaults?.impact?.documents ?? 0).toLocaleString()} documents are reindexed.</li>
        <li>{(workspaceDefaults?.impact?.knowledge_items ?? 0).toLocaleString()} knowledge items are deleted and published again.</li>
        <li>Until reindexing finishes, chat answers only from documents that are already reindexed.</li>
      </ul>
      <label className="check"><input type="checkbox" checked={rebuildAck} onChange={e => setRebuildAck(e.target.checked)} />{INDEX_CONFIRMATION}</label>
      {rebuildRemote && <label className="check"><input type="checkbox" checked={rebuildExternal} onChange={e => setRebuildExternal(e.target.checked)} />Allow document text to be sent to {rebuild.name} for reindexing. Provider usage may be billed.</label>}
      <div className="row" style={{ justifyContent: "flex-end", marginTop: 18 }}>
        <button className="btn" type="button" disabled={busy} onClick={() => setRebuild(null)}>Cancel</button>
        <button className="btn primary" type="button" disabled={busy || !rebuildAck || rebuildRemote && !rebuildExternal} onClick={() => applyDefault(rebuild, "embedding", true, rebuildRemote && rebuildExternal)}>Continue</button>
      </div>
    </section></div>}
  </div>;
}
