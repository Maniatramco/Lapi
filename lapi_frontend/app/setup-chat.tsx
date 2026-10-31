"use client";
import {useEffect,useRef,useState} from 'react';
import {ArrowUp,Mic,X} from 'lucide-react';
import {SUPPORT_NAME,helpMailto} from './support';
import {AgentLogo} from './agent-logo';
import {ACCEPT,fieldsToSchema,fileState,openReviewPage,pickFiles,recordCount,resultRows,type Field} from './quick-start-flow';
import {after,applyChange,cleanName,fieldList,helpWish,matchType,matchWorkspace,no,prompt,suggestFields,yes,type Quick,type Stage} from './setup-chat-script';
import {fieldKey} from './quick-start-flow';
import './setup-chat.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
type Line={who:'lapi'|'you';text:string};
const POLL_MS=3000,POLL_LIMIT_MS=10*60*1000;
const wait=(ms:number)=>new Promise(resolve=>window.setTimeout(resolve,ms));

/** First sign-in as a chat with Lapi: your name, a team workspace if you want one, which workspace
 * to use, your first collection, what to pull out (fields prefilled from your words), your first
 * documents, reading, extraction and the results. Answers can be typed, tapped or spoken. */
/** Lapi asks again in the chat (an unclear answer), as opposed to something that failed. */
class AskAgain extends Error{}

