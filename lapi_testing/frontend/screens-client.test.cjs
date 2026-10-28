const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/screens-client.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {deviceFor,viewAllowed,agentOnly,TRAINING_CARDS,CORE_VIEWS}=compiled.exports;
const phone={device:'phone',screens:[],views:[],core:['home','agent','quick-start'],administrator:false};

test('phones are under 640 px; the Dashboard and the agent always show; other views need a grant',()=>{
 assert.equal(deviceFor(375),'phone');assert.equal(deviceFor(640),'computer');
 for(const view of CORE_VIEWS)assert.equal(viewAllowed(view,phone,false),true);
 assert.equal(viewAllowed('Datasets',phone,false),false);
 assert.equal(viewAllowed('Datasets',{...phone,views:['Datasets']},false),true);
 assert.equal(viewAllowed('Datasets',phone,true),true);
 assert.equal(viewAllowed('Datasets',null,false),true);
});

test('the agent-only phone version has no More menu, except for administrators',()=>{
 assert.equal(agentOnly(phone,false),true);assert.equal(agentOnly(phone,true),false);
 assert.equal(agentOnly({...phone,views:['Review']},false),false);assert.equal(agentOnly({...phone,device:'computer'},false),false);
});

test('the training has five short cards and every example is something the agent can do',()=>{
 assert.equal(TRAINING_CARDS.length,5);
 for(const card of TRAINING_CARDS){assert.ok(card.title.length<40&&card.text.length<220,card.id);if(card.action==='ask')assert.ok(card.example);}
 assert.match(TRAINING_CARDS[4].text,/never/);
});
