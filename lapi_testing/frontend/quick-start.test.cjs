const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/quick-start-flow.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {stepsFor,uploadable,askable,fileState,progress,pickFiles,sourceName,defaultDatasetName,fieldKey,fieldsToSchema,fieldProblems,resultRows,MAX_FILES,canMerge,mergeByDefault,mergedName,extractionStages,recordCount,initialChoices,columnMapping,howChosen,columnValue}=compiled.exports;
const datasets=[{id:'v',name:'Policies',my_access:'viewer'},{id:'e',name:'Contracts',my_access:'editor'},{id:'o',name:'Old',my_access:'owner',active:false}];

test('people who can add documents choose to ask or extract; Viewers choose a collection and ask',()=>{
 assert.deepEqual(stepsFor(datasets,false),['dataset','documents','processing','choose','ask','done']);
 assert.deepEqual(stepsFor(datasets,false,'extract'),['dataset','documents','processing','choose','prompt','extracting','done']);
 assert.deepEqual(stepsFor([datasets[0]],false),['dataset','ask','done']);
 assert.deepEqual(stepsFor([],true),['dataset','documents','processing','choose','ask','done']);
 assert.deepEqual(uploadable(datasets,false).map(d=>d.id),['e']);
 assert.deepEqual(uploadable(datasets,true).map(d=>d.id),['v','e']);
 assert.deepEqual(askable(datasets).map(d=>d.id),['v','e']);
});

test('reading progress finishes when no file is still being read',()=>{
 assert.equal(fileState('queued'),'working');assert.equal(fileState('processing'),'working');
 assert.equal(fileState('ready'),'ready');assert.equal(fileState('failed'),'failed');
 assert.deepEqual(progress(['ready','working']),{ready:1,failed:0,total:2,finished:false,percent:50});
 assert.deepEqual(progress(['ready','failed']),{ready:1,failed:1,total:2,finished:true,percent:100});
 assert.equal(progress([]).finished,false);
});

test('only files Lapi can read are kept, at most ten, with a note about the rest',()=>{
 const file=(name,type='')=>({name,type,size:1000});
 const picked=pickFiles([file('a.pdf'),file('photo','image/jpeg'),file('b.exe'),file('c.DOCX')]);
 assert.deepEqual(picked.files.map(f=>f.name),['a.pdf','photo','c.DOCX']);
 assert.match(picked.note,/1 file was skipped/);
 assert.equal(pickFiles(Array.from({length:12},(_,i)=>file(i+'.txt'))).files.length,MAX_FILES);
 assert.equal(pickFiles([file('x.txt')]).note,'');
});

test('sources and default names read well',()=>{
 assert.equal(sourceName({title:'Lease.pdf',page:3}),'Lease.pdf · page 3');
 assert.equal(sourceName({}),'Source');
 assert.equal(defaultDatasetName('poorni',new Date('2026-10-28T10:00:00Z')),"poorni's documents Oct 2026");
});

test('edited fields become a strict Lapi prompt schema',()=>{
 assert.equal(fieldKey('Due date'),'due_date');assert.equal(fieldKey('Due date',['due_date']),'due_date_2');assert.equal(fieldKey('2nd party'),'f_2nd_party');assert.equal(fieldKey('!!'),'field');
 const fields=[{key:'due_date',label:'Due date',type:'date',description:'As YYYY-MM-DD.'},{key:'amount',label:'Amount',type:'number',description:'Plain number.'},
  {key:'paid',label:'Paid',type:'yes_no',description:'Whether it is paid.'},{key:'items',label:'Items',type:'list',description:'Line items.'}];
 const schema=fieldsToSchema(fields);
 assert.deepEqual(schema.required,['due_date','amount','paid','items']);assert.equal(schema.additionalProperties,false);
 assert.deepEqual(schema.properties.due_date,{type:['string','null'],format:'date',description:'Due date: As YYYY-MM-DD.'});
 assert.deepEqual(schema.properties.paid.type,['boolean','null']);assert.deepEqual(schema.properties.items.items,{type:'string'});
 assert.deepEqual(fieldProblems(fields),[]);
 assert.match(fieldProblems([])[0],/at least one/);
 assert.ok(fieldProblems([{...fields[0],description:' '}]).some(p=>/description/.test(p)));
 assert.ok(fieldProblems([fields[0],fields[0]]).some(p=>/same name/.test(p)));
});

test('extracted values show as labelled rows, missing ones as Not found',()=>{
 const fields=[{key:'due_date',label:'Due date',type:'date',description:'x'}];
 assert.deepEqual(resultRows({due_date:'2026-03-01',paid:true,items:['a','b'],note:null},fields),[
  {label:'Due date',value:'2026-03-01'},{label:'paid',value:'Yes'},{label:'items',value:'a, b'},{label:'note',value:'Not found'}]);
 assert.deepEqual(resultRows([{due_date:'x'}],fields),[{label:'Due date',value:'x'}]);
 assert.deepEqual(resultRows(null,fields),[]);
});

