"use client";
import {useEffect,useRef,useState} from 'react';
import {ArrowUp,Mic} from 'lucide-react';
import {AgentLogo} from './agent-logo';
import {after,cleanName,matchType,matchWorkspace,no,prompt,yes,type Quick,type Stage} from './setup-chat-script';
import './setup-chat.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
type Line={who:'lapi'|'you';text:string};

/** First sign-in as a short chat with Lapi: your name, a team workspace if you want one, which
 * workspace to use, and your first collection. Answers can be typed, tapped or spoken. */
export function SetupChat({api,user,workspaces,canCreateTeam,current,chosen,needName,onNamed,onTeamCreated,onChoose,onCollectionCreated,onDone}:{api:Api;user:Entity;workspaces:Entity[];canCreateTeam:boolean;current?:Entity;chosen:boolean;needName:boolean;onNamed:(name:string)=>void;onTeamCreated:(workspace:Entity)=>void;onChoose:(id:string)=>void;onCollectionCreated:(id:string)=>void;onDone:()=>void}){
 const ctx={workspaces,current,canCreateTeam,chosen};
 const [name,setName]=useState<string>(user.display_name||'');
 const [stage,setStage]=useState<Stage>(()=>needName?'name':after('name',ctx));
 const [lines,setLines]=useState<Line[]>([]);
 const [text,setText]=useState(''),[busy,setBusy]=useState(false),[listening,setListening]=useState(false),[error,setError]=useState('');
 const [teamName,setTeamName]=useState(''),[collectionName,setCollectionName]=useState('');
 const input=useRef<HTMLInputElement|null>(null),thread=useRef<HTMLDivElement|null>(null),recognizer=useRef<any>(null);
 const said=prompt(stage,{name,workspaces,current,canCreateTeam,teamName,collectionName});
 const voice=typeof window!=='undefined'&&Boolean((window as any).SpeechRecognition||(window as any).webkitSpeechRecognition);

 useEffect(()=>{setLines(previous=>[...previous,{who:'lapi',text:said.text}]);setText('');setError('');},[stage]);  // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(()=>{thread.current?.scrollTo({top:thread.current.scrollHeight});if(said.typing)input.current?.focus();},[lines,said.typing]);

 const say=(who:'you',value:string)=>setLines(previous=>[...previous,{who,text:value}]);
 const move=(next:Stage)=>setStage(next);
 const run=async(work:()=>Promise<void>)=>{setBusy(true);setError('');try{await work();}catch(e){setError(e instanceof Error?e.message:'That did not work. Please try again.');}finally{setBusy(false);}};

 const answer=(raw:string,label?:string)=>{
  const value=raw.trim();if(!value||busy)return;
  say('you',label||value);setText('');
  void run(async()=>{
   if(stage==='name'){
    const given=cleanName(value);if(!given)throw new Error("I didn't catch that. What should I call you?");
    const saved=await api('/me/preferences','GET',undefined,undefined,true).catch(()=>({}));
    const result=await api('/me/preferences','PUT',{goals:saved?.goals||[],sources:saved?.sources||[],completed:Boolean(saved?.completed),dismissed_next_steps:Boolean(saved?.dismissed_next_steps),name:given});
    setName(result?.name||given);onNamed(result?.name||given);move(after('name',ctx));
   }else if(stage==='team'){
    if(yes(value))move('team-name');else if(no(value))move(after('team',ctx));else throw new Error('Say yes for a team workspace, or not now.');
   }else if(stage==='team-name'){
    const made=await api('/workspaces','POST',{name:value.slice(0,120)});
    setTeamName(made.name);onTeamCreated(made);
    const next=[...workspaces,made];
    setLines(previous=>[...previous,{who:'lapi',text:`Created ${made.name}. You can add people to it any time from the workspace menu at the top.`}]);
    move(after('team',{...ctx,workspaces:next,chosen:false}));
   }else if(stage==='choose'){
    const picked=matchWorkspace(workspaces,value);if(!picked)throw new Error('Tap one of the workspaces, or say its name.');
    onChoose(picked.id);move(after('choose',{...ctx,current:picked,chosen:true}));
   }else if(stage==='collection'){
    setCollectionName(value.slice(0,200));move('type');
   }else if(stage==='type'){
    const type=matchType(value);
    const made=await api('/datasets','POST',{name:collectionName,description:'',collection_type:type,workspace_id:current?.id||''});
    await api(`/datasets/${encodeURIComponent(made.id)}/migrate-settings`,'POST',{});
    onCollectionCreated(made.id);
    setLines(previous=>[...previous,{who:'lapi',text:`${collectionName} is ready${type?` as a ${type} collection`:''}.`}]);
    move('done');
   }else if(stage==='done'){
    onDone();
   }
  });
 };

 const toggleMic=()=>{
  if(listening){recognizer.current?.stop();setListening(false);return;}
  const Recognizer=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition;if(!Recognizer)return;
  const r=new Recognizer();r.lang=navigator.language||'en';r.interimResults=false;r.maxAlternatives=1;
  r.onresult=(event:any)=>{const heard=event.results?.[0]?.[0]?.transcript||'';setListening(false);if(heard)answer(heard);};
  r.onerror=()=>{setListening(false);setError('I could not hear that. Type it instead, or try again.');};
  r.onend=()=>setListening(false);
  recognizer.current=r;setListening(true);r.start();
 };

 return <div className="setup-chat-backdrop"><div className="setup-chat" role="dialog" aria-modal="true" aria-label="Set up with Lapi">
  <header className="setup-chat-head"><AgentLogo size={34} label="Lapi"/><div><strong>Lapi</strong><small>{busy?'Working…':listening?'Listening…':'Setting you up'}</small></div></header>
  <div ref={thread} className="setup-chat-thread" aria-live="polite">
   {lines.map((line,i)=><p key={i} className={`setup-chat-line is-${line.who}`}>{line.text}</p>)}
   {error&&<p className="setup-chat-line is-lapi is-error" role="alert">{error}</p>}
  </div>
  {said.quick&&<div className="setup-chat-quick" role="group" aria-label="Quick answers">{said.quick.map((q:Quick)=><button key={q.value} type="button" disabled={busy} onClick={()=>answer(q.value,q.label)}>{q.label}</button>)}</div>}
  {(said.typing||!said.quick)&&<form className="setup-chat-compose" onSubmit={event=>{event.preventDefault();answer(text);}}>
   <input ref={input} aria-label="Your answer" value={text} maxLength={200} placeholder={stage==='name'?'Your name':'Type your answer…'} disabled={busy} onChange={event=>setText(event.target.value)}/>
   {voice&&<button type="button" className={listening?'is-on':''} aria-label={listening?'Stop listening':'Speak your answer'} aria-pressed={listening} disabled={busy} onClick={toggleMic}><Mic size={20}/></button>}
   <button type="submit" className="setup-chat-send" aria-label="Send" disabled={busy||!text.trim()}><ArrowUp size={20}/></button>
  </form>}
 </div></div>;
}
