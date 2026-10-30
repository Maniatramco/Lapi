const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.resolve(__dirname,'../../lapi_frontend/app/first-workspace.tsx'),'utf8');
const rule=/export const needsFirstWorkspace=\((.*?)\)=>(.*);/.exec(source);
const needs=new Function('workspaces','loaded','later','return '+rule[2]);

test('first sign-in asks for a workspace only when none is active and the list has loaded',()=>{
 assert.equal(needs([],true,false),true);
 assert.equal(needs([{id:'a',active:false}],true,false),true);
 assert.equal(needs([],false,false),false);  // Still loading: never flash the question.
 assert.equal(needs([{id:'a'}],true,false),false);
 assert.equal(needs([{id:'a',active:true}],true,false),false);
 assert.equal(needs([],true,true),false);  // "Not now" holds for this session.
});

test('the first workspace uses the same create and default-model calls as Quick start',()=>{
 assert.match(source,/api\('\/datasets','POST',\{name:value,description:''\}\)/);
 assert.match(source,/migrate-settings`,'POST',\{\}\)/);
});
