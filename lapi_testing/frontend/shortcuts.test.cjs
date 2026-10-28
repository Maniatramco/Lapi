const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/shortcuts.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {resolveShortcut,isTypingTarget,INITIAL_STATE,SEQUENCE_MS,SHORTCUT_LIST,GO_TARGETS,shortcutHint}=compiled.exports;
const everyone={isAdmin:false,canAddKnowledge:true},viewerOnly={isAdmin:false,canAddKnowledge:false};
const el=(tagName,attrs={},extra={})=>({tagName,getAttribute:name=>name in attrs?attrs[name]:null,...extra});
const body=el('BODY');
const press=(key,state=INITIAL_STATE,access=everyone,now=1000,extra={})=>resolveShortcut({key,target:body,...extra},state,access,now);
const sequence=(first,second,access=everyone,gap=200)=>{const a=press(first,INITIAL_STATE,access,1000);return press(second,a.state,access,1000+gap);};

test('single keys: ? help, / focus, n new chat, Esc closes',()=>{
 assert.deepEqual(press('?').command,{type:'help'});
 assert.deepEqual(press('/').command,{type:'focus'});
 assert.deepEqual(press('n').command,{type:'new-chat'});
 assert.deepEqual(press('N').command,{type:'new-chat'});
 assert.deepEqual(press('Escape').command,{type:'escape'});
 assert.equal(press('x').command,null);assert.equal(press('Enter').command,null);
});

test('g then a letter goes to a page; other letters and slow second keys cancel',()=>{
 assert.deepEqual(press('g').command,{type:'pending'});
 assert.deepEqual(sequence('g','d').command,{type:'go',view:'Home',label:'Dashboard'});
 assert.equal(sequence('g','a').command.view,'Lapi agent V2');
 assert.equal(sequence('g','k').command.view,'Add knowledge');
 assert.equal(sequence('g','s').command.view,'Datasets');
 assert.equal(sequence('g','u').command.view,'Users & passwords');
 assert.equal(sequence('G','D').command.view,'Home');
 assert.equal(sequence('g','z').command,null);
 assert.deepEqual(sequence('g','d').state,INITIAL_STATE);
 // Too slow: "d" alone does nothing and "n" is its own shortcut again.
 assert.equal(sequence('g','d',everyone,SEQUENCE_MS+1).command,null);
 assert.deepEqual(sequence('g','n',everyone,SEQUENCE_MS+1).command,{type:'new-chat'});
});

test('role visibility: people who cannot add knowledge are told why instead of navigating',()=>{
 const denied=sequence('g','k',viewerOnly).command;
 assert.equal(denied.type,'denied');assert.match(denied.message,/Editor access/);
 assert.equal(sequence('g','d',viewerOnly).command.type,'go');
 assert.ok(GO_TARGETS.every(t=>!['Access map','Token usage','Storage','Model Registration'].includes(t.view)),'no administrator pages are reachable by shortcut');
});

test('never while typing or with modifier keys',()=>{
 for(const target of [el('INPUT'),el('INPUT',{type:'search'}),el('input',{},{type:'email'}),el('TEXTAREA'),el('SELECT'),el('DIV',{},{isContentEditable:true}),el('DIV',{contenteditable:'true'}),el('DIV',{role:'textbox'})]){
  assert.equal(isTypingTarget(target),true,JSON.stringify(target));
  for(const key of ['?','/','n','g'])assert.equal(resolveShortcut({key,target},INITIAL_STATE,everyone,0).command,null);
 }
 for(const target of [el('INPUT',{},{type:'checkbox'}),el('BUTTON'),el('A'),el('DIV',{contenteditable:'false'}),body,null,undefined,'text'])assert.equal(isTypingTarget(target),false,String(target&&target.tagName));
 for(const modifier of ['ctrlKey','metaKey','altKey'])assert.equal(press('n',INITIAL_STATE,everyone,0,{[modifier]:true}).command,null);
 assert.equal(press('n',INITIAL_STATE,everyone,0,{isComposing:true}).command,null);
 assert.equal(press('g',INITIAL_STATE,everyone,0,{repeat:true}).command,null);
 // Typing interrupts a pending "g".
 const pending=press('g').state;assert.equal(resolveShortcut({key:'d',target:el('INPUT')},pending,everyone,1100).command,null);
 // Escape still closes dialogs from inside a field.
 assert.deepEqual(resolveShortcut({key:'Escape',target:el('INPUT')},INITIAL_STATE,everyone,0).command,{type:'escape'});
});

test('the help list and navigation tooltips describe every shortcut',()=>{
 const actions=SHORTCUT_LIST.map(item=>item.action);
 for(const expected of ['Show keyboard shortcuts','Search, or type in the chat','Go to Dashboard','Go to Lapi Agent','Go to Add knowledge','Go to Datasets','Go to Users & passwords','New chat in Lapi Agent','Close a dialog'])assert.ok(actions.includes(expected),expected);
 assert.equal(shortcutHint('Home'),' (G then D)');assert.equal(shortcutHint('Users & passwords'),' (G then U)');assert.equal(shortcutHint('Access map'),'');
});
