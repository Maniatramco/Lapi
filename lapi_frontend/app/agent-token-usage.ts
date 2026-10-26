type Cost={status?:string;amount?:string|null;currency?:string|null};
type Step={stage?:string;model_id?:string|null;provider_model?:string|null;embedding?:boolean;input_tokens?:unknown;cached_input_tokens?:unknown;cache_write_tokens?:unknown;output_tokens?:unknown;reasoning_tokens?:unknown;latency_ms?:unknown;cost?:Cost};
type CostSummary={status?:string;totals?:{currency:string;amount:string}[];price_not_set_calls?:number;not_reported_calls?:number};
type Usage={input_tokens?:unknown;output_tokens?:unknown;cached_input_tokens?:unknown;cache_write_tokens?:unknown;reasoning_tokens?:unknown;complete?:boolean;source?:string;model_calls?:number;reported_calls?:number;steps?:Step[];cost?:CostSummary};
export type TokenStepRow={stage:string;model:string;input:string;cached:string;output:string;reasoning:string;latency:string;cost:string};

export const STAGE_LABELS:Record<string,string>={prefetch_embedding:'Prefetch embedding',tool_step:'Tool step',final_answer:'Final answer',repair:'Repair',optimize:'Optimize',extraction:'Extraction',reindex:'Reindex',memory:'Memory',chat:'Chat'};
const valid=(value:unknown):value is number=>typeof value==='number'&&Number.isSafeInteger(value)&&value>=0;
const count=(value:unknown)=>valid(value)?value.toLocaleString('en-US'):null;
const SYMBOLS:Record<string,string>={USD:'$',EUR:'€',GBP:'£',JPY:'¥',INR:'₹'};
/** Approximate cost for display only; the exact decimal stays on the server. */
export function formatCost(amount:string|number,currency:string){
 const value=Number(amount);
 if(!Number.isFinite(value))return '—';
 const text=value===0?'0':value>=1?value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):value.toLocaleString('en-US',{maximumSignificantDigits:2});
 const symbol=SYMBOLS[currency];
 return symbol?`${symbol}${text}`:`${text} ${currency}`;
}
export function costText(cost:CostSummary|undefined){
 const totals=(cost?.totals||[]).filter(total=>total&&total.currency);
 if(totals.length)return totals.map(total=>`≈ ${formatCost(total.amount,total.currency)}`).join(' · ');
 if(cost?.status==='price_not_set')return 'Price not set';
 return '';
}
export function agentTokenSteps(usage:Usage|undefined):TokenStepRow[]{
 return (usage?.steps||[]).map(step=>{
  const reported=valid(step.input_tokens)&&valid(step.output_tokens);
  const cost=step.cost||{};
  return {stage:STAGE_LABELS[step.stage||'']||step.stage||'Chat',model:step.provider_model||step.model_id||'—',
   input:count(step.input_tokens)??'Not reported',cached:count(step.cached_input_tokens)??'—',
   output:count(step.output_tokens)??'Not reported',reasoning:count(step.reasoning_tokens)??'—',
   latency:valid(step.latency_ms)?`${(step.latency_ms/1000).toLocaleString('en-US',{maximumFractionDigits:2})} s`:'—',
   cost:!reported||cost.status==='not_reported'?'Not reported':cost.status==='priced'&&cost.amount&&cost.currency?`≈ ${formatCost(cost.amount,cost.currency)}`:'Price not set'};
 });
}
export function agentTokenUsage(usage:Usage|undefined,status:string){
 if(status==='streaming')return {text:'Input — · Output —',title:'Provider token usage is available when the answer completes.'};
 if(!usage)return {text:'Token usage unavailable',title:'Token counts were not recorded for this answer.'};
 const calls=typeof usage.model_calls==='number'?usage.model_calls:undefined;
 if(usage.source==='no_model_calls'||calls===0)return {text:'No model calls',title:'No model calls were needed for this response.'};
 const input=count(usage.input_tokens),output=count(usage.output_tokens);
 const callText=calls!==undefined?` · ${calls.toLocaleString('en-US')} call${calls===1?'':'s'}`:'';
 if(input===null&&output===null)return {text:`Not reported${callText}`,title:'The model provider did not report token counts for this answer.'};
 const cached=valid(usage.cached_input_tokens)&&usage.cached_input_tokens>0?` (${count(usage.cached_input_tokens)} cached)`:'';
 const cost=costText(usage.cost);
 const excluded=(usage.cost?.not_reported_calls||0),unpriced=(usage.cost?.price_not_set_calls||0);
 const notes=[`Provider-reported tokens for this answer, including routing, retrieval embeddings and answer generation. ${usage.reported_calls??0} of ${calls??0} calls reported both counts.`];
 if(cost.startsWith('≈'))notes.push('Cost is approximate, from the list prices entered in Model Registration.');
 if(excluded)notes.push(`${excluded} call${excluded===1?' was':'s were'} not reported and excluded from the cost.`);
 if(unpriced&&cost.startsWith('≈'))notes.push(`${unpriced} call${unpriced===1?' has':'s have'} no price set.`);
 return {text:`Input ${input??'—'}${cached} · Output ${output??'—'}${callText}${cost?` · ${cost}`:''}${usage.complete===false?' · partial':''}`,title:notes.join(' ')};
}
