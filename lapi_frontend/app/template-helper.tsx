"use client";
import {useState} from 'react';
import {Plus,Wand2,X} from 'lucide-react';
import {fieldsToSchema,type Field} from './quick-start-flow';
import {applyChange,fieldList,suggestFields} from './setup-chat-script';
import './template-helper.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;

/** In the Agent's "A few details" card when no prompt template is chosen: say what to pull out and Lapi
 * fills in the fields (from your words at once, or from the document once it is read), change them in
 * words, and save them as the template for this request. */
export function TemplateHelper({api,datasetId,documentIds,collectionType='',onCreated}:{api:Api;datasetId:string;documentIds:string[];collectionType?:string;onCreated:(template:Entity)=>void}){
 const [words,setWords]=useState(''),[change,setChange]=useState(''),[name,setName]=useState(''),[fields,setFields]=useState<Field[]>([]);
 const [busy,setBusy]=useState(''),[error,setError]=useState('');
 const run=async(label:string,work:()=>Promise<void>)=>{setBusy(label);setError('');try{await work();}catch(e){setError(e instanceof Error?e.message:'That did not work. Try again.');}finally{setBusy('');}};
 const fromWords=()=>{const made=suggestFields(words,collectionType);if(!made.fields.length){setError('Say what you want, for example: invoice number, vendor and total.');return;}setError('');setName(made.name);setFields(made.fields);};
 const fromDocument=()=>run('Reading the document…',async()=>{
  const made=await api('/templates/suggest','POST',{dataset_id:datasetId,document_ids:documentIds.slice(0,5),allow_external:true,...(words.trim()?{request:words.trim()}:{})});
  setName(made.name||'Extraction');setFields(made.fields||[]);
 });
 const save=()=>run('Saving…',async()=>{
  const template=await api('/templates','POST',{name:(name||words||'Extraction').slice(0,200),schema:fieldsToSchema(fields),instructions:'',dataset_id:datasetId});
  onCreated(template);
 });
 return <div className="template-helper" aria-label="Make a prompt template">
  <strong>No prompt template yet? Tell me what to pull out and I'll fill in the fields.</strong>
  <form className="template-helper-row" onSubmit={e=>{e.preventDefault();fromWords();}}>
   <input aria-label="What to pull out" value={words} maxLength={400} placeholder="For example: invoice totals and due dates" disabled={Boolean(busy)} onChange={e=>setWords(e.target.value)}/>
   <button type="submit" className="btn" disabled={Boolean(busy)||!words.trim()}><Wand2 size={16}/> Suggest</button>
   {documentIds.length>0&&<button type="button" className="btn" disabled={Boolean(busy)} onClick={()=>void fromDocument()} title="Read the document and propose fields">From the document</button>}
  </form>
  {fields.length>0&&<>
   <div className="quick-start-field-chips" role="group" aria-label="Fields">{fields.map((field,i)=><span key={field.key+i} className="quick-start-chip"><button type="button" disabled>{field.label}</button><button type="button" aria-label={`Remove ${field.label}`} disabled={Boolean(busy)} onClick={()=>setFields(fields.filter((_,j)=>j!==i))}><X size={14}/></button></span>)}</div>
   <form className="template-helper-row" onSubmit={e=>{e.preventDefault();if(change.trim()){const next=applyChange(fields,change.trim());setFields(next);setChange('');}}}>
    <input aria-label="Change the fields" value={change} maxLength={400} placeholder="Change them in words: add due date, remove currency" disabled={Boolean(busy)} onChange={e=>setChange(e.target.value)}/>
    <button type="submit" className="btn" disabled={Boolean(busy)||!change.trim()}><Plus size={16}/> Apply</button>
   </form>
   <button type="button" className="btn primary" disabled={Boolean(busy)} onClick={()=>void save()}>{busy==='Saving…'?'Saving…':`Use these ${fields.length} fields`}</button>
   <p className="small muted">{fieldList(fields)}</p>
  </>}
  {busy&&busy!=='Saving…'&&<p className="small muted" role="status">{busy}</p>}
  {error&&<p className="small template-helper-error" role="alert">{error}</p>}
 </div>;
}
