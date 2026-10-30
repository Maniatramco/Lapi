"use client";
import {AlertTriangle,ChevronRight,Loader2} from 'lucide-react';
import {extractionsRunning,readingNow} from './phone-home-data';
import './phone-status.css';

type Entity=Record<string,any>;

/** Phones only: one short line for what needs the person or is still running, instead of a floating card. */
export function PhoneStatus({documents,jobs,attention,onAttention,onReview}:{documents:Entity[];jobs:Entity[];attention:number;onAttention:()=>void;onReview:()=>void}){
 const reading=readingNow(documents,jobs),first=reading[0],extracting=extractionsRunning(jobs);
 if(!attention&&!first&&!extracting)return null;
 return <div className="phone-status" aria-label="Workspace status">
  {attention>0&&<button type="button" className="is-warning" onClick={onAttention}><AlertTriangle size={16} aria-hidden="true"/><span>Check {attention} {attention===1?'file':'files'}</span><ChevronRight size={16} aria-hidden="true"/></button>}
  {extracting>0&&<button type="button" onClick={onReview}><Loader2 size={16} className="animate-spin" aria-hidden="true"/><span>Extracting{extracting>1?` · ${extracting}`:''}</span><ChevronRight size={16} aria-hidden="true"/></button>}
  {first&&<div role="status" title={`${first.name}: ${first.step}`}><Loader2 size={16} className="animate-spin" aria-hidden="true"/><span>Reading{reading.length>1?` ${reading.length} files`:''}</span><small>{first.progress}%</small></div>}
 </div>;
}
