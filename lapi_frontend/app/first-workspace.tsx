"use client";
import {useEffect,useRef,useState} from 'react';
import {FolderPlus} from 'lucide-react';
import {defaultDatasetName} from './quick-start-flow';
import './first-workspace.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;
export const WORKSPACE_LATER_KEY='lapi-first-workspace-later';

/** Ask only once the list has loaded, nobody has an active workspace, and "Not now" was not chosen this session. */
export const needsFirstWorkspace=(workspaces:Entity[],loaded:boolean,later:boolean)=>loaded&&!later&&!workspaces.some(w=>w.active!==false);

/** First sign-in with no workspace: name one, so everything has a place to go. */
export function FirstWorkspace({api,username,canCreate,onCreated,onLater}:{api:Api;username?:string;canCreate:boolean;onCreated:(id:string)=>void;onLater:()=>void}){
 const [name,setName]=useState(defaultDatasetName(username)),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const field=useRef<HTMLInputElement>(null),later=useRef<HTMLButtonElement>(null);
 useEffect(()=>{if(canCreate){field.current?.focus();field.current?.select();}else later.current?.focus();},[canCreate]);
 const create=async()=>{
  const value=name.trim();if(!value){setError('Give your workspace a name.');return;}
  setBusy(true);setError('');
  try{
   const created=await api('/datasets','POST',{name:value,description:''});
   await api(`/datasets/${encodeURIComponent(created.id)}/migrate-settings`,'POST',{});  // The overall Default models.
   onCreated(created.id);
  }catch(e){setError(e instanceof Error?e.message:'Could not create the workspace.');}
  finally{setBusy(false);}
 };
 return <div className="first-workspace-backdrop"><div className="first-workspace" role="dialog" aria-modal="true" aria-labelledby="first-workspace-title">
  <span className="first-workspace-icon" aria-hidden="true"><FolderPlus size={26}/></span>
  {canCreate?<>
   <h2 id="first-workspace-title">Create your workspace</h2>
   <p>A workspace keeps all your documents, chats and results in one place.</p>
   <form onSubmit={event=>{event.preventDefault();void create();}}>
    <label htmlFor="first-workspace-name">Workspace name</label>
    <input ref={field} id="first-workspace-name" value={name} maxLength={120} disabled={busy} onChange={event=>setName(event.target.value)}/>
    {error&&<p className="review-error" role="alert">{error}</p>}
    <button type="submit" className="first-workspace-primary" disabled={busy}>{busy?'Creating…':'Create workspace'}</button>
   </form>
   <button ref={later} type="button" className="first-workspace-later" disabled={busy} onClick={onLater}>Not now</button>
  </>:<>
   <h2 id="first-workspace-title">No workspace yet</h2>
   <p>Ask your administrator to create a workspace or share one with you. You can still chat with Lapi in the meantime.</p>
   <button ref={later} type="button" className="first-workspace-primary" onClick={onLater}>OK</button>
  </>}
 </div></div>;
}
