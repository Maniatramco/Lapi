"use client";
import {useEffect,useRef,useState,type KeyboardEvent as ReactKeyboardEvent} from 'react';
import {CloudUpload,Database,FileJson,FileText,Layers,MessageSquare,Plus,Settings2,X} from 'lucide-react';
import {DatasetMappings} from './dataset-workspace';
import {openAttention} from './needs-attention';
import {DatasetMembers} from './dataset-members';
import {LEVEL_LABEL,type Level} from './access-map-data';
import './manage-dataset.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
export type ManageTab='details'|'models'|'documents'|'prompts'|'members';
export type ManageRequest={datasetId:string;tab?:ManageTab};
export type ManageView='Lapi agent V2'|'Add knowledge'|'Prompt templates'|'Files & processing'|'Model Registration';
const EVENT='lapi:manage-dataset';
/** Open the Manage dataset panel from any screen (Datasets, Lapi Agent onboarding, Dashboard). */
export function openDatasetEditor(datasetId:string,tab:ManageTab='details'){if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent(EVENT,{detail:{datasetId,tab}}));}
export function onDatasetEditor(handler:(request:ManageRequest)=>void){const listener=(event:Event)=>handler((event as CustomEvent<ManageRequest>).detail);window.addEventListener(EVENT,listener);return()=>window.removeEventListener(EVENT,listener);}

export const TABS:[ManageTab,string][]=[['details','Details'],['models','Models'],['documents','Documents'],['prompts','Prompts']];
const MEMBERS_TAB:[ManageTab,string]=['members','Members'];
const docState=(doc:Entity)=>['failed','cancelled'].includes(doc.status)?'failed':['queued','processing','running'].includes(doc.status)?'pending':doc.status==='ready'&&doc.requires_reindex?'stale':doc.status==='ready'?'ready':'pending';
const docLabel=(doc:Entity)=>({failed:'Failed',pending:'Processing',stale:'Needs reindex',ready:'Ready'} as Record<string,string>)[docState(doc)];

