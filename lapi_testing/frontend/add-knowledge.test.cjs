const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/add-knowledge.tsx'),mod=new Module(filename,module);mod.filename=filename;mod.paths=module.paths;
const options={compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}};
const guidesFile=path.resolve(__dirname,'../../lapi_frontend/app/connector-guides.ts'),guidesModule=new Module(guidesFile,module);guidesModule.paths=module.paths;
guidesModule._compile(ts.transpileModule(fs.readFileSync(guidesFile,'utf8'),options).outputText,guidesFile);
const original=mod.require.bind(mod);mod.require=id=>id.endsWith('.css')?{}:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):id==='./connector-guides'?guidesModule.exports:original(id);
mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),options).outputText,filename);
const {STORAGE_PROVIDERS,blankConnection,connectionPayload,vectorizeState,MAX_SELECTION,ConnectorGuidePanel}=mod.exports;
const {CONNECTOR_GUIDES}=guidesModule.exports;

test('all six storage providers are offered with read-only sign-in guidance',()=>{
 assert.deepEqual(STORAGE_PROVIDERS.map(p=>p.id),['s3','azure_blob','oci_object','sharepoint','google_drive','gcs']);
 assert.match(STORAGE_PROVIDERS.find(p=>p.id==='azure_blob').auth,/read and list only/);assert.equal(MAX_SELECTION,20);
});

test('new connections default to the provider region and never send saved metadata back',()=>{
 assert.equal(blankConnection('oci_object','d').region,'ap-mumbai-1');assert.equal(blankConnection('s3','d').region,'ap-south-1');assert.equal(blankConnection('azure_blob','d').region,'');
 const body=connectionPayload({...blankConnection('s3','d'),id:'c',version:2,updated_at:1,credentials_configured:true,secret_ref:'secret',owner:'bob'});
 for(const key of ['id','version','updated_at','credentials_configured','secret_ref','owner'])assert.equal(key in body,false);
 assert.equal(body.provider,'s3');assert.equal(body.dataset_id,'d');
});

test('vectorized copies are ready to ask only after indexing succeeds and chat knowledge is published',()=>{
 const docs=[{id:'a',status:'processing'},{id:'b',status:'ready'},{id:'c',status:'ready',requires_reindex:true},{id:'d',status:'failed'}];
 assert.equal(vectorizeState({status:'imported',document_id:'a'},docs).state,'running');
 assert.deepEqual(vectorizeState({status:'imported',document_id:'b'},docs),{state:'publishing',label:'Indexed · publishing to chat…'});
 assert.deepEqual(vectorizeState({status:'imported',document_id:'b'},docs,['b']),{state:'ready',label:'Ready to ask'});
 assert.equal(vectorizeState({status:'already_imported',document_id:'b'},docs,['b']).label,'Already indexed · ready to ask');
 assert.equal(vectorizeState({status:'imported',document_id:'c'},docs).state,'running');
 assert.equal(vectorizeState({status:'imported',document_id:'d'},docs).state,'failed');
 assert.equal(vectorizeState({status:'imported',document_id:'missing'},docs).state,'running');
 assert.deepEqual(vectorizeState({status:'failed',message:'Too large'},docs),{state:'failed',label:'Too large'});
});

test('every storage provider has a complete step-by-step guide that renders',()=>{
 const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
 assert.deepEqual(Object.keys(CONNECTOR_GUIDES).sort(),STORAGE_PROVIDERS.map(p=>p.id).sort());
 for(const [id,guide] of Object.entries(CONNECTOR_GUIDES)){
  assert.ok(guide.time&&guide.need.length&&guide.fields.length&&guide.problems.length,id);
  assert.ok(guide.parts.length>=2&&guide.parts.every(part=>part.title&&part.steps.length),id);
  assert.equal(guide.parts.at(-1).title,'Finish in Lapi',id);
  for(const text of [...guide.need,...guide.parts.flatMap(part=>part.steps),...guide.fields.flat(),...guide.problems.flat()])assert.equal(text.split('`').length%2,1,`${id}: unbalanced backticks in ${text}`);
 }
 const html=renderToStaticMarkup(React.createElement(ConnectorGuidePanel,{guide:CONNECTOR_GUIDES.google_drive,name:'Google Drive',open:true}));
 assert.match(html,/<details class="connector-guide" open="">/);assert.match(html,/Part 1: Create a Google Cloud project/);
 assert.match(html,/<code>drive.google.com<\/code>/);assert.match(html,/What goes where/);assert.match(html,/If Test connection shows an error/);
});

test('#Add knowledge/<provider> preselects a known provider only',()=>{
 const {requestedProvider}=mod.exports;
 assert.equal(requestedProvider('#Add%20knowledge/google_drive'),'google_drive');
 assert.equal(requestedProvider('#add knowledge/SharePoint/'),'sharepoint');
 for(const id of STORAGE_PROVIDERS.map(p=>p.id))assert.equal(requestedProvider('#Add%20knowledge/'+id),id);
 for(const bad of ['#Add%20knowledge','#Add%20knowledge/dropbox','#Datasets/s3','#Add%20knowledge/s3/extra','#%E0%A4%A','',undefined&&''])assert.equal(requestedProvider(bad),'');
});
