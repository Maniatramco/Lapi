const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');

/** Mounts TemplateHelper with a fake React and a controllable consent hook. */
function mount(receipt){
 let index=0;const hooks=[],calls=[],scopes=[];
 const react={useState(initial){const slot=index++;if(!(slot in hooks))hooks[slot]=typeof initial==='function'?initial():initial;return [hooks[slot],value=>{hooks[slot]=typeof value==='function'?value(hooks[slot]):value;}];}};
 const filename=path.resolve(__dirname,'../../lapi_frontend/app/template-helper.tsx');const compiled=new Module(filename,module);compiled.paths=module.paths;
 const original=compiled.require.bind(compiled);
 const stubs={'react':react,'lucide-react':new Proxy({},{get:()=>()=>null}),'./template-helper.css':{},
  './quick-start-flow':{fieldsToSchema:()=>({type:'object',properties:{}})},
  './setup-chat-script':{suggestFields:()=>({name:'',fields:[]}),applyChange:fields=>fields,fieldList:()=>''},
  './agent-consent':{useAgentConsent:()=>({popup:null,request:async scope=>{scopes.push(scope);return receipt;}})}};
 compiled.require=id=>id in stubs?stubs[id]:original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 const props={api:(...args)=>{calls.push(args);return Promise.resolve({name:'Invoices',fields:[{key:'total',label:'Total'}]});},datasetId:'dataset',documentIds:['doc'],onCreated(){}};
 let root;const render=()=>{index=0;root=compiled.exports.TemplateHelper(props);};
 const elements=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(elements):[node,...elements(node.props?.children)];
 const button=()=>elements(root).find(node=>node.type==='button'&&node.props.title==='Read the document and propose fields');
 const flush=()=>new Promise(resolve=>setImmediate(resolve));
 render();return {render,button,calls,scopes,elements:()=>elements(root),flush};
}

test('reading the document asks for external processing first and sends nothing when declined',async()=>{
 const view=mount(null);
 view.button().props.onClick();await view.flush();view.render();
 assert.deepEqual(view.scopes,[{dataset_id:'dataset',roles:['extraction']}]);
 assert.equal(view.calls.length,0,'Declining consent must not send document text');
 const alert=view.elements().find(node=>node.props?.role==='alert');
 assert.match(alert.props.children,/not approved/);
});

test('an approved request reads the document with the approval it was given',async()=>{
 const view=mount({dataset_id:'dataset',required:true,destinations:[{key:'model'}]});
 view.button().props.onClick();await view.flush();view.render();
 assert.equal(view.calls.length,1);assert.equal(view.calls[0][0],'/templates/suggest');
 assert.equal(view.calls[0][2].allow_external,true);assert.deepEqual(view.calls[0][2].document_ids,['doc']);
 assert.ok(!view.elements().some(node=>node.props?.role==='alert'));
});

test('a local model needs no approval and the request says so',async()=>{
 const view=mount({dataset_id:'dataset',required:false,destinations:[]});
 view.button().props.onClick();await view.flush();view.render();
 assert.equal(view.calls.length,1);assert.equal(view.calls[0][2].allow_external,false);
});
