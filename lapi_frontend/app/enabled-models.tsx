"use client";
import {useEffect,useState} from 'react';
import {Layers} from 'lucide-react';
import {defaultRoles,summary,switchable,usesOf} from './enabled-models-data';
import './enabled-models.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;

/** Administrators turn registered models on or off for new work, on any screen size. */
export function EnabledModels({models,api,onChanged,onRegistration}:{models:Entity[];api:Api;onChanged:(model:Entity)=>void;onRegistration:()=>void}){
 const [defaults,setDefaults]=useState<Entity|null>(null);
 const [saving,setSaving]=useState(''),[error,setError]=useState(''),[done,setDone]=useState('');
 useEffect(()=>{let live=true;api('/workspace/defaults').then(v=>{if(live)setDefaults(v);}).catch(()=>{if(live)setDefaults(null);});return()=>{live=false;};},[api,models]);
 const list=switchable(models),counts=summary(models);
 const flip=async(model:Entity)=>{
  const next=model.enabled===false;
  setSaving(model.id);setError('');setDone('');
  try{const saved=await api(`/model-registrations/${encodeURIComponent(model.id)}/enabled`,'PUT',{enabled:next});onChanged(saved);setDone(`${model.name} is ${next?'on':'off'}.`);}
  catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setSaving('');}
 };
 return <section className="panel enabled-models" aria-labelledby="enabled-models-title">
  <div className="enabled-models-head">
   <h2 id="enabled-models-title">Turn models on or off</h2>
   <p>Models that are off are not offered in chat or for new mappings. Work already running keeps its model. {counts.on} on · {counts.off} off · {counts.chat} for chat.</p>
  </div>
  {error&&<p className="review-error" role="alert">{error}</p>}
  <p className="sr-only" role="status" aria-live="polite">{done}</p>
  {list.length?<ul className="enabled-models-list">{list.map(m=>{
   const roles=defaultRoles(m,defaults),on=m.enabled!==false,locked=on&&roles.length>0;
   return <li key={m.id} data-on={on||undefined}>
    <div className="enabled-models-text">
     <strong>{m.name}</strong>
     <span className="enabled-models-uses">{usesOf(m).map((u:string)=><span key={u}>{u}</span>)}{roles.map(r=><span key={r} className="is-default">{r} Default</span>)}</span>
     {locked&&<small>Choose another {roles.join(' and ')} Default before turning it off.</small>}
    </div>
    <button type="button" role="switch" aria-checked={on} aria-label={`${m.name} ${on?'on':'off'}`} className="enabled-models-switch" disabled={Boolean(saving)||locked} onClick={()=>void flip(m)}>
     <span aria-hidden="true"/>
    </button>
   </li>;})}</ul>
  :<div className="empty"><Layers size={30}/><h3>No models registered yet</h3><p>Register a model first, then turn it on or off here.</p></div>}
  <button type="button" className="btn enabled-models-more" onClick={onRegistration}>Open Model Registration</button>
 </section>;
}
