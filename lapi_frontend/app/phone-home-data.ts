/** What the phone status strip shows: files still being read and extractions still running. */
type Entity=Record<string,any>;
export type ReadingItem={id:string;name:string;step:string;progress:number};

const STEP:Record<string,string>={upload:'Uploading',extract:'Reading text',ocr:'Reading images',index:'Making it searchable',prepare:'Preparing',ready:'Finishing'};
const PENDING=['queued','processing','running'];

const inDataset=(doc:Entity,datasetId?:string)=>!datasetId||(doc.dataset_id||doc.kb_id)===datasetId;

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

export const extractionsRunning=(jobs:Entity[])=>jobs.filter(job=>job.kind==='extract'&&['queued','running'].includes(job.status)).length;
