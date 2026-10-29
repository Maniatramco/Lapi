const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/walkthrough-data.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {SCENES,TOUR_VERSION,totalSeconds,clampScene,nextScene,previousScene,sceneStart,sceneAt,segmentFill,formatClock,shouldShowTour,wordsPerSecond,pickVoice,MOBILE_SCENES,scenesFor}=compiled.exports;

test('seven scenes tell Connect, Unify, Ask in about one minute, each with a caption',()=>{
 assert.deepEqual(SCENES.map(s=>s.id),['welcome','connect','unify','ask','extract','skills','secure']);
 const total=totalSeconds();assert.ok(total>=55&&total<=75,`total ${total}`);assert.equal(total,69);
 assert.deepEqual(SCENES.map((_,i)=>sceneStart(i)),[0,7,17,29,41,51,60]);
 for(const scene of SCENES){assert.ok(scene.seconds>0);assert.ok(scene.caption.length>20&&scene.caption.length<200,scene.id);}
 assert.match(SCENES[1].caption,/Add knowledge/);assert.match(SCENES[1].caption,/guide/);
 assert.match(SCENES[3].caption,/sources/);assert.match(SCENES[6].caption,/Dashboard/);assert.match(SCENES[5].caption,/skills/i);
 assert.ok(Number.isInteger(TOUR_VERSION)&&TOUR_VERSION>=1);
});

test('scene-at-time lookup finds the scene, its offset and progress, clamped to the tour',()=>{
 assert.deepEqual(sceneAt(0),{index:0,offset:0,progress:0});
 assert.equal(sceneAt(6.99).index,0);assert.equal(sceneAt(7).index,1);assert.equal(sceneAt(7).offset,0);
 assert.equal(sceneAt(23).index,2);assert.equal(sceneAt(23).offset,6);assert.equal(sceneAt(23).progress,.5);
 assert.equal(sceneAt(41).index,4);assert.equal(sceneAt(59.9).index,5);
 assert.deepEqual(sceneAt(60),{index:6,offset:0,progress:0});assert.deepEqual(sceneAt(500),{index:6,offset:9,progress:1});
 assert.deepEqual(sceneAt(-3),{index:0,offset:0,progress:0});assert.deepEqual(sceneAt(Number.NaN),{index:0,offset:0,progress:0});
 assert.deepEqual(segmentFill(23),[1,1,.5,0,0,0,0]);assert.deepEqual(segmentFill(60),[1,1,1,1,1,1,0]);assert.deepEqual(segmentFill(69),[1,1,1,1,1,1,1]);
});

test('next and previous scene clamp at both ends',()=>{
 assert.equal(nextScene(0),1);assert.equal(nextScene(6),6);assert.equal(nextScene(99),6);
 assert.equal(previousScene(3),2);assert.equal(previousScene(0),0);assert.equal(previousScene(-4),0);
 assert.equal(clampScene(2.7),2);assert.equal(clampScene(Number.NaN),0);assert.equal(clampScene(1,[]),0);
});

test('clock read-out and first-login decision',()=>{
 assert.equal(formatClock(0),'0:00');assert.equal(formatClock(7.9),'0:07');assert.equal(formatClock(60),'1:00');assert.equal(formatClock(-1),'0:00');
 assert.equal(shouldShowTour({seen:false,version:1}),true);assert.equal(shouldShowTour({seen:true,version:1}),false);
 for(const bad of [null,undefined,'no',{},{seen:'false'}])assert.equal(shouldShowTour(bad),false);
});

test('the player renders all controls, a live caption and the first scene as real text',()=>{
 const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
 const file=path.resolve(__dirname,'../../lapi_frontend/app/walkthrough.tsx'),mod=new Module(file,module);mod.filename=file;mod.paths=module.paths;
 const original=mod.require.bind(mod);mod.require=id=>id.endsWith('.css')?{}:id==='./walkthrough-data'?compiled.exports:original(id);
 mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{esModuleInterop:true,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
 const inline=renderToStaticMarkup(React.createElement(mod.exports.Walkthrough,{mode:'inline'}));
 for(const text of ['Lapi in one minute','Connect.','Unify.','Ask.','aria-live="polite"','Previous scene','Next scene','Play tour','0:00','1:09','aria-current="step"'])assert.ok(inline.includes(text),text);
 assert.equal((inline.match(/class="wt-segment"/g)||[]).length,7);assert.ok(!inline.includes('Skip tour'));
 const modal=renderToStaticMarkup(React.createElement(mod.exports.Walkthrough,{mode:'modal',onClose(){}}));
 assert.match(modal,/role="dialog"/);assert.match(modal,/aria-modal="true"/);assert.ok(modal.includes('Skip tour'));
});

test('every voice-over line can be spoken at a normal pace within its scene',()=>{
 for(const scene of SCENES)assert.ok(wordsPerSecond(scene)<=2.7,scene.id+' needs '+wordsPerSecond(scene).toFixed(2)+' words per second');
 assert.match(SCENES[2].caption,/administrator/);assert.match(SCENES[6].caption,/Quick start/);
});

test('the most natural English voice is chosen, never a non-English one',()=>{
 const voices=[{name:'Microsoft David',lang:'en-US',localService:true},{name:'Google Deutsch',lang:'de-DE',localService:false},
  {name:'Microsoft Aria Online (Natural)',lang:'en-US',localService:false},{name:'Google UK English Female',lang:'en-GB',localService:false}];
 assert.equal(pickVoice(voices).name,'Microsoft Aria Online (Natural)');
 assert.equal(pickVoice(voices.filter(v=>!/Aria/.test(v.name))).name,'Google UK English Female');
 assert.equal(pickVoice([{name:'Google Deutsch',lang:'de-DE'}]),undefined);
});

test('phones get their own tour with the same scenes and timing, narrated for taps and photos',()=>{
 assert.deepEqual(MOBILE_SCENES.map(s=>[s.id,s.seconds]),SCENES.map(s=>[s.id,s.seconds]));
 assert.equal(scenesFor('mobile'),MOBILE_SCENES);assert.equal(scenesFor('desktop'),SCENES);
 for(const scene of MOBILE_SCENES)assert.ok(wordsPerSecond(scene)<=2.7,scene.id);
 assert.match(MOBILE_SCENES[1].caption,/Tap Add/);assert.match(MOBILE_SCENES[1].caption,/photo/);assert.match(MOBILE_SCENES[1].caption,/merged/);
 assert.match(SCENES[3].caption,/keyboard shortcuts/);assert.match(SCENES[4].caption,/side by side/);
});
