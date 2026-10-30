"use client";
import {useEffect,useState} from 'react';
import {Plus,Users} from 'lucide-react';
import {LEVEL_HELP,LEVEL_LABEL,LEVELS,type Level} from './access-map-data';

type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
type Members={people:{user_id:string;level:Level}[];teams:{team_id:string;level:Level}[];directory:{id:string;username:string}[];all_teams:{id:string;name:string;source:string}[]};
type Change=Record<string,Level|null>;

/** Who can open this dataset and at which level. Dataset owners and administrators change it here;
 * administrators always have access and are not listed. */
export function DatasetMembers({api,datasetId,notify,onDirty,base}:{api:Api;datasetId:string;notify:(text:string)=>void;onDirty?:(dirty:boolean)=>void;base?:string}){
 const root=base||`/datasets/${encodeURIComponent(datasetId)}`;
 const [data,setData]=useState<Members|null>(null),[people,setPeople]=useState<Change>({}),[teams,setTeams]=useState<Change>({});
 const [addPerson,setAddPerson]=useState(''),[addTeam,setAddTeam]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const load=async()=>{setError('');try{setData(await api(`${root}/members`));setPeople({});setTeams({});}catch(e){setError(e instanceof Error?e.message:'Members could not be loaded.');}};
 useEffect(()=>{void load();},[datasetId]);
 useEffect(()=>{onDirty?.(Object.keys(people).length+Object.keys(teams).length>0);},[people,teams]);
 if(!data)return error?<p className="notice error" role="alert">{error}</p>:<p className="manage-empty" role="status">Loading members…</p>;
 const names=new Map(data.directory.map(p=>[p.id,p.username])),teamNames=new Map(data.all_teams.map(t=>[t.id,t.name]));
 const personLevel=(id:string)=>id in people?people[id]:data.people.find(p=>p.user_id===id)?.level??null;
 const teamLevel=(id:string)=>id in teams?teams[id]:data.teams.find(t=>t.team_id===id)?.level??null;
 const shownPeople=[...new Set([...data.people.map(p=>p.user_id),...Object.keys(people)])].filter(id=>personLevel(id)!==null||data.people.some(p=>p.user_id===id));
 const shownTeams=[...new Set([...data.teams.map(t=>t.team_id),...Object.keys(teams)])];
 const dirty=Object.keys(people).length+Object.keys(teams).length>0;
 const save=async()=>{setBusy(true);setError('');try{await api(`${root}/members`,'PUT',{people,teams});notify('Saved who can open this collection. It applies to their next request.');await load();}
  catch(e){setError(e instanceof Error?e.message:'Members were not saved.');}finally{setBusy(false);}};
 const select=(value:Level|null,onChange:(level:Level|null)=>void,label:string)=><select aria-label={label} value={value??''} disabled={busy} onChange={event=>onChange((event.target.value||null) as Level|null)}>
  {LEVELS.map(level=><option key={level} value={level}>{LEVEL_LABEL[level]} · {LEVEL_HELP[level]}</option>)}<option value="">No access</option></select>;
 return <div className="dataset-members">
  <p className="manage-note"><Users size={14} aria-hidden="true"/>Viewer: chat and read results. Editor: also upload, extract and review. Owner: also manage this collection and its members. Administrators always have access.</p>
  {error&&<p className="notice error" role="alert">{error}</p>}
  <h3>People</h3>
  {shownPeople.length?<ul className="manage-list">{shownPeople.map(id=><li key={id}><span className="manage-list-name"><strong>{names.get(id)||id}</strong></span>{select(personLevel(id),level=>setPeople(c=>({...c,[id]:level})),`Access for ${names.get(id)||id}`)}</li>)}</ul>:<p className="manage-empty">Only administrators can open this collection so far.</p>}
  <div className="manage-actions"><select aria-label="Person to add" value={addPerson} disabled={busy} onChange={event=>setAddPerson(event.target.value)}><option value="">Add a person…</option>{data.directory.filter(p=>!shownPeople.includes(p.id)).map(p=><option key={p.id} value={p.id}>{p.username}</option>)}</select>
   <button type="button" className="btn" disabled={busy||!addPerson} onClick={()=>{setPeople(c=>({...c,[addPerson]:'viewer'}));setAddPerson('');}}><Plus size={15}/>Add as Viewer</button></div>
  <h3>Teams</h3>
  {shownTeams.length?<ul className="manage-list">{shownTeams.map(id=><li key={id}><span className="manage-list-name"><strong>{teamNames.get(id)||id}</strong><small>Team</small></span>{select(teamLevel(id),level=>setTeams(c=>({...c,[id]:level})),`Access for team ${teamNames.get(id)||id}`)}</li>)}</ul>:<p className="manage-empty">No teams have access.</p>}
  {data.all_teams.length>0&&<div className="manage-actions"><select aria-label="Team to add" value={addTeam} disabled={busy} onChange={event=>setAddTeam(event.target.value)}><option value="">Add a team…</option>{data.all_teams.filter(t=>!shownTeams.includes(t.id)).map(t=><option key={t.id} value={t.id}>{t.name}{t.source==='keycloak'?' (Keycloak)':''}</option>)}</select>
   <button type="button" className="btn" disabled={busy||!addTeam} onClick={()=>{setTeams(c=>({...c,[addTeam]:'viewer'}));setAddTeam('');}}><Plus size={15}/>Add as Viewer</button></div>}
  <div className="manage-actions"><button type="button" className="btn primary" disabled={busy||!dirty} onClick={()=>void save()}>{busy?'Saving…':'Save members'}</button><button type="button" className="btn" disabled={busy||!dirty} onClick={()=>{setPeople({});setTeams({});}}>Reset</button></div>
 </div>;
}
