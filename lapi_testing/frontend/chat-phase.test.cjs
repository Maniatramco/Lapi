const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/chat-phase.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {answerPhase,answerProgress}=compiled.exports;
const at=(label,done=[])=>({answer_workflow:{steps:[...done.map(l=>({label:l,status:'completed'})),{label,status:'running'}]}});

test('the live status line says what Lapi is doing in plain words',()=>{
 assert.equal(answerPhase(null),'Thinking');assert.equal(answerPhase({}),'Thinking');
 assert.equal(answerPhase(at('Answering or routing')),'Understanding your question');
 assert.equal(answerPhase(at('Searching unified knowledge')),'Searching your knowledge');
 assert.equal(answerPhase(at('Generating answer')),'Writing the answer');
 assert.equal(answerPhase(at('Validating citations')),'Checking the answer against its sources');
 assert.equal(answerPhase(at('Checking accessible collections')),'Checking collection access');
 assert.deepEqual(answerProgress(at('Generating answer',['Answering or routing','Searching'])),{done:2,total:3});
});
