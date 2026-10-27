const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');
const file=path.resolve(__dirname,'../../lapi_frontend/app/agent-token-usage.ts');const compiled=new Module(file,module);compiled._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file);const {agentTokenUsage,agentTokenSteps,formatCost}=compiled.exports;
test('completed answer shows actual provider totals, cached input, calls and approximate cost',()=>{
 const usage=agentTokenUsage({input_tokens:4210,cached_input_tokens:3800,output_tokens:612,complete:true,reported_calls:3,model_calls:3,cost:{status:'complete',totals:[{currency:'USD',amount:'0.0042'}]}},'completed');
 assert.equal(usage.text,'Input 4,210 (3,800 cached) · Output 612 · 3 calls · ≈ $0.0042');
 assert.match(usage.title,/routing/);assert.match(usage.title,/approximate/);
});
test('older totals without calls or cost still render',()=>{assert.equal(agentTokenUsage({input_tokens:1234,output_tokens:56,complete:true,reported_calls:2,model_calls:2},'completed').text,'Input 1,234 · Output 56 · 2 calls');});
test('streaming and older history never invent usage',()=>{assert.equal(agentTokenUsage(undefined,'streaming').text,'Input — · Output —');assert.equal(agentTokenUsage(undefined,'completed').text,'Token usage unavailable');});
test('partial usage is labelled and missing output remains unknown',()=>{assert.equal(agentTokenUsage({input_tokens:9,output_tokens:null,complete:false},'completed').text,'Input 9 · Output — · partial');assert.equal(agentTokenUsage({input_tokens:true,output_tokens:-1,model_calls:1},'completed').text,'Not reported · 1 call');});
test('fast path without inference says No model calls',()=>{const usage=agentTokenUsage({input_tokens:0,output_tokens:0,complete:true,source:'no_model_calls',model_calls:0},'completed');assert.equal(usage.text,'No model calls');assert.match(usage.title,/No model calls/);});
test('price not set is never shown as zero and currencies are never added',()=>{
 assert.equal(agentTokenUsage({input_tokens:5,output_tokens:1,model_calls:1,complete:true,cost:{status:'price_not_set',totals:[],price_not_set_calls:1}},'completed').text,'Input 5 · Output 1 · 1 call · Price not set');
 const mixed=agentTokenUsage({input_tokens:5,output_tokens:1,model_calls:3,complete:false,cost:{status:'partial',totals:[{currency:'EUR',amount:'0.01'},{currency:'USD',amount:'2.5'}],not_reported_calls:1}},'completed');
 assert.equal(mixed.text,'Input 5 · Output 1 · 3 calls · ≈ €0.01 · ≈ $2.50 · partial');assert.match(mixed.title,/1 call was not reported and excluded/);
});
test('per-step table shows Not reported and Price not set',()=>{
 const rows=agentTokenSteps({steps:[
  {stage:'prefetch_embedding',provider_model:'embed-small',input_tokens:12,output_tokens:0,latency_ms:250,cost:{status:'priced',amount:'0.00000024',currency:'USD'}},
  {stage:'tool_step',provider_model:'gpt-x',input_tokens:4000,cached_input_tokens:3800,output_tokens:60,reasoning_tokens:20,cost:{status:'price_not_set'}},
  {stage:'final_answer',provider_model:'gpt-x',input_tokens:null,output_tokens:null,cost:{status:'not_reported'}}]});
 assert.deepEqual(rows.map(r=>r.stage),['Prefetch embedding','Tool step','Final answer']);
 assert.equal(rows[0].cost,'≈ $0.00000024');assert.equal(rows[0].latency,'0.25 s');
 assert.equal(rows[1].cached,'3,800');assert.equal(rows[1].reasoning,'20');assert.equal(rows[1].cost,'Price not set');
 assert.equal(rows[2].input,'Not reported');assert.equal(rows[2].cost,'Not reported');
});
test('cost formatting rounds for display only',()=>{assert.equal(formatCost('0.0042','USD'),'$0.0042');assert.equal(formatCost('12.345','EUR'),'€12.35');assert.equal(formatCost('0','USD'),'$0');assert.equal(formatCost('0.5','CHF'),'0.5 CHF');});
