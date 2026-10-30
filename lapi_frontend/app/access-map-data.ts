/** Access map data: who can open which dataset and at which level (Viewer, Editor, Owner),
 * directly or through a team, the unsaved changes an administrator is making, and whether
 * OpenFGA answers the same as the saved access. */
export type Level='viewer'|'editor'|'owner';
export type LevelMap=Record<string,Level>;
export type OpenFgaAnswer={administrator:boolean;auditor?:boolean;levels?:LevelMap;dataset_ids:string[];in_step:boolean};
export type MapUser={id:string;username:string;is_admin:boolean;is_auditor?:boolean;is_contributor?:boolean;workspace_role?:string;sign_in?:string;
 dataset_ids:string[];levels?:LevelMap;effective?:LevelMap;team_ids?:string[];openfga?:OpenFgaAnswer};
export type MapTeam={id:string;name:string;source:'local'|'keycloak'|string;member_ids:string[];grants:LevelMap};
export type MapDataset={id:string;name:string;status?:string};
export type OpenFgaStatus={enabled:boolean;reachable:boolean|null;differences:number};
export type AccessMapData={users:MapUser[];datasets:MapDataset[];teams?:MapTeam[];openfga:OpenFgaStatus;can_edit?:boolean};
/** Direct grants per person (or per team), as they will be once saved. */
export type Draft=Record<string,LevelMap>;
export type Access='admin'|Level|'none';

export const LEVELS:Level[]=['viewer','editor','owner'];
export const LEVEL_LABEL:Record<Level,string>={viewer:'Viewer',editor:'Editor',owner:'Owner'};
export const LEVEL_HELP:Record<Level,string>={viewer:'Chat and read results',editor:'Also upload, extract and review',owner:'Also manage the workspace and its members'};
const RANK:Record<string,number>={none:0,viewer:1,editor:2,owner:3,admin:4};

/** Saved direct grants of a person; older servers sent only dataset_ids (Viewer). */
export function savedLevels(user:MapUser):LevelMap{
 return user.levels||Object.fromEntries(user.dataset_ids.map(id=>[id,'viewer' as Level]));
}

export function initialDraft(users:MapUser[]):Draft{
 return Object.fromEntries(users.filter(user=>!user.is_admin).map(user=>[user.id,{...savedLevels(user)}]));
}

export function initialTeamDraft(teams:MapTeam[]):Draft{
 return Object.fromEntries(teams.map(team=>[team.id,{...team.grants}]));
}

/** No access → Viewer → Editor → Owner → no access. */
export function nextLevel(current:Level|undefined):Level|undefined{
 if(!current)return 'viewer';
 const index=LEVELS.indexOf(current);
 return index===LEVELS.length-1?undefined:LEVELS[index+1];
}

export function cycle(draft:Draft,id:string,datasetId:string):Draft{
 if(!(id in draft))return draft; // Administrators open every dataset by role.
 const next={...draft[id]};const level=nextLevel(next[datasetId]);
 if(level)next[datasetId]=level;else delete next[datasetId];
 return {...draft,[id]:next};
}

export function setLevel(draft:Draft,id:string,datasetId:string,level:Level|undefined):Draft{
 if(!(id in draft))return draft;
 const next={...draft[id]};if(level)next[datasetId]=level;else delete next[datasetId];
 return {...draft,[id]:next};
}

/** Highest level a person gets through their teams (using the teams' draft grants). */
export function teamLevel(user:MapUser,teams:MapTeam[],teamDraft:Draft,datasetId:string):{level?:Level;team?:string}{
 let best:{level?:Level;team?:string}={};
 for(const team of teams){
  if(!team.member_ids.includes(user.id))continue;
  const level=(teamDraft[team.id]||team.grants)[datasetId];
  if(level&&RANK[level]>RANK[best.level||'none'])best={level,team:team.name};
 }
 return best;
}

/** The person's own grant (draft) for a dataset. */
export function access(user:MapUser,draft:Draft,datasetId:string):Access{
 if(user.is_admin)return 'admin';
 return draft[user.id]?.[datasetId]||'none';
}

/** What the person will actually get: the higher of their own grant and their teams'. */
export function effective(user:MapUser,draft:Draft,teams:MapTeam[],teamDraft:Draft,datasetId:string):{access:Access;viaTeam?:string}{
 const own=access(user,draft,datasetId);
 if(own==='admin')return {access:own};
 const team=teamLevel(user,teams,teamDraft,datasetId);
 return team.level&&RANK[team.level]>RANK[own]?{access:team.level,viaTeam:team.team}:{access:own};
}

export function rank(access:Access){return RANK[access];}

/** True when the draft differs from what is saved for this person (or team) and dataset. */
export function changedCell(saved:LevelMap,draft:Draft,id:string,datasetId:string){
 return (saved[datasetId]||'')!==(draft[id]?.[datasetId]||'');
}

export function changed(user:MapUser,draft:Draft,datasetId:string){
 return !user.is_admin&&changedCell(savedLevels(user),draft,user.id,datasetId);
}

const same=(a:LevelMap,b:LevelMap)=>{const keys=new Set([...Object.keys(a),...Object.keys(b)]);return [...keys].every(key=>a[key]===b[key]);};

export function changedUsers(users:MapUser[],draft:Draft){
 return users.filter(user=>!user.is_admin&&!same(savedLevels(user),draft[user.id]||{})).map(user=>user.id);
}

export function changedTeams(teams:MapTeam[],teamDraft:Draft){
 return teams.filter(team=>!same(team.grants,teamDraft[team.id]||{})).map(team=>team.id);
}

/** How OpenFGA's answer compares with the saved access (own grants and teams):
 * 'missing' saved but OpenFGA refuses, 'extra' OpenFGA allows what is not saved,
 * 'level' both allow but at different levels. Undefined when they agree or OpenFGA is off. */
export function openfgaDifference(user:MapUser,datasetId?:string):'missing'|'extra'|'level'|undefined{
 const answer=user.openfga;if(!answer)return undefined;
 if(datasetId===undefined)return user.is_admin===answer.administrator?undefined:user.is_admin?'missing':'extra';
 const saved=(user.effective||savedLevels(user))[datasetId];
 const allowed=answer.levels?answer.levels[datasetId]:answer.dataset_ids.includes(datasetId)?'viewer':undefined;
 if(saved===allowed)return undefined;
 return !allowed?'missing':!saved?'extra':'level';
}

export function differenceText(kind:ReturnType<typeof openfgaDifference>){
 return kind==='missing'?'Saved, but OpenFGA refuses it':kind==='extra'?'Not saved, but OpenFGA allows it':kind==='level'?'OpenFGA answers a different level':undefined;
}

export function openfgaSummary(status:OpenFgaStatus){
 if(!status.enabled)return {tone:'info',title:'OpenFGA is off',text:'Lapi checks the saved access in its own database.'};
 if(status.reachable===false)return {tone:'error',title:'OpenFGA is not answering',text:'Lapi refuses workspace access until OpenFGA is back. Saved access is kept and reloaded into OpenFGA when it returns.'};
 if(status.differences)return {tone:'warn',title:`OpenFGA answers differently for ${status.differences} ${status.differences===1?'person':'people'}`,text:'Marked with ! below. Lapi reloads OpenFGA from the saved access when either restarts; saving that person again also fixes it.'};
 return {tone:'ok',title:'OpenFGA agrees with all saved access',text:'Every permission check is answered by OpenFGA, and its answers match what is saved here.'};
}
