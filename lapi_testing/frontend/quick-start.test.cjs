const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/quick-start-flow.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {stepsFor,uploadable,askable,fileState,progress,pickFiles,sourceName,defaultDatasetName,MAX_FILES}=compiled.exports;
const datasets=[{id:'v',name:'Policies',my_access:'viewer'},{id:'e',name:'Contracts',my_access:'editor'},{id:'o',name:'Old',my_access:'owner',active:false}];

test('people who can add documents get the full workflow; Viewers choose a dataset and ask',()=>{
 assert.deepEqual(stepsFor(datasets,false),['dataset','documents','processing','ask','done']);
 assert.deepEqual(stepsFor([datasets[0]],false),['dataset','ask','done']);
 assert.deepEqual(stepsFor([],true),['dataset','documents','processing','ask','done']);
 assert.deepEqual(uploadable(datasets,false).map(d=>d.id),['e']);
 assert.deepEqual(uploadable(datasets,true).map(d=>d.id),['v','e']);
 assert.deepEqual(askable(datasets).map(d=>d.id),['v','e']);
});

test('reading progress finishes when no file is still being read',()=>{
 assert.equal(fileState('queued'),'working');assert.equal(fileState('processing'),'working');
 assert.equal(fileState('ready'),'ready');assert.equal(fileState('failed'),'failed');
 assert.deepEqual(progress(['ready','working']),{ready:1,failed:0,total:2,finished:false,percent:50});
 assert.deepEqual(progress(['ready','failed']),{ready:1,failed:1,total:2,finished:true,percent:100});
 assert.equal(progress([]).finished,false);
});

test('only files Lapi can read are kept, at most ten, with a note about the rest',()=>{
 const file=(name,type='')=>({name,type,size:1000});
 const picked=pickFiles([file('a.pdf'),file('photo','image/jpeg'),file('b.exe'),file('c.DOCX')]);
 assert.deepEqual(picked.files.map(f=>f.name),['a.pdf','photo','c.DOCX']);
 assert.match(picked.note,/1 file was skipped/);
 assert.equal(pickFiles(Array.from({length:12},(_,i)=>file(i+'.txt'))).files.length,MAX_FILES);
 assert.equal(pickFiles([file('x.txt')]).note,'');
});

test('sources and default names read well',()=>{
 assert.equal(sourceName({title:'Lease.pdf',page:3}),'Lease.pdf · page 3');
 assert.equal(sourceName({}),'Source');
 assert.equal(defaultDatasetName('poorni',new Date('2026-10-28T10:00:00Z')),"poorni's documents Oct 2026");
});
