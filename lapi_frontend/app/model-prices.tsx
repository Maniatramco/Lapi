"use client";
import {useEffect,useState} from 'react';
import {X} from 'lucide-react';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;
const FIELDS:[string,string,boolean][]=[['input_price','Input',true],['cached_input_price','Cached input read',false],['cache_write_price','Cached input write',false],['output_price','Output',true],['reasoning_price','Reasoning (optional)',false]];
const today=()=>new Date().toISOString().slice(0,10);
const shown=(value:unknown)=>value===null||value===undefined||value===''?'—':String(value);

/** Dated list prices per 1M tokens for one registered model. New versions never reprice earlier calls. */
export function ModelPrices({model,api,onClose}:{model:Entity;api:Api;onClose:()=>void}){
 const [data,setData]=useState<Entity|null>(null),[error,setError]=useState(''),[saving,setSaving]=useState(false);
 const [form,setForm]=useState<Record<string,string>>({currency:'USD',input_price:'',cached_input_price:'',cache_write_price:'',output_price:'',reasoning_price:'',effective_at:today()});
 const load=()=>api(`/model-registrations/${encodeURIComponent(model.id)}/prices`).then(value=>{setData(value);setError('');}).catch(e=>setError(e instanceof Error?e.message:'Prices could not load.'));
 useEffect(()=>{void load();},[model.id]);
 const submit=async()=>{
  setSaving(true);setError('');
  try{
   const effective=form.effective_at===today()?null:form.effective_at;
   await api(`/model-registrations/${encodeURIComponent(model.id)}/prices`,'POST',{currency:form.currency.trim().toUpperCase(),input_price:form.input_price.trim(),output_price:form.output_price.trim(),
    cached_input_price:form.cached_input_price.trim()||null,cache_write_price:form.cache_write_price.trim()||null,reasoning_price:form.reasoning_price.trim()||null,effective_at:effective});
   setForm(f=>({...f,input_price:'',cached_input_price:'',cache_write_price:'',output_price:'',reasoning_price:''}));await load();
  }catch(e){setError(e instanceof Error?e.message:'The price could not be saved.');}finally{setSaving(false);}
 };
 return <section className="panel registration-prices" aria-labelledby="model-prices-title">
  <div className="panel-head"><h2 id="model-prices-title">Prices · {model.name}</h2><button type="button" className="btn icon" title="Close prices" aria-label="Close prices" onClick={onClose}><X size={16}/></button></div>
  <p className="muted small">List prices per 1M tokens, used for approximate cost only. Leave cached prices empty to use the input price; reasoning uses the output price unless set. Each call keeps the price version in force when it was made.</p>
  {error&&<p role="alert" className="agent-v2-error">{error}</p>}
  <form className="registration-fields" onSubmit={e=>{e.preventDefault();void submit();}}>
   <div className="field"><label htmlFor="price-currency">Currency</label><input id="price-currency" value={form.currency} maxLength={3} pattern="[A-Za-z]{3}" required onChange={e=>setForm({...form,currency:e.target.value})}/></div>
   {FIELDS.map(([key,label,required])=><div className="field" key={key}><label htmlFor={`price-${key}`}>{label}</label><input id={`price-${key}`} inputMode="decimal" pattern="[0-9]*[.]?[0-9]*" required={required} value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})} placeholder={required?'e.g. 2.50':'Optional'}/></div>)}
   <div className="field"><label htmlFor="price-effective">Effective from (UTC)</label><input id="price-effective" type="date" required value={form.effective_at} onChange={e=>setForm({...form,effective_at:e.target.value})}/></div>
   <div className="field"><button className="btn primary" type="submit" disabled={saving}>{saving?'Saving…':'Add price version'}</button></div>
  </form>
  <div className="registration-table" role="region" aria-label="Price versions" tabIndex={0}><table aria-label="Price versions">
   <thead><tr><th scope="col">Effective</th><th scope="col">Currency</th>{FIELDS.map(([key,label])=><th scope="col" key={key}>{label.replace(' (optional)','')}</th>)}</tr></thead>
   <tbody>{(data?.versions||[]).map((v:Entity)=><tr key={v.id}><th scope="row">{new Date(v.effective_at*1000).toISOString().slice(0,10)}{data?.current?.id===v.id&&<span className="pill green">Current</span>}</th><td>{v.currency}</td>{FIELDS.map(([key])=><td key={key}>{shown(v[key])}</td>)}</tr>)}
    {data&&!data.versions?.length&&<tr><td colSpan={7} className="registration-table-empty">Price not set. Costs show “Price not set” until a price is added.</td></tr>}</tbody>
  </table></div>
 </section>;
}
