/** Quick start: one guided workflow from "nothing" to a first result, kept small enough for a
 * phone. Pick or create a dataset → add documents (camera or files) → wait for them to be read
 * → choose: ask a question, or pull out data with an extraction prompt the AI drafts → done.
 * Viewers choose a dataset and ask. Every step that sends data to an AI model asks first. */
type Entity=Record<string,any>;

export type Step='dataset'|'documents'|'processing'|'choose'|'ask'|'prompt'|'extracting'|'done';
export type Path='ask'|'extract';
export type FileState='working'|'ready'|'failed';
export type FieldType='text'|'number'|'date'|'yes_no'|'list';
export type Field={key:string;label:string;type:FieldType;description:string};

/** Files people can add from a phone or computer (Lapi reads PDF, Word, text, JSON, spreadsheets and images). */
export const ACCEPT='.pdf,.docx,.txt,.json,.xlsx,.csv,.tsv,.png,.jpg,.jpeg,.webp,application/pdf,image/*';
export const MAX_FILES=10;

/** Opens the Quick start from anywhere (Dashboard, About, the agent's chips and /Start). */
export const OPEN_QUICK_START_EVENT='lapi:open-quick-start';
export function openQuickStart(files?:File[]){if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent(OPEN_QUICK_START_EVENT,{detail:{files:files||[]}}));}

/** Opens an extraction on the Review page (handled in page.tsx). */
export const OPEN_REVIEW_EVENT='lapi:open-review';
export function openReviewPage(id:string){if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent(OPEN_REVIEW_EVENT,{detail:{id}}));}

/** Several files can be stitched into one document before reading (pages of one paper
 * document, photos of one invoice). Photos only: merging is the likely intent. */
/** Spreadsheets stay tables: rows and columns are never stitched into another document. */
export const isSpreadsheet=(name:string)=>/\.(xlsx|csv|tsv)$/i.test(name);
export const canMerge=(files:{name:string}[])=>files.length>=2&&files.length<=20&&!files.some(file=>isSpreadsheet(file.name));
export const mergeByDefault=(files:{name:string;type?:string}[])=>canMerge(files)&&files.every(file=>file.type?.startsWith('image/')||/\.(png|jpe?g|webp)$/i.test(file.name));
export function mergedName(files:{name:string}[]){
 const first=(files[0]?.name||'Document').replace(/\.[^.]+$/,'');
 return `${first} + ${files.length-1} more`.slice(0,120);
}

export type StageState='done'|'on'|'todo'|'failed';
const stageIndex=(status:string|undefined)=>status==='ready'?5:status==='running'||status==='processing'?2:status==='queued'||status==='blocked'?1:0;
/** The extraction workflow shown while Lapi pulls out data, from the extraction's real status.
 * A failure is marked on the step it happened in: the furthest status seen while polling, or,
 * when it failed between polls, the step its error names (indexing or worker), else the AI read. */
export function extractionStages(status:string|undefined,documents:number,reached?:string,error=''):{label:string;state:StageState}[]{
 const labels=['Prompt saved','Waiting for a worker',`Reading ${documents} document${documents===1?'':'s'} with the AI model`,'Checking the values against your fields','Ready to review'];
 if(status==='failed'||status==='cancelled'){
  const failed=stageIndex(reached)>=2?2:/index|worker|queue|recovery/i.test(error)?1:2;
  return labels.map((label,i)=>({label,state:i<failed?'done':i===failed?'failed':'todo'}));
 }
 const at=stageIndex(status);
 return labels.map((label,i)=>({label,state:i<at?'done':i===at?'on':'todo'}));
}

export const SUGGESTED_QUESTIONS=[
 'Summarize this in five bullet points',
 'What are the key dates, amounts and names?',
 'What should I do next based on this?',
];

export const FIELD_TYPES:{id:FieldType;label:string}[]=[
 {id:'text',label:'Text'},{id:'number',label:'Number'},{id:'date',label:'Date'},{id:'yes_no',label:'Yes / no'},{id:'list',label:'List'},
];

const active=(datasets:Entity[])=>datasets.filter(d=>d.active!==false);

/** Datasets this person may add documents to: administrators everywhere, otherwise Editor or Owner. */
export function uploadable(datasets:Entity[],isAdmin:boolean){
 return active(datasets).filter(d=>isAdmin||d.my_access==='editor'||d.my_access==='owner');
}

