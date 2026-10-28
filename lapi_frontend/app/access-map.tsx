"use client";
import {ActionButton} from "./action-button";
import {useEffect,useMemo,useRef,useState,type KeyboardEvent} from "react";
import {BookOpen,RefreshCw,Search,ShieldCheck,User} from "lucide-react";
import "./access-map.css";
import {SummaryTiles} from "./summary-tiles";
import {access,changed,changedUsers,initialDraft,openfgaDifference,openfgaSummary,toggle,type Access,type AccessMapData,type Draft,type MapUser} from "./access-map-data";

type Api=(path:string,method?:string,body?:any)=>Promise<any>;
type Mode="person"|"dataset";
type Node={id:string;label:string;detail:string;access:Access;changed:boolean;warning?:string;locked:boolean};

const ROW=62,TOP=26;
const short=(text:string,size:number)=>text.length>size?text.slice(0,size-1)+"…":text;
const STATE_TEXT:Record<Access,string>={admin:"Opens via Administrator role",granted:"Can open",none:"No access"};

/** One person (or dataset) on the left, every dataset (or person) on the right; a line means access.
 * Clicking a node on the right switches that access in the unsaved draft. */
function AccessGraph({center,centerDetail,centerKind,nodes,onToggle}:{center:string;centerDetail:string;centerKind:Mode;nodes:Node[];onToggle:(id:string)=>void}){
 const height=Math.max(nodes.length*ROW+TOP*2,180),middle=height/2;
 const press=(event:KeyboardEvent,node:Node)=>{if((event.key==="Enter"||event.key===" ")&&!node.locked){event.preventDefault();onToggle(node.id);}};
 return <svg className="access-graph" viewBox={`0 0 760 ${height}`} role="group" aria-label={`Access graph for ${center}`}>
  {nodes.map((node,index)=>{const y=TOP+index*ROW+ROW/2;
   return <path key={"line-"+node.id} className={`access-line access-line-${node.access}${node.changed?" access-line-changed":""}`} d={`M250 ${middle} C360 ${middle} 360 ${y} 470 ${y}`}/>;})}
  <g className={`access-center access-center-${centerKind}`}>
   <rect x="16" y={middle-38} width="234" height="76" rx="18"/>
   <text x="40" y={middle-6} className="access-center-label">{short(center,22)}</text>
   <text x="40" y={middle+18} className="access-center-detail">{short(centerDetail,30)}</text>
   <title>{center}</title>
  </g>
  {nodes.map((node,index)=>{const y=TOP+index*ROW;
   const state=node.changed?(node.access==="granted"?"Unsaved: will get access":"Unsaved: access will be removed"):STATE_TEXT[node.access];
   return <g key={node.id} className={`access-node access-node-${node.access}${node.changed?" access-node-changed":""}${node.locked?" access-node-locked":""}`}
    role="button" tabIndex={node.locked?-1:0} aria-pressed={node.access!=="none"} aria-disabled={node.locked||undefined}
    aria-label={`${node.label}: ${state}${node.warning?". "+node.warning:""}`}
    onClick={()=>{if(!node.locked)onToggle(node.id);}} onKeyDown={event=>press(event,node)}>
    <rect x="470" y={y+6} width="274" height={ROW-12} rx="12"/>
    <circle cx="492" cy={y+ROW/2} r="6" className="access-dot"/>
    <text x="508" y={y+ROW/2-3} className="access-node-label">{short(node.label,24)}</text>
    <text x="508" y={y+ROW/2+13} className="access-node-detail">{state}</text>
    {node.warning&&<g className="access-warning"><circle cx="726" cy={y+ROW/2} r="10"/><text x="726" y={y+ROW/2+4}>!</text></g>}
    <title>{node.label}{node.warning?" — "+node.warning:""}</title>
   </g>;})}
  {!nodes.length&&<text x="470" y={middle} className="access-node-detail">Nothing to connect yet.</text>}
 </svg>;
}

