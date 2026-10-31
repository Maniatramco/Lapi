"use client";
import {useCallback,useEffect,useState} from 'react';
import {Brain,Download,Plus,Save,Sparkles,Trash2,Upload,X} from 'lucide-react';
import {useRef} from 'react';
import './agent-setup.css';
type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;
type Tab='Skills'|'Collection instructions'|'Model guides'|'My memory';
const TABS:Tab[]=['Skills','Collection instructions','Model guides','My memory'];
const blankSkill={id:'',name:'',description:'',instructions:'',allowed_tools:[] as string[],output_format:'',scope:'personal',dataset_id:'',applies_to:{} as Record<string,string[]>};
/** "When it applies" fields: comma-separated words the agent matches against requests and document names. */
const APPLIES:[string,string,string][]=[['document_types','Document types','invoice, purchase order'],['domains','Domains','finance, legal'],['keywords','Keywords','overdue, renewal'],['documents','Specific documents','*-msa.pdf, Acme contract']];
const termsText=(terms?:string[])=>(terms||[]).join(', ');
const parseTerms=(value:string)=>value.split(',').map(t=>t.trim().toLowerCase()).filter(Boolean).slice(0,20);

/** Agent setup: skills, dataset instructions, model guides and personal memory. */
export function AgentSetup({api,datasets,selectedDataset,isAdmin,onNotify}:{api:Api;datasets:Entity[];selectedDataset:string;isAdmin:boolean;onNotify:(message:string)=>void}){
 const [tab,setTab]=useState<Tab>('Skills');const [error,setError]=useState('');
 return <div className="agent-setup">
  <div className="agent-setup-tabs" role="tablist" aria-label="Agent setup">{TABS.map(name=><button key={name} role="tab" aria-selected={tab===name} className={`btn${tab===name?' primary':''}`} onClick={()=>{setTab(name);setError('');}}>{name}</button>)}</div>
  {error&&<p role="alert" className="agent-setup-error">{error}</p>}
  {tab==='Skills'&&<Skills api={api} datasets={datasets} selectedDataset={selectedDataset} isAdmin={isAdmin} onError={setError} onNotify={onNotify}/>}
  {tab==='Collection instructions'&&<Instructions api={api} datasets={datasets} selectedDataset={selectedDataset} isAdmin={isAdmin} onError={setError} onNotify={onNotify}/>}
  {tab==='Model guides'&&<ModelGuides api={api} isAdmin={isAdmin} onError={setError} onNotify={onNotify}/>}
  {tab==='My memory'&&<Memory api={api} onError={setError} onNotify={onNotify}/>}
 </div>;
}

