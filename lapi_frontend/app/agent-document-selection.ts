type Entity=Record<string,any>;
export function readyDatasetDocuments(documents:Entity[],dataset:string){
 return dataset?documents.filter(d=>d.parent_id===dataset&&d.status==='ready'):[];
}
export function matchingDocuments(documents:Entity[],query:string){
 const search=query.trim().toLocaleLowerCase();return documents.filter(d=>d.name.toLocaleLowerCase().includes(search));
}
export function documentMention(text:string,caret:number){
 const before=text.slice(0,caret);const match=/(?:^|\s)#([^\n#]*)$/.exec(before);
 if(!match)return null;
 return {start:before.lastIndexOf('#'),end:caret,query:match[1]};
}
export function documentOptionLabel(document:Entity,documents:Entity[]){
 return documents.filter(d=>d.name===document.name).length>1?`${document.name} · ${document.id.slice(-6)}`:document.name;
}
/** Where a model is offered (Enabled models): phones, computers or both; older servers send nothing, meaning both. */
export const offeredOn=(model:Entity,device:'phone'|'computer')=>(Array.isArray(model.devices)&&model.devices.length?model.devices:['computer','phone']).includes(device);
/** Chat models people may pick: the administrator's mappings for the dataset plus the workspace
 * Default (`chat_choices`), or, from older servers, the dataset's mapped models; with a device, only
 * the models offered on it. */
export function eligibleAgentModels(models:Entity[],dataset:Entity|undefined,device?:'phone'|'computer'){
 return (dataset?dataset.chat_choices||dataset.models||[]:models).filter((m:Entity)=>m.enabled!==false&&m.mapping_enabled!==false&&m.capabilities.includes('chat')&&(!device||offeredOn(m,device)));
}
