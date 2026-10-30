"use client";
import {useEffect,useRef,useState} from 'react';
import {Check,Plus,User,Users} from 'lucide-react';
import {DatasetMembers} from './dataset-members';
import {COLLECTION_TYPES} from './workspace-scope';
import './workspace-gate.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
export type GateMode='choose'|'team'|'people'|'collection';

/** The steps around a workspace: choose one, create a team one and add people, create a collection. */
export function WorkspaceGate({mode,api,workspaces,canCreateTeam,current,onChoose,onTeamCreated,onPeopleDone,onCollectionCreated,onLater}:{mode:GateMode;api:Api;workspaces:Entity[];canCreateTeam:boolean;current?:Entity;onChoose:(id:string)=>void;onTeamCreated:(workspace:Entity)=>void;onPeopleDone:()=>void;onCollectionCreated:(id:string)=>void;onLater:(()=>void)|null}){
 const [name,setName]=useState(''),[type,setType]=useState(''),[teamMode,setTeamMode]=useState(mode==='team');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[unsaved,setUnsaved]=useState(false),[saved,setSaved]=useState('');
 const first=useRef<HTMLInputElement|null>(null);
 useEffect(()=>{setTeamMode(mode==='team');setName('');setError('');},[mode]);
 useEffect(()=>{first.current?.focus();},[mode,teamMode]);
 const run=async(work:()=>Promise<void>)=>{setBusy(true);setError('');try{await work();}catch(e){setError(e instanceof Error?e.message:'That did not work. Please try again.');}finally{setBusy(false);}};
 const createTeam=()=>run(async()=>{
  const value=name.trim();if(!value)throw new Error('Give your team workspace a name.');
  onTeamCreated(await api('/workspaces','POST',{name:value}));
 });
 const createCollection=()=>run(async()=>{
  const value=name.trim();if(!value)throw new Error('Give your collection a name.');
  const made=await api('/datasets','POST',{name:value,description:'',collection_type:type.trim(),workspace_id:current?.id||''});
  await api(`/datasets/${encodeURIComponent(made.id)}/migrate-settings`,'POST',{});  // The overall Default models.
  onCollectionCreated(made.id);
 });
 const shell=(title:string,children:React.ReactNode)=><div className="workspace-gate-backdrop"><div className="workspace-gate" role="dialog" aria-modal="true" aria-labelledby="workspace-gate-title"><h2 id="workspace-gate-title">{title}</h2>{children}</div></div>;
 const failure=error&&<p className="review-error" role="alert">{error}</p>;

 if(mode==='people'&&current)return shell('Add your team',<>
  <p>Choose who can use <strong>{current.name}</strong>. They see every collection in it. You can change this any time.</p>
  <DatasetMembers api={api} base={`/workspaces/${encodeURIComponent(current.id)}`} datasetId={current.id} notify={setSaved} onDirty={setUnsaved}/>
  <p className="sr-only" role="status">{saved}</p>
  <p className="workspace-gate-note">People need a Lapi account before you can add them. Ask your administrator to create one for anyone not listed.</p>
  <button type="button" className="workspace-gate-primary" disabled={unsaved} onClick={onPeopleDone}>Done</button>
  {unsaved&&<p className="workspace-gate-note" role="status">Save members first, or Reset to discard.</p>}
 </>);

 if(teamMode)return shell('Create a team workspace',<>
  <p>A team workspace is where you and other people share collections.</p>
  <form onSubmit={event=>{event.preventDefault();void createTeam();}}>
   <label htmlFor="workspace-gate-team">Team workspace name</label>
   <input ref={first} id="workspace-gate-team" value={name} maxLength={120} disabled={busy} placeholder="For example: Finance team" onChange={event=>setName(event.target.value)}/>
   {failure}
   <button type="submit" className="workspace-gate-primary" disabled={busy}>{busy?'Creating…':'Create and add people'}</button>
  </form>
  {(onLater||mode==='choose')&&<button type="button" className="workspace-gate-later" disabled={busy} onClick={()=>mode==='choose'?setTeamMode(false):onLater?.()}>{mode==='choose'?'Back':'Not now'}</button>}
 </>);

 if(mode==='collection')return shell(current?.collection_count?'Create a collection':'Create your first collection',<>
  <p>A collection holds related documents in <strong>{current?.name}</strong>. You can make as many as you need.</p>
  <form onSubmit={event=>{event.preventDefault();void createCollection();}}>
   <label htmlFor="workspace-gate-name">Collection name</label>
   <input ref={first} id="workspace-gate-name" value={name} maxLength={200} disabled={busy} placeholder="For example: Invoices 2026" onChange={event=>setName(event.target.value)}/>
   <label htmlFor="workspace-gate-type">Type <small>(optional)</small></label>
   <input id="workspace-gate-type" value={type} maxLength={40} disabled={busy} placeholder="Choose below or type your own" onChange={event=>setType(event.target.value)}/>
   <div className="workspace-gate-types" role="group" aria-label="Suggested types">{COLLECTION_TYPES.map(item=><button key={item} type="button" aria-pressed={type===item} disabled={busy} onClick={()=>setType(type===item?'':item)}>{item}</button>)}</div>
   {failure}
   <button type="submit" className="workspace-gate-primary" disabled={busy}>{busy?'Creating…':'Create collection'}</button>
  </form>
  {onLater&&<button type="button" className="workspace-gate-later" disabled={busy} onClick={onLater}>Not now</button>}
 </>);

 return shell('Which workspace?',<>
  <ul className="workspace-gate-list">{workspaces.map(w=><li key={w.id}><button type="button" aria-current={w.id===current?.id||undefined} onClick={()=>onChoose(w.id)}>
   <span className="workspace-gate-icon" aria-hidden="true">{w.audience==='personal'?<User size={20}/>:<Users size={20}/>}</span>
   <span className="workspace-gate-text"><strong>{w.name}</strong><small>{w.audience==='personal'?'Personal':'Team'} · {w.collection_count} {w.collection_count===1?'collection':'collections'}</small></span>
   {w.id===current?.id&&<Check size={18} aria-hidden="true"/>}
  </button></li>)}</ul>
  {canCreateTeam&&<button type="button" className="workspace-gate-later" onClick={()=>setTeamMode(true)}><Plus size={16} aria-hidden="true"/> Create a team workspace</button>}
 </>);
}
