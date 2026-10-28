"use client";
import {ActionButton} from "./action-button";
import {useEffect,useMemo,useRef,useState,type KeyboardEvent} from "react";
import {BookOpen,Plus,RefreshCw,Search,ShieldCheck,Trash2,User,Users} from "lucide-react";
import "./access-map.css";
import {SummaryTiles} from "./summary-tiles";
import {LEVEL_HELP,LEVEL_LABEL,access,changed,changedCell,changedTeams,changedUsers,cycle,differenceText,effective,initialDraft,initialTeamDraft,openfgaDifference,openfgaSummary,savedLevels,
 type Access,type AccessMapData,type Draft,type MapTeam,type MapUser} from "./access-map-data";

type Api=(path:string,method?:string,body?:any)=>Promise<any>;
type Mode="person"|"dataset"|"team";
type Node={id:string;label:string;access:Access;viaTeam?:string;changed:boolean;warning?:string;locked:boolean;team?:boolean};

const ROW=62,TOP=26;
const short=(text:string,size:number)=>text.length>size?text.slice(0,size-1)+"…":text;
const STATE_TEXT:Record<Access,string>={admin:"Administrator: every dataset",owner:"Owner",editor:"Editor",viewer:"Viewer",none:"No access"};
const CELL_TEXT:Record<Access,string>={admin:"A",owner:"O",editor:"E",viewer:"V",none:""};

function nodeState(node:Node){
 if(node.changed)return node.access==="none"?"Unsaved: access removed":`Unsaved: will be ${STATE_TEXT[node.access]}`;
 return STATE_TEXT[node.access]+(node.viaTeam?` via ${node.viaTeam}`:"");
}

/** One person, dataset or team on the left; everything it connects to on the right. A line means
 * access, its colour the level. Clicking a node on the right moves it to the next level. */
function AccessGraph({center,centerDetail,centerKind,nodes,onCycle}:{center:string;centerDetail:string;centerKind:Mode;nodes:Node[];onCycle:(node:Node)=>void}){
 const height=Math.max(nodes.length*ROW+TOP*2,180),middle=height/2;
 const press=(event:KeyboardEvent,node:Node)=>{if((event.key==="Enter"||event.key===" ")&&!node.locked){event.preventDefault();onCycle(node);}};
 return <svg className="access-graph" viewBox={`0 0 760 ${height}`} role="group" aria-label={`Access graph for ${center}`}>
  {nodes.map((node,index)=>{const y=TOP+index*ROW+ROW/2;
   return <path key={"line-"+node.id} className={`access-line access-line-${node.access}${node.viaTeam?" access-line-team":""}${node.changed?" access-line-changed":""}`} d={`M250 ${middle} C360 ${middle} 360 ${y} 470 ${y}`}/>;})}
  <g className={`access-center access-center-${centerKind}`}>
   <rect x="16" y={middle-38} width="234" height="76" rx="18"/>
   <text x="40" y={middle-6} className="access-center-label">{short(center,20)}</text>
   <text x="40" y={middle+18} className="access-center-detail">{short(centerDetail,30)}</text>
   <title>{center}</title>
  </g>
  {nodes.map((node,index)=>{const y=TOP+index*ROW,state=nodeState(node);
   return <g key={node.id} className={`access-node access-node-${node.access}${node.viaTeam?" access-node-team":""}${node.changed?" access-node-changed":""}${node.locked?" access-node-locked":""}`}
    role="button" tabIndex={node.locked?-1:0} aria-disabled={node.locked||undefined}
    aria-label={`${node.team?"Team ":""}${node.label}: ${state}${node.warning?". "+node.warning:""}${node.locked?"":". Activate to change the level"}`}
    onClick={()=>{if(!node.locked)onCycle(node);}} onKeyDown={event=>press(event,node)}>
    <rect x="470" y={y+6} width="274" height={ROW-12} rx="12"/>
    <circle cx="492" cy={y+ROW/2} r="6" className="access-dot"/>
    <text x="508" y={y+ROW/2-3} className="access-node-label">{(node.team?"Team · ":"")+short(node.label,node.team?17:24)}</text>
    <text x="508" y={y+ROW/2+13} className="access-node-detail">{short(state,34)}</text>
    {node.warning&&<g className="access-warning"><circle cx="726" cy={y+ROW/2} r="10"/><text x="726" y={y+ROW/2+4}>!</text></g>}
    <title>{node.label}: {state}{node.warning?" — "+node.warning:""}</title>
   </g>;})}
  {!nodes.length&&<text x="470" y={middle} className="access-node-detail">Nothing to connect yet.</text>}
 </svg>;
}

