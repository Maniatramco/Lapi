/** Quick start: one guided workflow from "nothing" to a first cited answer, kept small enough
 * for a phone. Pick or create a dataset → add documents (camera or files) → wait for them to be
 * read → ask a first question → done. Viewers skip straight to choosing a dataset and asking. */
type Entity=Record<string,any>;

export type Step='dataset'|'documents'|'processing'|'ask'|'done';
export type FileState='working'|'ready'|'failed';

/** Files people can add from a phone or computer (Lapi reads PDF, Word, text, JSON and images). */
export const ACCEPT='.pdf,.docx,.txt,.json,.png,.jpg,.jpeg,.webp,application/pdf,image/*';
export const MAX_FILES=10;

export const SUGGESTED_QUESTIONS=[
 'Summarize this in five bullet points',
 'What are the key dates, amounts and names?',
 'What should I do next based on this?',
];

const active=(datasets:Entity[])=>datasets.filter(d=>d.active!==false);

/** Datasets this person may add documents to: administrators everywhere, otherwise Editor or Owner. */
export function uploadable(datasets:Entity[],isAdmin:boolean){
 return active(datasets).filter(d=>isAdmin||d.my_access==='editor'||d.my_access==='owner');
}

/** Datasets this person can ask about (any level). */
export const askable=(datasets:Entity[])=>active(datasets);

/** The steps this person goes through, in order. */
export function stepsFor(datasets:Entity[],isAdmin:boolean):Step[]{
 return isAdmin||uploadable(datasets,isAdmin).length?['dataset','documents','processing','ask','done']:['dataset','ask','done'];
}

export function canCreateDataset(isAdmin:boolean){return isAdmin;}

export function fileState(status:string|undefined):FileState{
 if(status==='ready')return 'ready';
 if(status==='failed'||status==='cancelled'||status==='deleting')return 'failed';
 return 'working';
}

export const FILE_STATE_TEXT:Record<FileState,string>={working:'Reading…',ready:'Ready to ask',failed:'Could not read'};

/** Overall progress of the uploaded files: done when none is still being read. */
export function progress(states:FileState[]){
 const ready=states.filter(s=>s==='ready').length,failed=states.filter(s=>s==='failed').length;
 const total=states.length;
 return {ready,failed,total,finished:total>0&&ready+failed===total,percent:total?Math.round((ready+failed)/total*100):0};
}

/** Files picked on the device, limited to what Lapi can read; returns kept files and a note about the rest. */
export function pickFiles(files:File[]):{files:File[];note:string}{
 const ok=/\.(pdf|docx|txt|json|png|jpe?g|webp)$/i;
 const kept=files.filter(file=>ok.test(file.name)||file.type.startsWith('image/')).slice(0,MAX_FILES);
 const skipped=files.length-kept.length;
 return {files:kept,note:skipped?`${skipped} file${skipped===1?' was':'s were'} skipped: Lapi reads PDF, Word, text, JSON and images, up to ${MAX_FILES} at a time.`:''};
}

/** A readable name for a cited source. */
export function sourceName(citation:Entity){
 return String(citation.title||citation.name||citation.filename||citation.document_name||'Source')+(citation.page?` · page ${citation.page}`:'');
}

/** A short default name for a first dataset. */
export function defaultDatasetName(username:string|undefined,now=new Date()){
 const month=now.toLocaleString('en',{month:'short'});
 return `${username?username+"'s ":''}documents ${month} ${now.getFullYear()}`.slice(0,120);
}
