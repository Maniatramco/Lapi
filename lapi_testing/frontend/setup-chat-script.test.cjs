const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const load=(file)=>{const filename=path.resolve(__dirname,'../../lapi_frontend/app/'+file),compiled=new Module(filename,module);compiled.paths=module.paths;
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);return compiled.exports;};
// The script imports the collection types; resolve that import to the compiled module.
const scope=load('workspace-scope.ts');require.cache[path.resolve(__dirname,'../../lapi_frontend/app/workspace-scope')]={exports:scope};
Module._resolveFilename=((original)=>function(request,...rest){if(request==='./workspace-scope')return path.resolve(__dirname,'../../lapi_frontend/app/workspace-scope');return original.call(this,request,...rest);})(Module._resolveFilename);
const flow=load('quick-start-flow.ts');require.cache[path.resolve(__dirname,'../../lapi_frontend/app/quick-start-flow')]={exports:flow};
Module._resolveFilename=((original)=>function(request,...rest){if(request==='./quick-start-flow')return path.resolve(__dirname,'../../lapi_frontend/app/quick-start-flow');return original.call(this,request,...rest);})(Module._resolveFilename);
const support=load('support.ts');require.cache[path.resolve(__dirname,'../../lapi_frontend/app/support')]={exports:support};
Module._resolveFilename=((original)=>function(request,...rest){if(request==='./support')return path.resolve(__dirname,'../../lapi_frontend/app/support');return original.call(this,request,...rest);})(Module._resolveFilename);
const {cleanName,matchWorkspace,matchType,after,prompt,yes,no,suggestFields,applyChange,helpWish}=load('setup-chat-script.ts');
const me={id:'me',name:"Mani's workspace",audience:'personal',my_access:'owner',collection_count:0},team={id:'t',name:'Finance team',audience:'team',my_access:'editor',collection_count:3};

test('a spoken or typed name becomes a clean first name',()=>{
 assert.equal(cleanName("hi, I'm mani"),'Mani');
 assert.equal(cleanName('My name is Priya Sharma.'),'Priya Sharma');
 assert.equal(cleanName('call me arjun'),'Arjun');
 assert.equal(cleanName('   '),'');
});

test('yes and no are understood in everyday words',()=>{
 assert.ok(yes('Yes please')&&yes('sure')&&yes('ok'));
 assert.ok(no('not now')&&no('No')&&no('later'));
 assert.ok(!yes('maybe')&&!no('maybe'));
});

test('workspaces and types match by name, tap or part of the name',()=>{
 assert.equal(matchWorkspace([me,team],'finance').id,'t');
 assert.equal(matchWorkspace([me,team],'t').id,'t');
 assert.equal(matchWorkspace([me,team],"mani's").id,'me');
 assert.equal(matchType('finance'),'Finance');
 assert.equal(matchType('skip'),'');
 assert.equal(matchType('Tax returns'),'Tax returns');
});

test('fields are prefilled from everyday words, then changed by them',()=>{
 const invoices=suggestFields('invoice totals and due dates','Finance');
 assert.equal(invoices.name,'Invoices');
 assert.ok(invoices.fields.some(f=>f.label==='Total amount')&&invoices.fields.some(f=>f.label==='Due date'));
 assert.ok(!invoices.fields.some(f=>/^(Invoice totals|Due dates)$/.test(f.label)),'covered mentions are not repeated');
 const own=suggestFields('vendor, total and delivery date');
 assert.deepEqual(own.fields.map(f=>f.label).slice(-1),['Delivery date']);
 assert.equal(own.fields.find(f=>f.label==='Delivery date').type,'date');
 const resumes=suggestFields('','Resume');
 assert.ok(resumes.fields.some(f=>f.label==='Skills'));
 const changed=applyChange(invoices.fields,'add payment terms, remove currency');
 assert.ok(changed.some(f=>f.label==='Payment terms')&&!changed.some(f=>f.label==='Currency'));
 const replaced=applyChange(invoices.fields,'name, phone');
 assert.deepEqual(replaced.map(f=>f.label),['Name','Phone']);
});

test('stages skip what does not apply',()=>{
 assert.equal(after('name',{workspaces:[me],current:me,canCreateTeam:true,chosen:true}),'team');
 assert.equal(after('name',{workspaces:[me],current:me,canCreateTeam:false,chosen:true}),'collection');
 assert.equal(after('team',{workspaces:[me,team],current:me,canCreateTeam:true,chosen:false}),'choose');
 assert.equal(after('choose',{workspaces:[me,team],current:team,canCreateTeam:true,chosen:true}),'done');
 assert.equal(after('type',{workspaces:[me],current:me,canCreateTeam:true,chosen:true}),'done');
 assert.equal(after('type',{workspaces:[me],current:me,canCreateTeam:true,chosen:true,created:true}),'interest');
 assert.match(prompt('team',{name:'Mani Tram',workspaces:[me],current:me,canCreateTeam:true}).text,/Nice to meet you, Mani\./);
 assert.equal(prompt('choose',{name:'',workspaces:[me,team],canCreateTeam:true}).quick.length,2);
});

test('the Help Bot understands what people want in a few words',()=>{
 assert.equal(helpWish('something is broken'),'email');
 assert.equal(helpWish('I want to pull out invoice totals'),'extract');
 assert.equal(helpWish('share with my team'),'team');
 assert.equal(helpWish('make a new collection'),'collection');
 assert.equal(helpWish('hello'),'');
 assert.ok(prompt('help',{name:'Mani',workspaces:[me],current:me,canCreateTeam:true}).quick.some(q=>/Email/.test(q.label)));
});
