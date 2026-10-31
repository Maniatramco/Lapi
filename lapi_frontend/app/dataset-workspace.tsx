"use client";
import {ActionButton} from "./action-button";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Database, Layers, Settings2, X } from "lucide-react";
import "./dataset-focus.css";
import "./model-configuration.css";
import {useDatasetLifecycle} from "./dataset-lifecycle";
import {DirectoryRows,directorySummary} from "./dataset-directory";
import {SummaryTiles} from "./summary-tiles";
import {AgentOnboarding} from "./agent-onboarding";
import {selectMappingDefault,setMappingEnabled,type MappingDraft} from './dataset-mapping-draft';

type Entity = Record<string, any>;
type Api = (path: string, method?: string, body?: unknown) => Promise<any>;
export const eligibleModels = (dataset: Entity | undefined, capability: string): Entity[] =>
  (dataset?.active === false ? [] : dataset?.models || []).filter((m: Entity) => m.enabled !== false && m.mapping_enabled !== false && m.capabilities?.includes(capability));
export const modelLabel = (model: Entity | undefined) => model?.name || model?.provider_model || "Model not selected";
export function ModelPicker({ dataset, capability, value, onChange, onConfigure, disabled = false }: {
  dataset?: Entity; capability: "chat" | "extraction"; value: string; onChange: (id: string) => void; onConfigure: () => void; disabled?: boolean;
}) {
  const models = eligibleModels(dataset, capability);
  const label = capability === "chat" ? "Chat model" : "Extraction model";
  const [localModels,setLocalModels]=useState<Entity | null>(null);
  const selected=models.find(m=>m.id===value) || (models.length===1 ? models[0] : undefined);
  const local=selected?.provider==="ollama";
  useEffect(()=>{let active=true;if(local)fetch("/api/local-models",{credentials:"include"}).then(r=>r.ok?r.json():null).then(data=>{if(active)setLocalModels(data);}).catch(()=>{if(active)setLocalModels({available:false,models:[]});});return()=>{active=false;};},[local,value]);
  const installed=localModels?.models?.some((m:Entity)=>m.name===selected?.provider_model || m.name===selected?.provider_model+":latest");

  const defaultId = dataset?.[capability === "chat" ? "default_chat_model_id" : "default_extraction_model_id"];
  return <div className="model-picker">
    <label className="control-label">{label}</label>
    {!dataset ? <div className="model-readonly muted"><Layers size={15} />Choose a collection first</div> : dataset.active === false ? <div className="model-unavailable"><strong>This collection is inactive</strong><p>Ask your administrator to activate it before starting new work.</p></div> : models.length === 0 ?
      <div className="model-unavailable"><strong>No eligible {capability} models</strong><p>Map an enabled model with {capability} capability to this collection.</p><ActionButton type="button" className="text-button" onClick={onConfigure} label="Configure collection models" action="mapping"/></div> : models.length === 1 ?
      <div className="model-readonly" aria-label={label}><Layers size={16} /><span>{modelLabel(models[0])}<small>{models[0].provider_model} · Only eligible model</small></span><CheckCircle2 size={15} /></div> :
      <select aria-label={label} value={value} onChange={e => onChange(e.target.value)} disabled={disabled}><option value="" disabled>Select a mapped model</option>{models.map(m => <option key={m.id} value={m.id}>{modelLabel(m)}{m.id === defaultId ? " · Collection default" : ""}</option>)}</select>}
    {local && <p className="muted small" role="status">Local · Ollama · {localModels === null ? "Checking installation…" : !localModels.available ? "Ollama unavailable" : installed ? "Installed · No paid API" : "Model not installed"}<br />Embedding: overall Default{dataset?.models?.find((m:Entity)=>m.id===dataset?.embedding_model_id)?.provider_model ? ` · ${dataset.models.find((m:Entity)=>m.id===dataset.embedding_model_id).provider_model}` : ""}. Changing the chat model keeps the one knowledge index.</p>}
  </div>;
}

