/** Access map data: who can open which dataset, the unsaved changes an administrator is making,
 * and whether OpenFGA answers the same as the saved access. */
export type OpenFgaAnswer={administrator:boolean;dataset_ids:string[];in_step:boolean};
export type MapUser={id:string;username:string;is_admin:boolean;sign_in?:string;dataset_ids:string[];openfga?:OpenFgaAnswer};
export type MapDataset={id:string;name:string;status?:string};
export type OpenFgaStatus={enabled:boolean;reachable:boolean|null;differences:number};
export type AccessMapData={users:MapUser[];datasets:MapDataset[];openfga:OpenFgaStatus};
/** Dataset IDs each non-administrator will be able to open once saved. */
export type Draft=Record<string,string[]>;
export type Access='admin'|'granted'|'none';

export function initialDraft(users:MapUser[]):Draft{
 return Object.fromEntries(users.filter(user=>!user.is_admin).map(user=>[user.id,[...user.dataset_ids].sort()]));
}

export function toggle(draft:Draft,userId:string,datasetId:string):Draft{
 if(!(userId in draft))return draft; // Administrators open every dataset by role.
 const current=draft[userId];
 const next=current.includes(datasetId)?current.filter(id=>id!==datasetId):[...current,datasetId].sort();
 return {...draft,[userId]:next};
}

export function access(user:MapUser,draft:Draft,datasetId:string):Access{
 if(user.is_admin)return 'admin';
 return (draft[user.id]||[]).includes(datasetId)?'granted':'none';
}

/** True when the draft differs from what is saved for this person and dataset. */
export function changed(user:MapUser,draft:Draft,datasetId:string){
 return !user.is_admin&&user.dataset_ids.includes(datasetId)!==(draft[user.id]||[]).includes(datasetId);
}

export function changedUsers(users:MapUser[],draft:Draft){
 return users.filter(user=>!user.is_admin&&[...user.dataset_ids].sort().join('\n')!==(draft[user.id]||[]).join('\n')).map(user=>user.id);
}

/** How OpenFGA's answer compares with the saved access: 'missing' means saved but OpenFGA refuses,
 * 'extra' means OpenFGA allows what is not saved. Undefined when they agree or OpenFGA is off. */
export function openfgaDifference(user:MapUser,datasetId?:string):'missing'|'extra'|undefined{
 const answer=user.openfga;if(!answer)return undefined;
 const saved=datasetId===undefined?user.is_admin:user.dataset_ids.includes(datasetId);
 const allowed=datasetId===undefined?answer.administrator:answer.dataset_ids.includes(datasetId);
 return saved===allowed?undefined:saved?'missing':'extra';
}

export function openfgaSummary(status:OpenFgaStatus){
 if(!status.enabled)return {tone:'info',title:'OpenFGA is off',text:'Lapi checks the saved access in its own database.'};
 if(status.reachable===false)return {tone:'error',title:'OpenFGA is not answering',text:'Lapi refuses dataset access until OpenFGA is back. Saved access is kept and reloaded into OpenFGA when it returns.'};
 if(status.differences)return {tone:'warn',title:`OpenFGA answers differently for ${status.differences} ${status.differences===1?'person':'people'}`,text:'Marked with ! below. Lapi reloads OpenFGA from the saved access when either restarts; saving that person again also fixes it.'};
 return {tone:'ok',title:'OpenFGA agrees with all saved access',text:'Every permission check is answered by OpenFGA, and its answers match what is saved here.'};
}
