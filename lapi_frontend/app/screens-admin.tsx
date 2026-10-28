"use client";
import {useEffect,useState} from 'react';
import {Lock,Monitor,Smartphone} from 'lucide-react';

type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;
type Grant={screen:string;label:string;device:'computer'|'phone';admin_only:boolean;everyone:boolean;teams:string[];users:string[];default:boolean};
type Data={grants:Grant[];teams:{id:string;name:string}[];users:{id:string;username:string}[];core:string[];presets:Record<string,string>};
const key=(g:{screen:string;device:string})=>g.screen+'/'+g.device;
/** A cell's choice: everyone, off, or one team (people-level grants stay possible through the API). */
const choice=(g:Grant)=>g.everyone?'everyone':g.teams.length?'team:'+g.teams[0]:'off';

/** Access map → Screens: who sees each screen on phones and computers. Saved like dataset access
 * (database, then OpenFGA); people see the change within a minute, with no deploy. */
export function ScreensAdmin({api,onNotice}:{api:Api;onNotice:(text:string)=>void}){
 const [data,setData]=useState<Data|null>(null),[draft,setDraft]=useState<Record<string,string>>({}),[saving,setSaving]=useState(false),[error,setError]=useState('');
 const load=async()=>{try{const next:Data=await api('/screens');setData(next);setDraft(Object.fromEntries(next.grants.map(g=>[key(g),choice(g)])));setError('');}catch(e){setError(e instanceof Error?e.message:'Unable to load screens.');}};
 useEffect(()=>{void load();},[]);
 if(error)return <p role="alert" className="agent-v2-error">{error}</p>;
 if(!data)return <p role="status">Loading screens…</p>;
 const screens=Array.from(new Map(data.grants.map(g=>[g.screen,g])).values());
 const changed=data.grants.filter(g=>draft[key(g)]!==choice(g));
 const save=async()=>{
  setSaving(true);
  try{
   const grants=changed.map(g=>{const value=draft[key(g)];return {screen:g.screen,device:g.device,everyone:value==='everyone',teams:value.startsWith('team:')?[value.slice(5)]:[],users:value==='keep-users'?g.users:[]};});
   const next:Data=await api('/screens','PUT',{grants});setData(next);setDraft(Object.fromEntries(next.grants.map(g=>[key(g),choice(g)])));
   onNotice(`Saved ${grants.length} screen change${grants.length===1?'':'s'}. People see it within a minute.`);
  }catch(e){setError(e instanceof Error?e.message:'Could not save.');}finally{setSaving(false);}
 };
 const preset=async(name:string)=>{setSaving(true);try{const next:Data=await api('/screens/preset','POST',{preset:name});setData(next);setDraft(Object.fromEntries(next.grants.map(g=>[key(g),choice(g)])));onNotice('Preset applied: '+data.presets[name]);}catch(e){setError(e instanceof Error?e.message:'Could not apply the preset.');}finally{setSaving(false);}};
 const cell=(g:Grant)=><select aria-label={`${g.label} on ${g.device}`} value={draft[key(g)]} disabled={saving} onChange={e=>setDraft({...draft,[key(g)]:e.target.value})}>
  <option value="everyone">Everyone</option><option value="off">Off</option>
  {data.teams.map(t=><option key={t.id} value={'team:'+t.id}>Team: {t.name}</option>)}
  {g.users.length>0&&<option value="keep-users">{g.users.length} selected {g.users.length===1?'person':'people'}</option>}
 </select>;
 return <div className="screens-admin">
  <p className="muted">Dashboard, Lapi Agent and Quick start are always on. Administrators always see every screen. Everything else is switched here, per device, and applies within a minute, with no deploy. Hiding a screen changes what people see; the API stays protected as before.</p>
  <div className="screens-presets"><span>Presets:</span>
   <button type="button" className="btn" disabled={saving} onClick={()=>void preset('agent-only-phone')} title={data.presets['agent-only-phone']}>Agent only on phones</button>
   <button type="button" className="btn" disabled={saving} onClick={()=>void preset('everything')} title={data.presets.everything}>Everything everywhere</button>
  </div>
  <div className="access-matrix-scroll"><table className="access-matrix screens-matrix">
   <thead><tr><th scope="col">Screen</th><th scope="col"><Smartphone size={14} aria-hidden="true"/> Phone</th><th scope="col"><Monitor size={14} aria-hidden="true"/> Computer</th></tr></thead>
   <tbody>{screens.map(s=><tr key={s.screen}>
    <th scope="row">{s.label}{s.admin_only&&<small title="Administrators always see it"><Lock size={11} aria-hidden="true"/> admin screen</small>}</th>
    {(['phone','computer'] as const).map(device=>{const g=data.grants.find(x=>x.screen===s.screen&&x.device===device)!;return <td key={device} className={draft[key(g)]!==choice(g)?'screens-changed':''}>{cell(g)}</td>;})}
   </tr>)}</tbody></table></div>
  {changed.length>0&&<div className="access-savebar" role="region" aria-label="Unsaved screen changes">
   <span><strong>{changed.length}</strong> unsaved screen change{changed.length===1?'':'s'}</span>
   <div className="row"><button className="btn" disabled={saving} onClick={()=>setDraft(Object.fromEntries(data.grants.map(g=>[key(g),choice(g)])))}>Discard</button>
    <button className="btn primary" disabled={saving} onClick={()=>void save()}>{saving?'Saving…':'Save screens'}</button></div>
  </div>}
 </div>;
}