/** Datasets this person can ask about (any level). */
export const askable=(datasets:Entity[])=>active(datasets);

export const canAddDocuments=(datasets:Entity[],isAdmin:boolean)=>isAdmin||uploadable(datasets,isAdmin).length>0;

/** The steps this person goes through, in order, for the chosen path. */
export function stepsFor(datasets:Entity[],isAdmin:boolean,path:Path='ask'):Step[]{
 if(!canAddDocuments(datasets,isAdmin))return ['dataset','ask','done'];
 return ['dataset','documents','processing','choose',...(path==='extract'?['prompt','extracting'] as Step[]:['ask'] as Step[]),'done'];
}

export function canCreateDataset(isAdmin:boolean){return isAdmin;}

export function fileState(status:string|undefined):FileState{
 if(status==='ready')return 'ready';
 if(status==='failed'||status==='cancelled'||status==='deleting')return 'failed';
 return 'working';
}

export const FILE_STATE_TEXT:Record<FileState,string>={working:'Reading…',ready:'Ready',failed:'Could not read'};

/** Overall progress of the uploaded files: done when none is still being read. */
export function progress(states:FileState[]){
 const ready=states.filter(s=>s==='ready').length,failed=states.filter(s=>s==='failed').length;
 const total=states.length;
 return {ready,failed,total,finished:total>0&&ready+failed===total,percent:total?Math.round((ready+failed)/total*100):0};
}

/** Files picked on the device, limited to what Lapi can read; returns kept files and a note about the rest. */
export function pickFiles(files:File[]):{files:File[];note:string}{
 const ok=/\.(pdf|docx|txt|json|xlsx|csv|tsv|png|jpe?g|webp)$/i;
 const kept=files.filter(file=>ok.test(file.name)||file.type.startsWith('image/')).slice(0,MAX_FILES);
 const skipped=files.length-kept.length;
 return {files:kept,note:skipped?`${skipped} file${skipped===1?' was':'s were'} skipped: Lapi reads PDF, Word, text, JSON, spreadsheets (XLSX, CSV) and images, up to ${MAX_FILES} at a time.`:''};
}

/** A readable name for a cited source. */
export function sourceName(citation:Entity){
 const where=citation.section?` · ${String(citation.section).replace(/^Sheet: /,'sheet ')}`:citation.page?` · page ${citation.page}`:'';
 return String(citation.title||citation.name||citation.filename||citation.document_name||'Source')+where;
}

/** A short default name for a first dataset. */
export function defaultDatasetName(username:string|undefined,now=new Date()){
 const month=now.toLocaleString('en',{month:'short'});
 return `${username?username+"'s ":''}documents ${month} ${now.getFullYear()}`.slice(0,120);
}

/** A field key from a label: "Due date" → "due_date". */
export function fieldKey(label:string,taken:string[]=[]){
 let key=label.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g,'_').replace(/^_+|_+$/g,'').slice(0,40)||'field';
 if(!/^[a-z]/.test(key))key='f_'+key.slice(0,38);
 let unique=key,n=2;while(taken.includes(unique)){unique=`${key.slice(0,36)}_${n++}`;}
 return unique;
}

/** The editable fields as the JSON Schema Lapi prompt templates use (strict: every field required, nullable). */
export function fieldsToSchema(fields:Field[]){
 const properties:Record<string,Entity>={};
 for(const field of fields){
  const description=`${field.label}: ${field.description}`;
  properties[field.key]=field.type==='list'?{type:['array','null'],items:{type:'string'},description}
   :{type:[field.type==='number'?'number':field.type==='yes_no'?'boolean':'string','null'],...(field.type==='date'?{format:'date'}:{}),description};
 }
 return {type:'object',additionalProperties:false,properties,required:Object.keys(properties)};
}

/** Field problems to fix before saving, in plain words; empty when the list is fine. */
export function fieldProblems(fields:Field[]){
 const problems:string[]=[];
 if(!fields.length)problems.push('Keep at least one field.');
 if(fields.some(f=>!f.label.trim()))problems.push('Every field needs a name.');
 if(fields.some(f=>!f.description.trim()))problems.push('Every field needs a short description of what to pull out.');
 if(new Set(fields.map(f=>f.key)).size!==fields.length)problems.push('Two fields have the same name.');
 return problems;
}

/** Extracted values as label/value rows for a small results card (first record when there are several). */
/** How many records an extraction returned (several for spreadsheet rows or merged files). */
export const recordCount=(result:unknown)=>{const records=(result as {records?:unknown})?.records;return Array.isArray(records)?records.length:result?1:0;};

