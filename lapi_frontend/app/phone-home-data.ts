/** What the phone Home shows: a greeting, questions worth asking and the files Lapi is still reading. */
type Entity=Record<string,any>;
export type ReadingItem={id:string;name:string;step:string;progress:number};

const STEP:Record<string,string>={upload:'Uploading',extract:'Reading text',ocr:'Reading images',index:'Making it searchable',prepare:'Preparing',ready:'Finishing'};
const PENDING=['queued','processing','running'];

export function greeting(hour:number){return hour<5?'Good evening':hour<12?'Good morning':hour<18?'Good afternoon':'Good evening';}

const inDataset=(doc:Entity,datasetId?:string)=>!datasetId||(doc.dataset_id||doc.kb_id)===datasetId;
export const readyCount=(documents:Entity[],datasetId?:string)=>documents.filter(doc=>inDataset(doc,datasetId)&&doc.status==='ready'&&!doc.requires_reindex).length;

/** Files still being processed, newest first, with the step and share of stages done. */
export function readingNow(documents:Entity[],jobs:Entity[],datasetId?:string,limit=3):ReadingItem[]{
 return documents.filter(doc=>inDataset(doc,datasetId)&&PENDING.includes(doc.status))
  .sort((a,b)=>(b.created_at||0)-(a.created_at||0)).slice(0,limit)
  .map(doc=>{
   const job=jobs.filter(j=>(j.document_id||j.target_id)===doc.id).sort((a,b)=>(b.created_at||0)-(a.created_at||0))[0];
   const stages=Object.values(job?.workflow?.stages||{}) as Entity[];
   const done=stages.filter(stage=>stage.status==='completed').length;
   const current=job?.workflow?.current||job?.stage||'';
   return {id:String(doc.id),name:String(doc.name||doc.filename||'Document'),step:doc.status==='queued'?'Waiting to start':STEP[current]||'Reading',progress:stages.length?Math.round(done/stages.length*100):0};
  });
}

/** Up to three questions that work on any dataset, starting from its newest ready files. */
export function suggestions(documents:Entity[],datasetId?:string):string[]{
 const ready=documents.filter(doc=>inDataset(doc,datasetId)&&doc.status==='ready').sort((a,b)=>(b.created_at||0)-(a.created_at||0));
 const named=ready.slice(0,2).map(doc=>`What is in ${String(doc.name||'this file').replace(/\.[a-z0-9]+$/i,'')}?`);
 return ready.length?[...named,'Summarise what changed recently']:[];
}
