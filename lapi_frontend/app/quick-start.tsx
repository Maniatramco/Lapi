"use client";
import {useEffect,useRef,useState} from "react";
import {ArrowLeft,Camera,Check,CircleAlert,FileSearch,FileUp,Loader2,Maximize2,MessageSquare,Minimize2,Plus,Sparkles,Table2,Trash2,Users,Wand2,X} from "lucide-react";
import "./quick-start.css";
import {ACCEPT,FIELD_TYPES,FILE_STATE_TEXT,SUGGESTED_QUESTIONS,askable,canAddDocuments,workspaceSlots,canMerge,columnMapping,columnValue,defaultDatasetName,extractionStages,howBadge,howChosen,initialChoices,isSpreadsheet,fieldKey,fieldProblems,fieldsToSchema,fileState,mergeByDefault,openReviewPage,pickFiles,progress,recordCount,resultRows,sourceName,stepsFor,uploadable,
 type Field,type FieldType,type FileState,type Path,type Step,type TablePlan} from "./quick-start-flow";
import {eligibleAgentModels} from "./agent-document-selection";
import {currentDevice} from "./screens-client";
import {openDatasetEditor} from "./manage-dataset";

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:any,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
type Uploaded={id:string;name:string;state:FileState;error:string};

const STEP_TITLE:Record<Step,string>={dataset:'Choose where it goes',documents:'Add your documents',processing:'Reading your documents',choose:'What would you like to do?',
 ask:'Ask your first question',prompt:'What should Lapi pull out?',extracting:'Pulling out your data',done:'You did it'};
// Short names for the step rail on wide screens.
const STEP_RAIL:Record<Step,string>={dataset:'Workspace',documents:'Documents',processing:'Reading',choose:'Ask or extract',ask:'Ask',prompt:'Fields',extracting:'Results',done:'Done'};
const POLL_MS=3000,POLL_LIMIT_MS=10*60*1000;
const wait=(ms:number)=>new Promise(resolve=>window.setTimeout(resolve,ms));

/** A guided sheet that takes a person through one complete workflow: dataset → documents →
 * reading → a first answer with sources, or a first extraction with a prompt the AI drafts
 * from the document. Full screen on phones, a dialog on larger screens. */
