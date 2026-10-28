"use client";
import {useEffect,useState} from 'react';
import {Check,ChevronLeft,ChevronRight,GraduationCap,X} from 'lucide-react';
import {AgentLogo} from './agent-logo';
import {TRAINING_CARDS,TRAINING_VERSION,type TrainingAction} from './screens-client';

type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
/** Opens the agent training from anywhere (the Dashboard hero, the composer chip). */
export const OPEN_TRAINING_EVENT='lapi:open-agent-training';
export function openAgentTraining(){if(typeof window!=='undefined')window.dispatchEvent(new Event(OPEN_TRAINING_EVENT));}

/** Five cards inside the agent that show what it does, each with something real to try. Shown once per
 * person (the server remembers it, like the tour) and any time from "How the agent works". */
export function AgentTraining({api,userId,onTry}:{api:Api;userId:string;onTry:(action:TrainingAction,example?:string)=>void}){
 const [open,setOpen]=useState(false),[index,setIndex]=useState(0),[checked,setChecked]=useState('');
 useEffect(()=>{
  if(!userId||checked===userId)return;
  setChecked(userId);
  Promise.resolve().then(()=>api('/me/agent-training','GET',undefined,undefined,true)).then(status=>{if(status&&status.seen===false){setIndex(0);setOpen(true);}}).catch(()=>undefined);
 },[api,userId,checked]);
 useEffect(()=>{const show=()=>{setIndex(0);setOpen(true);};window.addEventListener(OPEN_TRAINING_EVENT,show);return()=>window.removeEventListener(OPEN_TRAINING_EVENT,show);},[]);
 const finish=()=>{setOpen(false);Promise.resolve().then(()=>api('/me/agent-training','POST',{version:TRAINING_VERSION},undefined,true)).catch(()=>undefined);};
 if(!open)return null;
 const card=TRAINING_CARDS[index],last=index===TRAINING_CARDS.length-1;
 return <section className="agent-training" aria-label="How the agent works" aria-live="polite">
  <header><span className="agent-training-mark"><AgentLogo size={22}/></span><strong><GraduationCap size={15} aria-hidden="true"/> How Lapi Agent works</strong><span className="agent-training-count">{index+1} / {TRAINING_CARDS.length}</span>
   <button type="button" className="btn icon" aria-label="Close training" onClick={finish}><X size={15}/></button></header>
  <ol className="agent-training-dots" aria-hidden="true">{TRAINING_CARDS.map((c,i)=><li key={c.id} className={i<index?'done':i===index?'on':''}/>)}</ol>
  <h3>{card.title}</h3>
  <p>{card.text}</p>
  <div className="agent-training-actions">
   {card.action!=='none'&&<button type="button" className="btn" onClick={()=>onTry(card.action,card.example)}>{card.tryLabel}</button>}
   <span className="agent-training-nav">
    <button type="button" className="btn icon" aria-label="Previous" disabled={index===0} onClick={()=>setIndex(index-1)}><ChevronLeft size={16}/></button>
    {last?<button type="button" className="btn primary" onClick={finish}><Check size={15}/> Got it</button>
     :<button type="button" className="btn primary" aria-label="Next" onClick={()=>setIndex(index+1)}>Next <ChevronRight size={16}/></button>}
   </span>
  </div>
 </section>;
}