/** The four things onboarding set up — details, models, documents and prompts — edited in one place. */
export function ManageDataset({dataset,tab:initialTab='details',models,documents,templates,isAdmin,api,reload,notify,onNavigate,onClose,variant='dialog',onCommand}:{dataset:Entity;tab?:ManageTab;models:Entity[];documents:Entity[];templates:Entity[];isAdmin:boolean;api:Api;reload:()=>void;notify:(text:string)=>void;onNavigate:(view:ManageView)=>void;onClose:()=>void;variant?:'dialog'|'inline';onCommand?:(label:string)=>void}){
 const inline=variant==='inline';
 // The person's level on this dataset (the API enforces it; this only hides what would be refused).
 const level:Level=isAdmin?'owner':(['viewer','editor','owner'].includes(dataset.my_access)?dataset.my_access:'viewer');
 const canEdit=level!=='viewer',isOwner=level==='owner';
 const tabs=isOwner?[...TABS,MEMBERS_TAB]:TABS;
 const [tab,setTab]=useState<ManageTab>(initialTab);
 const [name,setName]=useState(dataset.name||''),[description,setDescription]=useState(dataset.description||''),[active,setActive]=useState(dataset.active!==false);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const panel=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(inline){panel.current?.scrollIntoView?.({block:'nearest',behavior:'smooth'});return;}const previous=document.activeElement as HTMLElement|null;panel.current?.querySelector<HTMLElement>('[role=tab][aria-selected=true]')?.focus();const key=(event:KeyboardEvent)=>{if(event.key==='Escape')onClose();};document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);previous?.focus?.();};},[onClose,inline]);
 const run=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');try{await fn();}catch(e){setError(e instanceof Error?e.message:'The change failed. Nothing was saved.');}finally{setBusy(false);}};
 const docs=documents.filter(doc=>(doc.dataset_id||doc.kb_id)===dataset.id);
 const prompts=templates.filter(t=>t.dataset_id===dataset.id);
 const counts={documents:docs.length,prompts:prompts.length,failed:docs.filter(d=>docState(d)==='failed'||docState(d)==='stale').length};
 const changed=name.trim()!==(dataset.name||'')||description.trim()!==(dataset.description||'')||active!==(dataset.active!==false);
 const save=()=>run(async()=>{
  if(!name.trim())throw new Error('Enter a collection name.');
  if(name.trim()!==(dataset.name||'')||description.trim()!==(dataset.description||''))await api(`/datasets/${dataset.id}`,'PATCH',{name:name.trim(),description:description.trim()});
  if(active!==(dataset.active!==false))await api(`/datasets/${dataset.id}/status`,'PATCH',{active});
  notify(`Saved ${name.trim()}. Models, documents and prompts are unchanged.`);reload();
 });
 const body=<div ref={panel} className={`manage-dataset${inline?' manage-inline':''}`} {...(inline?{role:'region','aria-labelledby':'manage-dataset-title',onKeyDown:(event:ReactKeyboardEvent)=>{if(event.key==='Escape'){event.stopPropagation();onClose();}}}:{role:'dialog','aria-modal':true,'aria-labelledby':'manage-dataset-title'})}>
   <header className="manage-head"><span className="manage-icon"><Database size={18} aria-hidden="true"/></span><div><span className="manage-eyebrow">{inline?'Lapi Agent · Manage collection':'Manage collection'}</span><h2 id="manage-dataset-title">{dataset.name}</h2><p>{counts.documents} document{counts.documents===1?'':'s'} · {counts.prompts} prompt{counts.prompts===1?'':'s'}{dataset.active===false?' · Inactive':''} · {isAdmin?'You are an administrator':`Your access: ${LEVEL_LABEL[level]}`}</p></div><button type="button" className="btn icon" aria-label={inline?'Close collection card':'Close'} onClick={onClose}><X size={16}/></button></header>
   <div className="manage-tabs" role="tablist" aria-label="Collection settings">{tabs.map(([id,label])=><button key={id} type="button" role="tab" id={`manage-tab-${id}`} aria-selected={tab===id} aria-controls={`manage-panel-${id}`} tabIndex={tab===id?0:-1} onClick={()=>setTab(id)} onKeyDown={event=>{const i=tabs.findIndex(([t])=>t===tab);if(event.key==='ArrowRight'||event.key==='ArrowLeft'){event.preventDefault();const next=tabs[(i+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length][0];setTab(next);(event.currentTarget.parentElement?.querySelector(`#manage-tab-${next}`) as HTMLElement|null)?.focus();}}}>{label}{id==='documents'&&counts.failed>0&&<span className="manage-badge" aria-label={`${counts.failed} need attention`}>{counts.failed}</span>}</button>)}</div>
   {error&&<p className="notice error" role="alert">{error}</p>}
   <div className="manage-body">
    {tab==='details'&&<section id="manage-panel-details" role="tabpanel" aria-labelledby="manage-tab-details" className="manage-panel">
     {!isOwner&&<p className="manage-note">Only this collection's owners and administrators can change its details.</p>}
     <label className="manage-field">Collection name<input value={name} maxLength={200} disabled={!isOwner||busy} onChange={event=>setName(event.target.value)}/></label>
     <label className="manage-field">Description<textarea rows={3} maxLength={10000} value={description} disabled={!isOwner||busy} placeholder="What this collection holds and who uses it" onChange={event=>setDescription(event.target.value)}/></label>
     <label className="manage-switch"><input type="checkbox" checked={active} disabled={!isAdmin||busy} onChange={event=>setActive(event.target.checked)}/><span><strong>Active</strong><small>Inactive collections keep their knowledge but cannot start new uploads or extractions.</small></span></label>
     {isOwner&&<div className="manage-actions"><button type="button" className="btn primary" disabled={busy||!changed||!name.trim()} onClick={()=>void save()}>{busy?'Saving…':'Save changes'}</button><button type="button" className="btn" disabled={busy||!changed} onClick={()=>{setName(dataset.name||'');setDescription(dataset.description||'');setActive(dataset.active!==false);}}>Reset</button></div>}
    </section>}
    {tab==='models'&&<section id="manage-panel-models" role="tabpanel" aria-labelledby="manage-tab-models" className="manage-panel">
     <p className="manage-note"><Layers size={14} aria-hidden="true"/>The overall Default embedding model indexes knowledge for every collection; chat answers; extraction fills prompts; OCR reads scans. Changing OCR marks documents for reindexing.</p>
     {isAdmin?<DatasetMappings key={dataset.id} dataset={dataset} models={models} api={api} run={run} busy={busy} reload={reload} notify={notify} onConnections={()=>onNavigate('Model Registration')}/>:<p className="manage-note">Only administrators can change model mappings.</p>}
    </section>}
    {tab==='documents'&&<section id="manage-panel-documents" role="tabpanel" aria-labelledby="manage-tab-documents" className="manage-panel">
     {!canEdit&&<p className="manage-note">You have Viewer access: you can read and chat. Ask an owner for Editor access to add or change documents.</p>}
     <div className="manage-actions">{canEdit&&<><button type="button" className="btn primary" onClick={()=>onCommand?onCommand('/Upload'):onNavigate('Lapi agent V2')}><Plus size={15}/>{onCommand?'Upload with /Upload':'Upload in Lapi Agent'}</button><button type="button" className="btn" onClick={()=>onNavigate('Add knowledge')}><CloudUpload size={15}/>Add from cloud storage</button></>}{counts.failed>0&&<button type="button" className="btn danger" onClick={()=>openAttention({datasetId:dataset.id})}>Review {counts.failed} that need attention</button>}{isAdmin&&<button type="button" className="btn" onClick={()=>onNavigate('Files & processing')}><Settings2 size={15}/>Reindex or delete files</button>}</div>
     {docs.length?<ul className="manage-list">{docs.map(doc=><li key={doc.id}><FileText size={15} aria-hidden="true"/><span className="manage-list-name"><strong title={doc.name}>{doc.name}</strong><small>{doc.created_at?new Date(doc.created_at*1000).toLocaleString():''}</small></span><span className="manage-state" data-state={docState(doc)}>{docLabel(doc)}</span></li>)}</ul>:<p className="manage-empty">No documents yet. Upload files in Lapi Agent with /Upload, or add them from cloud storage.</p>}
    </section>}
    {tab==='prompts'&&<section id="manage-panel-prompts" role="tabpanel" aria-labelledby="manage-tab-prompts" className="manage-panel">
     {canEdit?<div className="manage-actions"><button type="button" className="btn primary" onClick={()=>onNavigate('Prompt templates')}><Plus size={15}/>New or edit prompt</button><button type="button" className="btn" onClick={()=>onCommand?onCommand('/Extract'):onNavigate('Lapi agent V2')}><MessageSquare size={15}/>{onCommand?'Extract with /Extract':'Extract in Lapi Agent'}</button></div>:<p className="manage-note">You have Viewer access: prompts and extraction need Editor access.</p>}
     {prompts.length?<ul className="manage-list">{prompts.map(t=><li key={t.id}><FileJson size={15} aria-hidden="true"/><span className="manage-list-name"><strong title={t.name}>{t.name}</strong><small>Version {t.version||1}{t.source_filename?` · ${t.source_filename}`:''}</small></span><span className="manage-state" data-state="ready">{Object.keys(t.schema?.properties||{}).length} fields</span></li>)}</ul>:<p className="manage-empty">No prompts for this collection yet. Create one in Prompt, or attach a JSON prompt in Lapi Agent.</p>}
    </section>}
    {tab==='members'&&isOwner&&<section id="manage-panel-members" role="tabpanel" aria-labelledby="manage-tab-members" className="manage-panel">
     <DatasetMembers api={api} datasetId={dataset.id} notify={notify}/>
    </section>}
   </div>
  </div>;
 return inline?body:<div className="manage-backdrop" onClick={event=>{if(event.target===event.currentTarget)onClose();}}>{body}</div>;
}