export function AccessMap({api}:{api:Api}){
 const [data,setData]=useState<AccessMapData|null>(null),[draft,setDraft]=useState<Draft>({});
 const [mode,setMode]=useState<Mode>("person"),[selected,setSelected]=useState(""),[search,setSearch]=useState("");
 const [loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const mounted=useRef(true);
 async function load(keepNotice=false){
  setLoading(true);setError("");if(!keepNotice)setNotice("");
  try{const next:AccessMapData=await api("/access-map");if(!mounted.current)return;
   setData(next);setDraft(initialDraft(next.users));
   setSelected(current=>{const ids=mode==="person"?next.users.map(u=>u.id):next.datasets.map(d=>d.id);
    return ids.includes(current)?current:mode==="person"?(next.users.find(u=>!u.is_admin)||next.users[0])?.id||"":ids[0]||"";});
  }catch(e){if(mounted.current)setError(e instanceof Error?e.message:"Unable to load the access map.");}
  finally{if(mounted.current)setLoading(false);}
 }
 useEffect(()=>{mounted.current=true;void load();return()=>{mounted.current=false;};},[]);
 const pending=useMemo(()=>data?changedUsers(data.users,draft):[],[data,draft]);
 function switchMode(next:Mode){if(!data||next===mode)return;setMode(next);setSearch("");
  setSelected(next==="person"?(data.users.find(u=>!u.is_admin)||data.users[0])?.id||"":data.datasets[0]?.id||"");}
 async function save(){
  if(!data||!pending.length)return;setSaving(true);setError("");setNotice("");
  const names=new Map(data.users.map(u=>[u.id,u.username])),done:string[]=[];
  try{for(const id of pending){await api(`/users/${encodeURIComponent(id)}/datasets`,"PUT",{dataset_ids:draft[id]});done.push(names.get(id)||id);}
   setNotice(`Saved access for ${done.join(", ")}. It applies to their next request.`);await load(true);}
  catch(e){setError((done.length?`Saved ${done.join(", ")}; then: `:"")+(e instanceof Error?e.message:"Access was not saved."));if(done.length)await load(true);}
  finally{setSaving(false);}
 }
 if(!data)return <div className="access-map">{loading?<p role="status" className="muted">Loading the access map…</p>:<div role="alert" className="notice error">{error||"Unable to load the access map."}<div className="row"><ActionButton className="btn" onClick={()=>void load()} label="Retry" action="retry" showLabel/></div></div>}</div>;

 const fga=openfgaSummary(data.openfga),people=data.users.filter(u=>!u.is_admin);
 const links=people.reduce((sum,u)=>sum+u.dataset_ids.length,0);
 const lower=search.toLowerCase();
 const person=data.users.find(u=>u.id===selected),dataset=data.datasets.find(d=>d.id===selected);
 const fgaWarning=(user:MapUser,datasetId:string)=>{const difference=openfgaDifference(user,datasetId);
  return difference==="missing"?"Saved, but OpenFGA refuses it":difference==="extra"?"Not saved, but OpenFGA allows it":undefined;};
 let graph=null;
 if(mode==="person"&&person){
  graph=<AccessGraph centerKind="person" center={person.username} centerDetail={person.is_admin?"Administrator · every dataset":`${(draft[person.id]||[]).length} of ${data.datasets.length} datasets`}
   nodes={data.datasets.map(d=>({id:d.id,label:d.name,detail:d.status||"",access:access(person,draft,d.id),changed:changed(person,draft,d.id),warning:person.is_admin?undefined:fgaWarning(person,d.id),locked:person.is_admin||saving}))}
   onToggle={id=>{setNotice("");setDraft(current=>toggle(current,person.id,id));}}/>;
 }else if(mode==="dataset"&&dataset){
  const count=data.users.filter(u=>access(u,draft,dataset.id)!=="none").length;
  graph=<AccessGraph centerKind="dataset" center={dataset.name} centerDetail={`${count} of ${data.users.length} people can open it`}
   nodes={data.users.map(u=>({id:u.id,label:u.username,detail:"",access:access(u,draft,dataset.id),changed:changed(u,draft,dataset.id),warning:u.is_admin?undefined:fgaWarning(u,dataset.id),locked:u.is_admin||saving}))}
   onToggle={id=>{setNotice("");setDraft(current=>toggle(current,id,dataset.id));}}/>;
 }
 const list=mode==="person"
  ?data.users.filter(u=>u.username.toLowerCase().includes(lower)).map(u=>({id:u.id,label:u.username,detail:u.is_admin?"Administrator · every dataset":`${(draft[u.id]||[]).length} dataset${(draft[u.id]||[]).length===1?"":"s"}`+(u.sign_in==="keycloak"?" · Keycloak":""),warn:Boolean(u.openfga&&!u.openfga.in_step),dirty:pending.includes(u.id)}))
  :data.datasets.filter(d=>d.name.toLowerCase().includes(lower)).map(d=>{const count=data.users.filter(u=>access(u,draft,d.id)!=="none").length;
   return {id:d.id,label:d.name,detail:`${count} ${count===1?"person":"people"}`,warn:data.users.some(u=>!u.is_admin&&openfgaDifference(u,d.id)),dirty:data.users.some(u=>changed(u,draft,d.id))};});

 return <div className="access-map">
  <SummaryTiles label="Access summary" tiles={[
   {label:"People",value:data.users.length,detail:`${data.users.length-people.length} administrator${data.users.length-people.length===1?"":"s"} open everything`,tone:""},
   {label:"Datasets",value:data.datasets.length,detail:"in this workspace",tone:"info"},
   {label:"Access links",value:links,detail:"saved person → dataset grants",tone:"ok"},
   {label:"OpenFGA",value:!data.openfga.enabled?"Off":data.openfga.reachable===false?"Down":data.openfga.differences?data.openfga.differences+" differ":"In step",detail:data.openfga.enabled?"answers every access check":"database decides",tone:fga.tone==="ok"?"ok":fga.tone==="info"?"info":fga.tone==="warn"?"warn":"error"},
  ]}/>
  <section className={`access-fga access-fga-${fga.tone}`} role="status"><ShieldCheck size={20} aria-hidden="true"/><div><strong>{fga.title}</strong><p>{fga.text}</p></div>
   <button className="btn" title="Check again" aria-label="Check access again" disabled={loading||saving} onClick={()=>void load()}><RefreshCw size={15}/></button></section>
  {notice&&<div role="status" className="notice">{notice}</div>}
  {error&&<div role="alert" className="notice error">{error}</div>}
  <section className="card access-workbench">
   <div className="access-toolbar">
    <div className="access-modes" role="tablist" aria-label="Show access by">
     <button role="tab" aria-selected={mode==="person"} className={mode==="person"?"selected":""} onClick={()=>switchMode("person")}><User size={15}/> By person</button>
     <button role="tab" aria-selected={mode==="dataset"} className={mode==="dataset"?"selected":""} onClick={()=>switchMode("dataset")}><BookOpen size={15}/> By dataset</button>
    </div>
    <ul className="access-legend" aria-label="Legend">
     <li><span className="key key-granted"/>Can open</li><li><span className="key key-admin"/>Administrator</li><li><span className="key key-none"/>No access</li><li><span className="key key-changed"/>Unsaved change</li>{data.openfga.enabled&&<li><span className="key key-warn">!</span>OpenFGA differs</li>}
    </ul>
   </div>
   <div className="access-columns">
    <div className="access-picker">
     <label className="account-search" htmlFor="access-search"><Search size={16}/><input id="access-search" placeholder={mode==="person"?"Search people":"Search datasets"} value={search} onChange={e=>setSearch(e.target.value)}/></label>
     <ul aria-label={mode==="person"?"People":"Datasets"}>{list.map(item=><li key={item.id}>
      <button className={item.id===selected?"selected":""} aria-current={item.id===selected||undefined} onClick={()=>setSelected(item.id)}>
       <span className="access-picker-name">{item.label}{item.dirty&&<i className="access-picker-dirty" title="Unsaved changes">●</i>}{item.warn&&<i className="access-picker-warn" title="OpenFGA answers differently">!</i>}</span>
       <small>{item.detail}</small>
      </button></li>)}</ul>
     {!list.length&&<p className="muted small">{search?"Nothing matches this search.":mode==="person"?"No people yet.":"No datasets yet. Create one in Datasets."}</p>}
    </div>
    <div className="access-canvas">
     {graph&&<div className="access-graph-scroll">{graph}</div>}
     {mode==="person"&&person?.is_admin&&<p className="muted small">Administrators open every dataset. Change their role in Users &amp; passwords.</p>}
     {graph&&!(mode==="person"&&person?.is_admin)&&<p className="muted small">Click a {mode==="person"?"dataset":"person"} to give or remove access, then save.</p>}
    </div>
   </div>
  </section>
  <section className="card access-matrix-card">
   <h2>Everyone at a glance</h2>
   <p className="muted small">Each row is a person, each column a dataset. Click a cell to switch access; click a name to see that person's graph.</p>
   <div className="access-matrix"><table><thead><tr><th scope="col">Person</th>{data.datasets.map(d=><th key={d.id} scope="col" title={d.name}><span>{short(d.name,18)}</span></th>)}</tr></thead>
    <tbody>{data.users.map(u=><tr key={u.id}><th scope="row"><button className="access-matrix-name" onClick={()=>{setMode("person");setSearch("");setSelected(u.id);}}>{u.username}</button>{u.is_admin&&<small>Administrator</small>}</th>
     {data.datasets.map(d=>{const state=access(u,draft,d.id),dirty=changed(u,draft,d.id),warning=u.is_admin?undefined:fgaWarning(u,d.id);
      return <td key={d.id}><button className={`access-cell access-cell-${state}${dirty?" access-cell-changed":""}`} disabled={u.is_admin||saving}
       aria-pressed={state!=="none"} aria-label={`${u.username} · ${d.name}: ${STATE_TEXT[state]}${dirty?" (unsaved)":""}${warning?". "+warning:""}`}
       title={`${u.username} · ${d.name}: ${STATE_TEXT[state]}${warning?" — "+warning:""}`} onClick={()=>{setNotice("");setDraft(current=>toggle(current,u.id,d.id));}}>{warning&&<i>!</i>}</button></td>;})}
    </tr>)}</tbody></table>
    {!data.datasets.length&&<p className="muted small">No datasets yet.</p>}</div>
  </section>
  {pending.length>0&&<div className="access-savebar" role="region" aria-label="Unsaved access changes">
   <span><strong>{pending.length}</strong> {pending.length===1?"person has":"people have"} unsaved access changes</span>
   <div className="row"><button className="btn" disabled={saving} onClick={()=>{setDraft(initialDraft(data.users));setNotice("");}}>Discard</button>
    <button className="btn primary" disabled={saving} onClick={()=>void save()}>{saving?"Saving…":"Save access"}</button></div>
  </div>}
 </div>;
}
