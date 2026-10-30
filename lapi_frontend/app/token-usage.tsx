"use client";
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {Download,RefreshCw,X} from 'lucide-react';
import './token-usage.css';
import {SummaryTiles} from './summary-tiles';
import {STAGE_LABELS,costText} from './agent-token-usage';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:any,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
type Filters={start:string;end:string;dataset_id:string;model_id:string;owner_id:string;stage:string};
/** Categorical slots in fixed order (validated: CVD and normal-vision separation pass; tables give label relief). */
const SERIES=['#2563eb','#eb6834','#1baf7a','#eda100','#e87ba4','#008300','#6250d6'];
const OTHER='#94a3b8';
const day=(offset=0)=>{const d=new Date();d.setUTCDate(d.getUTCDate()+offset);return d.toISOString().slice(0,10);};
const tokens=(value:unknown)=>typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('en-US'):'—';
const percent=(part:number,whole:number)=>whole?`${Math.round(part/whole*100)}%`:'—';
const compact=(value:number)=>value>=1e9?`${(value/1e9).toFixed(1)}B`:value>=1e6?`${(value/1e6).toFixed(1)}M`:value>=1e3?`${(value/1e3).toFixed(1)}k`:String(value);
function costCell(cost:Entity|undefined){
 const text=costText(cost);
 if(text)return text+(cost?.excluded_calls?` (${cost.excluded_calls} excluded)`:'');
 return cost?.status==='not_reported'?'Not reported':cost?.status==='no_model_calls'?'—':'Price not set';
}

