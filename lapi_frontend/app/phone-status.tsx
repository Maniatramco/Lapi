"use client";
import {ChevronRight,Loader2} from 'lucide-react';
import {extractionsRunning,readingNow} from './phone-home-data';
import './phone-status.css';

type Entity=Record<string,any>;

/** Phones only: one short line for what is still running, instead of a floating card. Files that need the person show in the top row. */
export function PhoneStatus({documents,jobs,onReview}:{documents:Entity[];jobs:Entity[];onReview:()=>void}){
 const reading=readingNow(documents,jobs),first=reading[0],extracting=extractionsRunning(jobs);
 if(!first&&!extracting)return null;
 return <div className="phone-status" aria-label="App status">
  {extracting>0&&<button type="button" onClick={onReview}><Loader2 size={16} className="animate-spin" aria-hidden="true"/><span>Extracting{extracting>1?` · ${extracting}`:''}</span><ChevronRight size={16} aria-hidden="true"/></button>}
  {first&&<div role="status" title={`${first.name}: ${first.step}`}><Loader2 size={16} className="animate-spin" aria-hidden="true"/><span>Reading{reading.length>1?` ${reading.length} files`:''}</span><small>{first.progress}%</small></div>}
 </div>;
}
