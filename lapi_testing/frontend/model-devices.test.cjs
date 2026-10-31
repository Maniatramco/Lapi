const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/agent-document-selection.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {eligibleAgentModels,offeredOn}=compiled.exports;

const models=[
 {id:'small',capabilities:['chat'],enabled:true,devices:['phone']},
 {id:'big',capabilities:['chat'],enabled:true,devices:['computer']},
 {id:'any',capabilities:['chat'],enabled:true},
 {id:'off',capabilities:['chat'],enabled:false,devices:['phone']}];

test('phones list only the models offered on phones, computers only those offered on computers',()=>{
 assert.deepEqual(eligibleAgentModels(models,undefined,'phone').map(m=>m.id),['small','any']);
 assert.deepEqual(eligibleAgentModels(models,undefined,'computer').map(m=>m.id),['big','any']);
 assert.deepEqual(eligibleAgentModels(models,undefined).map(m=>m.id),['small','big','any']);
 assert.deepEqual(eligibleAgentModels([],{chat_choices:models},'phone').map(m=>m.id),['small','any']);
});

test('a model with no saved devices is offered on both',()=>{
 assert.equal(offeredOn({},'phone'),true);assert.equal(offeredOn({devices:[]},'computer'),true);
 assert.equal(offeredOn({devices:['phone']},'computer'),false);
});