export function DatasetWorkspace({onNewCollection,datasets,models,documents,onSelect,onCreated,api,reload,notify,onUse,canManage=true,directorySearch,onClearDirectorySearch,onDirectoryVisibilityChange,storageKey,defaults}: {
  onNewCollection?:()=>void;datasets:Entity[];models:Entity[];documents:Entity[];onSelect:(id:string)=>void;onCreated:(dataset:Entity)=>void;api:Api;reload:()=>void;notify:(text:string)=>void;onUse:(view:"Lapi agent V2"|"Extract")=>void;canManage?:boolean;directorySearch:string;onClearDirectorySearch:()=>void;onDirectoryVisibilityChange:(visible:boolean)=>void;storageKey:string;defaults?:Entity;
}) {
  const lifecycle=useDatasetLifecycle(api,reload,canManage);
  const [creating,setCreating]=useState(false),[onboardingBusy,setOnboardingBusy]=useState(false);
  useEffect(()=>{onDirectoryVisibilityChange(!creating);return()=>onDirectoryVisibilityChange(false);},[creating,onDirectoryVisibilityChange]);
  const completed=(dataset:Entity)=>{
    sessionStorage.removeItem(storageKey);sessionStorage.removeItem(storageKey+'-request');
    onCreated(dataset);setCreating(false);notify('Collection created with its model mappings.');reload();
  };
  return <div className="dataset-focus">
    {!creating&&lifecycle.controls}
    {!creating&&datasets.length>0&&<SummaryTiles label="Collection readiness" tiles={directorySummary(datasets,documents)}/>}
    {!creating&&<div className="dataset-intro dataset-navigation"><span className="pill">{datasets.length} collection{datasets.length===1?'':'s'}</span>{(canManage||onNewCollection)&&<ActionButton className="btn primary" onClick={()=>canManage?setCreating(true):onNewCollection?.()} label="New collection" action="add" showLabel/>}</div>}
    {creating?<AgentOnboarding datasetOnly api={api} models={models} defaults={defaults} storageKey={storageKey} onBusy={setOnboardingBusy} onReady={()=>{}} onCompleted={completed} onUse={()=>{}} onClose={()=>{if(!onboardingBusy)setCreating(false);}}/>:<>
      {datasets.length>0&&<DirectoryRows onDelete={canManage?lifecycle.requestDelete:undefined} datasets={datasets} documents={documents} search={directorySearch} onClearSearch={onClearDirectorySearch} onChat={id=>{onSelect(id);onUse('Lapi agent V2');}}/>}
      {!datasets.length&&<div className="panel dataset-empty"><Database size={30}/><h3>{canManage||onNewCollection?'Your first collection starts here':'No collections here yet'}</h3><p>{canManage||onNewCollection?'A collection holds related documents.':'Ask an owner of this workspace to add one.'}</p>{(canManage||onNewCollection)&&<ActionButton className="btn primary" onClick={()=>canManage?setCreating(true):onNewCollection?.()} label="New collection" action="add"/>}</div>}
    </>}
  </div>;
}

const providerLabels:Record<string,string>={'ollama':'Ollama','openai-compatible':'OpenAI-compatible','azure-openai':'Azure OpenAI','anthropic':'Anthropic Claude','bedrock':'Amazon Bedrock','vertex':'Google Vertex AI','oci':'OCI','openai':'OpenAI','sentence_transformers':'Sentence Transformers'};
function providerName(model?:Entity){const provider:string|undefined=model?.connection?.protocol||model?.provider;return provider?providerLabels[provider]||provider:'—';}

