"use client";
import {useEffect,useState} from 'react';
import {Layers,Monitor,Smartphone} from 'lucide-react';
import {defaultRoles,devicesOf,summary,switchable,toggleDevice,usesOf,type Device} from './enabled-models-data';
import './enabled-models.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;

/** Administrators turn registered models on or off for new work, on any screen size. */
export function EnabledModels({models,api,onChanged,onRegistration}:{models:Entity[];api:Api;onChanged:(model:Entity)=>void;onRegistration:()=>void}){
 const [defaults,setDefaults]=useState<Entity|null>(null);
 const [saving,setSaving]=useState(''),[error,setError]=useState(''),[done,setDone]=useState('');
 useEffect(()=>{let live=true;api('/workspace/defaults').then(v=>{if(live)setDefaults(v);}).catch(()=>{if(live)setDefaults(null);});return()=>{live=false;};},[api,models]);
 const list=switchable(models),counts=summary(models);
 const save=async(model:Entity,body:{enabled:boolean;devices?:Device[]},said:string)=>{
  setSaving(model.id);setError('');setDone('');
  try{const saved=await api(`/model-registrations/${encodeURIComponent(model.id)}/enabled`,'PUT',body);onChanged(saved);setDone(said);}
  catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setSaving('');}
 };
 const flip=(model:Entity)=>{const next=model.enabled===false;void save(model,{enabled:next},`${model.name} is ${next?'on':'off'}.`);};
 const place=(model:Entity,device:Device)=>{
  const next=toggleDevice(devicesOf(model),device);
  void save(model,{enabled:true,devices:next},`${model.name} is offered on ${next.length===2?'phones and computers':next[0]==='phone'?'phones only':'computers only'}.`);
 };
 return <section className="panel enabled-models" aria-labelledby="enabled-models-title">
  <div className="enabled-models-head">
   <h2 id="enabled-models-title">Turn models on or off</h2>
   <p>Models that are off are not offered in chat or for new mappings. Choose where each one is offered: phones, computers or both, so small models can serve phones and large ones computers. Work already running keeps its model. {counts.on} on · {counts.off} off · chat: {counts.phoneChat} on phones, {counts.computerChat} on computers.</p>
  </div>
  {error&&<p className="review-error" role="alert">{error}</p>}
  <p className="sr-only" role="status" aria-live="polite">{done}</p>
  {list.length?<ul className="enabled-models-list">{list.map(m=>{
   const roles=defaultRoles(m,defaults),on=m.enabled!==false,locked=on&&roles.length>0;
   return <li key={m.id} data-on={on||undefined}>
    <div className="enabled-models-text">
     <strong>{m.name}</strong>
     <span className="enabled-models-uses">{usesOf(m).map((u:string)=><span key={u}>{u}</span>)}{roles.map(r=><span key={r} className="is-default">{r} Default</span>)}</span>
     {on&&<span className="enabled-models-devices" role="group" aria-label={`Where ${m.name} is offered`}>{(['phone','computer'] as Device[]).map(d=>{const pressed=devicesOf(m).includes(d),last=pressed&&devicesOf(m).length===1;const Icon=d==='phone'?Smartphone:Monitor;
      return <button key={d} type="button" aria-pressed={pressed} disabled={Boolean(saving)||last} title={last?'Offered on one device at least: turn the model off instead':undefined} onClick={()=>place(m,d)}><Icon size={16} aria-hidden="true"/>{d==='phone'?'Phone':'Computer'}</button>;})}</span>}
     {locked&&<small>{roles.length===1&&roles[0]==='Decisions'?'Choose Stop using next to its Decisions Default in Model Registration before turning it off.':`Choose another ${roles.join(' and ')} Default before turning it off.`}</small>}
    </div>
    <button type="button" role="switch" aria-checked={on} aria-label={`${m.name} ${on?'on':'off'}`} className="enabled-models-switch" disabled={Boolean(saving)||locked} onClick={()=>void flip(m)}>
     <span aria-hidden="true"/>
    </button>
   </li>;})}</ul>
  :<div className="empty"><Layers size={30}/><h3>No models registered yet</h3><p>Register a model first, then turn it on or off here.</p></div>}
  <button type="button" className="btn enabled-models-more" onClick={onRegistration}>Open Model Registration</button>
 </section>;
}