export function AccessMap({api}:{api:Api}){
 const [data,setData]=useState<AccessMapData|null>(null),[draft,setDraft]=useState<Draft>({}),[teamDraft,setTeamDraft]=useState<Draft>({});
 const [mode,setMode]=useState<Mode>("person"),[selected,setSelected]=useState(""),[search,setSearch]=useState("");
 const [loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const [teamName,setTeamName]=useState(""),[members,setMembers]=useState<string[]|null>(null);
 const mounted=useRef(true);
 const firstOf=(next:AccessMapData,which:Mode)=>which==="person"?(next.users.find(u=>!u.is_admin)||next.users[0])?.id||"":which==="dataset"?next.datasets[0]?.id||"":next.teams?.[0]?.id||"";
 async function load(keepNotice=false,which:Mode=mode){
  setLoading(true);setError("");if(!keepNotice)setNotice("");
  try{const next:AccessMapData=await api("/access-map");if(!mounted.current)return;
   setData(next);setDraft(initialDraft(next.users));setTeamDraft(initialTeamDraft(next.teams||[]));setMembers(null);
   setSelected(current=>{const ids=which==="person"?next.users.map(u=>u.id):which==="dataset"?next.datasets.map(d=>d.id):(next.teams||[]).map(t=>t.id);
    return ids.includes(current)?current:firstOf(next,which);});
  }catch(e){if(mounted.current)setError(e instanceof Error?e.message:"Unable to load the access map.");}
  finally{if(mounted.current)setLoading(false);}
 }
 useEffect(()=>{mounted.current=true;void load();return()=>{mounted.current=false;};},[]);
 const teams=data?.teams||[];
 const pending=useMemo(()=>data?changedUsers(data.users,draft):[],[data,draft]);
 const pendingTeams=useMemo(()=>data?changedTeams(teams,teamDraft):[],[data,teamDraft]);
 const readOnly=data?.can_edit===false;
 function switchMode(next:Mode){if(!data||next===mode)return;setMode(next);setSearch("");setMembers(null);setSelected(firstOf(data,next));}
 async function save(){
  if(!data||(!pending.length&&!pendingTeams.length))return;setSaving(true);setError("");setNotice("");
  const names=new Map<string,string>([...data.users.map(u=>[u.id,u.username] as [string,string]),...teams.map(t=>[t.id,"team "+t.name] as [string,string])]),done:string[]=[];
  try{
   for(const id of pending){const levels=draft[id]||{};await api(`/users/${encodeURIComponent(id)}/datasets`,"PUT",{dataset_ids:Object.keys(levels),levels});done.push(names.get(id)||id);}
   for(const id of pendingTeams){await api(`/teams/${encodeURIComponent(id)}/datasets`,"PUT",{grants:teamDraft[id]||{}});done.push(names.get(id)||id);}
   setNotice(`Saved access for ${done.join(", ")}. It applies to their next request.`);await load(true);}
  catch(e){setError((done.length?`Saved ${done.join(", ")}; then: `:"")+(e instanceof Error?e.message:"Access was not saved."));if(done.length)await load(true);}
  finally{setSaving(false);}
 }
 async function createTeam(){
  const name=teamName.trim();if(!name)return;setSaving(true);setError("");setNotice("");
  try{const team=await api("/teams","POST",{name});setTeamName("");setNotice(`Created team ${team.name}. Add its members, then give it datasets.`);setMode("team");await load(true,"team");setSelected(team.id);}
  catch(e){setError(e instanceof Error?e.message:"The team was not created.");}finally{setSaving(false);}
 }
 async function saveMembers(team:MapTeam){
  if(!members)return;setSaving(true);setError("");setNotice("");
  try{await api(`/teams/${encodeURIComponent(team.id)}/members`,"PUT",{user_ids:members});setNotice(`Saved the members of ${team.name}.`);await load(true);}
  catch(e){setError(e instanceof Error?e.message:"Members were not saved.");}finally{setSaving(false);}
 }
 async function removeTeam(team:MapTeam){
  if(!window.confirm(`Delete the team ${team.name}? Its members lose the access it gave them.${team.source==="keycloak"?" Keycloak adds it back at the next sign-in of anyone still in the group.":""}`))return;
  setSaving(true);setError("");setNotice("");
  try{await api(`/teams/${encodeURIComponent(team.id)}`,"DELETE");setNotice(`Deleted the team ${team.name}.`);await load(true);}
  catch(e){setError(e instanceof Error?e.message:"The team was not deleted.");}finally{setSaving(false);}
 }
 if(!data)return <div className="access-map">{loading?<p role="status" className="muted">Loading the access map…</p>:<div role="alert" className="notice error">{error||"Unable to load the access map."}<div className="row"><ActionButton className="btn" onClick={()=>void load()} label="Retry" action="retry" showLabel/></div></div>}</div>;

 const fga=openfgaSummary(data.openfga),people=data.users.filter(u=>!u.is_admin);
 const links=people.reduce((sum,u)=>sum+Object.keys(savedLevels(u)).length,0)+teams.reduce((sum,t)=>sum+Object.keys(t.grants).length,0);
 const lower=search.toLowerCase();
 const person=data.users.find(u=>u.id===selected),dataset=data.datasets.find(d=>d.id===selected),team=teams.find(t=>t.id===selected);
 const warn=(user:MapUser,datasetId:string)=>user.is_admin?undefined:differenceText(openfgaDifference(user,datasetId));
 const cyclePerson=(userId:string,datasetId:string)=>{setNotice("");setDraft(current=>cycle(current,userId,datasetId));};
 const cycleTeam=(teamId:string,datasetId:string)=>{setNotice("");setTeamDraft(current=>cycle(current,teamId,datasetId));};
 let graph=null;
 if(mode==="person"&&person){
  const count=data.datasets.filter(d=>effective(person,draft,teams,teamDraft,d.id).access!=="none").length;
  graph=<AccessGraph centerKind="person" center={person.username} centerDetail={person.is_admin?"Administrator · every dataset":`${count} of ${data.datasets.length} datasets`}
   nodes={data.datasets.map(d=>{const e=effective(person,draft,teams,teamDraft,d.id);return {id:d.id,label:d.name,access:e.access,viaTeam:e.viaTeam,changed:changed(person,draft,d.id),warning:warn(person,d.id),locked:person.is_admin||saving||readOnly};})}
   onCycle={node=>cyclePerson(person.id,node.id)}/>;
 }else if(mode==="dataset"&&dataset){
  const count=data.users.filter(u=>effective(u,draft,teams,teamDraft,dataset.id).access!=="none").length;
  graph=<AccessGraph centerKind="dataset" center={dataset.name} centerDetail={`${count} of ${data.users.length} people can open it`}
   nodes={[...data.users.map(u=>{const e=effective(u,draft,teams,teamDraft,dataset.id);return {id:u.id,label:u.username,access:e.access,viaTeam:e.viaTeam,changed:changed(u,draft,dataset.id),warning:warn(u,dataset.id),locked:u.is_admin||saving||readOnly};}),
    ...teams.map(t=>({id:"team:"+t.id,label:t.name,team:true,access:(teamDraft[t.id]?.[dataset.id]||"none") as Access,changed:changedCell(t.grants,teamDraft,t.id,dataset.id),locked:saving||readOnly}))]}
   onCycle={node=>node.team?cycleTeam(node.id.slice(5),dataset.id):cyclePerson(node.id,dataset.id)}/>;
 }else if(mode==="team"&&team){
  graph=<AccessGraph centerKind="team" center={team.name} centerDetail={`${team.member_ids.length} ${team.member_ids.length===1?"member":"members"} · ${team.source==="keycloak"?"Keycloak":"Lapi"} team`}
   nodes={data.datasets.map(d=>({id:d.id,label:d.name,access:(teamDraft[team.id]?.[d.id]||"none") as Access,changed:changedCell(team.grants,teamDraft,team.id,d.id),locked:saving||readOnly}))}
   onCycle={node=>cycleTeam(team.id,node.id)}/>;
 }
 const list=mode==="person"
  ?data.users.filter(u=>u.username.toLowerCase().includes(lower)).map(u=>{const n=Object.keys(draft[u.id]||{}).length,teamCount=(u.team_ids||[]).length;
   return {id:u.id,label:u.username,detail:u.is_admin?"Administrator · every dataset":[`${n} dataset${n===1?"":"s"}`,teamCount?`${teamCount} team${teamCount===1?"":"s"}`:"",u.is_auditor?"Auditor":"",u.sign_in==="keycloak"?"Keycloak":""].filter(Boolean).join(" · "),
    warn:Boolean(u.openfga&&!u.openfga.in_step),dirty:pending.includes(u.id)};})
  :mode==="dataset"?data.datasets.filter(d=>d.name.toLowerCase().includes(lower)).map(d=>{const count=data.users.filter(u=>effective(u,draft,teams,teamDraft,d.id).access!=="none").length;
   return {id:d.id,label:d.name,detail:`${count} ${count===1?"person":"people"}`,warn:data.users.some(u=>!u.is_admin&&openfgaDifference(u,d.id)),dirty:data.users.some(u=>changed(u,draft,d.id))||teams.some(t=>changedCell(t.grants,teamDraft,t.id,d.id))};})
  :teams.filter(t=>t.name.toLowerCase().includes(lower)).map(t=>({id:t.id,label:t.name,detail:`${t.member_ids.length} member${t.member_ids.length===1?"":"s"} · ${Object.keys(teamDraft[t.id]||{}).length} datasets${t.source==="keycloak"?" · Keycloak":""}`,warn:false,dirty:pendingTeams.includes(t.id)}));
 const names=new Map(data.users.map(u=>[u.id,u.username]));
 const editingMembers=members??team?.member_ids??[];

 return <div className="access-map">
  <SummaryTiles label="Access summary" tiles={[
   {label:"People",value:data.users.length,detail:`${data.users.length-people.length} administrator${data.users.length-people.length===1?"":"s"} open everything`,tone:""},
   {label:"Teams",value:teams.length,detail:"give access to groups of people",tone:"info"},
   {label:"Access links",value:links,detail:"saved grants to people and teams",tone:"ok"},
   {label:"OpenFGA",value:!data.openfga.enabled?"Off":data.openfga.reachable===false?"Down":data.openfga.differences?data.openfga.differences+" differ":"In step",detail:data.openfga.enabled?"answers every access check":"database decides",tone:fga.tone==="ok"?"ok":fga.tone==="info"?"info":fga.tone==="warn"?"warn":"error"},
  ]}/>
  <section className={`access-fga access-fga-${fga.tone}`} role="status"><ShieldCheck size={20} aria-hidden="true"/><div><strong>{fga.title}</strong><p>{fga.text}</p></div>
   <button className="btn" title="Check again" aria-label="Check access again" disabled={loading||saving} onClick={()=>void load()}><RefreshCw size={15}/></button></section>
  {readOnly&&<div role="note" className="notice">You are viewing access as an Auditor: you can see everything here but not change it.</div>}
  {notice&&<div role="status" className="notice">{notice}</div>}
  {error&&<div role="alert" className="notice error">{error}</div>}
  <section className="card access-levels-help" aria-label="Access levels">
   {(["viewer","editor","owner"] as const).map(level=><div key={level}><span className={`key key-${level}`}/><strong>{LEVEL_LABEL[level]}</strong><small>{LEVEL_HELP[level]}</small></div>)}
   <div><span className="key key-admin"/><strong>Administrator</strong><small>Every dataset, people and settings</small></div>
  </section>
  <section className="card access-workbench">
   <div className="access-toolbar">
    <div className="access-modes" role="tablist" aria-label="Show access by">
     <button role="tab" aria-selected={mode==="person"} className={mode==="person"?"selected":""} onClick={()=>switchMode("person")}><User size={15}/> By person</button>
     <button role="tab" aria-selected={mode==="dataset"} className={mode==="dataset"?"selected":""} onClick={()=>switchMode("dataset")}><BookOpen size={15}/> By dataset</button>
     <button role="tab" aria-selected={mode==="team"} className={mode==="team"?"selected":""} onClick={()=>switchMode("team")}><Users size={15}/> By team</button>
    </div>
    <ul className="access-legend" aria-label="Legend">
     <li><span className="key key-team"/>Through a team</li><li><span className="key key-none"/>No access</li><li><span className="key key-changed"/>Unsaved change</li>{data.openfga.enabled&&<li><span className="key key-warn">!</span>OpenFGA differs</li>}
    </ul>
   </div>
   <div className="access-columns">
    <div className="access-picker">
     <label className="account-search" htmlFor="access-search"><Search size={16}/><input id="access-search" placeholder={mode==="person"?"Search people":mode==="dataset"?"Search datasets":"Search teams"} value={search} onChange={e=>setSearch(e.target.value)}/></label>
     <ul aria-label={mode==="person"?"People":mode==="dataset"?"Datasets":"Teams"}>{list.map(item=><li key={item.id}>
      <button className={item.id===selected?"selected":""} aria-current={item.id===selected||undefined} onClick={()=>{setSelected(item.id);setMembers(null);}}>
       <span className="access-picker-name">{item.label}{item.dirty&&<i className="access-picker-dirty" title="Unsaved changes">●</i>}{item.warn&&<i className="access-picker-warn" title="OpenFGA answers differently">!</i>}</span>
       <small>{item.detail}</small>
      </button></li>)}</ul>
     {!list.length&&<p className="muted small">{search?"Nothing matches this search.":mode==="person"?"No people yet.":mode==="dataset"?"No datasets yet. Create one in Datasets.":"No teams yet."}</p>}
     {mode==="team"&&!readOnly&&<form className="access-new-team" onSubmit={e=>{e.preventDefault();void createTeam();}}>
      <label htmlFor="access-team-name">New Lapi team</label>
      <div className="row"><input id="access-team-name" value={teamName} maxLength={200} placeholder="For example Finance" onChange={e=>setTeamName(e.target.value)} disabled={saving}/>
       <button className="btn" type="submit" disabled={saving||!teamName.trim()}><Plus size={15}/> Add</button></div>
      <small className="muted">Teams from Keycloak groups appear here after their members sign in.</small>
     </form>}
    </div>
    <div className="access-canvas">
     {graph&&<div className="access-graph-scroll">{graph}</div>}
     {mode==="person"&&person?.is_admin&&<p className="muted small">Administrators open every dataset. Change their role in Users &amp; passwords.</p>}
     {graph&&!readOnly&&!(mode==="person"&&person?.is_admin)&&<p className="muted small">Click a {mode==="person"||mode==="team"?"dataset":"person or team"} to move it to the next level: No access → Viewer → Editor → Owner.</p>}
     {mode==="team"&&team&&<div className="access-team-members">
      <div className="access-team-head"><h3>Members of {team.name}</h3>
       {!readOnly&&<button className="btn access-team-delete" disabled={saving} onClick={()=>void removeTeam(team)}><Trash2 size={15}/> Delete team</button>}</div>
      {team.source==="keycloak"?<p className="muted small">Keycloak sets this team's members from the group "{team.name}" at each sign-in. Change them in Keycloak.</p>:null}
      <ul>{data.users.filter(u=>!u.is_admin).map(u=>{const checked=editingMembers.includes(u.id),locked=readOnly||saving||team.source==="keycloak";
       return <li key={u.id}><label className={locked?"locked":""}><input type="checkbox" checked={checked} disabled={locked} onChange={e=>setMembers(e.target.checked?[...editingMembers,u.id]:editingMembers.filter(id=>id!==u.id))}/>{u.username}</label></li>;})}</ul>
      {!data.users.some(u=>!u.is_admin)&&<p className="muted small">No people to add yet.</p>}
      {members&&!readOnly&&<div className="row"><button className="btn primary" disabled={saving} onClick={()=>void saveMembers(team)}>Save members</button><button className="btn" disabled={saving} onClick={()=>setMembers(null)}>Cancel</button></div>}
     </div>}
    </div>
   </div>
  </section>
  <section className="card access-matrix-card">
   <h2>Everyone at a glance</h2>
   <p className="muted small">Rows are people and teams, columns are datasets. V, E and O are Viewer, Editor and Owner; a faded cell comes from a team.{readOnly?"":" Click a cell to move it to the next level."}</p>
   <div className="access-matrix"><table><thead><tr><th scope="col">Person or team</th>{data.datasets.map(d=><th key={d.id} scope="col" title={d.name}><span>{short(d.name,18)}</span></th>)}</tr></thead>
    <tbody>{data.users.map(u=><tr key={u.id}><th scope="row"><button className="access-matrix-name" onClick={()=>{setMode("person");setSearch("");setSelected(u.id);}}>{u.username}</button>{u.is_admin?<small>Administrator</small>:u.is_auditor?<small>Auditor</small>:null}</th>
     {data.datasets.map(d=>{const e=effective(u,draft,teams,teamDraft,d.id),own=access(u,draft,d.id),dirty=changed(u,draft,d.id),warning=warn(u,d.id);
      const label=`${u.username} · ${d.name}: ${STATE_TEXT[e.access]}${e.viaTeam?" via "+e.viaTeam:""}${dirty?" (unsaved)":""}${warning?". "+warning:""}`;
      return <td key={d.id}><button className={`access-cell access-cell-${e.access}${e.viaTeam&&own==="none"?" access-cell-team":""}${dirty?" access-cell-changed":""}`} disabled={u.is_admin||saving||readOnly}
       aria-label={label} title={label} onClick={()=>cyclePerson(u.id,d.id)}>{CELL_TEXT[e.access]}{warning&&<i>!</i>}</button></td>;})}
    </tr>)}
    {teams.map(t=><tr key={"team-"+t.id} className="access-matrix-team"><th scope="row"><button className="access-matrix-name" onClick={()=>{setMode("team");setSearch("");setSelected(t.id);setMembers(null);}}>{t.name}</button><small>Team · {t.member_ids.length} member{t.member_ids.length===1?"":"s"}</small></th>
     {data.datasets.map(d=>{const level=(teamDraft[t.id]?.[d.id]||"none") as Access,dirty=changedCell(t.grants,teamDraft,t.id,d.id),label=`Team ${t.name} · ${d.name}: ${STATE_TEXT[level]}${dirty?" (unsaved)":""}`;
      return <td key={d.id}><button className={`access-cell access-cell-${level}${dirty?" access-cell-changed":""}`} disabled={saving||readOnly} aria-label={label} title={label} onClick={()=>cycleTeam(t.id,d.id)}>{CELL_TEXT[level]}</button></td>;})}
    </tr>)}</tbody></table>
    {!data.datasets.length&&<p className="muted small">No datasets yet.</p>}</div>
   {data.users.some(u=>u.team_ids?.length)&&<p className="muted small access-matrix-note">Team members: {teams.filter(t=>t.member_ids.length).map(t=>`${t.name} (${t.member_ids.map(id=>names.get(id)||id).join(", ")})`).join("; ")}.</p>}
  </section>
  {!readOnly&&(pending.length>0||pendingTeams.length>0)&&<div className="access-savebar" role="region" aria-label="Unsaved access changes">
   <span><strong>{pending.length+pendingTeams.length}</strong> {pending.length+pendingTeams.length===1?"person or team has":"people and teams have"} unsaved access changes</span>
   <div className="row"><button className="btn" disabled={saving} onClick={()=>{setDraft(initialDraft(data.users));setTeamDraft(initialTeamDraft(teams));setNotice("");}}>Discard</button>
    <button className="btn primary" disabled={saving} onClick={()=>void save()}>{saving?"Saving…":"Save access"}</button></div>
  </div>}
 </div>;
}