function Skills({api,datasets,selectedDataset,isAdmin,onError,onNotify}:{api:Api;datasets:Entity[];selectedDataset:string;isAdmin:boolean;onError:(m:string)=>void;onNotify:(m:string)=>void}){
 const [skills,setSkills]=useState<Entity[]>([]);const [draft,setDraft]=useState<Entity|null>(null);const [busy,setBusy]=useState(false);const fileInput=useRef<HTMLInputElement>(null);
 const upload=async(file:File)=>{setBusy(true);onError('');
  try{const form=new FormData();form.append('file',file);form.append('scope','personal');const saved=await api('/skills/upload','POST',form);onNotify(saved.replaced?`Skill "${saved.name}" replaced with the uploaded file.`:`Skill "${saved.name}" added. I use it automatically when it applies, or type /skill ${saved.name}.`);await load();}
  catch(e){onError(e instanceof Error?e.message:'Could not upload the skill.');}finally{setBusy(false);}};
 const load=useCallback(()=>api(`/skills?dataset_id=${encodeURIComponent(selectedDataset||'')}`).then(r=>setSkills(r.skills||[])).catch(e=>onError(e.message)),[api,selectedDataset,onError]);
 useEffect(()=>{void load();},[load]);
 const save=async()=>{if(!draft)return;setBusy(true);onError('');
  try{const body:Entity=draft;
   await api(draft.id?`/skills/${draft.id}`:'/skills',draft.id?'PUT':'POST',{name:body.name,description:body.description,instructions:body.instructions,allowed_tools:body.allowed_tools||[],output_format:body.output_format||'',scope:body.scope,dataset_id:body.scope==='dataset'?body.dataset_id:'',applies_to:body.applies_to||{}});
   setDraft(null);onNotify('Skill saved. Use it in chat with /skill '+draft.name+'.');await load();}
  catch(e){onError(e instanceof Error?e.message:'Could not save the skill.');}finally{setBusy(false);}};
 const remove=async(skill:Entity)=>{if(!window.confirm(`Remove the skill "${skill.name}"?`))return;try{await api(`/skills/${skill.id}`,'DELETE');await load();}catch(e){onError(e instanceof Error?e.message:'Could not remove the skill.');}};
 return <section aria-label="Skills">
  <div className="agent-setup-head"><p className="muted">Skills are playbooks the agent follows for a kind of document or request. Say when one applies (document types, domains, keywords, specific documents) and the agent uses it by itself whenever a request or document matches; or type <code>/skill name request</code>. Upload a <code>SKILL.md</code> file or write one here; download any skill to share it.</p>
   <span className="agent-setup-actions"><input ref={fileInput} type="file" hidden accept=".md,.txt,.markdown" onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void upload(file);}}/><button className="btn" disabled={busy} onClick={()=>fileInput.current?.click()}><Upload size={16}/>Upload SKILL.md</button><button className="btn primary" onClick={()=>setDraft({...blankSkill,dataset_id:selectedDataset})}><Plus size={16}/>New skill</button></span></div>
  {draft&&<form className="agent-setup-card" onSubmit={e=>{e.preventDefault();void save();}}>
   <div className="agent-setup-row"><label>Name<input value={draft.name} required maxLength={40} pattern="[a-z0-9][a-z0-9 -]{1,39}" placeholder="contract-risks" onChange={e=>setDraft({...draft,name:e.target.value})}/></label>
    <label>Shared with<select value={draft.scope} onChange={e=>setDraft({...draft,scope:e.target.value})}><option value="personal">Only me</option>{isAdmin&&<option value="dataset">One collection</option>}{isAdmin&&<option value="workspace">Everyone</option>}</select></label>
    {draft.scope==='dataset'&&<label>Collection<select value={draft.dataset_id} onChange={e=>setDraft({...draft,dataset_id:e.target.value})}><option value="">Choose…</option>{datasets.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>}</div>
   <label>When to use it<input value={draft.description} required maxLength={300} placeholder="Summarise contract risks: termination, liability, renewal" onChange={e=>setDraft({...draft,description:e.target.value})}/></label>
   <label>Steps<textarea rows={7} value={draft.instructions} required maxLength={8000} placeholder={'1. Find the termination and renewal clauses.\n2. …'} onChange={e=>setDraft({...draft,instructions:e.target.value})}/></label>
   <label>Answer format (optional)<input value={draft.output_format} maxLength={500} placeholder="A table of risks with clause and severity" onChange={e=>setDraft({...draft,output_format:e.target.value})}/></label>
   <fieldset className="agent-setup-applies"><legend>When it applies (optional; the agent then uses it automatically)</legend><div className="agent-setup-row">{APPLIES.map(([key,label,hint])=><label key={key}>{label}<input value={termsText(draft.applies_to?.[key])} placeholder={hint} onChange={e=>setDraft({...draft,applies_to:{...(draft.applies_to||{}),[key]:parseTerms(e.target.value)}})}/></label>)}</div></fieldset>
   <div className="agent-setup-actions"><button className="btn primary" disabled={busy}><Save size={16}/>Save skill</button><button type="button" className="btn" onClick={()=>setDraft(null)}><X size={16}/>Cancel</button></div>
  </form>}
  <ul className="agent-setup-list">{skills.map(skill=><li key={skill.id} className="agent-setup-card">
   <div className="agent-setup-row spread"><strong><Sparkles size={15}/> {skill.name}</strong><span className="small muted">{skill.source==='builtin'?'Built-in':skill.scope==='personal'?'Only me':skill.scope==='dataset'?'Collection':'Everyone'}</span></div>
   <p>{skill.description}</p>
   {Object.values(skill.applies_to||{}).some((t:any)=>t?.length)&&<p className="agent-setup-chips" aria-label="When it applies">{APPLIES.flatMap(([key,label])=>(skill.applies_to?.[key]||[]).map((term:string)=><span key={key+term} className="agent-chip" title={label}>{term}</span>))}</p>}
   <div className="agent-setup-actions">{skill.editable&&<button className="btn" onClick={()=>setDraft({...skill,applies_to:skill.applies_to||{}})}>Edit</button>}{skill.source!=='builtin'&&<a className="btn" href={`/api/skills/${encodeURIComponent(skill.id)}/download`} download><Download size={15}/>Download</a>}{skill.editable&&<button className="btn" aria-label={`Remove ${skill.name}`} onClick={()=>void remove(skill)}><Trash2 size={15}/></button>}</div>
  </li>)}</ul>
 </section>;
}

