/** "Ask first, then guide": the set-up questions and the next steps chosen from the answers and the person's access.
 * Pure logic only, so it can be tested without a browser. */
export type Goal='ask'|'extract'|'research'|'knowledge_base';
export type Source='files'|'google_drive'|'sharepoint'|'s3'|'azure_blob'|'gcs'|'oci_object'|'not_sure';
export type Preferences={goals:Goal[];sources:Source[];completed:boolean;dismissed_next_steps:boolean};
export const BLANK_PREFERENCES:Preferences={goals:[],sources:[],completed:false,dismissed_next_steps:false};

export const GOALS:{id:Goal;title:string;detail:string}[]=[
 {id:'ask',title:'Ask questions about documents',detail:'Get answers with the sources they came from'},
 {id:'extract',title:'Pull fields out of documents',detail:'Extract names, amounts and dates, then review them'},
 {id:'research',title:'Compare and research across sources',detail:'Find differences and patterns in many files'},
 {id:'knowledge_base',title:'Build a team knowledge base',detail:'Bring documents together for your team'},
];
/** Cloud sources match the Add knowledge provider ids; "files" is uploaded in Lapi Agent. */
export const SOURCES:{id:Source;title:string}[]=[
 {id:'files',title:'Files on my computer'},
 {id:'google_drive',title:'Google Drive'},
 {id:'sharepoint',title:'SharePoint / OneDrive'},
 {id:'s3',title:'Amazon S3'},
 {id:'azure_blob',title:'Azure Blob Storage'},
 {id:'gcs',title:'Google Cloud Storage'},
 {id:'oci_object',title:'OCI Object Storage'},
 {id:'not_sure',title:'Not sure yet'},
];
const CONNECTOR_NAMES:Record<string,string>={google_drive:'Google Drive',sharepoint:'SharePoint',s3:'Amazon S3',azure_blob:'Azure Blob Storage',gcs:'Google Cloud Storage',oci_object:'OCI Object Storage'};

/** Keep only known answers, once each, in the order the questions list them. */
export function cleanPreferences(value:unknown):Preferences{
 const data=value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};
 const pick=<T extends string>(list:unknown,allowed:{id:T}[])=>Array.isArray(list)?allowed.map(a=>a.id).filter(id=>list.includes(id)):[];
 return {goals:pick(data.goals,GOALS),sources:pick(data.sources,SOURCES),completed:data.completed===true,dismissed_next_steps:data.dismissed_next_steps===true};
}
/** Choosing "Not sure yet" clears the named sources, and naming a source clears "Not sure yet". */
export function toggleSource(current:Source[],id:Source):Source[]{
 if(current.includes(id))return current.filter(s=>s!==id);
 if(id==='not_sure')return ['not_sure'];
 return cleanPreferences({sources:[...current.filter(s=>s!=='not_sure'),id]}).sources;
}
export function toggleGoal(current:Goal[],id:Goal):Goal[]{
 return current.includes(id)?current.filter(g=>g!==id):cleanPreferences({goals:[...current,id]}).goals;
}

type Dataset={active?:boolean;my_access?:string};
export type Access={isAdmin:boolean;canAddKnowledge:boolean;datasetCount:number};
/** Administrators, and Editors or Owners of any active dataset, can add knowledge; Viewers only read and ask. */
export function accessFor(user:{is_admin?:boolean;is_contributor?:boolean}|null|undefined,datasets:Dataset[]):Access{
 const active=datasets.filter(d=>d.active!==false);
 const isAdmin=Boolean(user?.is_admin||user?.is_contributor);
 return {isAdmin,canAddKnowledge:isAdmin||active.some(d=>d.my_access==='editor'||d.my_access==='owner'),datasetCount:active.length};
}
/** The set-up sheet opens until the person finishes or skips it once. */
export const shouldAskSetup=(preferences:Preferences|null)=>Boolean(preferences&&!preferences.completed);
export const showNextSteps=(preferences:Preferences|null)=>Boolean(preferences&&preferences.completed&&!preferences.dismissed_next_steps);