export function TokenUsageAdmin({api}:{api:Api}){
 const [filters,setFilters]=useState<Filters>({start:day(-29),end:day(),dataset_id:'',model_id:'',owner_id:'',stage:''});
 const [data,setData]=useState<Entity|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const [open,setOpen]=useState(''),[hover,setHover]=useState<Entity|null>(null);
 const sequence=useRef(0);
 const query=useMemo(()=>new URLSearchParams(Object.entries(filters).filter(([,v])=>v)).toString(),[filters]);
 const load=useCallback(async()=>{
  const request=++sequence.current;setLoading(true);
  try{const value=await api(`/admin/token-usage?${query}&group_by=dataset`);if(request===sequence.current){setData(value);setError('');}}
  catch(e){if(request===sequence.current)setError(e instanceof Error?e.message:'Token usage could not load.');}
  finally{if(request===sequence.current)setLoading(false);}
 },[api,query]);
 useEffect(()=>{const timer=setTimeout(()=>void load(),200);return()=>clearTimeout(timer);},[load]);
 const set=(key:keyof Filters,value:string)=>{setOpen('');setFilters(current=>({...current,[key]:value}));};
 const totals=data?.totals||{};
 const byModel:Entity[]=data?.by_model||[];
 const colors=useMemo(()=>{const map:Record<string,string>={};byModel.slice(0,SERIES.length).forEach((m,i)=>{map[m.key]=SERIES[i];});return map;},[byModel]);
 const color=(key:string)=>colors[key]||OTHER;
 const label=(key:string)=>byModel.find(m=>m.key===key)?.label||key;
 const days:Entity[]=data?.by_day||[];
 const peak=Math.max(1,...days.map(d=>d.total_tokens||0));
 const narrowed=filters.start===filters.end&&!!filters.start;
 const options=data?.options||{datasets:[],models:[],users:[],stages:[]};
 return <div className="token-usage">
  <section className="panel token-usage-filters" aria-label="Token usage filters">
   <label>From<input type="date" value={filters.start} max={filters.end||undefined} onChange={e=>set('start',e.target.value)}/></label>
   <label>To<input type="date" value={filters.end} min={filters.start||undefined} onChange={e=>set('end',e.target.value)}/></label>
   <label>Workspace<select value={filters.dataset_id} onChange={e=>set('dataset_id',e.target.value)}><option value="">All workspaces</option>{options.datasets.map((o:Entity)=><option key={o.id} value={o.id}>{o.name}</option>)}<option value="none">No workspace</option></select></label>
   <label>Model<select value={filters.model_id} onChange={e=>set('model_id',e.target.value)}><option value="">All models</option>{options.models.map((o:Entity)=><option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
   <label>User<select value={filters.owner_id} onChange={e=>set('owner_id',e.target.value)}><option value="">All users</option>{options.users.map((o:Entity)=><option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
   <label>Stage<select value={filters.stage} onChange={e=>set('stage',e.target.value)}><option value="">All stages</option>{(options.stages||[]).map((s:string)=><option key={s} value={s}>{STAGE_LABELS[s]||s}</option>)}</select></label>
   <div className="token-usage-actions">
    <button type="button" className="btn icon" title="Refresh token usage" aria-label="Refresh token usage" onClick={()=>void load()} disabled={loading}><RefreshCw size={15} className={loading?'animate-spin':''}/></button>
    <a className="btn" href={`/api/admin/token-usage/export?${query}`} download><Download size={15} aria-hidden="true"/>Export CSV</a>
   </div>
  </section>
  {error&&<div className="panel" role="alert">{error}</div>}
  {data&&<>
   <SummaryTiles label="Token usage summary" tiles={[
    {label:'Total tokens',value:tokens(totals.total_tokens),detail:`${tokens(totals.input_tokens)} input · ${tokens(totals.output_tokens)} output`,tone:''},
    {label:'Approximate cost',value:costText(totals.cost)||(totals.model_calls?'Price not set':'—'),detail:totals.cost?.excluded_calls?`${totals.cost.not_reported_calls} not reported · ${totals.cost.price_not_set_calls} without a price, excluded`:'From admin-entered list prices',tone:'info'},
    {label:'Model calls',value:tokens(totals.model_calls),detail:totals.not_reported_calls?`${totals.not_reported_calls} not reported by the provider`:'All reported by the provider',tone:totals.not_reported_calls?'warn':'ok'},
    {label:'Cache hit rate',value:typeof totals.cache_hit_rate==='number'?`${Math.round(totals.cache_hit_rate*100)}%`:'—',detail:`${tokens(totals.cached_input_tokens)} cached of ${tokens(totals.input_tokens)} input`,tone:''},
   ]}/>
   {data.truncated&&<p className="small muted" role="status">Showing the first 200,000 calls. Narrow the date range for complete totals.</p>}
   <section className="panel token-usage-chart" aria-labelledby="token-chart-title">
    <div className="token-usage-head"><h2 id="token-chart-title">Tokens per day by model</h2>{(narrowed||filters.model_id)&&<button type="button" className="btn" onClick={()=>setFilters(f=>({...f,start:narrowed?day(-29):f.start,end:narrowed?day():f.end,model_id:''}))}><X size={14}/>Clear chart selection</button>}</div>
    {days.length?<>
     <div className="token-usage-plot" onMouseLeave={()=>setHover(null)}>
      <div className="token-usage-axis" aria-hidden="true"><span>{compact(peak)}</span><span>{compact(Math.round(peak/2))}</span><span>0</span></div>
      <div className="token-usage-bars" role="list" aria-label="Daily token totals; select a day to filter">
       {days.map(d=>{
        const entries=Object.entries(d.models as Record<string,number>).sort((a,b)=>byModel.findIndex(m=>m.key===a[0])-byModel.findIndex(m=>m.key===b[0]));
        return <button type="button" role="listitem" key={d.day} className="token-usage-day" aria-label={`${d.day}: ${tokens(d.total_tokens)} tokens. Filter to this day`} onMouseEnter={()=>setHover(d)} onFocus={()=>setHover(d)} onBlur={()=>setHover(null)} onClick={()=>setFilters(f=>({...f,start:d.day,end:d.day}))}>
         <span className="token-usage-stack" style={{height:`${Math.max(2,d.total_tokens/peak*100)}%`}}>{entries.map(([key,value])=><span key={key} style={{flexGrow:value,background:color(key)}}/>)}</span>
        </button>;})}
      </div>
      {hover&&<div className="token-usage-tooltip" role="status"><strong>{hover.day}</strong> · {tokens(hover.total_tokens)} tokens{Object.entries(hover.models as Record<string,number>).map(([key,value])=><span key={key}><i style={{background:color(key)}}/>{label(key)}: {tokens(value)}</span>)}</div>}
     </div>
     <div className="token-usage-days" aria-hidden="true"><span>{days[0].day}</span>{days.length>1&&<span>{days[days.length-1].day}</span>}</div>
     <ul className="token-usage-legend" aria-label="Models">{byModel.slice(0,SERIES.length).map(m=><li key={m.key}><button type="button" onClick={()=>set('model_id',m.key)} aria-label={`Filter to ${m.label}`}><i style={{background:color(m.key)}}/>{m.label}</button></li>)}{byModel.length>SERIES.length&&<li><i style={{background:OTHER}}/>Other models</li>}</ul>
    </>:<p className="muted">No model calls match these filters.</p>}
   </section>
   <section className="panel" aria-labelledby="token-dataset-title">
    <h2 id="token-dataset-title">By workspace</h2>
    <div className="token-usage-table" role="region" aria-label="Token usage by workspace" tabIndex={0}><table>
     <thead><tr><th scope="col">Workspace</th><th scope="col">Tokens</th><th scope="col">Cached share</th><th scope="col">Approx. cost</th><th scope="col">Calls</th><th scope="col">Top model</th></tr></thead>
     <tbody>{(data.by_dataset||[]).map((row:Entity)=><DatasetRow key={row.key} row={row} open={open===row.key} onToggle={()=>setOpen(open===row.key?'':row.key)}/>)}
      {!(data.by_dataset||[]).length&&<tr><td colSpan={6} className="muted">No usage in this range.</td></tr>}</tbody>
    </table></div>
   </section>
   <section className="panel" aria-labelledby="token-model-title">
    <h2 id="token-model-title">By model</h2>
    <div className="token-usage-table" role="region" aria-label="Token usage by model" tabIndex={0}><table>
     <thead><tr><th scope="col">Model</th><th scope="col">Input</th><th scope="col">Cached</th><th scope="col">Output</th><th scope="col">Reasoning</th><th scope="col">Approx. cost</th><th scope="col">Avg latency</th></tr></thead>
     <tbody>{byModel.map(row=><tr key={row.key}><th scope="row"><span className="token-usage-swatch" style={{background:color(row.key)}} aria-hidden="true"/>{row.label}</th><td>{tokens(row.input_tokens)}</td><td>{tokens(row.cached_input_tokens)}</td><td>{tokens(row.output_tokens)}</td><td>{tokens(row.reasoning_tokens)}</td><td>{costCell(row.cost)}</td><td>{typeof row.avg_latency_ms==='number'?`${(row.avg_latency_ms/1000).toFixed(2)} s`:'—'}</td></tr>)}
      {!byModel.length&&<tr><td colSpan={7} className="muted">No usage in this range.</td></tr>}</tbody>
    </table></div>
    <p className="small muted">Tokens are as reported by each provider; calls the provider did not report are counted but not priced. Costs are approximate, from the list prices entered in Model Registration, and are shown per currency.</p>
   </section>
  </>}
  {!data&&loading&&<div className="panel muted" role="status">Loading token usage…</div>}
 </div>;
}

function DatasetRow({row,open,onToggle}:{row:Entity;open:boolean;onToggle:()=>void}){
 return <>
  <tr className={open?'token-usage-open':''}>
   <th scope="row"><button type="button" className="text-button" aria-expanded={open} onClick={onToggle}>{row.label}</button></th>
   <td>{tokens(row.total_tokens)}</td><td>{percent(row.cached_input_tokens||0,row.input_tokens||0)}</td><td>{costCell(row.cost)}</td><td>{tokens(row.model_calls)}</td><td>{row.top_model_label||'—'}</td>
  </tr>
  {open&&<tr className="token-usage-detail"><td colSpan={6}>
   <div><strong>Conversations</strong>{row.conversations?.length?<ul>{row.conversations.map((c:Entity)=><li key={c.id}><code>{c.id.slice(0,8)}</code> · {tokens(c.total_tokens)} tokens · {c.model_calls} calls</li>)}</ul>:<p className="muted">None</p>}</div>
   <div><strong>Jobs</strong>{row.jobs?.length?<ul>{row.jobs.map((j:Entity)=><li key={j.id}><code>{j.id.slice(0,8)}</code> · {tokens(j.total_tokens)} tokens · {j.model_calls} calls</li>)}</ul>:<p className="muted">None</p>}</div>
  </td></tr>}
 </>;
}