function Instructions({api,datasets,selectedDataset,isAdmin,onError,onNotify}:{api:Api;datasets:Entity[];selectedDataset:string;isAdmin:boolean;onError:(m:string)=>void;onNotify:(m:string)=>void}){
 const [dataset,setDataset]=useState(selectedDataset||datasets[0]?.id||'');const [current,setCurrent]=useState<Entity|null>(null);const [text,setText]=useState('');const [versions,setVersions]=useState<Entity[]>([]);const [warnings,setWarnings]=useState<string[]>([]);
 useEffect(()=>{if(!dataset)return;setWarnings([]);
  api(`/datasets/${dataset}/instructions`).then(r=>{setCurrent(r);setText(r.text||'');}).catch(e=>onError(e.message));
  api(`/datasets/${dataset}/instructions/versions`).then(r=>setVersions(r.versions||[])).catch(()=>setVersions([]));},[api,dataset,onError]);
 const save=async()=>{try{const r=await api(`/datasets/${dataset}/instructions`,'PUT',{text,expected_version:current?.version??null});setCurrent(r);setWarnings(r.warnings||[]);onNotify('Collection instructions saved.');
  setVersions((await api(`/datasets/${dataset}/instructions/versions`)).versions||[]);}catch(e){onError(e instanceof Error?e.message:'Could not save.');}};
 const bytes=new TextEncoder().encode(text).length;
 return <section aria-label="Collection instructions" className="agent-setup-card">
  <p className="muted">Instructions tell the agent how to answer for this collection: terms, which fields matter, preferred format. They never switch off citations or confirmation. In chat, <code>/instructions</code> shows them and <code>/optimize</code> drafts better ones.</p>
  <label>Collection<select value={dataset} onChange={e=>setDataset(e.target.value)}>{datasets.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
  <label>Instructions {current?.version?<span className="small muted">· version {current.version}</span>:null}<textarea rows={10} value={text} readOnly={!isAdmin} maxLength={4096} onChange={e=>setText(e.target.value)} placeholder="Answer in short bullet points. Amounts are in INR. 'Vendor' means the supplier field."/></label>
  <p className={`small ${bytes>4096?'agent-setup-error':'muted'}`}>{bytes} / 4096 bytes</p>
  {warnings.length>0&&<p role="status" className="agent-setup-warning">Saved, but check this: {warnings.join('; ')}.</p>}
  {isAdmin?<div className="agent-setup-actions"><button className="btn primary" disabled={bytes>4096||text===(current?.text||'')} onClick={()=>void save()}><Save size={16}/>Save instructions</button></div>:<p className="small muted">Only an administrator can change collection instructions.</p>}
  {versions.length>1&&<details><summary>Earlier versions · {versions.length-1}</summary>{versions.slice(1).map(v=><div key={v.version} className="agent-setup-version"><div className="small muted">Version {v.version}{v.summary?` · ${v.summary}`:''}</div><pre>{v.text||'(empty)'}</pre>{isAdmin&&<button className="btn" onClick={()=>setText(v.text||'')}>Restore into editor</button>}</div>)}</details>}
 </section>;
}

function ModelGuides({api,isAdmin,onError,onNotify}:{api:Api;isAdmin:boolean;onError:(m:string)=>void;onNotify:(m:string)=>void}){
 const [models,setModels]=useState<Entity[]>([]);const [model,setModel]=useState('');const [guide,setGuide]=useState<Entity|null>(null);const [text,setText]=useState('');
 useEffect(()=>{api('/models').then(r=>{const chat=(Array.isArray(r)?r:r.models||[]).filter((m:Entity)=>(m.capabilities||[]).includes('chat'));setModels(chat);setModel(chat[0]?.id||'');}).catch(e=>onError(e.message));},[api,onError]);
 useEffect(()=>{if(!model)return;api(`/models/${model}/prompt-guide`).then(r=>{setGuide(r);setText(r.text||'');}).catch(e=>onError(e.message));},[api,model,onError]);
 return <section aria-label="Model guides" className="agent-setup-card">
  <p className="muted">A model guide holds prompting tips for one chat model (for example "call tools in parallel", "keep answers short"). Lapi adds it after its own rules. Without a guide, a built-in tip for the model family is used.</p>
  {models.length===0?<p className="muted">No chat models are registered yet.</p>:<>
   <label>Chat model<select value={model} onChange={e=>setModel(e.target.value)}>{models.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
   <label>Guide<textarea rows={8} value={text} readOnly={!isAdmin} maxLength={8192} placeholder={guide?.default_text||'No built-in tip for this model family.'} onChange={e=>setText(e.target.value)}/></label>
   {isAdmin&&<div className="agent-setup-actions"><button className="btn primary" disabled={text===(guide?.text||'')} onClick={()=>void api(`/models/${model}/prompt-guide`,'PUT',{text}).then(r=>{setGuide({...guide,...r});onNotify('Model guide saved.');}).catch(e=>onError(e.message))}><Save size={16}/>Save guide</button></div>}
  </>}
 </section>;
}

function Memory({api,onError,onNotify}:{api:Api;onError:(m:string)=>void;onNotify:(m:string)=>void}){
 const [memory,setMemory]=useState<Entity|null>(null);const [note,setNote]=useState('');
 useEffect(()=>{api('/me/memory').then(r=>{setMemory(r);setNote(r.note||'');}).catch(e=>onError(e.message));},[api,onError]);
 const update=(body:Entity,message:string)=>api('/me/memory','PUT',body).then(r=>{setMemory(r);setNote(r.note||'');onNotify(message);}).catch(e=>onError(e.message));
 const clear=()=>{if(!window.confirm('Clear your memory note and question history?'))return;void api('/me/memory','DELETE').then(r=>{setMemory(r);setNote('');onNotify('Memory cleared.');}).catch(e=>onError(e.message));};
 if(!memory)return <p className="muted">Loading…</p>;
 return <section aria-label="My memory" className="agent-setup-card">
  <div className="agent-setup-row spread"><p className="muted"><Brain size={15}/> The agent keeps a short private note about how you like answers and can look up your earlier questions. Facts are always re-read from your sources. History is kept for {memory.retention_days} days.</p>
   <label className="agent-setup-toggle"><input type="checkbox" checked={memory.enabled} onChange={e=>void update({enabled:e.target.checked},e.target.checked?'Memory turned on.':'Memory turned off.')}/> Memory on</label></div>
  <label>Memory note<textarea rows={4} value={note} maxLength={memory.note_limit} onChange={e=>setNote(e.target.value)} placeholder="Prefers tables. Works mostly with the Invoices collection."/></label>
  <div className="agent-setup-actions"><button className="btn primary" disabled={note===(memory.note||'')} onClick={()=>void update({note},'Memory note saved.')}><Save size={16}/>Save note</button><button className="btn" onClick={clear}><Trash2 size={15}/>Clear memory</button></div>
  <details><summary>Recent questions · {memory.history_count}</summary><ul className="agent-setup-history">{memory.history.map((h:Entity,i:number)=><li key={i}><span className="small muted">{new Date(h.asked_at*1000).toLocaleString()}</span><div>{h.question}</div>{h.answer&&<div className="small muted">{h.answer}</div>}</li>)}</ul></details>
 </section>;
}