const ENLARGED_KEY='lapi:quick-start-enlarged';
export function QuickStart({api,user,datasets,sources=[],initialFiles=[],quickExtract=false,onClose,onChanged,onNavigate,onSelectDataset}:{api:Api;user:Entity;datasets:Entity[];sources?:string[];initialFiles?:File[];quickExtract?:boolean;onClose:()=>void;onChanged:()=>void;onNavigate:(view:string)=>void;onSelectDataset?:(id:string)=>void}){
 // Contributors (Keycloak lapi-contributor) create datasets and are Owner on all of them, like administrators.
 const isAdmin=Boolean(user?.is_admin||user?.is_contributor);
 const editor=canAddDocuments(datasets,isAdmin);
 const choices=editor?uploadable(datasets,isAdmin):askable(datasets);
 const [path,setPath]=useState<Path>(quickExtract?'extract':'ask');
 const slots=workspaceSlots(datasets,isAdmin),canCreate=slots.length>0;
 const [newAudience,setNewAudience]=useState<'personal'|'team'>(slots[0]||'personal');
 const [datasetId,setDatasetId]=useState<string>(choices[0]?.id||(canCreate?'new':''));
 // A new workspace belongs to its creator, so its documents step is always available.
 const steps=stepsFor(datasets,isAdmin||datasetId==='new',path);
 const [step,setStep]=useState<Step>('dataset');
 // Enlarged: the Quick start fills the window (remembered on this device).
 const [enlarged,setEnlarged]=useState(()=>{try{return localStorage.getItem(ENLARGED_KEY)==='1';}catch{return false;}});
 const toggleEnlarged=()=>setEnlarged(value=>{try{localStorage.setItem(ENLARGED_KEY,value?'0':'1');}catch{}return !value;});
 const [newName,setNewName]=useState(defaultDatasetName(user?.username)),[newDescription,setNewDescription]=useState('');
 const [files,setFiles]=useState<File[]>(initialFiles),[note,setNote]=useState('');  // may start with documents attached in the agent
 // Two or more files: stitch them into one document first, or keep them separate.
 const [merge,setMerge]=useState(false),[mergeTouched,setMergeTouched]=useState(false);
 // Consent, asked where data first goes to an AI model: reading documents, then answering or extracting.
 const [uploadConsent,setUploadConsent]=useState(false),[aiConsent,setAiConsent]=useState(false);
 const [uploaded,setUploaded]=useState<Uploaded[]>([]);
 const [question,setQuestion]=useState(''),[answer,setAnswer]=useState<Entity|null>(null);
 const [promptName,setPromptName]=useState(''),[instructions,setInstructions]=useState(''),[fields,setFields]=useState<Field[]>([]),[change,setChange]=useState('');
 const [extraction,setExtraction]=useState<Entity|null>(null);
 // Spreadsheets: how each field will be read (matched by meaning), confirmed before extracting.
 const [tablePlan,setTablePlan]=useState<TablePlan|null>(null),[columnPicks,setColumnPicks]=useState<Record<string,string>>({});
 const [busy,setBusy]=useState(false),[working,setWorking]=useState(''),[error,setError]=useState('');
 const reached=useRef<string|undefined>(undefined),sheet=useRef<HTMLDivElement>(null),camera=useRef<HTMLInputElement>(null),picker=useRef<HTMLInputElement>(null);
 const dataset=datasets.find(d=>d.id===datasetId);
 const position=Math.max(0,steps.indexOf(step));
 const cloud=sources.filter(s=>s!=='files'&&s!=='not_sure');
 const readyIds=uploaded.filter(item=>item.state==='ready').map(item=>item.id);

 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;sheet.current?.querySelector<HTMLElement>('h2')?.focus();
  const key=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!busy)onClose();};document.addEventListener('keydown',key);
  return()=>{document.removeEventListener('keydown',key);previous?.focus?.();};},[]);
 useEffect(()=>{sheet.current?.querySelector<HTMLElement>('h2')?.focus();setError('');},[step]);
 useEffect(()=>{setTablePlan(null);},[fields]);  // changed fields need a new match

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

 const run=async(label:string,fn:()=>Promise<void>)=>{setBusy(true);setWorking(label);setError('');try{await fn();}catch(e){setError(e instanceof Error?e.message:'That did not work. Try again.');}finally{setBusy(false);setWorking('');}};
 const go=(target:Step)=>setStep(target);
 const next=()=>go(steps[Math.min(position+1,steps.length-1)]);
 const back=()=>go(steps[Math.max(position-1,0)]);

 const chooseDataset=()=>run('Creating the workspace…',async()=>{
  if(datasetId==='new'){
   const name=newName.trim();if(!name)throw new Error('Give the workspace a name.');
   const created=await api('/datasets','POST',{name,description:newDescription.trim(),audience:newAudience});
   await api(`/datasets/${encodeURIComponent(created.id)}/migrate-settings`,'POST',{});  // Workspace Default models.
   setDatasetId(created.id);onChanged();
  }else if(!datasetId)throw new Error('Choose a workspace.');
  next();
 });
 const chooseFiles=(next:File[])=>{setFiles(next);if(!mergeTouched)setMerge(mergeByDefault(next));};
 const addFiles=(list:FileList|null)=>{if(!list)return;const picked=pickFiles([...files,...Array.from(list)]);chooseFiles(picked.files);setNote(picked.note);};
 const merging=merge&&canMerge(files);
 const upload=()=>run(merging?'Merging your files into one document, then uploading…':'Uploading…',async()=>{
  if(!files.length)throw new Error('Add at least one document or photo.');
  if(!uploadConsent)throw new Error('Tick the box to let Lapi read these documents.');
  const form=new FormData();files.forEach(file=>form.append('files',file,file.name));
  form.append('dataset_id',datasetId);form.append('allow_external','true');
  if(merging)form.append('merge_files','true');
  const result=await api('/documents/upload','POST',form);
  setUploaded((result.documents||[]).map((doc:Entity)=>({id:doc.id,name:doc.name||doc.filename||'Document',state:fileState(doc.status),error:''})));
  setFiles([]);setMergeTouched(false);onChanged();go('processing');
 });
 const ask=(text:string)=>run('Lapi is reading your documents to answer…',async()=>{
  const value=text.trim();if(!value)throw new Error('Type a question, or tap one of the suggestions.');
  if(!aiConsent)throw new Error('Tick the box to let Lapi use the AI model to answer.');
  setQuestion(value);setAnswer(null);
  const catalog=await api('/dataset-chat/catalog','GET',undefined,undefined,true);
  const known=(catalog.datasets||[]).find((d:Entity)=>d.id===datasetId)||dataset;
  const models=eligibleAgentModels(catalog.models||[],known,currentDevice());
  const model=models.find((m:Entity)=>m.id===known?.default_chat_model_id)?.id||models[0]?.id;
  if(!model)throw new Error(`This workspace has no chat model for ${currentDevice()==='phone'?'phones':'computers'} yet. Ask an administrator to turn one on in Settings › Enabled models.`);
  const reply=await api('/dataset-chat/messages','POST',{text:value,dataset_ids:[datasetId],...(readyIds.length?{document_ids:readyIds}:{}),model_id:model});
  setAnswer(reply.message||null);
 });
 const suggest=(request='')=>run(request?'Rewriting the fields…':'Reading your document and suggesting fields…',async()=>{
  const result=await api('/templates/suggest','POST',{dataset_id:datasetId,document_ids:readyIds.slice(0,5),allow_external:true,
   ...(request?{request,current:fields}:{})});
  setPromptName(result.name||'Extraction');setInstructions(result.instructions||'');setFields(result.fields||[]);setChange('');
 });
 const startExtract=()=>{if(!aiConsent){setError('Tick the box to let Lapi use the AI model.');return;}setPath('extract');go('prompt');if(!fields.length)void suggest();};
 const startAsk=()=>{if(!aiConsent){setError('Tick the box to let Lapi use the AI model.');return;}setPath('ask');go('ask');};
 const editField=(index:number,patch:Partial<Field>)=>setFields(current=>current.map((field,i)=>{
  if(i!==index)return field;
  const updated={...field,...patch};
  if(patch.label!==undefined)updated.key=fieldKey(patch.label,current.filter((_,j)=>j!==index).map(f=>f.key));
  return updated;}));
 const addField=()=>setFields(current=>[...current,{key:fieldKey('New field',current.map(f=>f.key)),label:'New field',type:'text',description:'What to pull out, exactly as written.'}]);
 const extract=(confirmed?:Record<string,{sheet:string;column:string}|null>)=>run('Saving the prompt…',async()=>{
  const problems=fieldProblems(fields);if(problems.length)throw new Error(problems[0]);
  const schema=fieldsToSchema(fields);
  const sheets=uploaded.filter(item=>item.state==='ready');
  if(!confirmed&&sheets.length&&sheets.every(item=>isSpreadsheet(item.name))){
   // Show how each field will be read from the columns first; the person confirms or changes it.
   setWorking('Matching your fields to the spreadsheet columns…');
   const plan:TablePlan=await api('/templates/table-plan','POST',{dataset_id:datasetId,document_ids:readyIds.slice(0,20),schema,allow_external:true});
   if(plan.applies&&plan.documents[0]){setTablePlan(plan);setColumnPicks(initialChoices(plan.documents[0],fields.map(f=>f.key)));return;}
  }
  const template=await api('/templates','POST',{name:(promptName.trim()||'Extraction').slice(0,200),schema,instructions,dataset_id:datasetId});
  go('extracting');setWorking('Pulling out your data…');
  const created=await api('/extractions','POST',{document_ids:readyIds.slice(0,20),template_id:template.id,dataset_id:datasetId,allow_external:true,...(confirmed?{column_mapping:confirmed}:{})});
  const id=created.id||created.extraction_id;const started=Date.now();
  let current:Entity=created;setExtraction(created);reached.current=created.status;
  while(!['ready','failed','cancelled'].includes(current.status)&&Date.now()-started<POLL_LIMIT_MS){
   await wait(POLL_MS);current=await api(`/extractions/${encodeURIComponent(id)}`,'GET',undefined,undefined,true);
   if(!['failed','cancelled'].includes(current.status))reached.current=current.status;setExtraction(current);
  }
  setExtraction(current);onChanged();
  if(current.status!=='ready')throw new Error(current.error||(['failed','cancelled'].includes(current.status)?'The extraction did not finish. Open Review to see it, or try again.':'This is taking longer than 10 minutes. It keeps running: check it later on the Review page.'));
 });

 const state=progress(uploaded.map(item=>item.state));
 const canShare=isAdmin||dataset?.my_access==='owner';
 const extractStopped=extraction?.status==='failed'||extraction?.status==='cancelled';
 const rows=extraction?.status==='ready'?resultRows(extraction.result,fields):[];
 const consentBox=(id:string,checked:boolean,set:(value:boolean)=>void,text:string)=><label className="quick-start-consent" htmlFor={id}>
  <input id={id} type="checkbox" checked={checked} onChange={e=>set(e.target.checked)} disabled={busy}/><span>{text}</span></label>;

 return <div className="quick-start-backdrop" onClick={event=>{if(event.target===event.currentTarget&&!busy)onClose();}}>
  <div ref={sheet} className={enlarged?'quick-start is-enlarged':'quick-start'} role="dialog" aria-modal="true" aria-labelledby="quick-start-title">
   <nav className="quick-start-rail" aria-label="Quick start steps">
    <p className="quick-start-rail-brand"><Sparkles size={18}/> Quick start</p>
    <ol>{steps.map((s,i)=><li key={s} className={i<position?'done':i===position?'on':''} aria-current={i===position?'step':undefined}>
     <span className="quick-start-rail-dot">{i<position?<Check size={14}/>:i+1}</span>{STEP_RAIL[s]}</li>)}</ol>
    <p className="quick-start-rail-note">Each step that sends data to an AI model asks first.</p>
   </nav>
   <div className="quick-start-main">
   <header className="quick-start-head">
    <div className="quick-start-bar-row">
     {position>0&&!['done','processing','extracting'].includes(step)?<button type="button" className="quick-start-icon" aria-label="Back" onClick={back} disabled={busy}><ArrowLeft size={20}/></button>:<span className="quick-start-icon-space"/>}
     <div className="quick-start-progress" aria-label={`Step ${position+1} of ${steps.length}`}>{steps.map((s,i)=><span key={s} className={i<position?'done':i===position?'on':''}/>)}</div>
     <span className="quick-start-icons">
      <button type="button" className="quick-start-icon quick-start-enlarge" aria-label={enlarged?'Make quick start smaller':'Enlarge quick start'} title={enlarged?'Smaller':'Enlarge'} aria-pressed={enlarged} onClick={toggleEnlarged}>{enlarged?<Minimize2 size={18}/>:<Maximize2 size={18}/>}</button>
      <button type="button" className="quick-start-icon" aria-label="Close quick start" onClick={onClose} disabled={busy}><X size={20}/></button>
     </span>
    </div>
    <p className="quick-start-eyebrow">Quick start · step {position+1} of {steps.length}</p>
    <h2 id="quick-start-title" tabIndex={-1}>{quickExtract&&step==='choose'?'Ready to pull out your data':STEP_TITLE[step]}</h2>
   </header>
   <div className="quick-start-body">

    {step==='dataset'&&<>
     <p className="quick-start-lead">{editor?'Documents always go into a workspace: a shared folder with its own models and people.':'Pick a workspace shared with you to ask about.'}</p>
     {!choices.length&&!canCreate?<p className="quick-start-empty">No workspaces are shared with you yet. Ask an administrator or a workspace owner to give you access.</p>:
     <div className="quick-start-options" role="radiogroup" aria-label="Workspaces">
      {choices.map(d=><label key={d.id} className={datasetId===d.id?'selected':''}><input type="radio" name="qs-dataset" checked={datasetId===d.id} onChange={()=>setDatasetId(d.id)}/>
       <span><strong>{d.name}</strong><small>{d.description||(d.my_access?`Your access: ${d.my_access}`:'')}</small></span></label>)}
      {canCreate&&<label className={datasetId==='new'?'selected':''}><input type="radio" name="qs-dataset" checked={datasetId==='new'} onChange={()=>setDatasetId('new')}/>
       <span><strong><Plus size={15}/> New workspace</strong><small>Uses the workspace's default models</small></span></label>}
     </div>}
     {datasetId==='new'&&<fieldset className="quick-start-new">
      {slots.length>1&&<label>Who is it for?<select aria-label="Who is it for" value={newAudience} onChange={e=>setNewAudience(e.target.value as 'personal'|'team')}>{slots.map(kind=><option key={kind} value={kind}>{kind==='personal'?'Just me':'My team'}</option>)}</select></label>}
      <legend>New workspace</legend>
      <label className="quick-start-field">Name<input value={newName} maxLength={200} onChange={e=>setNewName(e.target.value)} disabled={busy}/></label>
      <label className="quick-start-field">Description <small>(optional)</small><textarea rows={2} value={newDescription} maxLength={1000} placeholder="What goes in here, for example: supplier invoices for 2026" onChange={e=>setNewDescription(e.target.value)} disabled={busy}/></label>
     </fieldset>}
     {!editor&&choices.length>0&&consentBox('qs-consent-ask-viewer',aiConsent,setAiConsent,'Let Lapi send my questions and the matching document text to the AI model set up for this workspace.')}
    </>}

    {step==='documents'&&<>
     <p className="quick-start-lead">Into <strong>{dataset?.name||'your workspace'}</strong>. Photos of paper documents work too: Lapi reads them.</p>
     <div className="quick-start-pick">
      <button type="button" onClick={()=>camera.current?.click()} disabled={busy}><Camera size={26}/><span>Take a photo</span></button>
      <button type="button" onClick={()=>picker.current?.click()} disabled={busy}><FileUp size={26}/><span>Choose files</span></button>
      <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={e=>{addFiles(e.target.files);e.target.value='';}}/>
      <input ref={picker} type="file" accept={ACCEPT} multiple hidden onChange={e=>{addFiles(e.target.files);e.target.value='';}}/>
     </div>
     {note&&<p className="quick-start-note">{note}</p>}
     {files.length>0&&<ul className="quick-start-files">{files.map((file,i)=><li key={file.name+i}><span>{file.name}</span><small>{Math.max(1,Math.round(file.size/1024))} KB</small>
      <button type="button" aria-label={`Remove ${file.name}`} onClick={()=>chooseFiles(files.filter((_,j)=>j!==i))} disabled={busy}><X size={16}/></button></li>)}</ul>}
     {canMerge(files)&&<fieldset className="quick-start-merge">
      <legend>{files.length} files: one document or separate?</legend>
      <div className="quick-start-options">
       <label className={merge?'selected':''}><input type="radio" name="qs-merge" checked={merge} onChange={()=>{setMerge(true);setMergeTouched(true);}} disabled={busy}/>
        <span><strong>Merge into one document</strong><small>Pages or photos of one paper document. Lapi stitches them in this order, then reads them as one.</small></span></label>
       <label className={!merge?'selected':''}><input type="radio" name="qs-merge" checked={!merge} onChange={()=>{setMerge(false);setMergeTouched(true);}} disabled={busy}/>
        <span><strong>Keep as separate documents</strong><small>Different documents. Each is read and extracted on its own.</small></span></label>
      </div>
      {merge&&<p className="quick-start-note">It is saved as "merged-{files[0].name.replace(/\.[^.]+$/,'')}-{files.length}-files", and keeps each original file and page.</p>}
     </fieldset>}
     {consentBox('qs-consent-upload',uploadConsent,setUploadConsent,'Let Lapi read and index these documents with the AI services set up for this workspace.')}
     {cloud.length>0&&<p className="quick-start-alt">Your files are in cloud storage? <a href={'#'+encodeURIComponent('Add knowledge')+'/'+encodeURIComponent(cloud[0])} onClick={onClose}>Connect it with the step-by-step guide</a> instead.</p>}
    </>}

    {step==='processing'&&<>
     <p className="quick-start-lead">{state.finished?(state.ready?'Done. Your documents are ready.':'Lapi could not read these files.'):'This usually takes under a minute. You can continue as soon as one is ready.'}</p>
     <div className="quick-start-meter" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={state.percent}><span style={{width:`${Math.max(state.percent,6)}%`}}/></div>
     <ul className="quick-start-files" aria-live="polite">{uploaded.map(item=><li key={item.id} data-state={item.state}>
      {item.state==='working'?<Loader2 size={17} className="animate-spin"/>:item.state==='ready'?<Check size={17}/>:<CircleAlert size={17}/>}
      <span>{item.name}</span><small>{item.state==='failed'&&item.error?item.error:FILE_STATE_TEXT[item.state]}</small></li>)}</ul>
     {state.finished&&!state.ready&&<button type="button" className="quick-start-secondary" onClick={()=>{setUploaded([]);go('documents');}}>Try other files</button>}
    </>}

    {step==='choose'&&<>
     <p className="quick-start-lead">{quickExtract?'This uses':'Both use'} the AI models set up for <strong>{dataset?.name||'this workspace'}</strong>.</p>
     {consentBox('qs-consent-ai',aiConsent,setAiConsent,'Let Lapi send my question or the document text to the AI model set up for this workspace.')}
     {quickExtract?<div className="quick-start-paths"><button type="button" onClick={startExtract} disabled={busy}><Table2 size={24}/><span><strong>Continue</strong><small>Lapi suggests the fields from your document; you check them, then it extracts.</small></span></button></div>:<div className="quick-start-paths">
      <button type="button" onClick={startAsk} disabled={busy}><MessageSquare size={24}/><span><strong>Ask a question</strong><small>Get an answer with the sources it came from.</small></span></button>
      <button type="button" onClick={startExtract} disabled={busy}><Table2 size={24}/><span><strong>Pull out data</strong><small>Lapi suggests the fields from your document; you check them, then it extracts.</small></span></button>
     </div>}
    </>}

    {step==='ask'&&<>
     <p className="quick-start-lead">Ask anything about <strong>{dataset?.name||'this workspace'}</strong>. Every answer shows where it came from.</p>
     {!editor&&!aiConsent&&consentBox('qs-consent-ask',aiConsent,setAiConsent,'Let Lapi send my questions and the matching document text to the AI model set up for this workspace.')}
     {!answer&&<div className="quick-start-chips">{SUGGESTED_QUESTIONS.map(q=><button key={q} type="button" onClick={()=>void ask(q)} disabled={busy}>{q}</button>)}</div>}
     <form className="quick-start-ask" onSubmit={e=>{e.preventDefault();void ask(question);}}>
      <textarea aria-label="Your question" rows={2} value={question} placeholder="Type your question…" maxLength={2000} onChange={e=>setQuestion(e.target.value)} disabled={busy}/>
      <button type="submit" className="quick-start-send" disabled={busy||!question.trim()} aria-label="Ask">{busy?<Loader2 size={18} className="animate-spin"/>:<MessageSquare size={18}/>}</button>
     </form>
     {answer&&<article className="quick-start-answer" aria-live="polite">
      <p>{answer.text}</p>
      {(answer.citations||[]).length>0&&<><h3>Sources</h3><ol>{answer.citations.map((c:Entity)=><li key={c.index}>{sourceName(c)}</li>)}</ol></>}
     </article>}
    </>}

    {step==='prompt'&&<>
     <p className="quick-start-lead">Lapi read your document and suggests these fields. Change anything, or ask the AI to rewrite them.</p>
     {fields.length>0&&<>
      <label className="quick-start-field">Prompt name<input value={promptName} maxLength={200} onChange={e=>setPromptName(e.target.value)} disabled={busy}/></label>
      <ul className="quick-start-fields">{fields.map((field,i)=><li key={i}>
       <div className="quick-start-field-row">
        <input aria-label={`Field ${i+1} name`} value={field.label} maxLength={60} onChange={e=>editField(i,{label:e.target.value})} disabled={busy}/>
        <select aria-label={`Field ${i+1} type`} value={field.type} onChange={e=>editField(i,{type:e.target.value as FieldType})} disabled={busy}>{FIELD_TYPES.map(t=><option key={t.id} value={t.id}>{t.label}</option>)}</select>
        <button type="button" aria-label={`Remove ${field.label}`} onClick={()=>setFields(fields.filter((_,j)=>j!==i))} disabled={busy}><Trash2 size={16}/></button>
       </div>
       <textarea aria-label={`What to pull out for ${field.label}`} rows={2} value={field.description} maxLength={240} onChange={e=>editField(i,{description:e.target.value})} disabled={busy}/>
      </li>)}</ul>
      <button type="button" className="quick-start-secondary" onClick={addField} disabled={busy||fields.length>=15}><Plus size={16}/> Add a field</button>
      <form className="quick-start-rewrite" onSubmit={e=>{e.preventDefault();if(change.trim())void suggest(change.trim());}}>
       <label htmlFor="qs-rewrite">Ask the AI to change them</label>
       <div><input id="qs-rewrite" value={change} maxLength={1000} placeholder="For example: add the due date, remove the address" onChange={e=>setChange(e.target.value)} disabled={busy}/>
        <button type="submit" className="quick-start-secondary" disabled={busy||!change.trim()}><Wand2 size={16}/> Rewrite</button></div>
      </form>
     </>}
     {tablePlan?.documents[0]&&(()=>{const doc=tablePlan.documents[0];return <section className="quick-start-mapping" aria-label="How Lapi will read your spreadsheet">
      <h3>How Lapi will read {doc.name}</h3>
      <p className="quick-start-note">One record per row of sheet “{doc.sheet}” ({doc.rows.toLocaleString()} rows). Values come straight from the columns; check each match and change any that are wrong.</p>
      <ul>{fields.map(field=>{const pick=columnPicks[field.key]??'',badge=howBadge(doc,field.key,pick);return <li key={field.key} data-how={badge.kind}>
       <span className="quick-start-mapping-head"><label htmlFor={`qs-col-${field.key}`}>{field.label}</label><span className="quick-start-mapping-badge">{badge.label}</span></span>
       <select id={`qs-col-${field.key}`} value={pick} onChange={e=>setColumnPicks(current=>({...current,[field.key]:e.target.value}))} disabled={busy}>
        <option value="">Leave empty</option>
        <option value="row">Read from each row (AI)</option>
        {doc.columns.map(c=><option key={columnValue(c.sheet,c.column)} value={columnValue(c.sheet,c.column)}>{c.sheet===doc.sheet?c.column:`${c.sheet} › ${c.column}`}</option>)}
       </select>
       <small>{howChosen(doc,field.key,pick)}</small></li>;})}</ul>
     </section>;})()}
     {!fields.length&&!busy&&<div className="quick-start-foot-actions quick-start-start-fields">
      <button type="button" className="quick-start-secondary" onClick={()=>void suggest()}><Wand2 size={16}/> Suggest fields</button>
      <button type="button" className="quick-start-secondary" onClick={()=>{setError('');setPromptName(name=>name||'Extraction');addField();}}><Plus size={16}/> Add fields yourself</button>
     </div>}
    </>}

    {step==='extracting'&&<>
     {!rows.length&&!error&&<p className="quick-start-lead">Lapi is reading your documents with the prompt. This usually takes under a minute.</p>}
     {!rows.length&&error&&<p className="quick-start-error" role="alert"><CircleAlert size={16}/> {extractStopped?`The extraction stopped: ${error}`:error}</p>}
     {!rows.length&&<ol className="quick-start-stages" aria-live="polite">{extractionStages(extraction?.status||'saved',Math.max(1,Math.min(readyIds.length,20)),reached.current,extraction?.error||error).map(stage=><li key={stage.label} data-state={stage.state}>
      <span className="quick-start-stage-dot">{stage.state==='done'?<Check size={14}/>:stage.state==='on'?<Loader2 size={14} className="animate-spin"/>:stage.state==='failed'?<X size={14}/>:null}</span>{stage.label}</li>)}</ol>}
     {error&&!busy&&<button type="button" className="quick-start-secondary" onClick={()=>{setExtraction(null);go('prompt');}}>Back to the fields</button>}
     {rows.length>0&&<article className="quick-start-answer" aria-live="polite"><h3><Check size={16}/> {promptName||'Extracted values'}</h3>
      <dl className="quick-start-values">{rows.map(row=><div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl>
      <p className="quick-start-note">{recordCount(extraction?.result)>1?`This is record 1 of ${recordCount(extraction?.result).toLocaleString()} (one per row or file). See all of them on the Review page, correct anything, then approve.`:'Check each value against its source on the Review page, correct anything, then approve.'}</p></article>}
    </>}

    {step==='done'&&<>
     <div className="quick-start-celebrate"><Sparkles size={34}/></div>
     <p className="quick-start-lead">{path==='extract'?'You added documents, let Lapi write an extraction prompt and pulled out your first data.':'You added documents and got your first answer with sources.'} Everything is in <strong>{dataset?.name||'your workspace'}</strong>.</p>
     <div className="quick-start-next">
      {path==='extract'?<button type="button" onClick={()=>{if(extraction)openReviewPage(extraction.extraction_id||extraction.id);else onNavigate('Extract');onClose();}}><FileSearch size={18}/><span>Check the results in Review</span></button>
       :<button type="button" onClick={()=>{onClose();onNavigate('Home');}}><MessageSquare size={18}/><span>Keep asking on the Dashboard</span></button>}
      {dataset&&<button type="button" onClick={()=>{onSelectDataset?.(dataset.id);onClose();onNavigate('Lapi agent V2');}}><Sparkles size={18}/><span>Continue in Lapi Agent</span></button>}
      {editor&&<button type="button" onClick={()=>{setAnswer(null);setQuestion('');setUploaded([]);setExtraction(null);go('documents');}}><FileUp size={18}/><span>Add more documents</span></button>}
      {canShare&&dataset&&<button type="button" onClick={()=>{onClose();openDatasetEditor(dataset.id,'members');}}><Users size={18}/><span>Share with your team</span></button>}
     </div>
    </>}

    {busy&&working&&<p className="quick-start-working" role="status"><Loader2 size={16} className="animate-spin"/> {working}</p>}
    {error&&step!=='extracting'&&<p className="quick-start-error" role="alert"><CircleAlert size={16}/> {error}</p>}
   </div>

   <footer className="quick-start-foot">
    {step==='dataset'&&<button type="button" className="quick-start-primary" disabled={busy||(!choices.length&&!canCreate)||(!editor&&!aiConsent)} onClick={()=>void chooseDataset()}>{busy?'Creating…':'Continue'}</button>}
    {step==='documents'&&<button type="button" className="quick-start-primary" disabled={busy||!files.length||!uploadConsent} onClick={()=>void upload()}>{busy?(merging?'Merging and uploading…':'Uploading…'):merging?`Merge ${files.length} into one and read`:`Upload ${files.length||''} and read`.replace('  ',' ')}</button>}
    {step==='processing'&&<button type="button" className="quick-start-primary" disabled={!state.ready} onClick={next}>{state.ready?'Continue':'Reading…'}</button>}
    {step==='choose'&&<p className="quick-start-foot-note">{aiConsent?(quickExtract?'Tap Continue above.':'Choose one above.'):'Tick the box above to continue.'}</p>}
    {step==='ask'&&<button type="button" className="quick-start-primary" disabled={!answer||busy} onClick={next}>{answer?'Finish':'Ask to continue'}</button>}
    {step==='prompt'&&<button type="button" className="quick-start-primary" disabled={busy||!fields.length} onClick={()=>void extract(tablePlan?columnMapping(columnPicks):undefined)}>{tablePlan?'Extract with these columns':'Save prompt and extract'}</button>}
    {step==='extracting'&&(rows.length&&extraction?<div className="quick-start-foot-actions">
     <button type="button" className="quick-start-secondary" onClick={next}>Finish</button>
     <button type="button" className="quick-start-primary" onClick={()=>{openReviewPage(extraction.extraction_id||extraction.id);onClose();}}><FileSearch size={18}/> Review</button>
    </div>:<button type="button" className="quick-start-primary" disabled>{error?(extractStopped?'Stopped':'Still running'):'Extracting…'}</button>)}
    {step==='done'&&<button type="button" className="quick-start-primary" onClick={onClose}>Close</button>}
   </footer>
   </div>
  </div>
 </div>;
}
