const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/access-map-data.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {initialDraft,initialTeamDraft,cycle,nextLevel,access,effective,changed,changedUsers,changedTeams,openfgaDifference,openfgaSummary,savedLevels}=compiled.exports;
const users=[
 {id:'admin',username:'Admin',is_admin:true,dataset_ids:[],levels:{},openfga:{administrator:true,dataset_ids:[],levels:{},in_step:true}},
 {id:'ana',username:'Ana',is_admin:false,dataset_ids:['a','b'],levels:{a:'editor',b:'viewer'},effective:{a:'editor',b:'viewer',c:'owner'},team_ids:['fin'],
  openfga:{administrator:false,dataset_ids:['a','c'],levels:{a:'editor',c:'viewer'},in_step:false}},
];
const teams=[{id:'fin',name:'Finance',source:'local',member_ids:['ana'],grants:{c:'owner'}}];

test('levels cycle No access → Viewer → Editor → Owner → No access, only for non-administrators',()=>{
 assert.equal(nextLevel(undefined),'viewer');assert.equal(nextLevel('viewer'),'editor');assert.equal(nextLevel('editor'),'owner');assert.equal(nextLevel('owner'),undefined);
 const draft=initialDraft(users);
 assert.deepEqual(draft,{ana:{a:'editor',b:'viewer'}});
 assert.equal(cycle(draft,'admin','a'),draft);
 const once=cycle(draft,'ana','a');assert.equal(once.ana.a,'owner');assert.equal(draft.ana.a,'editor');
 assert.equal('a' in cycle(once,'ana','a').ana,false);
 assert.equal(access(users[0],draft,'z'),'admin');assert.equal(access(users[1],draft,'b'),'viewer');assert.equal(access(users[1],draft,'c'),'none');
 assert.deepEqual(savedLevels({id:'old',username:'Old',is_admin:false,dataset_ids:['x']}),{x:'viewer'});
});

test('team grants raise what a person gets, and the higher level wins',()=>{
 const draft=initialDraft(users),teamDraft=initialTeamDraft(teams);
 assert.deepEqual(effective(users[1],draft,teams,teamDraft,'c'),{access:'owner',viaTeam:'Finance'});
 assert.deepEqual(effective(users[1],draft,teams,teamDraft,'a'),{access:'editor'});
 assert.deepEqual(effective(users[1],draft,teams,cycle(teamDraft,'fin','c'),'c'),{access:'none'});
 assert.deepEqual(changedTeams(teams,cycle(teamDraft,'fin','a')),['fin']);
});

test('unsaved changes are found per cell and per person',()=>{
 const draft=initialDraft(users);
 assert.deepEqual(changedUsers(users,draft),[]);
 const next=cycle(draft,'ana','b');
 assert.ok(changed(users[1],next,'b'));assert.ok(!changed(users[1],next,'a'));
 assert.deepEqual(changedUsers(users,next),['ana']);
});

test('OpenFGA differences are named: missing, extra and a different level',()=>{
 assert.equal(openfgaDifference(users[1],'a'),undefined);
 assert.equal(openfgaDifference(users[1],'b'),'missing');
 assert.equal(openfgaDifference(users[1],'c'),'level');
 assert.equal(openfgaDifference({...users[1],effective:{}},'a'),'extra');
 assert.equal(openfgaDifference(users[0]),undefined);
 assert.equal(openfgaDifference({...users[1],openfga:undefined},'b'),undefined);
 assert.equal(openfgaSummary({enabled:false,reachable:null,differences:0}).tone,'info');
 assert.equal(openfgaSummary({enabled:true,reachable:false,differences:0}).tone,'error');
 assert.match(openfgaSummary({enabled:true,reachable:true,differences:1}).title,/1 person$/);
 assert.equal(openfgaSummary({enabled:true,reachable:true,differences:0}).tone,'ok');
});
