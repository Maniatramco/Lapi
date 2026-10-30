const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const load=(file)=>{const filename=path.resolve(__dirname,'../../lapi_frontend/app/'+file),compiled=new Module(filename,module);compiled.paths=module.paths;
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);return compiled.exports;};
// The script imports the collection types; resolve that import to the compiled module.
const scope=load('workspace-scope.ts');require.cache[path.resolve(__dirname,'../../lapi_frontend/app/workspace-scope')]={exports:scope};
Module._resolveFilename=((original)=>function(request,...rest){if(request==='./workspace-scope')return path.resolve(__dirname,'../../lapi_frontend/app/workspace-scope');return original.call(this,request,...rest);})(Module._resolveFilename);
const {cleanName,matchWorkspace,matchType,after,prompt,yes,no}=load('setup-chat-script.ts');
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

test('stages skip what does not apply',()=>{
 assert.equal(after('name',{workspaces:[me],current:me,canCreateTeam:true,chosen:true}),'team');
 assert.equal(after('name',{workspaces:[me],current:me,canCreateTeam:false,chosen:true}),'collection');
 assert.equal(after('team',{workspaces:[me,team],current:me,canCreateTeam:true,chosen:false}),'choose');
 assert.equal(after('choose',{workspaces:[me,team],current:team,canCreateTeam:true,chosen:true}),'done');
 assert.equal(after('type',{workspaces:[me],current:me,canCreateTeam:true,chosen:true}),'done');
 assert.match(prompt('team',{name:'Mani Tram',workspaces:[me],current:me,canCreateTeam:true}).text,/Nice to meet you, Mani\./);
 assert.equal(prompt('choose',{name:'',workspaces:[me,team],canCreateTeam:true}).quick.length,2);
});
