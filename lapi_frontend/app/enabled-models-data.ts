/** Enabled models: which registered models are offered for new work, and why some must stay on. */
type Entity=Record<string,any>;

export const ROLE_NAMES:Record<string,string>={chat_model_id:'Chat',extraction_model_id:'Extraction',embedding_model_id:'Embedding',ocr_model_id:'OCR'};
const USE_NAMES:Record<string,string>={chat:'Chat',extraction:'Extraction',embedding:'Embedding',ocr:'OCR'};

/** The workspace Default roles this model holds; a Default cannot be switched off. */
export function defaultRoles(model:Entity,defaults:Entity|null):string[]{
 if(!defaults)return [];
 return Object.entries(ROLE_NAMES).filter(([key])=>defaults[key]===model.id).map(([,name])=>name);
}

export const usesOf=(model:Entity)=>(model.capabilities||[]).map((c:string)=>USE_NAMES[c]||c);

/** Registered models, chat first, then by name; archived registrations are left out. */
export function switchable(models:Entity[]):Entity[]{
 const rank=(m:Entity)=>(m.capabilities||[]).includes('chat')?0:(m.capabilities||[]).includes('extraction')?1:2;
 return models.filter(m=>!m.archived).sort((a,b)=>rank(a)-rank(b)||String(a.name).localeCompare(String(b.name)));
}

export type Device='phone'|'computer';
/** Where a model is offered; nothing saved means both. */
export const devicesOf=(model:Entity):Device[]=>Array.isArray(model.devices)&&model.devices.length?model.devices:['computer','phone'];

/** The devices after pressing one: add it, or remove it unless it is the last one (turn the model off instead). */
export function toggleDevice(current:Device[],device:Device):Device[]{
 const next=current.includes(device)?current.filter(d=>d!==device):[...current,device];
 return next.length?(['computer','phone'] as Device[]).filter(d=>next.includes(d)):current;
}

export function summary(models:Entity[]){
 const list=switchable(models),live=list.filter(m=>m.enabled!==false),chat=live.filter(m=>(m.capabilities||[]).includes('chat'));
 return {on:live.length,off:list.length-live.length,phoneChat:chat.filter(m=>devicesOf(m).includes('phone')).length,computerChat:chat.filter(m=>devicesOf(m).includes('computer')).length};
}
