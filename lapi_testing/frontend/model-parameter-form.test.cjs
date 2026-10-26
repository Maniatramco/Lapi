const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');
const app=path.resolve(__dirname,'../../lapi_frontend/app');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const catalog=[{id:'ollama',name:'Local · Ollama',protocol:'ollama',endpoint:'http://127.0.0.1:11435',region:'',auth_modes:['none'],categories:['chat','extraction','embedding']},
 {id:'anthropic',name:'Anthropic · Claude (direct)',protocol:'anthropic',endpoint:'https://api.anthropic.com/v1',region:'',auth_modes:['api_key'],categories:['chat']},
 {id:'bedrock',name:'AWS · Bedrock',protocol:'bedrock',endpoint:'https://bedrock-runtime.us-east-1.amazonaws.com',region:'us-east-1',auth_modes:['aws_keys'],categories:['chat','extraction','embedding']}];
// Abridged copies of GET /model-registrations/parameter-schema responses.
const field=(key,extra)=>({key,label:key,help:'help',default:null,default_note:'Provider default: set by the model.',...extra});
const schemas={
 ollama:{protocol:'ollama',category:'chat',accepts_overrides:true,notice:null,
  fields:[field('temperature',{type:'number',min:0,max:2,step:0.05,default:0.8,default_note:'Provider default: 0.8'}),field('seed',{type:'integer',min:0,max:2147483647,step:1}),field('stop',{type:'string_list',max_items:16,max_length:256})],
  stages:[{key:'chat',label:'Chat answer',help:'h',lapi_defaults:{temperature:0,seed:42},suggested:{temperature:0.2}},{key:'tool_step',label:'Tool steps',help:'h',lapi_defaults:{temperature:0,seed:42},suggested:{temperature:0,seed:42}},{key:'optimize',label:'Optimize',help:'h',lapi_defaults:{temperature:0.7,seed:42},suggested:{temperature:0.3}}],
  model_lapi_defaults:{temperature:0,seed:42}},
 anthropic:{protocol:'anthropic',category:'chat',accepts_overrides:false,notice:'Direct Claude does not accept sampling overrides; the model uses its own settings.',fields:[],stages:[],model_lapi_defaults:{}},
 bedrock:{protocol:'bedrock',category:'chat',accepts_overrides:true,notice:null,fields:[field('temperature',{type:'number',min:0,max:1,step:0.05})],
  stages:[{key:'chat',label:'Chat answer',help:'h',lapi_defaults:{},suggested:{temperature:0.2}},{key:'tool_step',label:'Tool steps',help:'h',lapi_defaults:{},suggested:{temperature:0}},{key:'optimize',label:'Optimize',help:'h',lapi_defaults:{},suggested:{temperature:0.3}}],model_lapi_defaults:{}},
};
function compile(file,react){const m=new Module(file,module);m.filename=file;m.paths=module.paths;const base=m.require.bind(m);
 m.require=id=>id==='react'?react:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):id.endsWith('.css')?{}:id==='./summary-tiles'?{SummaryTiles:()=>null}:
  ['./action-button','./model-parameters','./model-parameter-form'].includes(id)?compile(path.resolve(app,id.slice(2)+(id==='./model-parameters'?'.ts':'.tsx')),react).exports:base(id);
 m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);return m;}
const helpers=compile(path.resolve(app,'model-parameters.ts'),{}).exports;

async function screen(){
 let cursor=0,root,effects=[];const hooks=[],calls=[];
 const react={useState(initial){const i=cursor++;if(!(i in hooks))hooks[i]=typeof initial==='function'?initial():initial;return[hooks[i],v=>hooks[i]=typeof v==='function'?v(hooks[i]):v];},useEffect(fn,deps){effects.push([fn,deps]);}};
 const mod=compile(path.resolve(app,'model-registration.tsx'),react);
 const nodes=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(typeof n.type==='function'?n.type(n.props):n.props?.children)];
 const props={models:[],settings:{model_defaults:{timeout:60,context_limit:32768,embedding_context_limit:8192,max_output_tokens:4096,headroom_tokens:512,context_max:2097152,output_max:131072,timeout_min:5,timeout_max:1800}},busy:false,onSaved:()=>{},onMapping:()=>{},run:async fn=>{try{await fn();}catch{}},
  api:async(...args)=>{calls.push(args);if(args[0]==='/model-providers')return catalog;if(args[0].startsWith('/model-registrations/parameter-schema?'))return schemas[new URLSearchParams(args[0].split('?')[1]).get('protocol')];
   if(args[0]==='/model-registrations/test')return {ok:true,elapsed_ms:10,agent_tool_call_validated:true,effective_parameters:{tool_step:{parameters:{temperature:0.1,seed:42},sources:{temperature:'stage',seed:'lapi_default'}}}};return {id:'saved'};}};
 // Run each effect whose dependencies changed, like React does after a render.
 let previous=[];
 const render=async()=>{cursor=0;effects=[];root=mod.exports.ModelRegistration(props);const current=effects;
  current.forEach(([fn,deps],i)=>{const old=previous[i];if(!old||!deps||deps.some((d,j)=>d!==old[1][j]))fn();});previous=current;await flush();cursor=0;effects=[];root=mod.exports.ModelRegistration(props);previous=previous.map((e,i)=>effects[i]||e);};
 await render();
 const all=()=>nodes(root);
 const byId=id=>all().find(n=>n.props?.id===id);
 const button=text=>all().find(n=>n.props?.['aria-label']===text||(n.type==='button'&&JSON.stringify(n.props.children).includes(text)));
 button('Register model').props.onClick();await render();
 return {render,calls,byId,button,all,choose:async id=>{byId('registration-protocol').props.onChange({target:{value:id}});await render();}};
}

