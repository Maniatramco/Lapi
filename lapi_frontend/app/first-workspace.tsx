"use client";
import {useEffect,useRef,useState} from 'react';
import {FolderPlus,User,Users} from 'lucide-react';
import {DatasetMembers} from './dataset-members';
import {defaultDatasetName} from './quick-start-flow';
import './first-workspace.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
export const WORKSPACE_LATER_KEY='lapi-first-workspace-later';

/** Ask only once the list has loaded, nobody has an active workspace, and "Not now" was not chosen this session. */
export const needsFirstWorkspace=(workspaces:Entity[],loaded:boolean,later:boolean)=>loaded&&!later&&!workspaces.some(w=>w.active!==false);

/** First sign-in with no workspace: name one, so everything has a place to go. */
export function FirstWorkspace({api,username,canCreate,onCreated,onLater}:{api:Api;username?:string;canCreate:boolean;onCreated:(id:string)=>void;onLater:()=>void}){
 const [name,setName]=useState(defaultDatasetName(username)),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [audience,setAudience]=useState<'me'|'team'>('me'),[created,setCreated]=useState(''),[unsaved,setUnsaved]=useState(false),[saved,setSaved]=useState('');
 const field=useRef<HTMLInputElement>(null),later=useRef<HTMLButtonElement>(null);
 useEffect(()=>{if(canCreate){field.current?.focus();field.current?.select();}else later.current?.focus();},[canCreate]);
 const create=async()=>{
  const value=name.trim();if(!value){setError('Give your workspace a name.');return;}
  setBusy(true);setError('');
  try{
   const made=await api('/datasets','POST',{name:value,description:'',audience:audience==='team'?'team':'personal'});
   await api(`/datasets/${encodeURIComponent(made.id)}/migrate-settings`,'POST',{});  // The overall Default models.
   // A team workspace stays open for adding people; the list refreshes once this step is done.
   if(audience==='team')setCreated(made.id);else onCreated(made.id);
  }catch(e){setError(e instanceof Error?e.message:'Could not create the workspace.');}
  finally{setBusy(false);}
 };
 if(created)return <div className="first-workspace-backdrop"><div className="first-workspace is-team" role="dialog" aria-modal="true" aria-labelledby="first-workspace-title">
  <h2 id="first-workspace-title">Add your team</h2>
  <p>Choose who can use <strong>{name.trim()}</strong>. You can change this any time.</p>
  <DatasetMembers api={api} datasetId={created} notify={setSaved} onDirty={setUnsaved}/>
  <p className="sr-only" role="status">{saved}</p>
  <p className="first-workspace-note">People need a Lapi account before you can add them. Ask your administrator to create one for anyone not listed.</p>
  <button type="button" className="first-workspace-primary" disabled={unsaved} onClick={()=>onCreated(created)}>Done</button>
  {unsaved&&<p className="first-workspace-note" role="status">Save members first, or Reset to discard.</p>}
 </div></div>;
 return <div className="first-workspace-backdrop"><div className="first-workspace" role="dialog" aria-modal="true" aria-labelledby="first-workspace-title">
  <span className="first-workspace-icon" aria-hidden="true"><FolderPlus size={26}/></span>
  {canCreate?<>
   <h2 id="first-workspace-title">Create your workspace</h2>
   <p>A workspace keeps all your documents, chats and results in one place.</p>
   <form onSubmit={event=>{event.preventDefault();void create();}}>
    <label htmlFor="first-workspace-name">Workspace name</label>
    <input ref={field} id="first-workspace-name" value={name} maxLength={120} disabled={busy} onChange={event=>setName(event.target.value)}/>
    <fieldset className="first-workspace-audience"><legend>Who is it for?</legend>
     <label data-selected={audience==='me'||undefined}><input type="radio" name="first-workspace-audience" checked={audience==='me'} disabled={busy} onChange={()=>setAudience('me')}/><User size={20} aria-hidden="true"/><span><strong>Just me</strong><small>Private to you and your administrators</small></span></label>
     <label data-selected={audience==='team'||undefined}><input type="radio" name="first-workspace-audience" checked={audience==='team'} disabled={busy} onChange={()=>setAudience('team')}/><Users size={20} aria-hidden="true"/><span><strong>My team</strong><small>Add people next</small></span></label>
    </fieldset>
    {error&&<p className="review-error" role="alert">{error}</p>}
    <button type="submit" className="first-workspace-primary" disabled={busy}>{busy?'Creating…':audience==='team'?'Create and add people':'Create workspace'}</button>
   </form>
   <button ref={later} type="button" className="first-workspace-later" disabled={busy} onClick={onLater}>Not now</button>
  </>:<>
   <h2 id="first-workspace-title">No workspace yet</h2>
   <p>Ask your administrator to create a workspace or share one with you. You can still chat with Lapi in the meantime.</p>
   <button ref={later} type="button" className="first-workspace-primary" onClick={onLater}>OK</button>
  </>}
 </div></div>;
}
