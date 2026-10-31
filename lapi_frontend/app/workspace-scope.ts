/** Which workspace is open, what login asks next, and which collections belong to it. Pure helpers, unit tested. */
type Entity=Record<string,any>;
export type GateStep='choose'|'collection'|null;
export const COLLECTION_TYPES=['Finance','Resume','Legal','HR','Invoices','Contracts','Reports'];

const canAdd=(workspace?:Entity|null)=>Boolean(workspace&&['owner','editor'].includes(workspace.my_access));
export const canAddCollections=canAdd;

/** The saved workspace if it is still available, else the person's own, else the first. */
export function pickWorkspace(workspaces:Entity[],saved?:string|null):string{
 return (workspaces.find(w=>w.id===saved)||workspaces.find(w=>w.audience==='personal'&&w.mine)||workspaces[0])?.id||'';
}

/** Login: choose a workspace when there is a real choice; then, in an empty workspace, guide to a first collection. */
export function gateStep({workspaces,current,chosen,skipped}:{workspaces:Entity[];current:string;chosen:boolean;skipped:boolean}):GateStep{
 if(!workspaces.length)return null;
 if(!chosen&&workspaces.length>1)return 'choose';
 const open=workspaces.find(w=>w.id===current);
 return open&&!open.collection_count&&canAdd(open)&&!skipped?'collection':null;
}

/** Collections of the open workspace. Ones not placed yet stay visible until the next refresh places them. */
export function inWorkspace<T extends Entity>(collections:T[],workspaceId:string):T[]{
 return workspaceId?collections.filter(c=>!c.workspace_id||c.workspace_id===workspaceId):collections;
}

const cache=new WeakMap<object,Map<string,Entity>>();
/** The Agent's choices for the open workspace; the same object while nothing changes. */
export function scopeCatalog(catalog:Entity,workspaceId?:string):Entity{
 if(!workspaceId)return catalog;
 const known=cache.get(catalog)||new Map<string,Entity>();cache.set(catalog,known);
 if(!known.has(workspaceId)){
  const datasets=inWorkspace(catalog.datasets||[],workspaceId),ids=new Set(datasets.map((d:Entity)=>d.id));
  known.set(workspaceId,{...catalog,datasets,documents:(catalog.documents||[]).filter((d:Entity)=>!d.parent_id||ids.has(d.parent_id))});
 }
 return known.get(workspaceId)!;
}