export function resultRows(result:unknown,fields:Field[]):{label:string;value:string}[]{
 let record:any=result;
 if(Array.isArray(record))record=record[0];
 if(record&&typeof record==='object'&&!Array.isArray(record)&&record.records&&Array.isArray(record.records))record=record.records[0];
 // A record list (one per spreadsheet row or per merged file) shows the first record's own fields.
 if(record&&typeof record==='object'&&record.fields&&typeof record.fields==='object'&&!Array.isArray(record.fields)&&'source_key' in record)record=record.fields;
 if(!record||typeof record!=='object')return [];
 const label=(key:string)=>fields.find(f=>f.key===key)?.label||key.replace(/_/g,' ');
 const show=(value:unknown):string=>value===null||value===undefined||value===''?'Not found':Array.isArray(value)?value.map(show).join(', '):typeof value==='boolean'?(value?'Yes':'No'):typeof value==='object'?JSON.stringify(value):String(value);
 // In the order of the person's fields; anything else the model returned comes after.
 const order=(key:string)=>{const index=fields.findIndex(f=>f.key===key);return index<0?fields.length:index;};
 return Object.entries(record).sort(([a],[b])=>order(a)-order(b)).map(([key,value])=>({label:label(key),value:show(value)}));
}

/** How each field will be read from a spreadsheet (POST /templates/table-plan), shown before extracting. */
export type ColumnChoice={sheet:string;column:string;how:string;confidence:number;via?:{column:string;key:string;strength:string}};
export type TablePlanDocument={document_id:string;name:string;sheet:string;rows:number;fields:Record<string,ColumnChoice>;row_fields:string[];whole_fields:string[];unmatched:string[];columns:{sheet:string;column:string}[]};
export type TablePlan={applies:boolean;documents:TablePlanDocument[]};
const SEP='\u0001';
export const columnValue=(sheet:string,column:string)=>sheet+SEP+column;

/** The select value per field: a column, "row" (read by the model from each row) or "" (leave empty). */
export function initialChoices(doc:TablePlanDocument,keys:string[]):Record<string,string>{
 return Object.fromEntries(keys.map(key=>{const found=doc.fields[key];return [key,found?columnValue(found.sheet,found.column):doc.row_fields.includes(key)?'row':''];}));
}

/** The person's choices as the extraction's column_mapping; "row" stays the server's decision. */
export function columnMapping(choices:Record<string,string>):Record<string,{sheet:string;column:string}|null>{
 const out:Record<string,{sheet:string;column:string}|null>={};
 for(const [key,value] of Object.entries(choices)){
  if(value==='row')continue;
  if(!value){out[key]=null;continue;}
  const [sheet,column]=value.split(SEP);out[key]={sheet,column};
 }
 return out;
}

/** Why a column was chosen, in plain words. */
/** A short badge for a field's column choice; the full sentence comes from howChosen. */
export function howBadge(doc:TablePlanDocument,key:string,choice:string):{kind:string;label:string}{
 if(choice==='row')return {kind:'row',label:'AI per row'};
 if(!choice)return doc.whole_fields.includes(key)?{kind:'whole',label:'Ask in chat'}:{kind:'none',label:'No column'};
 const found=doc.fields[key];
 if(!found||columnValue(found.sheet,found.column)!==choice)return {kind:'you',label:'Your choice'};
 if(found.via)return {kind:'linked',label:'Linked sheet'};
 return found.how==='by meaning'?{kind:'meaning',label:'By meaning'}:found.how==='same name'?{kind:'same',label:'Same name'}:{kind:'similar',label:'Similar name'};
}
export function howChosen(doc:TablePlanDocument,key:string,choice:string):string{
 if(choice==='row')return 'Read from each row\'s cells, comments and images by the AI model';
 if(!choice)return doc.whole_fields.includes(key)?'About the whole table: ask in chat for an exact answer':'No matching column: left empty';
 const found=doc.fields[key];
 if(!found||columnValue(found.sheet,found.column)!==choice)return 'Chosen by you';
 const via=found.via?` through ${found.via.column} → ${found.sheet}.${found.via.key}`:'';
 return found.how==='by meaning'?`Matched by meaning (${Math.round(found.confidence*100)}% sure)${via}`:found.how==='same name'?`Same name${via}`:`Similar name${via}`;
}
