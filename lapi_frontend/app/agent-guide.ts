/** Plain-words requests ("upload this one", "pull out the totals", "make a dataset") are understood here,
 * before anything reaches the model, and turned into a guided step when something is missing: documents
 * to attach, a dataset to hold them, a prompt to extract with. The person is led end to end instead of
 * getting an unrelated answer. Pure functions: no React, no network. */
export type GuideIntent='upload'|'extract'|'dataset'|'prompt'|'start'|null;
export type GuideAction='attach'|'quick-start'|'choose-dataset'|'onboard'|'prompt'|'send';
export type GuideStep={text:string;actions:{label:string;action:GuideAction}[]};
export type GuideState={dataset:boolean;files:number;templates:number;canOnboard:boolean;datasets:number;promptAttached:boolean};

const UPLOAD=/\b(upload|attach|add|import|index|ingest|load|put|save)\b.*\b(this|that|these|those|it|them|file|files|doc|docs|document|documents|pdf|pdfs|scan|scans|image|photo|invoice|invoices|contract|contracts|resume|resumes|sheet|spreadsheet|excel|csv|one|ones)\b|^\s*(upload|attach|add|import)\s*(this|it|these|them|one|ones)?\s*[.!]?\s*$/i;
const EXTRACT=/\b(extract|pull out|pull|take out|get|capture|read)\b.*\b(fields?|values?|data|totals?|amounts?|dates?|names?|numbers?|details?|information|info|table|tables)\b|\b(extract|extraction)\b/i;
const DATASET=/\b(create|make|set ?up|new|start|open|add|onboard|register)\b.*\bdatasets?\b|\bdatasets?\b.*\b(create|make|set ?up|new)\b/i;
const PROMPT=/\b(prompt|template|instructions?)\b.*\b(create|make|write|draft|new|set ?up|add|need|want|define)\b|\b(create|make|write|draft|new|set ?up|add|need|want|define)\b.*\b(prompt|template)\b/i;
const START=/^\s*(start|begin|get started|guide me|help me (start|begin|get started)|walk me through|show me how|how do i (start|begin|use this|get started))\b/i;
const QUESTION=/^\s*(what|which|who|where|when|why|how (much|many|long))\b/i;

/** The intent behind plain text. Commands ("/Upload") and knowledge questions ("what is the total…") are not guided. */
export function guideIntent(text:string):GuideIntent{
 const value=text.trim();
 if(!value||/^\s*[/@#]/.test(value))return null;
 if(START.test(value))return 'start';
 if(QUESTION.test(value)&&!/\b(how do i|how can i|how to)\b/i.test(value))return null;
 if(DATASET.test(value))return 'dataset';
 if(PROMPT.test(value))return 'prompt';
 if(UPLOAD.test(value))return 'upload';
 if(EXTRACT.test(value))return 'extract';
 return null;
}

/** The step to show before the request can run; null when the server's own workflow can take it from here
 * (it asks for the dataset and prompt itself in its "A few details" card). Guided only where the server could
 * do nothing sensible: no document attached, no dataset exists at all, dataset creation by someone who may
 * not onboard, prompt help, or "start". */
export function guideFor(intent:GuideIntent,state:GuideState):GuideStep|null{
 const quick={label:'Guided start',action:'quick-start' as const};
 if(intent==='start')return {text:'I will walk you through it: a dataset, your documents, then a question or the fields to pull out.',actions:[quick]};
 if(intent==='upload'){
  if(!state.files)return {text:'Attach the document first (PDF, Word, text, spreadsheet or a photo), then send again and I will read it.',actions:[{label:'Add documents',action:'attach'},quick]};
  if(!state.dataset&&!state.datasets)return {text:'There is no dataset yet. I can create one and read your document in a guided start.',actions:[quick]};
  return null;
 }
 if(intent==='extract'){
  if(!state.dataset&&!state.datasets)return {text:'Pulling out data needs a dataset with documents and a prompt that lists the fields. I can set all of that up in a guided start.',actions:[quick]};
  return null;
 }
 if(intent==='dataset')return state.canOnboard?null:{text:'I will create the dataset for you in a guided start and read your first documents into it.',actions:[quick]};
 if(intent==='prompt')return {text:'A prompt lists the fields to pull out of documents. I can draft one from your documents in a guided start, or you can write one on the Prompt page.',actions:[quick,{label:'Write a prompt',action:'prompt'}]};
 return null;
}

/** The deterministic server operation for a guided intent that can go ahead. */
export function guidedOperation(intent:GuideIntent):'onboard'|undefined{
 // Upload and extract phrases keep the server's own routing (it already understands them and asks for details).
 return intent==='dataset'?'onboard':undefined;
}
