const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');
const file=path.resolve(__dirname,'../../lapi_frontend/app/agent-guide.ts');const compiled=new Module(file,module);compiled._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file);const {guideIntent,guideFor,guidedOperation}=compiled.exports;
const ready={dataset:true,files:1,templates:1,canOnboard:true,datasets:2,promptAttached:false};

test('plain words are understood; commands and knowledge questions are left alone',()=>{
 for(const t of ['upload this one','Upload','can you add these docs','attach it','import the invoices please','save this pdf'])assert.equal(guideIntent(t),'upload',t);
 for(const t of ['pull out the totals','extract fields','get the invoice dates from them','Extract the table'])assert.equal(guideIntent(t),'extract',t);
 for(const t of ['create a dataset','make a new dataset for contracts','set up dataset'])assert.equal(guideIntent(t),'dataset',t);
 for(const t of ['write a prompt','I need a prompt template','create an extraction prompt'])assert.equal(guideIntent(t),'prompt',t);
 for(const t of ['start','get started','walk me through','how do I start'])assert.equal(guideIntent(t),'start',t);
 for(const t of ['/Upload files','#invoice.pdf what is the total','what is the total of invoice 7','which documents mention Alice','summarize the contract','','   '])assert.equal(guideIntent(t),null,t);
});

test('upload: attach first; with nothing to hold it, a guided start; otherwise the server takes it',()=>{
 const noFiles=guideFor('upload',{...ready,files:0});
 assert.match(noFiles.text,/Attach the document first/);assert.deepEqual(noFiles.actions.map(a=>a.action),['attach','quick-start']);
 const nothing=guideFor('upload',{...ready,dataset:false,datasets:0});
 assert.match(nothing.text,/no dataset yet/);assert.deepEqual(nothing.actions.map(a=>a.action),['quick-start']);
 assert.equal(guideFor('upload',{...ready,dataset:false}),null,'the server asks which dataset itself');
 assert.equal(guideFor('upload',ready),null);assert.equal(guidedOperation('upload'),undefined);
});

test('extract: guided only when no dataset exists; the server asks for the prompt itself',()=>{
 assert.match(guideFor('extract',{...ready,dataset:false,datasets:0}).text,/guided start/);
 assert.equal(guideFor('extract',{...ready,dataset:false}),null);
 assert.equal(guideFor('extract',{...ready,templates:0}),null);
 assert.equal(guideFor('extract',ready),null);assert.equal(guidedOperation('extract'),undefined);
});

test('dataset creation goes ahead for people who may onboard, and is guided for everyone else',()=>{
 assert.equal(guideFor('dataset',ready),null);assert.equal(guidedOperation('dataset'),'onboard');
 assert.deepEqual(guideFor('dataset',{...ready,canOnboard:false}).actions.map(a=>a.action),['quick-start']);
 assert.deepEqual(guideFor('start',ready).actions.map(a=>a.action),['quick-start']);
 assert.equal(guideFor(null,ready),null);assert.equal(guidedOperation(null),undefined);
});
