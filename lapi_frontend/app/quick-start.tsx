"use client";
import {useEffect,useRef,useState} from "react";
import {ArrowLeft,Camera,Check,CircleAlert,FileUp,Loader2,MessageSquare,Plus,Sparkles,Users,X} from "lucide-react";
import "./quick-start.css";
import {ACCEPT,FILE_STATE_TEXT,SUGGESTED_QUESTIONS,askable,canCreateDataset,defaultDatasetName,fileState,pickFiles,progress,sourceName,stepsFor,uploadable,type FileState,type Step} from "./quick-start-flow";
import {eligibleAgentModels} from "./agent-document-selection";
import {openDatasetEditor} from "./manage-dataset";

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:any,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
type Uploaded={id:string;name:string;state:FileState;error:string};

const STEP_TITLE:Record<Step,string>={dataset:'Choose where it goes',documents:'Add your documents',processing:'Reading your documents',ask:'Ask your first question',done:'You did it'};
const POLL_MS=3000,POLL_LIMIT_MS=10*60*1000;

/** A guided sheet that takes a person through one complete workflow: dataset → documents →
 * reading → a first cited answer. Full screen on phones, a dialog on larger screens. */
export function QuickStart({api,user,datasets,sources=[],onClose,onChanged,onNavigate}:{api:Api;user:Entity;datasets:Entity[];sources?:string[];onClose:()=>void;onChanged:()=>void;onNavigate:(view:string)=>void}){
 const isAdmin=Boolean(user?.is_admin);
 const steps=stepsFor(datasets,isAdmin);
 const choices=steps.includes('documents')?uploadable(datasets,isAdmin):askable(datasets);
 const [step,setStep]=useState<Step>('dataset');
 const [datasetId,setDatasetId]=useState<string>(choices[0]?.id||(isAdmin?'new':''));
 const [newName,setNewName]=useState(defaultDatasetName(user?.username));
 const [files,setFiles]=useState<File[]>([]),[note,setNote]=useState(''),[consent,setConsent]=useState(false);
 const [uploaded,setUploaded]=useState<Uploaded[]>([]);
 const [question,setQuestion]=useState(''),[answer,setAnswer]=useState<Entity|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const sheet=useRef<HTMLDivElement>(null),camera=useRef<HTMLInputElement>(null),picker=useRef<HTMLInputElement>(null);
 const dataset=datasets.find(d=>d.id===datasetId);
 const position=steps.indexOf(step);
 const cloud=sources.filter(s=>s!=='files'&&s!=='not_sure');

 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;sheet.current?.querySelector<HTMLElement>('h2')?.focus();
  const key=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!busy)onClose();};document.addEventListener('keydown',key);
  return()=>{document.removeEventListener('keydown',key);previous?.focus?.();};},[]);
 useEffect(()=>{sheet.current?.querySelector<HTMLElement>('h2')?.focus();setError('');},[step]);

 // While documents are being read, check them every few seconds.
 useEffect(()=>{
  if(step!=='processing'||!uploaded.length)return;
  let stopped=false;const started=Date.now();
  const tick=async()=>{
   const next=await Promise.all(uploaded.map(async item=>{if(item.state!=='working')return item;
    try{const doc=await api(`/documents/${encodeURIComponent(item.id)}`,'GET',undefined,undefined,true);return {...item,state:fileState(doc.status),error:doc.error||''};}
    catch{return item;}}));
   if(stopped)return;setUploaded(next);
   if(next.some(item=>item.state==='working')&&Date.now()-started<POLL_LIMIT_MS)timer=window.setTimeout(()=>void tick(),POLL_MS);
   else onChanged();
  };
  let timer=window.setTimeout(()=>void tick(),POLL_MS);
  return()=>{stopped=true;window.clearTimeout(timer);};
 },[step,uploaded.length]);

 const run=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');try{await fn();}catch(e){setError(e instanceof Error?e.message:'That did not work. Try again.');}finally{setBusy(false);}};
 const next=()=>setStep(steps[Math.min(position+1,steps.length-1)]);
 const back=()=>setStep(steps[Math.max(position-1,0)]);

 const chooseDataset=()=>run(async()=>{
  if(datasetId==='new'){
   const name=newName.trim();if(!name)throw new Error('Give the dataset a name.');
   const created=await api('/datasets','POST',{name});
   await api(`/datasets/${encodeURIComponent(created.id)}/migrate-settings`,'POST',{});  // Workspace Default models.
   setDatasetId(created.id);onChanged();
  }else if(!datasetId)throw new Error('Choose a dataset.');
  next();
 });
 const addFiles=(list:FileList|null)=>{if(!list)return;const picked=pickFiles([...files,...Array.from(list)]);setFiles(picked.files);setNote(picked.note);};
 const upload=()=>run(async()=>{
  if(!files.length)throw new Error('Add at least one document or photo.');
  if(!consent)throw new Error('Tick the box to let Lapi read these documents.');
  const form=new FormData();files.forEach(file=>form.append('files',file,file.name));
  form.append('dataset_id',datasetId);form.append('allow_external','true');
  const result=await api('/documents/upload','POST',form);
  setUploaded((result.documents||[]).map((doc:Entity)=>({id:doc.id,name:doc.name||doc.filename||'Document',state:fileState(doc.status),error:''})));
  setFiles([]);onChanged();setStep('processing');
 });
 const ask=(text:string)=>run(async()=>{
  const value=text.trim();if(!value)throw new Error('Type a question, or tap one of the suggestions.');
  setQuestion(value);setAnswer(null);
  const catalog=await api('/dataset-chat/catalog','GET',undefined,undefined,true);
  const known=(catalog.datasets||[]).find((d:Entity)=>d.id===datasetId)||dataset;
  const models=eligibleAgentModels(catalog.models||[],known);
  const model=models.find((m:Entity)=>m.id===known?.default_chat_model_id)?.id||models[0]?.id;
  if(!model)throw new Error('This dataset has no chat model yet. Ask an administrator to set one in Model Mapping.');
  const ready=uploaded.filter(item=>item.state==='ready').map(item=>item.id);
  const reply=await api('/dataset-chat/messages','POST',{text:value,dataset_ids:[datasetId],...(ready.length?{document_ids:ready}:{}),model_id:model});
  setAnswer(reply.message||null);
 });

 const state=progress(uploaded.map(item=>item.state));
 const canShare=isAdmin||dataset?.my_access==='owner';
 return <div className="quick-start-backdrop" onClick={event=>{if(event.target===event.currentTarget&&!busy)onClose();}}>
  <div ref={sheet} className="quick-start" role="dialog" aria-modal="true" aria-labelledby="quick-start-title">
   <header className="quick-start-head">
    {position>0&&step!=='done'&&step!=='processing'?<button type="button" className="quick-start-icon" aria-label="Back" onClick={back} disabled={busy}><ArrowLeft size={20}/></button>:<span className="quick-start-icon-space"/>}
    <div className="quick-start-progress" aria-label={`Step ${position+1} of ${steps.length}`}>{steps.map((s,i)=><span key={s} className={i<=position?'on':''}/>)}</div>
    <button type="button" className="quick-start-icon" aria-label="Close quick start" onClick={onClose} disabled={busy}><X size={20}/></button>
   </header>
   <div className="quick-start-body">
    <p className="quick-start-eyebrow">Quick start · step {position+1} of {steps.length}</p>
    <h2 id="quick-start-title" tabIndex={-1}>{STEP_TITLE[step]}</h2>

    {step==='dataset'&&<>
     <p className="quick-start-lead">{steps.includes('documents')?'Documents always go into a dataset: a shared folder with its own models and people.':'Pick a dataset shared with you to ask about.'}</p>
     {!choices.length&&!canCreateDataset(isAdmin)?<p className="quick-start-empty">No datasets are shared with you yet. Ask an administrator or a dataset owner to give you access.</p>:
     <div className="quick-start-options" role="radiogroup" aria-label="Datasets">
      {choices.map(d=><label key={d.id} className={datasetId===d.id?'selected':''}><input type="radio" name="qs-dataset" checked={datasetId===d.id} onChange={()=>setDatasetId(d.id)}/>
       <span><strong>{d.name}</strong><small>{d.description||(d.my_access?`Your access: ${d.my_access}`:'')}</small></span></label>)}
      {canCreateDataset(isAdmin)&&<label className={datasetId==='new'?'selected':''}><input type="radio" name="qs-dataset" checked={datasetId==='new'} onChange={()=>setDatasetId('new')}/>
       <span><strong><Plus size={15}/> New dataset</strong><small>Uses the workspace's default models</small></span></label>}
     </div>}
     {datasetId==='new'&&<label className="quick-start-field">Dataset name<input value={newName} maxLength={200} onChange={e=>setNewName(e.target.value)} disabled={busy}/></label>}
    </>}

    {step==='documents'&&<>
     <p className="quick-start-lead">Into <strong>{dataset?.name||'your dataset'}</strong>. Photos of paper documents work too: Lapi reads them.</p>
     <div className="quick-start-pick">
      <button type="button" onClick={()=>camera.current?.click()} disabled={busy}><Camera size={26}/><span>Take a photo</span></button>
      <button type="button" onClick={()=>picker.current?.click()} disabled={busy}><FileUp size={26}/><span>Choose files</span></button>
      <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={e=>{addFiles(e.target.files);e.target.value='';}}/>
      <input ref={picker} type="file" accept={ACCEPT} multiple hidden onChange={e=>{addFiles(e.target.files);e.target.value='';}}/>
     </div>
     {note&&<p className="quick-start-note">{note}</p>}
     {files.length>0&&<ul className="quick-start-files">{files.map((file,i)=><li key={file.name+i}><span>{file.name}</span><small>{Math.max(1,Math.round(file.size/1024))} KB</small>
      <button type="button" aria-label={`Remove ${file.name}`} onClick={()=>setFiles(files.filter((_,j)=>j!==i))} disabled={busy}><X size={16}/></button></li>)}</ul>}
     <label className="quick-start-consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)} disabled={busy}/>
      <span>Let Lapi read and index these documents with the AI services set up for this dataset.</span></label>
     {cloud.length>0&&<p className="quick-start-alt">Your files are in {cloud.length===1?'cloud storage':'cloud storage'}? <a href={'#'+encodeURIComponent('Add knowledge')+'/'+encodeURIComponent(cloud[0])} onClick={onClose}>Connect it with the step-by-step guide</a> instead.</p>}
    </>}

    {step==='processing'&&<>
     <p className="quick-start-lead">{state.finished?(state.ready?'Done. You can ask about them now.':'Lapi could not read these files.'):'This usually takes under a minute. You can ask as soon as one is ready.'}</p>
     <div className="quick-start-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={state.percent}><span style={{width:`${Math.max(state.percent,6)}%`}}/></div>
     <ul className="quick-start-files" aria-live="polite">{uploaded.map(item=><li key={item.id} data-state={item.state}>
      {item.state==='working'?<Loader2 size={17} className="animate-spin"/>:item.state==='ready'?<Check size={17}/>:<CircleAlert size={17}/>}
      <span>{item.name}</span><small>{item.state==='failed'&&item.error?item.error:FILE_STATE_TEXT[item.state]}</small></li>)}</ul>
     {state.finished&&!state.ready&&<button type="button" className="quick-start-secondary" onClick={()=>{setUploaded([]);setStep('documents');}}>Try other files</button>}
    </>}

    {step==='ask'&&<>
     <p className="quick-start-lead">Ask anything about <strong>{dataset?.name||'this dataset'}</strong>. Every answer shows where it came from.</p>
     {!answer&&<div className="quick-start-chips">{SUGGESTED_QUESTIONS.map(q=><button key={q} type="button" onClick={()=>void ask(q)} disabled={busy}>{q}</button>)}</div>}
     <form className="quick-start-ask" onSubmit={e=>{e.preventDefault();void ask(question);}}>
      <textarea aria-label="Your question" rows={2} value={question} placeholder="Type your question…" maxLength={2000} onChange={e=>setQuestion(e.target.value)} disabled={busy}/>
      <button type="submit" className="quick-start-send" disabled={busy||!question.trim()} aria-label="Ask">{busy?<Loader2 size={18} className="animate-spin"/>:<MessageSquare size={18}/>}</button>
     </form>
     {busy&&<p className="quick-start-note" role="status">Lapi is reading your documents to answer…</p>}
     {answer&&<article className="quick-start-answer" aria-live="polite">
      <p>{answer.text}</p>
      {(answer.citations||[]).length>0&&<><h3>Sources</h3><ol>{answer.citations.map((c:Entity)=><li key={c.index}>{sourceName(c)}</li>)}</ol></>}
     </article>}
    </>}

    {step==='done'&&<>
     <div className="quick-start-celebrate"><Sparkles size={34}/></div>
     <p className="quick-start-lead">You added documents and got your first answer with sources. Everything is in <strong>{dataset?.name||'your dataset'}</strong>.</p>
     <div className="quick-start-next">
      <button type="button" onClick={()=>{onClose();onNavigate('Home');}}><MessageSquare size={18}/><span>Keep asking on the Dashboard</span></button>
      {steps.includes('documents')&&<button type="button" onClick={()=>{setAnswer(null);setQuestion('');setUploaded([]);setStep('documents');}}><FileUp size={18}/><span>Add more documents</span></button>}
      {canShare&&dataset&&<button type="button" onClick={()=>{onClose();openDatasetEditor(dataset.id,'members');}}><Users size={18}/><span>Share with your team</span></button>}
     </div>
    </>}

    {error&&<p className="quick-start-error" role="alert"><CircleAlert size={16}/> {error}</p>}
   </div>

   <footer className="quick-start-foot">
    {step==='dataset'&&<button type="button" className="quick-start-primary" disabled={busy||(!choices.length&&!canCreateDataset(isAdmin))} onClick={()=>void chooseDataset()}>{busy?'Creating…':'Continue'}</button>}
    {step==='documents'&&<button type="button" className="quick-start-primary" disabled={busy||!files.length} onClick={()=>void upload()}>{busy?'Uploading…':`Upload ${files.length||''} and read`.replace('  ',' ')}</button>}
    {step==='processing'&&<button type="button" className="quick-start-primary" disabled={!state.ready} onClick={next}>{state.ready?'Ask a question':'Reading…'}</button>}
    {step==='ask'&&<button type="button" className="quick-start-primary" disabled={!answer||busy} onClick={next}>{answer?'Finish':'Ask to continue'}</button>}
    {step==='done'&&<button type="button" className="quick-start-primary" onClick={onClose}>Close</button>}
   </footer>
  </div>
 </div>;
}
