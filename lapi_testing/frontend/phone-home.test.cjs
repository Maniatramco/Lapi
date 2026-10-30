const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const load=name=>{const filename=path.resolve(__dirname,'../../lapi_frontend/app/'+name),compiled=new Module(filename,module);compiled.paths=module.paths;
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);return compiled.exports;};
const {greeting,readingNow,readyCount,suggestions}=load('phone-home-data.ts');
const {howBadge,columnValue}=load('quick-start-flow.ts');

const docs=[
 {id:'a',name:'ledger.xlsx',dataset_id:'d1',status:'ready',created_at:3},
 {id:'b',name:'policy.pdf',dataset_id:'d1',status:'ready',created_at:5},
 {id:'c',name:'old.pdf',dataset_id:'d1',status:'ready',requires_reindex:true,created_at:1},
 {id:'d',name:'scan.png',dataset_id:'d1',status:'processing',created_at:9},
 {id:'e',name:'queued.docx',dataset_id:'d1',status:'queued',created_at:8},
 {id:'f',name:'other.pdf',dataset_id:'d2',status:'processing',created_at:10}];
const jobs=[{document_id:'d',created_at:1,workflow:{current:'ocr',stages:{upload:{status:'completed'},extract:{status:'completed'},ocr:{status:'running'},index:{status:'pending'}}}}];

test('the phone Home greets by time of day',()=>{
 assert.equal(greeting(3),'Good evening');assert.equal(greeting(9),'Good morning');assert.equal(greeting(14),'Good afternoon');assert.equal(greeting(20),'Good evening');
});

test('ready documents exclude ones needing a reindex and stay in the chosen dataset',()=>{
 assert.equal(readyCount(docs,'d1'),2);assert.equal(readyCount(docs),2);assert.equal(readyCount(docs,'d2'),0);
});

test('Reading now shows the newest files still processing with their step and share of stages done',()=>{
 assert.deepEqual(readingNow(docs,jobs,'d1'),[{id:'d',name:'scan.png',step:'Reading images',progress:50},{id:'e',name:'queued.docx',step:'Waiting to start',progress:0}]);
 assert.equal(readingNow(docs,jobs).length,3);
});

test('suggested questions start from the newest ready files',()=>{
 assert.deepEqual(suggestions(docs,'d1'),['What is in policy?','What is in ledger?','Summarise what changed recently']);
 assert.deepEqual(suggestions(docs,'d2'),[]);
});

test('each mapped field gets a short badge saying how its column was chosen',()=>{
 const doc={whole_fields:['total'],fields:{invoice:{sheet:'T',column:'Reference No',how:'by meaning',confidence:.9},amount:{sheet:'T',column:'Amount',how:'same name'},
  country:{sheet:'Vendors',column:'Country',how:'by meaning',via:{column:'Counterparty',key:'Name'}},vendor:{sheet:'T',column:'Payee',how:'similar name'}}};
 assert.deepEqual(howBadge(doc,'invoice',columnValue('T','Reference No')),{kind:'meaning',label:'By meaning'});
 assert.deepEqual(howBadge(doc,'amount',columnValue('T','Amount')),{kind:'same',label:'Same name'});
 assert.deepEqual(howBadge(doc,'country',columnValue('Vendors','Country')),{kind:'linked',label:'Linked sheet'});
 assert.deepEqual(howBadge(doc,'vendor',columnValue('T','Payee')),{kind:'similar',label:'Similar name'});
 assert.deepEqual(howBadge(doc,'invoice',columnValue('T','Amount')),{kind:'you',label:'Your choice'});
 assert.deepEqual(howBadge(doc,'receipt','row'),{kind:'row',label:'AI per row'});
 assert.deepEqual(howBadge(doc,'total',''),{kind:'whole',label:'Ask in chat'});
 assert.deepEqual(howBadge(doc,'terms',''),{kind:'none',label:'No column'});
});