export function SetupChat({api,user,workspaces,canCreateTeam,current,chosen,needName,entry='setup',dataset,lastError='',page='',version='',onNamed,onTeamCreated,onChoose,onCollectionCreated,onChanged,onDone}:{api:Api;user:Entity;workspaces:Entity[];canCreateTeam:boolean;current?:Entity;chosen:boolean;needName:boolean;entry?:'setup'|'help'|'email';dataset?:Entity;lastError?:string;page?:string;version?:string;onNamed:(name:string)=>void;onTeamCreated:(workspace:Entity)=>void;onChoose:(id:string)=>void;onCollectionCreated:(id:string)=>void;onChanged?:()=>void;onDone:()=>void}){
 const ctx={workspaces,current,canCreateTeam,chosen};
 const [name,setName]=useState<string>(user.display_name||'');
 const [stage,setStage]=useState<Stage>(()=>entry==='help'?'help':entry==='email'?'email':needName?'name':after('name',ctx));
 const [lines,setLines]=useState<Line[]>([]);
 const [text,setText]=useState(''),[busy,setBusy]=useState(false),[listening,setListening]=useState(false),[error,setError]=useState('');
 const [teamName,setTeamName]=useState(''),[collectionName,setCollectionName]=useState(''),[collectionType,setCollectionType]=useState(''),[collectionId,setCollectionId]=useState('');
 const [promptName,setPromptName]=useState(''),[fields,setFields]=useState<Field[]>([]),[files,setFiles]=useState<File[]>([]);
 const [progress,setProgress]=useState(''),[results,setResults]=useState(''),[extractionId,setExtractionId]=useState('');
 const input=useRef<HTMLInputElement|null>(null),thread=useRef<HTMLDivElement|null>(null),recognizer=useRef<any>(null),camera=useRef<HTMLInputElement|null>(null),picker=useRef<HTMLInputElement|null>(null),live=useRef(true);
 const said=prompt(stage,{name,workspaces,current,canCreateTeam,teamName,collectionName,collectionType,fields,files:files.map(f=>f.name),progress,results,lastError});
 const voice=typeof window!=='undefined'&&Boolean((window as any).SpeechRecognition||(window as any).webkitSpeechRecognition);

 useEffect(()=>()=>{live.current=false;},[]);
 useEffect(()=>{setLines(previous=>[...previous,{who:'lapi',text:said.text}]);setText('');setError('');},[stage]);  // eslint-disable-line react-hooks/exhaustive-deps
 // Reading and extracting update their own line as they go.
 useEffect(()=>{if(stage!=='reading'&&stage!=='extracting')return;setLines(previous=>{const next=[...previous];for(let i=next.length-1;i>=0;i--)if(next[i].who==='lapi'){next[i]={who:'lapi',text:said.text};break;}return next;});},[said.text,stage]);
 useEffect(()=>{thread.current?.scrollTo({top:thread.current.scrollHeight});if(said.typing)input.current?.focus();},[lines,said.typing]);

 const say=(value:string)=>setLines(previous=>[...previous,{who:'you',text:value}]);
 const tell=(value:string)=>setLines(previous=>[...previous,{who:'lapi',text:value}]);
 const move=(next:Stage)=>setStage(next);
 // Asking again is part of the conversation, not an error: it shows as Lapi's next line.
 const run=async(work:()=>Promise<void>)=>{setBusy(true);setError('');try{await work();}catch(e){if(e instanceof AskAgain)tell(e.message);else setError(e instanceof Error?e.message:'That did not work. Please try again.');}finally{setBusy(false);}};

 /** Upload, then read until every file is ready or has failed, then extract. */
 const readAndExtract=async()=>{
  const form=new FormData();files.forEach(file=>form.append('files',file,file.name));
  form.append('dataset_id',collectionId);form.append('allow_external','true');
  const uploaded=await api('/documents/upload','POST',form);
  let docs:Entity[]=(uploaded.documents||[]).map((d:Entity)=>({id:d.id,name:d.name||d.filename||'Document',state:fileState(d.status)}));
  setFiles([]);onChanged?.();
  const started=Date.now();
  while(docs.some(d=>d.state==='working')&&Date.now()-started<POLL_LIMIT_MS&&live.current){
   await wait(POLL_MS);
   docs=await Promise.all(docs.map(async d=>{if(d.state!=='working')return d;try{const doc=await api(`/documents/${encodeURIComponent(d.id)}`,'GET',undefined,undefined,true);return {...d,state:fileState(doc.status)};}catch{return d;}}));
   const ready=docs.filter(d=>d.state==='ready').length;setProgress(`Reading your documents… ${ready} of ${docs.length} ready.`);
  }
  const readyIds=docs.filter(d=>d.state==='ready').map(d=>d.id);
  if(!readyIds.length)throw new Error('I could not read those files. Try a clearer photo, or different files.');
  if(!fields.length){move('done');return;}
  setProgress('');move('extracting');
  const template=await api('/templates','POST',{name:(promptName||'Extraction').slice(0,200),schema:fieldsToSchema(fields),instructions:'',dataset_id:collectionId});
  const created=await api('/extractions','POST',{document_ids:readyIds.slice(0,20),template_id:template.id,dataset_id:collectionId,allow_external:true});
  const id=created.id||created.extraction_id;let currentRun:Entity=created;const begun=Date.now();
  while(!['ready','failed','cancelled'].includes(currentRun.status)&&Date.now()-begun<POLL_LIMIT_MS&&live.current){
   await wait(POLL_MS);currentRun=await api(`/extractions/${encodeURIComponent(id)}`,'GET',undefined,undefined,true);
   setProgress(`Pulling out ${fieldList(fields)}… ${currentRun.status==='saved'||currentRun.status==='queued'?'waiting for the model':currentRun.status}.`);
  }
  onChanged?.();
  if(currentRun.status!=='ready')throw new Error(currentRun.error||'The extraction did not finish. You can see it on the Review page.');
  const rows=resultRows(currentRun.result,fields);const count=recordCount(currentRun.result);
  setExtractionId(id);
  setResults(`Done: ${count} ${count===1?'record':'records'} from ${readyIds.length} ${readyIds.length===1?'document':'documents'}.\n${rows.map(r=>`${r.label}: ${r.value}`).join('\n')}${count>1?`\n(That is record 1 of ${count}; the Review page has them all.)`:''}`);
  move('results');
 };

 /** Fields the model proposed, as the screen's own field records. */
 const fromModel=(list:any[]|undefined):Field[]=>{const taken:string[]=[];return (list||[]).slice(0,15).map((f:any)=>{const key=fieldKey(String(f.label||''),taken);taken.push(key);return {key,label:String(f.label||'').slice(0,60),type:f.type||'text',description:String(f.description||'').slice(0,240)};}).filter(f=>f.label);};
 /** What a typed or spoken answer means, read by the Default chat model when there is one. Taps need no reading. */
 const interpret=async(value:string,tapped:boolean)=>{
  if(tapped)return null;
  try{const read=await api('/setup/interpret','POST',{stage,answer:value,options:(said.quick||[]).map((q:Quick)=>q.label),fields:fields.map(f=>f.label),collection_type:collectionType,name},undefined,true);return read&&read.decision&&read.decision!=='rules'?read:null;}catch{return null;}
 };
 const answer=(raw:string,label?:string)=>{
  const value=raw.trim();if(!value||busy)return;
  say(label||value);setText('');
  void run(async()=>{
   const read=await interpret(value,Boolean(label));
   const d=read?.decision;
   const isYes=d==='yes'||(!d||d==='answer'||d==='unclear')&&yes(value);
   const isNo=d==='no'||d==='skip'||(!d||d==='answer'||d==='unclear')&&no(value);
   const unclear=(fallback:string)=>new AskAgain(read?.message||fallback);
   if(stage==='help'){
    const wish=(['collection','team','extract','email'].includes(read?.pick||'')?read?.pick:label?value:helpWish(value)) as string;
    if(wish==='collection')move('collection');
    else if(wish==='team')move(canCreateTeam?'team-name':'collection');
    else if(wish==='extract'){if(dataset?.id){setCollectionId(dataset.id);setCollectionName(dataset.name||'');setCollectionType(dataset.collection_type||'');move('interest');}else move('collection');}
    else if(wish==='email')move('email');
    else throw unclear('Tap one of the options, or say what you need in a few words.');
   }else if(stage==='email'){
    window.location.href=helpMailto({message:value,name,workspace:current?.name,page,version,error:lastError});
    move('sent');
   }else if(stage==='sent'){
    if(value==='help')move('help');else onDone();
   }else if(stage==='name'){
    const given=cleanName(read?.name||value);if(!given)throw unclear("I didn't catch that. What should I call you?");
    const saved=await api('/me/preferences','GET',undefined,undefined,true).catch(()=>({}));
    const result=await api('/me/preferences','PUT',{goals:saved?.goals||[],sources:saved?.sources||[],completed:Boolean(saved?.completed),dismissed_next_steps:Boolean(saved?.dismissed_next_steps),name:given});
    setName(result?.name||given);onNamed(result?.name||given);move(after('name',ctx));
   }else if(stage==='team'){
    if(isYes)move('team-name');else if(isNo)move(after('team',ctx));else throw unclear('Say yes for a team workspace, or not now.');
   }else if(stage==='team-name'){
    const made=await api('/workspaces','POST',{name:(read?.pick||value).slice(0,120)});
    setTeamName(made.name);onTeamCreated(made);
    tell(`Created ${made.name}. You can add people to it any time from the workspace menu at the top.`);
    move(after('team',{...ctx,workspaces:[...workspaces,made],chosen:false}));
   }else if(stage==='choose'){
    const picked=matchWorkspace(workspaces,read?.pick||value);if(!picked)throw unclear('Tap one of the workspaces, or say its name.');
    onChoose(picked.id);move(after('choose',{...ctx,current:picked,chosen:true}));
   }else if(stage==='collection'){
    if(d==='skip'||value==='skip'){move(after('type',ctx));return;}
    setCollectionName((read?.pick||value).slice(0,200));move('type');
   }else if(stage==='type'){
    const type=d==='skip'?'':matchType(read?.pick||value);setCollectionType(type);
    const made=await api('/datasets','POST',{name:collectionName,description:'',collection_type:type,workspace_id:current?.id||''});
    await api(`/datasets/${encodeURIComponent(made.id)}/migrate-settings`,'POST',{});
    setCollectionId(made.id);onCollectionCreated(made.id);
    tell(`${collectionName} is ready${type?` as a ${type} collection`:''}.`);
    move(after('type',{...ctx,created:true}));
   }else if(stage==='interest'){
    if(isNo){setFields([]);move('documents');return;}
    const proposed=fromModel(read?.fields);
    const suggested=proposed.length?{name:read?.pick||suggestFields(value,collectionType).name,fields:proposed}:suggestFields(value,collectionType);
    if(!suggested.fields.length)throw unclear('Tell me the things you want, for example: invoice number, vendor and total.');
    setPromptName(suggested.name);setFields(suggested.fields);move('fields');
   }else if(stage==='fields'){
    const proposed=fromModel(read?.fields);
    if(proposed.length){setFields(proposed);tell(`Now: ${fieldList(proposed)}.`);}
    else if(isYes)move('documents');else if(d==='change'||/change|edit|no|different/i.test(value))move('change');else{const next=applyChange(fields,value);setFields(next);tell(`Now: ${fieldList(next)}.`);}
   }else if(stage==='change'){
    const proposed=fromModel(read?.fields);
    const next=proposed.length?proposed:applyChange(fields,value);if(!next.length)throw unclear('That would leave nothing to pull out. Name at least one field.');
    setFields(next);move('fields');
   }else if(stage==='documents'){
    if(value==='camera')camera.current?.click();else if(value==='files')picker.current?.click();else if(isNo)move('done');else throw unclear('Tap Take a photo or Choose files.');
   }else if(stage==='consent'){
    if(value==='more'||d==='change'){move('documents');return;}
    if(isNo){setFiles([]);move('documents');return;}
    if(!isYes)throw unclear('Say yes to read them, or start over.');
    setProgress('');move('reading');await readAndExtract();
   }else if(stage==='results'){
    if(value==='review'&&extractionId){openReviewPage(extractionId);onDone();}else onDone();
   }else if(stage==='done'){
    onDone();
   }
  });
 };

 const addFiles=(list:FileList|null)=>{if(!list)return;const picked=pickFiles([...files,...Array.from(list)]);setFiles(picked.files);if(picked.note)tell(picked.note);if(picked.files.length)move('consent');};

 const toggleMic=()=>{
  if(listening){recognizer.current?.stop();setListening(false);return;}
  const Recognizer=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition;if(!Recognizer)return;
  const r=new Recognizer();r.lang=navigator.language||'en';r.interimResults=false;r.maxAlternatives=1;
  r.onresult=(event:any)=>{const heard=event.results?.[0]?.[0]?.transcript||'';setListening(false);if(heard)answer(heard);};
  r.onerror=()=>{setListening(false);setError('I could not hear that. Type it instead, or try again.');};
  r.onend=()=>setListening(false);
  recognizer.current=r;setListening(true);r.start();
 };

 const working=stage==='reading'||stage==='extracting';
 return <div className="setup-chat-backdrop"><div className="setup-chat" role="dialog" aria-modal="true" aria-label="Set up with Lapi">
  <header className="setup-chat-head"><AgentLogo size={34} label="Lapi"/><div><strong>Lapi</strong><small>{busy||working?'Working…':listening?'Listening…':entry==='setup'?'Setting you up':'Here to help'}</small></div><button type="button" className="setup-chat-close" aria-label="Close" disabled={working} onClick={onDone}><X size={20}/></button></header>
  <div ref={thread} className="setup-chat-thread" aria-live="polite">
   {lines.map((line,i)=><p key={i} className={`setup-chat-line is-${line.who}`}>{line.text}</p>)}
   {error&&<p className="setup-chat-line is-lapi is-error" role="alert">{error}</p>}
  </div>
  <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={e=>{addFiles(e.target.files);e.target.value='';}}/>
  <input ref={picker} type="file" accept={ACCEPT} multiple hidden onChange={e=>{addFiles(e.target.files);e.target.value='';}}/>
  {said.quick&&!working&&<div className="setup-chat-quick" role="group" aria-label="Quick answers">{said.quick.map((q:Quick)=><button key={q.value} type="button" disabled={busy} onClick={()=>answer(q.value,q.label)}>{q.label}</button>)}</div>}
  {(said.typing||!said.quick)&&!working&&<form className="setup-chat-compose" onSubmit={event=>{event.preventDefault();answer(text);}}>
   <input ref={input} aria-label="Your answer" value={text} maxLength={200} placeholder={stage==='name'?'Your name':'Type your answer…'} disabled={busy} onChange={event=>setText(event.target.value)}/>
   {voice&&<button type="button" className={listening?'is-on':''} aria-label={listening?'Stop listening':'Speak your answer'} aria-pressed={listening} disabled={busy} onClick={toggleMic}><Mic size={20}/></button>}
   <button type="submit" className="setup-chat-send" aria-label="Send" disabled={busy||!text.trim()}><ArrowUp size={20}/></button>
  </form>}
 </div></div>;
}