test('several files can be merged into one document; photos merge by default',()=>{
 const photo=n=>({name:n+'.jpg',type:'image/jpeg'}),pdf=n=>({name:n+'.pdf',type:'application/pdf'});
 assert.equal(canMerge([photo('a')]),false);assert.equal(canMerge([photo('a'),pdf('b')]),true);
 assert.equal(mergeByDefault([photo('page1'),photo('page2')]),true);assert.equal(mergeByDefault([photo('a'),pdf('b')]),false);
 assert.equal(mergedName([pdf('Invoice'),pdf('Annex'),photo('p3')]),'Invoice + 2 more');
});

test('the extraction workflow follows the real extraction status',()=>{
 const states=s=>extractionStages(s,2).map(stage=>stage.state);
 assert.deepEqual(states('saved'),['on','todo','todo','todo','todo']);
 assert.deepEqual(states('queued'),['done','on','todo','todo','todo']);
 assert.deepEqual(states('running'),['done','done','on','todo','todo']);
 assert.deepEqual(states('ready'),['done','done','done','done','done']);
 assert.deepEqual(states('failed'),['done','done','failed','todo','todo']);
 // The failure is marked where it happened, not always on the worker step.
 assert.deepEqual(extractionStages('failed',2,'running').map(x=>x.state),['done','done','failed','todo','todo']);
 assert.deepEqual(extractionStages('failed',2,'queued','Model provider rejected the request').map(x=>x.state),['done','done','failed','todo','todo']);
 assert.deepEqual(extractionStages('failed',2,'blocked','Source indexing failed. Correct/retry the source job').map(x=>x.state),['done','failed','todo','todo','todo']);
 assert.deepEqual(extractionStages('failed',2,'queued','Worker recovery attempts exhausted').map(x=>x.state),['done','failed','todo','todo','todo']);
 assert.match(extractionStages('running',1)[2].label,/Reading 1 document with/);
});

test('a record list shows the first record\'s own fields and counts every record',()=>{
 const result={records:[{source_filename:'ledger.xlsx · Transactions row 2',source_key:'d#1:2',fields:{transaction_id:'TXN-100001',amount:10}},{source_filename:'ledger.xlsx · Transactions row 3',source_key:'d#1:3',fields:{transaction_id:'TXN-100002',amount:11.25}}]};
 const rows=resultRows(result,[{key:'transaction_id',label:'Transaction ID',type:'text',description:''},{key:'amount',label:'Amount',type:'number',description:''}]);
 assert.deepEqual(rows,[{label:'Transaction ID',value:'TXN-100001'},{label:'Amount',value:'10'}]);
 assert.equal(recordCount(result),2);assert.equal(recordCount({total:1}),1);assert.equal(recordCount(null),0);
});

test('spreadsheet fields show how they will be read and the person can change them',()=>{
 const doc={document_id:'d',name:'ledger.xlsx',sheet:'Transactions',rows:6,row_fields:['dispute'],whole_fields:['total'],unmatched:['total','paid'],
  fields:{invoice:{sheet:'Transactions',column:'Reference No',how:'by meaning',confidence:0.93},country:{sheet:'Vendors',column:'Country',how:'by meaning',confidence:0.9,via:{column:'Counterparty',key:'Name',strength:'proven'}}},
  columns:[{sheet:'Transactions',column:'Reference No'},{sheet:'Vendors',column:'Country'},{sheet:'Transactions',column:'Amount (USD)'}]};
 const picks=initialChoices(doc,['invoice','country','dispute','total','paid']);
 assert.deepEqual(picks,{invoice:columnValue('Transactions','Reference No'),country:columnValue('Vendors','Country'),dispute:'row',total:'',paid:''});
 assert.equal(howChosen(doc,'invoice',picks.invoice),'Matched by meaning (93% sure)');
 assert.equal(howChosen(doc,'country',picks.country),'Matched by meaning (90% sure) through Counterparty → Vendors.Name');
 assert.match(howChosen(doc,'total',''),/whole table/);assert.match(howChosen(doc,'dispute','row'),/each row/);
 picks.paid=columnValue('Transactions','Amount (USD)');
 assert.equal(howChosen(doc,'paid',picks.paid),'Chosen by you');
 assert.deepEqual(columnMapping(picks),{invoice:{sheet:'Transactions',column:'Reference No'},country:{sheet:'Vendors',column:'Country'},total:null,paid:{sheet:'Transactions',column:'Amount (USD)'}});
});
