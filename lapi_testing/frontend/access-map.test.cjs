const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/access-map-data.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {initialDraft,toggle,access,changed,changedUsers,openfgaDifference,openfgaSummary}=compiled.exports;
const users=[
 {id:'admin',username:'Admin',is_admin:true,dataset_ids:[],openfga:{administrator:true,dataset_ids:[],in_step:true}},
 {id:'ana',username:'Ana',is_admin:false,dataset_ids:['b','a'],openfga:{administrator:false,dataset_ids:['a','c'],in_step:false}},
];
test('the draft starts from saved access and toggles only non-administrators',()=>{
 const draft=initialDraft(users);
 assert.deepEqual(draft,{ana:['a','b']});
 assert.equal(toggle(draft,'admin','a'),draft);
 const removed=toggle(draft,'ana','a');
 assert.deepEqual(removed.ana,['b']);assert.deepEqual(draft.ana,['a','b']);
 assert.deepEqual(toggle(removed,'ana','a').ana,['a','b']);
 assert.equal(access(users[0],draft,'z'),'admin');
 assert.equal(access(users[1],removed,'a'),'none');assert.equal(access(users[1],removed,'b'),'granted');
});
test('unsaved changes are found per cell and per person',()=>{
 const draft=initialDraft(users);
 assert.deepEqual(changedUsers(users,draft),[]);
 const next=toggle(draft,'ana','c');
 assert.ok(changed(users[1],next,'c'));assert.ok(!changed(users[1],next,'a'));
 assert.deepEqual(changedUsers(users,next),['ana']);
 assert.deepEqual(changedUsers(users,toggle(next,'ana','c')),[]);
});
test('OpenFGA differences are named in both directions and summarised',()=>{
 assert.equal(openfgaDifference(users[1],'a'),undefined);
 assert.equal(openfgaDifference(users[1],'b'),'missing');
 assert.equal(openfgaDifference(users[1],'c'),'extra');
 assert.equal(openfgaDifference(users[0]),undefined);
 assert.equal(openfgaDifference({...users[1],openfga:undefined},'b'),undefined);
 assert.equal(openfgaSummary({enabled:false,reachable:null,differences:0}).tone,'info');
 assert.equal(openfgaSummary({enabled:true,reachable:false,differences:0}).tone,'error');
 assert.match(openfgaSummary({enabled:true,reachable:true,differences:1}).title,/1 person$/);
 assert.equal(openfgaSummary({enabled:true,reachable:true,differences:0}).tone,'ok');
});
