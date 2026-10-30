const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/workspace-scope.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {gateStep,pickWorkspace,inWorkspace,scopeCatalog,canAddCollections}=compiled.exports;
const me={id:'me',audience:'personal',mine:true,my_access:'owner',collection_count:0},team={id:'team',audience:'team',my_access:'viewer',collection_count:0};

test('login asks which workspace only when there is a choice',()=>{
 assert.equal(gateStep({workspaces:[me,team],current:'me',chosen:false,skipped:false}),'choose');
 assert.equal(gateStep({workspaces:[{...me,collection_count:2}],current:'me',chosen:false,skipped:false}),null);
 assert.equal(gateStep({workspaces:[],current:'',chosen:false,skipped:false}),null);
});

test('an empty workspace guides to a first collection, unless the person cannot add or said not now',()=>{
 assert.equal(gateStep({workspaces:[me],current:'me',chosen:false,skipped:false}),'collection');
 assert.equal(gateStep({workspaces:[me],current:'me',chosen:true,skipped:true}),null);
 assert.equal(gateStep({workspaces:[me,team],current:'team',chosen:true,skipped:false}),null);
 assert.equal(canAddCollections(team),false);assert.equal(canAddCollections(me),true);
});

test('the saved workspace wins while it is still available, else the person\'s own',()=>{
 assert.equal(pickWorkspace([team,me],'team'),'team');
 assert.equal(pickWorkspace([team,me],'gone'),'me');
 assert.equal(pickWorkspace([team],null),'team');
 assert.equal(pickWorkspace([],null),'');
});

test('screens show the open workspace, and the Agent choices keep their identity',()=>{
 const items=[{id:'a',workspace_id:'x'},{id:'b',workspace_id:'y'},{id:'old'}];
 assert.deepEqual(inWorkspace(items,'x').map(i=>i.id),['a','old']);
 assert.deepEqual(inWorkspace(items,'').map(i=>i.id),['a','b','old']);
 const catalog={datasets:items,documents:[{id:'d1',parent_id:'a'},{id:'d2',parent_id:'b'}]};
 const scoped=scopeCatalog(catalog,'x');
 assert.deepEqual(scoped.documents.map(d=>d.id),['d1']);
 assert.equal(scopeCatalog(catalog,'x'),scoped);
 assert.equal(scopeCatalog(catalog,undefined),catalog);
});
