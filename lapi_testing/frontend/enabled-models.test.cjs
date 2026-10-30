const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/enabled-models-data.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {defaultRoles,switchable,summary,usesOf}=compiled.exports;

const models=[
 {id:'e',name:'Embed',capabilities:['embedding'],enabled:true},
 {id:'x',name:'Extractor',capabilities:['extraction'],enabled:false},
 {id:'b',name:'Beta chat',capabilities:['chat','extraction'],enabled:true},
 {id:'a',name:'Alpha chat',capabilities:['chat'],enabled:false},
 {id:'old',name:'Old',capabilities:['chat'],enabled:true,archived:true}];

test('models are listed chat first, then by name, without archived registrations',()=>{
 assert.deepEqual(switchable(models).map(m=>m.id),['a','b','x','e']);
});

test('the summary counts models that are on, off and on for chat',()=>{
 assert.deepEqual(summary(models),{on:2,off:2,chat:1});
});

test('a workspace Default is named so it cannot be switched off by mistake',()=>{
 const defaults={chat_model_id:'b',extraction_model_id:'b',embedding_model_id:'e',ocr_model_id:null};
 assert.deepEqual(defaultRoles(models[2],defaults),['Chat','Extraction']);
 assert.deepEqual(defaultRoles(models[0],defaults),['Embedding']);
 assert.deepEqual(defaultRoles(models[3],defaults),[]);
 assert.deepEqual(defaultRoles(models[2],null),[]);
 assert.deepEqual(usesOf(models[2]),['Chat','Extraction']);
});
