/** "How I read your question", built from the calculation that actually ran, never from the model's wording. */
type Entity=Record<string,any>;
export type Reading={source:number;headline:{label:string;value:string}|null;lines:string[]};

const OP:Record<string,string>={'=':'is','!=':'is not','>':'is above','>=':'is at least','<':'is below','<=':'is at most',in:'is one of',contains:'contains'};
const METRIC:Record<string,string>={sum:'Sum',avg:'Average',mean:'Average',min:'Lowest',max:'Highest',count:'Number of rows',median:'Median'};

const shown=(value:unknown)=>Array.isArray(value)?value.join(', '):String(value);
const number=(value:unknown)=>typeof value==='number'?value.toLocaleString(undefined,{maximumFractionDigits:2}):String(value??'');
const metricName=(metric:Entity)=>(METRIC[metric.op]||metric.op)+(metric.column?` of ${metric.column}`:'');

export function answerReadings(citations:Entity[]=[]):Reading[]{
 return citations.filter(source=>source?.reading).map(source=>{
  const r=source.reading,metrics:Entity[]=r.metrics||[];
  const lines=[
   ...(r.filters||[]).map((f:Entity)=>`${f.column} ${OP[f.op]||f.op} ${shown(f.value)}`),
   ...(r.join?.on?[`Joined ${r.join.on} (${number(r.join.matched_rows)} rows matched, ${number(r.join.unmatched_rows)} did not)`]:[]),
   ...(r.group_by?.length?[`Grouped by ${r.group_by.map((g:unknown)=>typeof g==='string'?g:(g as Entity).column).join(', ')}`]:[]),
   ...metrics.map(m=>metricName(m)),
   `${number(r.matched_rows)} ${r.matched_rows===1?'row':'rows'} used`];
  // One calculated row with no grouping is a single answer, so it can lead.
  const row=r.rows?.length===1&&!r.group_by?.length&&metrics.length?r.rows[0]:null;
  return {source:source.index,lines,headline:row&&row.length?{label:metricName(metrics[0]),value:number(row[0])}:null};
 });
}

/** The sheet and rows a citation points at, so its Row, Attached and Linked tabs can open. */
export function citedRows(source:Entity,saved?:Entity|null):{sheet:string;rows:number[]}|null{
 const section=/^Sheet: (.+?)(?: · row (\d+))?$/.exec(String(source?.section||''));
 const sheet=source?.sheet||saved?.sheet||section?.[1]||'';
 const rows:number[]=Array.isArray(source?.rows)&&source.rows.length?source.rows:saved?.row_start?[saved.row_start]:section?.[2]?[Number(section[2])]:[];
 return sheet&&rows.length?{sheet,rows}:null;
}

/** The next record when paging through a result one at a time, or null at either end. */
export function recordStep(profile:string,count:number,delta:number):string|null{
 const current=profile==='all'?(delta>0?-1:count):Number(profile),next=current+delta;
 return next>=0&&next<count?String(next):null;
}