test('field resolution follows stage, model value, Lapi default, then provider default',()=>{
 const s=schemas.ollama;
 assert.deepEqual(helpers.resolveField(s,'temperature',{},{},'tool_step'),{value:0,source:'lapi_default'});
 assert.deepEqual(helpers.resolveField(s,'temperature',{temperature:0.5},{},'tool_step'),{value:0.5,source:'model'});
 assert.deepEqual(helpers.resolveField(s,'temperature',{temperature:0.5},{tool_step:{temperature:0.1}},'tool_step'),{value:0.1,source:'stage'});
 assert.deepEqual(helpers.resolveField(s,'temperature',{temperature:0.5},{tool_step:{temperature:null}},'tool_step'),{value:undefined,source:'provider_default'});
 assert.deepEqual(helpers.resolveField(s,'seed',{seed:null},{},'chat'),{value:undefined,source:'provider_default'});
 assert.deepEqual(helpers.resolveField(s,'stop',{},{},'chat'),{value:undefined,source:'provider_default'});
});

test('modes map to absent, null and a value; ranges match the backend, including Bedrock',()=>{
 const temperature=schemas.ollama.fields[0];
 assert.deepEqual(helpers.withMode({temperature:0.3},temperature,'default'),{});
 assert.deepEqual(helpers.withMode({},temperature,'provider'),{temperature:null});
 assert.deepEqual(helpers.withMode({},temperature,'custom',0),{temperature:0});
 assert.deepEqual(helpers.withMode({temperature:0.3},temperature,'custom',0),{temperature:0.3});
 assert.equal(helpers.fieldError(temperature,2),'');
 assert.match(helpers.fieldError(schemas.bedrock.fields[0],1.5),/between 0 and 1/);
 assert.match(helpers.fieldError(schemas.ollama.fields[1],1.5),/whole number/);
 assert.equal(helpers.valuesError(schemas.bedrock,{temperature:null}),'');
 assert.deepEqual(helpers.cleanStages(schemas.ollama,{chat:{},tool_step:{temperature:0},extraction:{temperature:0}}),{tool_step:{temperature:0}});
 assert.deepEqual(helpers.testStages('chat',{},{tool_step:{temperature:0}}),[]);
 assert.deepEqual(helpers.testStages('chat',{},{chat:{temperature:0.2},optimize:{seed:1}}),['chat','optimize']);
 assert.deepEqual(helpers.testStages('extraction',{temperature:1},{}),[]);
});

test('typed per-stage form sends exactly the chosen values with the connection test and the save',async()=>{
 const s=await screen();
 assert.ok(s.calls.some(c=>c[0].startsWith('/model-registrations/parameter-schema?protocol=ollama&category=chat')));
 assert.ok(s.byId('parameter-scope-tool_step'));
 assert.ok(JSON.stringify(s.all().filter(n=>n.type==='small').map(n=>n.props.children)).includes('Lapi sends 0 (documented Lapi default)'));
 s.byId('parameter-scope-tool_step').props.onClick();await s.render();
 s.byId('parameter-tool_step-temperature-mode').props.onChange({target:{value:'custom'}});await s.render();
 assert.equal(s.byId('parameter-tool_step-temperature').props.value,0);
 s.byId('parameter-tool_step-temperature').props.onChange({target:{value:'0.1'}});await s.render();
 s.byId('parameter-tool_step-seed-mode').props.onChange({target:{value:'provider'}});await s.render();
 s.byId('parameter-scope-model').props.onClick();await s.render();
 s.byId('parameter-model-temperature-mode').props.onChange({target:{value:'custom'}});await s.render();
 s.byId('parameter-model-temperature').props.onChange({target:{value:'0.6'}});await s.render();
 s.byId('registration-name').props.onChange({target:{value:'Local chat'}});s.byId('registration-model').props.onChange({target:{value:'qwen3:4b'}});await s.render();
 s.button('Test Connection').props.onClick({currentTarget:{form:{reportValidity:()=>true}}});await flush();await s.render();
 const sent=s.calls.find(c=>c[0]==='/model-registrations/test')[2];
 assert.deepEqual(sent.extra_parameters,{temperature:0.6});
 assert.deepEqual(sent.stage_parameters,{tool_step:{temperature:0.1,seed:null}});
 assert.deepEqual(sent.test_stages,['chat']);
 assert.ok(JSON.stringify(s.all().filter(n=>n.type==='li').map(n=>n.props.children)).includes('temperature 0.1 (this stage)'));
 assert.equal(s.button('Save Model').props.disabled,false);
 s.all().find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await flush();
 const saved=s.calls.find(c=>c[0]==='/model-registrations')[2];
 assert.deepEqual(saved.stage_parameters,{tool_step:{temperature:0.1,seed:null}});assert.equal(saved.test_stages,undefined);
});

test('out-of-range values (Bedrock temperature above 1) block the connection test',async()=>{
 const s=await screen();await s.choose('bedrock');
 s.byId('parameter-model-temperature-mode').props.onChange({target:{value:'custom'}});await s.render();
 s.byId('parameter-model-temperature').props.onChange({target:{value:'1.5'}});await s.render();
 assert.ok(s.all().some(n=>n.props?.role==='alert'&&String(n.props.children).includes('between 0 and 1')));
 assert.equal(s.button('Test Connection').props.disabled,true);
});

test('a provider without sampling overrides shows a notice instead of an empty form',async()=>{
 const s=await screen();await s.choose('anthropic');
 const notice=s.all().find(n=>n.props?.role==='note');
 assert.ok(notice&&JSON.stringify(notice.props.children).includes('does not accept sampling overrides'));
 assert.equal(s.byId('parameter-model-temperature-mode'),undefined);
});