export type StepKind='quick-start'|'create-dataset'|'connect'|'add-knowledge'|'upload'|'ask'|'research'|'agent'|'extract';
export type NextStep={kind:StepKind;label:string;detail:string;provider?:string};
export type Guidance={primary:NextStep;steps:NextStep[];notes:string[]};

const named=(sources:Source[])=>sources.filter(s=>s!=='not_sure');
const sourceStep=(source:Source):NextStep=>source==='files'
 ?{kind:'upload',label:'Upload files',detail:'Attach files from this device in Lapi Agent; they are indexed into a workspace.'}
 :{kind:'connect',provider:source,label:`Connect ${CONNECTOR_NAMES[source]}`,detail:`Opens Add knowledge with the step-by-step ${CONNECTOR_NAMES[source]} guide.`};
const ASK:NextStep={kind:'ask',label:'Ask a question',detail:'Ask across your workspaces; answers cite their sources.'};
const RESEARCH:NextStep={kind:'research',label:'Compare sources',detail:'Ask Lapi to compare details across your documents.'};
const AGENT:NextStep={kind:'agent',label:'Open Lapi Agent',detail:'Chat with the agent about your workspaces or about Lapi.'};
const EXTRACT:NextStep={kind:'extract',label:'Run an extraction',detail:'Pull fields out of documents, then review them side by side.'};
const CREATE:NextStep={kind:'create-dataset',label:'Create your first workspace',detail:'A workspace holds documents, models and who can see them.'};
const ADD:NextStep={kind:'add-knowledge',label:'Add knowledge',detail:'Choose a storage provider and follow its guide.'};
// One guided workflow end to end (quick-start.tsx): dataset → documents → reading → a first answer.
const QUICK:NextStep={kind:'quick-start',label:'Add documents and ask',detail:'2 minutes: add a photo or files, then ask your first question with sources.'};
const QUICK_FIRST:NextStep={kind:'quick-start',label:'Create a workspace and add documents',detail:'2 minutes: name it, add a photo or files, then ask your first question.'};
const QUICK_ASK:NextStep={kind:'quick-start',label:'Ask your first question',detail:'Pick a workspace shared with you and get an answer with its sources.'};

/** One primary action plus up to three one-tap steps, chosen from the answers and what the person may do.
 * The primary action is always the Quick start, so everyone completes one workflow end to end. */
export function recommendNextSteps(preferences:Pick<Preferences,'goals'|'sources'>,access:Access):Guidance{
 const goals=preferences.goals,sources=named(preferences.sources);
 const cloud=sources.filter(s=>s!=='files');
 const goalStep=(canExtract:boolean)=>goals.includes('extract')&&canExtract?EXTRACT:goals.includes('research')?RESEARCH:ASK;
 const steps:NextStep[]=[],notes:string[]=[];
 const add=(step:NextStep)=>{if(steps.length<3&&!steps.some(s=>s.kind===step.kind&&s.provider===step.provider))steps.push(step);};
 if(access.canAddKnowledge){
  if(access.isAdmin&&access.datasetCount===0){
   add(QUICK_FIRST);
   notes.push('The quick start creates your first workspace: knowledge is always added into a workspace.');
  }else add(QUICK);
  if(cloud[0])add(sourceStep(cloud[0]));
  add(goalStep(true));
  if(cloud[1])add(sourceStep(cloud[1]));
  add(AGENT);
 }else{
  if(access.datasetCount===0){
   add(AGENT);
   notes.push('No workspaces are shared with you yet. Ask an administrator to give you access to one.');
  }else{
   add(QUICK_ASK);add(goals.includes('research')?RESEARCH:ASK);add(AGENT);
  }
  for(const source of sources)notes.push(source==='files'?'Ask a workspace owner or administrator to add your files.':`Ask a workspace owner or administrator to connect ${CONNECTOR_NAMES[source]}.`);
  if(goals.includes('extract'))notes.push('Extracting fields needs Editor access to a workspace. You can ask for it from a workspace owner.');
 }
 return {primary:steps[0],steps,notes};
}
/** The hash route that opens Add knowledge with a provider's guide already chosen. */
export const addKnowledgeRoute=(provider?:string)=>'#'+encodeURIComponent('Add knowledge')+(provider?'/'+encodeURIComponent(provider):'');
