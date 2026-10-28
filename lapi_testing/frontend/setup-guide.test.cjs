const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/setup-guide.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {GOALS,SOURCES,cleanPreferences,toggleSource,toggleGoal,accessFor,shouldAskSetup,showNextSteps,recommendNextSteps,addKnowledgeRoute}=compiled.exports;
const admin={isAdmin:true,canAddKnowledge:true,datasetCount:2},editor={isAdmin:false,canAddKnowledge:true,datasetCount:1},viewer={isAdmin:false,canAddKnowledge:false,datasetCount:3};

test('the questions offer the four goals and eight sources the server accepts',()=>{
 assert.deepEqual(GOALS.map(g=>g.id),['ask','extract','research','knowledge_base']);
 assert.deepEqual(SOURCES.map(s=>s.id),['files','google_drive','sharepoint','s3','azure_blob','gcs','oci_object','not_sure']);
 assert.equal(SOURCES.find(s=>s.id==='sharepoint').title,'SharePoint / OneDrive');
});

test('answers are cleaned to known values in question order; "Not sure yet" excludes named sources',()=>{
 assert.deepEqual(cleanPreferences({goals:['extract','x','ask','ask'],sources:['s3','files'],completed:true,dismissed_next_steps:'yes'}),{goals:['ask','extract'],sources:['files','s3'],completed:true,dismissed_next_steps:false});
 for(const bad of [null,undefined,'x',[],{goals:'ask'}])assert.deepEqual(cleanPreferences(bad),{goals:[],sources:[],completed:false,dismissed_next_steps:false});
 assert.deepEqual(toggleSource(['files'],'not_sure'),['not_sure']);
 assert.deepEqual(toggleSource(['not_sure'],'gcs'),['gcs']);
 assert.deepEqual(toggleSource(['gcs','files'],'gcs'),['files']);
 assert.deepEqual(toggleSource(['gcs'],'files'),['files','gcs']);
 assert.deepEqual(toggleGoal(['research'],'ask'),['ask','research']);assert.deepEqual(toggleGoal(['ask'],'ask'),[]);
});

test('access: administrators and dataset Editors or Owners can add knowledge, Viewers cannot',()=>{
 assert.deepEqual(accessFor({is_admin:true},[]),{isAdmin:true,canAddKnowledge:true,datasetCount:0});
 assert.equal(accessFor({},[{my_access:'viewer'},{my_access:'editor'}]).canAddKnowledge,true);
 assert.equal(accessFor({},[{my_access:'owner'}]).canAddKnowledge,true);
 assert.equal(accessFor({},[{my_access:'viewer'}]).canAddKnowledge,false);
 assert.equal(accessFor({},[{my_access:'editor',active:false}]).canAddKnowledge,false);
 assert.equal(accessFor(null,[{my_access:'viewer'},{my_access:'viewer',active:false}]).datasetCount,1);
});

test('the sheet asks until answered or skipped; the card shows until hidden',()=>{
 assert.equal(shouldAskSetup(null),false);
 assert.equal(shouldAskSetup(cleanPreferences({})),true);
 assert.equal(shouldAskSetup(cleanPreferences({completed:true})),false);
 assert.equal(showNextSteps(cleanPreferences({completed:true})),true);
 assert.equal(showNextSteps(cleanPreferences({completed:true,dismissed_next_steps:true})),false);
 assert.equal(showNextSteps(cleanPreferences({})),false);
});

test('people who can add knowledge get the connector guide for their first source as the primary step',()=>{
 const drive=recommendNextSteps({goals:['ask'],sources:['google_drive','s3']},editor);
 assert.deepEqual(drive.primary,{kind:'connect',provider:'google_drive',label:'Connect Google Drive',detail:drive.primary.detail});
 assert.match(drive.primary.detail,/step-by-step Google Drive guide/);
 assert.deepEqual(drive.steps.map(s=>s.kind+(s.provider?':'+s.provider:'')),['connect:google_drive','ask','connect:s3']);
 assert.deepEqual(drive.notes,[]);
 const files=recommendNextSteps({goals:['extract'],sources:['files']},editor);
 assert.equal(files.primary.kind,'upload');assert.deepEqual(files.steps.map(s=>s.kind),['upload','extract','ask']);
 const unsure=recommendNextSteps({goals:[],sources:['not_sure']},admin);
 assert.equal(unsure.primary.kind,'add-knowledge');assert.ok(unsure.steps.length>=2&&unsure.steps.length<=3);
 const research=recommendNextSteps({goals:['research'],sources:['sharepoint']},admin);
 assert.equal(research.primary.label,'Connect SharePoint');assert.equal(research.steps[1].kind,'research');
});

test('an administrator with no datasets is offered "Create your first dataset" first',()=>{
 const first=recommendNextSteps({goals:['knowledge_base'],sources:['oci_object']},{isAdmin:true,canAddKnowledge:true,datasetCount:0});
 assert.equal(first.primary.kind,'create-dataset');assert.equal(first.primary.label,'Create your first dataset');
 assert.deepEqual(first.steps.map(s=>s.kind),['create-dataset','connect','ask']);assert.equal(first.steps[1].provider,'oci_object');
});

test('Viewers are guided to ask in shared datasets and to ask an owner to connect their sources',()=>{
 const guide=recommendNextSteps({goals:['ask','extract'],sources:['google_drive','files','not_sure']},viewer);
 assert.equal(guide.primary.kind,'ask');
 assert.ok(guide.steps.every(s=>!['connect','upload','add-knowledge','extract','create-dataset'].includes(s.kind)));
 assert.ok(guide.steps.some(s=>s.kind==='agent'));
 assert.ok(guide.notes.includes('Ask a dataset owner or administrator to connect Google Drive.'));
 assert.ok(guide.notes.includes('Ask a dataset owner or administrator to add your files.'));
 assert.ok(guide.notes.some(n=>/Editor access/.test(n)));
 const none=recommendNextSteps({goals:[],sources:[]},{isAdmin:false,canAddKnowledge:false,datasetCount:0});
 assert.equal(none.primary.kind,'agent');assert.match(none.notes[0],/No datasets are shared with you/);
 assert.equal(recommendNextSteps({goals:['research'],sources:[]},viewer).primary.kind,'research');
});

test('every recommendation has a primary step and at most three steps, without duplicates',()=>{
 const goalsSets=[[],['ask'],['extract'],['research','knowledge_base'],GOALS.map(g=>g.id)];
 const sourceSets=[[],['not_sure'],['files'],['gcs','azure_blob','s3'],SOURCES.map(s=>s.id)];
 const accesses=[admin,editor,viewer,{isAdmin:true,canAddKnowledge:true,datasetCount:0},{isAdmin:false,canAddKnowledge:false,datasetCount:0}];
 for(const goals of goalsSets)for(const sources of sourceSets)for(const access of accesses){
  const g=recommendNextSteps({goals,sources},access);
  assert.ok(g.primary&&g.primary.label,JSON.stringify({goals,sources,access}));
  assert.equal(g.primary,g.steps[0]);assert.ok(g.steps.length>=1&&g.steps.length<=3);
  assert.equal(new Set(g.steps.map(s=>s.kind+(s.provider||''))).size,g.steps.length);
 }
});

test('the Add knowledge route carries the provider for the guide',()=>{
 assert.equal(addKnowledgeRoute('google_drive'),'#Add%20knowledge/google_drive');
 assert.equal(addKnowledgeRoute(),'#Add%20knowledge');
});