export function DatasetMappings({ dataset, models, api, run, busy, reload, notify, onConnections }: { dataset: Entity; models: Entity[]; api: Api; run: (fn: () => Promise<void>) => Promise<void>; busy: boolean; reload: () => void; notify: (text: string) => void; onConnections: () => void }) {
  const savedDraft = (source: Entity): MappingDraft => ({
    mappings: (source.mappings || (source.models || []).map((m: Entity) => ({ model_id: m.id, enabled: m.mapping_enabled !== false }))).map((m: Entity) => ({ ...m })),
    chatDefault: source.default_chat_model_id || "",
    extractDefault: source.default_extraction_model_id || "",
    // Datasets no longer choose an embedding model: the workspace Default indexes all.
    embedding: "",
    ocr: source.ocr_model_id || "",
  });
  const [draft, setDraft] = useState<MappingDraft>(() => savedDraft(dataset));
  const { mappings, chatDefault, extractDefault, ocr = "" } = draft;
  const workspace: Entity = dataset.workspace_defaults || {};
  const workspaceModel = (id?: string) => id ? models.find(m => m.id === id) : undefined;

  const [remoteChanged, setRemoteChanged] = useState(false);
  const dirty = useRef(false);
  const savedRevision = useRef({ id: dataset.id, version: dataset.version });
  const loadSavedDraft = () => {
    setDraft(savedDraft(dataset));
    savedRevision.current = { id: dataset.id, version: dataset.version };
    dirty.current = false;
    setRemoteChanged(false);
  };
  useEffect(() => {
    // A workspace refresh returns new objects, even when nothing was saved.
    // Only a new persisted revision may reconcile the editor's local draft.
    if (savedRevision.current.id === dataset.id && savedRevision.current.version === dataset.version) return;
    if (dirty.current && savedRevision.current.id === dataset.id) {
      setRemoteChanged(true);
      return;
    }
    loadSavedDraft();
  }, [dataset.id, dataset.version]);
  const candidates = (capability: string) => models.filter(m => m.enabled !== false && m.capabilities?.includes(capability));
  const changeDefault = (key: "chatDefault" | "extractDefault" | "ocr", value: string) => {
    dirty.current = true;
    setDraft(current => selectMappingDefault(current,key,value));
  };
  const ocrCandidates = models.filter(m=>m.enabled!==false&&m.ocr_eligible===true);
  const selectedOcr = ocrCandidates.find(m=>m.id===ocr);
  // Empty OCR uses the workspace OCR Default, or a vision extraction default when none is set.
  const workspaceOcr = workspaceModel(workspace.ocr_model_id);
  const automaticOcr = workspaceOcr ? `Collection OCR Default · ${modelLabel(workspaceOcr)}` : 'Automatic · cloud extraction default';
  // Empty means "use the workspace Default" for chat and extraction.
  const roleReady=(capability:string,value:string,fallback?:string)=>value?candidates(capability).some(m=>m.id===value):!!workspaceModel(fallback);
  const embeddingDefault = workspaceModel(workspace.embedding_model_id || dataset.embedding_model_id);
  const complete=roleReady('chat',chatDefault,workspace.chat_model_id)&&roleReady('extraction',extractDefault,workspace.extraction_model_id)&&!!embeddingDefault&&(!ocr||!!selectedOcr);
  const ocrChanged = ocr !== (dataset.ocr_model_id || '');
  return <div className="dataset-mappings">
    {remoteChanged && <div className="notice warn"><Settings2 size={16} /><div><strong>Saved mappings changed while you were editing.</strong><p>Your unsaved selections are preserved. Load the latest saved mappings before making further changes.</p><button className="btn" onClick={loadSavedDraft}>Discard draft and load saved mappings</button></div></div>}
    <div className="panel-head"><span className="pill">Chat and Extraction per collection · Embedding is the overall Default</span><ActionButton className="btn" onClick={onConnections} label="Register model" action="add"/></div>
    <div className="mapping-table" role="region" aria-label="Collection model mappings table" tabIndex={0}>
      <table aria-label="Collection model mappings"><colgroup><col className="mapping-category-column"/><col className="mapping-model-column"/><col/><col/><col/><col/></colgroup>
        <thead><tr><th scope="col">Category</th><th scope="col">Default model</th><th scope="col">Provider</th><th scope="col" className="mapping-tokens" title="Configured input limit for embeddings; total context limit for chat and extraction">Input / context</th><th scope="col" className="mapping-tokens" title="Configured maximum output tokens">Output</th><th scope="col">Status</th></tr></thead>
        <tbody><tr>
          <th scope="row"><span>Embedding</span><small>Indexing and search</small></th>
          <td><span title="Set in Model Registration. Every collection uses the overall Default embedding model and the one knowledge index.">{embeddingDefault?`${modelLabel(embeddingDefault)} · ${embeddingDefault.provider_model}`:'No Default embedding model'}</span></td>
          <td>{providerName(embeddingDefault)}</td>
          <td className="mapping-tokens" title="Input tokens">{embeddingDefault?.context_limit?.toLocaleString()||'—'}</td>
          <td className="mapping-tokens" title="Not applicable to embeddings">—</td>
          <td><span className={`pill ${embeddingDefault?'green':'amber'}`} title="Change the overall Default in Model Registration">{embeddingDefault?'Overall Default':'Required'}</span></td>
        </tr>{[{label:"Chat model", cap:"chat", value:chatDefault, key:"chatDefault" as const, fallback:workspaceModel(workspace.chat_model_id)}, {label:"Extraction model", cap:"extraction", value:extractDefault, key:"extractDefault" as const, fallback:workspaceModel(workspace.extraction_model_id)}].map(f=>{
          const options=candidates(f.cap);const chosen=options.find(m=>m.id===f.value);const selected=chosen||(!f.value?f.fallback:undefined);
          const purpose=f.cap==='chat'?'Collection questions':'Structured extraction';
          return <tr key={f.cap}>
            <th scope="row"><label htmlFor={`mapping-${f.cap}`}>{f.cap==='chat'?'Chat':'Extraction'}</label><small>{purpose}</small></th>
            <td><select id={`mapping-${f.cap}`} aria-label={f.label} value={f.value} onChange={e=>changeDefault(f.key,e.target.value)} disabled={busy} required={!f.fallback} title={selected?`${modelLabel(selected)} · ${selected.provider_model}`:`Choose ${f.label.toLowerCase()}`}><option value="">{f.fallback?`Overall Default · ${modelLabel(f.fallback)}`:`Select ${f.cap==='extraction'?'an extraction':'a chat'} model`}</option>{options.map(m=><option key={m.id} value={m.id}>{modelLabel(m)} · {m.provider_model}</option>)}</select>{!options.length&&!f.fallback&&<small className="field-error">Register an enabled {f.cap} model first.</small>}</td>
            <td>{providerName(selected)}</td>
            <td className="mapping-tokens" title="Context tokens">{selected?.context_limit?.toLocaleString()||'—'}</td>
            <td className="mapping-tokens" title="Maximum output tokens">{selected?.max_output_tokens?.toLocaleString()||'—'}</td>
            <td><span className={`pill ${selected?'green':'amber'}`} title={chosen?'Collection override; Save & Apply commits the mapping':selected?'Uses the overall Default':'A model is required for this category'}>{chosen?'Selected':selected?'Overall Default':'Required'}</span></td>
          </tr>;
        })}<tr>
          <th scope="row"><label htmlFor="mapping-ocr">OCR</label><small>Scans and document images</small></th>
          <td><select id="mapping-ocr" aria-label="OCR model" title={selectedOcr?`${modelLabel(selectedOcr)} · ${selectedOcr.provider_model}`:automaticOcr} value={ocr} onChange={e=>changeDefault('ocr',e.target.value)} disabled={busy}>
            <option value="">{automaticOcr}</option>
            {ocrCandidates.map(model=><option key={model.id} value={model.id}>{modelLabel(model)} · {model.provider_model}</option>)}
            {ocr&&!selectedOcr&&<option value={ocr} disabled>Choose a cloud OCR model</option>}
          </select></td>
          <td>{(selectedOcr||workspaceOcr)?((selectedOcr||workspaceOcr)!.connection?.endpoint?.includes('api.openai.com')?'OpenAI':'Google Gemini'):'Cloud'}</td>
          <td className="mapping-tokens">{(selectedOcr||workspaceOcr)?.context_limit?.toLocaleString()||'—'}</td>
          <td className="mapping-tokens">{(selectedOcr||workspaceOcr)?.max_output_tokens?.toLocaleString()||'—'}</td>
          <td><span className={`pill ${!ocr||selectedOcr?'green':'amber'}`}>{!ocr?(workspaceOcr?'Overall Default':'Automatic'):selectedOcr?'Selected':'Unavailable'}</span></td>
        </tr></tbody>
      </table>
    </div>
    <p className="muted small">OCR reads text from images, scanned PDFs and images in Word documents using cloud models only. Choose an OpenAI or Gemini model ticked for OCR in Model Registration (its test reads a sample image), or gpt-4o, gpt-4o-mini or a Gemini extraction model. Leave it empty to use the collection OCR Default, or the compatible cloud extraction default when none is set; it never falls back to local OCR.</p>
    {ocrChanged&&<p className="notice" role="status">The next indexing job will use this OCR choice. Reindex existing documents to read their images again; their embedding model stays the same.</p>}
    <div className="mapping-availability">
      {(['chat','extraction'] as const).map(capability=><fieldset key={capability} disabled={busy||remoteChanged}>
        <legend>Available {capability} models</legend>
        <p className="muted small">Enable models to offer them in this collection's {capability==='chat'?'chat':'extraction'} selector. Keep one default above.</p>
        <div className="mapping-model-options">{candidates(capability).map(model=>{
          const isDefault=[chatDefault,extractDefault,ocr==='local'?'':ocr].includes(model.id);
          const enabled=mappings.some(item=>item.model_id===model.id&&item.enabled!==false);
          return <label className="check mapping-model-option" key={model.id}>
            <input type="checkbox" aria-label={`Enable ${modelLabel(model)} for ${capability}`} checked={enabled} disabled={isDefault}
              onChange={event=>{dirty.current=true;setDraft(current=>setMappingEnabled(current,model.id,event.target.checked));}}/>
            <span>{modelLabel(model)}<small>{model.provider_model}{[chatDefault,extractDefault].includes(model.id)?' · Collection default':''}{ocr===model.id?' · OCR default':''}</small></span>
          </label>;
        })}</div>
      </fieldset>)}
    </div>
    <p className="muted small">Collections do not choose an embedding model. The overall Default embedding model, set in Model Registration, builds the one knowledge index for every collection.</p>
    <div className="row between wrap mapping-actions"><span className="muted small">Index generation {dataset.index_generation || 1} · Connection credentials remain encrypted</span><ActionButton className="btn primary" disabled={busy || remoteChanged || !complete} onClick={() => run(async () => { const saved = await api(`/datasets/${dataset.id}/models`, "PUT", { mappings, default_chat_model_id: chatDefault || null, default_extraction_model_id: extractDefault || null, ocr_model_id: ocr || null, expected_version: dataset.version }); setDraft(savedDraft(saved)); dirty.current = false; notify("Mappings applied. The next operation will use these selections."); reload(); })} label="Save & Apply" action="save"/></div>
  </div>;
}

