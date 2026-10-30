"use client";
import {AlertTriangle,ArrowUp,ChevronRight,FileSpreadsheet,FileText,Paperclip} from 'lucide-react';
import {greeting,readingNow,readyCount,suggestions} from './phone-home-data';
import './phone-home.css';

type Entity=Record<string,any>;

/** Phones only: the Dashboard opens on one ask box, what needs the person and what is still being read. */
export function PhoneHome({datasetName,datasetId,documents,jobs,attention,canAdd,onAsk,onAdd,onAttention}:{datasetName:string;datasetId?:string;documents:Entity[];jobs:Entity[];attention:number;canAdd:boolean;onAsk:(text?:string)=>void;onAdd:()=>void;onAttention:()=>void}){
 const ready=readyCount(documents,datasetId),reading=readingNow(documents,jobs,datasetId),questions=suggestions(documents,datasetId);
 const where=datasetName||'your documents';
 return <section className="phone-home" aria-labelledby="phone-home-title">
  <div className="phone-home-hello">
   <h2 id="phone-home-title">{greeting(new Date().getHours())}</h2>
   <p>{ready?`${datasetName?datasetName+' · ':''}${ready.toLocaleString()} ${ready===1?'document':'documents'} ready to ask`:canAdd?'Add a document to start asking':'Nothing is ready to ask yet'}</p>
  </div>
  <div className="phone-home-ask">
   <button type="button" className="phone-home-ask-field" onClick={()=>onAsk()}>Ask anything about {where}…</button>
   <div className="phone-home-ask-tools">
    {canAdd&&<button type="button" className="phone-home-tool" aria-label="Add files or a photo" onClick={onAdd}><Paperclip size={20} aria-hidden="true"/></button>}
    <span/>
    <button type="button" className="phone-home-send" aria-label="Ask" onClick={()=>onAsk()}><ArrowUp size={20} aria-hidden="true"/></button>
   </div>
  </div>
  {questions.length>0&&<div className="phone-home-chips" aria-label="Suggested questions">{questions.map(q=><button key={q} type="button" onClick={()=>onAsk(q)}>{q}</button>)}</div>}
  {attention>0&&<div className="phone-home-group">
   <h3>Needs you</h3>
   <button type="button" className="phone-home-card is-warning" onClick={onAttention}>
    <span className="phone-home-card-icon" aria-hidden="true"><AlertTriangle size={22}/></span>
    <span className="phone-home-card-text"><strong>{attention} {attention===1?'file needs':'files need'} attention</strong><small>See why and what to do next</small></span>
    <ChevronRight size={18} aria-hidden="true"/>
   </button>
  </div>}
  {reading.length>0&&<div className="phone-home-group">
   <h3>Reading now</h3>
   {reading.map(item=><div key={item.id} className="phone-home-card">
    <span className="phone-home-card-icon is-file" aria-hidden="true">{/\.(xlsx|xlsm|csv|tsv)$/i.test(item.name)?<FileSpreadsheet size={20}/>:<FileText size={20}/>}</span>
    <span className="phone-home-card-text"><strong>{item.name}</strong><small>{item.step}</small>
     <span className="phone-home-bar" role="progressbar" aria-label={`${item.name} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={item.progress}><span style={{width:`${Math.max(item.progress,4)}%`}}/></span></span>
    <span className="phone-home-percent">{item.progress}%</span>
   </div>)}
  </div>}
 </section>;
}
