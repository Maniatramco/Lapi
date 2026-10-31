const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const load=name=>{const filename=path.resolve(__dirname,'../../lapi_frontend/app/'+name),compiled=new Module(filename,module);compiled.paths=module.paths;
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);return compiled.exports;};
const {readingNow,extractionsRunning}=load('phone-home-data.ts');
const {howBadge,columnValue}=load('quick-start-flow.ts');
const {viewAllowed,phoneRedirect}=load('screens-client.ts');
const {answerReadings,citedRows,recordStep}=load('answer-reading.ts');

const docs=[
 {id:'a',name:'ledger.xlsx',dataset_id:'d1',status:'ready',created_at:3},
 {id:'d',name:'scan.png',dataset_id:'d1',status:'processing',created_at:9},
 {id:'e',name:'queued.docx',dataset_id:'d1',status:'queued',created_at:8},
 {id:'f',name:'other.pdf',dataset_id:'d2',status:'processing',created_at:10}];
const jobs=[{document_id:'d',created_at:1,kind:'index',status:'running',workflow:{current:'ocr',stages:{upload:{status:'completed'},extract:{status:'completed'},ocr:{status:'running'},index:{status:'pending'}}}},{kind:'extract',status:'running'},{kind:'extract',status:'completed'}];

test('the status strip shows the newest files still processing with their step and share of stages done',()=>{
 assert.deepEqual(readingNow(docs,jobs,'d1'),[{id:'d',name:'scan.png',step:'Reading images',progress:50},{id:'e',name:'queued.docx',step:'Waiting to start',progress:0}]);
 assert.equal(readingNow(docs,jobs).length,3);
 assert.equal(extractionsRunning(jobs),1);
});

test('phones have no Dashboard for anyone and can always open Review after Quick Extract',()=>{
 const phone={device:'phone',screens:[],views:[],core:[],administrator:false};
 assert.equal(viewAllowed('Home',phone,false),false);
 assert.equal(viewAllowed('Home',{...phone,administrator:true},true),false);
 assert.equal(viewAllowed('Lapi agent V2',phone,false),true);
 assert.equal(viewAllowed('Extract',phone,false),true);
 assert.equal(viewAllowed('Datasets',phone,false),false);
 assert.equal(viewAllowed('Datasets',phone,true),true);
 assert.equal(viewAllowed('Home',{...phone,device:'computer'},false),true);
 assert.equal(phoneRedirect('Home','phone'),true);
 assert.equal(phoneRedirect('Home','computer'),false);
 assert.equal(phoneRedirect('Extract','phone'),false);
});

test('how the question was read comes from the calculation that ran',()=>{
 const reading={filters:[{column:'Status',op:'in',value:['Pending','Overdue']},{column:'Vendors.Country',op:'=',value:'India'}],metrics:[{op:'sum',column:'Amount (USD)'},{op:'count'}],group_by:[],
  join:{on:'Transactions.Counterparty = Vendors.Name',matched_rows:6,unmatched_rows:0},matched_rows:2,columns:['sum','count'],rows:[[8245.37,2]]};
 const [read]=answerReadings([{index:1},{index:2,reading}]);
 assert.equal(read.source,2);
 assert.deepEqual(read.headline,{label:'Sum of Amount (USD)',value:(8245.37).toLocaleString(undefined,{maximumFractionDigits:2})});
 assert.ok(read.lines.includes('Status is one of Pending, Overdue'));
 assert.ok(read.lines.includes('Vendors.Country is India'));
 assert.ok(read.lines.some(line=>line.startsWith('Joined Transactions.Counterparty = Vendors.Name')));
 assert.equal(read.lines.at(-1),'2 rows used');
 const grouped=answerReadings([{index:1,reading:{...reading,group_by:['Region']}}])[0];
 assert.equal(grouped.headline,null);assert.ok(grouped.lines.includes('Grouped by Region'));
 assert.deepEqual(answerReadings(),[]);
});

test('a citation points at its sheet and rows only when it has them',()=>{
 assert.deepEqual(citedRows({sheet:'T',rows:[3,4]}),{sheet:'T',rows:[3,4]});
 assert.deepEqual(citedRows({section:'Sheet: Transactions · row 3'}),{sheet:'Transactions',rows:[3]});
 assert.deepEqual(citedRows({},{sheet:'T',row_start:9}),{sheet:'T',rows:[9]});
 assert.equal(citedRows({section:'Sheet: Transactions'}),null);
 assert.equal(citedRows({}),null);
});

test('records page one at a time and stop at either end',()=>{
 assert.equal(recordStep('0',3,1),'1');assert.equal(recordStep('2',3,1),null);assert.equal(recordStep('0',3,-1),null);
 assert.equal(recordStep('all',3,1),'0');assert.equal(recordStep('all',3,-1),'2');
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