export function ModelCatalog({ models, profiles, api, run, busy, reload, notify }: { models: Entity[]; profiles: Entity[]; api: Api; run: (fn: () => Promise<void>) => Promise<void>; busy: boolean; reload: () => void; notify: (text: string) => void }) {
  const blank = { name: "", connection_profile_id: "", provider_model: "", capabilities: ["chat", "extraction"], enabled: true };
  const [form, setForm] = useState<Entity>(blank);
  const [editing, setEditing] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [catalogSearch, setCatalogSearch] = useState("");
  const visibleModels = models.filter(m => `${modelLabel(m)} ${m.provider_model || ""}`.toLowerCase().includes(catalogSearch.toLowerCase()));
  return <section className="panel model-catalog-focus" id="model-catalog">
    {!showForm && <div className="panel-head"><div><h2>Model catalog</h2><p className="muted small">Shared models available to your collections.</p></div><ActionButton className="btn primary" onClick={() => { setForm(blank); setEditing(""); setShowForm(true); }} label="Add model" action="add"/></div>}
    {!showForm && models.length > 6 && <div className="field"><input aria-label="Search shared models" placeholder="Search shared models" value={catalogSearch} onChange={e => setCatalogSearch(e.target.value)} /></div>}
    {!showForm && !!models.length && !visibleModels.length && <p className="muted">No matching models.</p>}
    {!showForm && <div className="catalog-list">{visibleModels.map(m => <div key={m.id} className="catalog-row"><span className="file-icon"><Layers size={18} /></span><div className="catalog-name"><strong>{modelLabel(m)}</strong><small>{m.provider_model} · {profiles.find(p => p.id === m.connection_profile_id)?.name || "Saved connection"}</small></div><div className="model-chips">{(m.capabilities || []).map((c: string) => <span className="model-chip" key={c}>{c}</span>)}<span className={`pill ${m.enabled !== false ? "green" : "amber"}`}>{m.enabled !== false ? "Enabled" : "Disabled"}</span></div><ActionButton className="btn" onClick={() => { setForm({ name:m.name, connection_profile_id:m.connection_profile_id, provider_model:m.provider_model, capabilities:m.capabilities || [], enabled:m.enabled !== false }); setEditing(m.id); setShowForm(true); }} label="Edit model" action="edit"/></div>)}</div>}
    {!models.length && !showForm && <div className="empty"><Layers size={30} /><h3>Build your shared model catalog</h3><p>Save a connection in the Profiles section, then add chat, extraction, or embedding models.</p></div>}
    {showForm && <form className="catalog-form" onSubmit={e => { e.preventDefault(); run(async () => { await api(`/models${editing ? "/" + editing : ""}`, editing ? "PUT" : "POST", form); setShowForm(false); notify(editing ? "Catalog model updated. Review its collection mappings." : "Model added to the catalog. Map it to a collection to use it."); reload(); }); }}><div className="panel-head"><h3>{editing ? "Edit catalog model" : "Add a catalog model"}</h3><button title="Cancel model edit" type="button" className="btn icon" aria-label="Cancel model edit" onClick={() => setShowForm(false)}><X size={14} /></button></div><div className="grid3"><div className="field"><label>Model name</label><input autoFocus aria-label="Model name" value={form.name} onChange={e => setForm({...form, name:e.target.value})} placeholder="e.g. Research assistant" required /></div><div className="field"><label>Connection profile</label><select aria-label="Model connection profile" value={form.connection_profile_id} onChange={e => setForm({...form, connection_profile_id:e.target.value})} required><option value="">Select saved connection</option>{profiles.map(p => <option key={p.id} value={p.id}>{p.name} · v{p.version}</option>)}</select></div><div className="field"><label>Provider model ID</label><input aria-label="Provider model ID" value={form.provider_model} onChange={e => setForm({...form, provider_model:e.target.value})} placeholder="e.g. gpt-4.1-mini" required /></div></div><div className="row between wrap"><div className="row wrap">{["chat", "extraction", "embedding"].map(cap => <label className="check" key={cap}><input type="checkbox" aria-label={`Model capability ${cap}`} checked={form.capabilities.includes(cap)} onChange={e => setForm({...form, capabilities:e.target.checked ? cap === "embedding" ? ["embedding"] : [...form.capabilities.filter((c: string) => c !== "embedding"), cap] : form.capabilities.filter((c: string) => c !== cap)})} />{cap}</label>)}<label className="check"><input type="checkbox" aria-label="Model enabled" checked={form.enabled} onChange={e => setForm({...form, enabled:e.target.checked})} />Enabled</label></div><ActionButton className="btn primary" disabled={busy || !profiles.length || !form.capabilities.length} label="Save catalog model" action="save"/></div>{!profiles.length && <p className="small muted" style={{marginTop:14}}>Save a connection in the Profiles section before adding this model.</p>}<p className="small muted" style={{marginTop:14, marginBottom:0}}>Embedding models are separate from chat and extraction models. Select supported capabilities; adding embedding clears generation capabilities. Credentials are never copied into the collection or returned to the browser.</p></form>}
  </section>;
}
