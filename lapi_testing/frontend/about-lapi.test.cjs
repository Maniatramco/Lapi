const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const file=path.resolve(__dirname,'../../lapi_frontend/app/about-lapi.tsx'),mod=new Module(file,module);mod.filename=file;mod.paths=module.paths;const original=mod.require.bind(mod);
// The About screen embeds the tour player: compile its local TypeScript modules on the fly.
const compileLocal=id=>{const base=path.resolve(path.dirname(file),id),source=fs.existsSync(base+'.tsx')?base+'.tsx':base+'.ts';const child=new Module(source,mod);child.filename=source;child.paths=module.paths;child.require=inner=>inner.endsWith('.css')?{}:inner.startsWith('./')?compileLocal(inner):original(inner);child._compile(ts.transpileModule(fs.readFileSync(source,'utf8'),{compilerOptions:{esModuleInterop:true,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,source);return child.exports;};
mod.require=id=>id.endsWith('.css')?{}:id==='./walkthrough'?compileLocal(id):original(id);
mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{esModuleInterop:true,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
const release=require('../../lapi_frontend/app/application-version.json');
test('About presents the current version and complete prior feature history from the shared version source',()=>{
 const html=renderToStaticMarkup(React.createElement(mod.exports.AboutLapi));assert.match(release.version,/^\d+\.\d+\.\d+\.\d+$/);assert.ok(release.releases.some(item=>item.version==='26.1.1.0'));assert.equal(release.releases[0].version,release.version);
 const escaped=text=>renderToStaticMarkup(React.createElement(React.Fragment,null,text));
 for(const entry of release.releases){assert.ok(html.includes('v'+entry.version));for(const change of entry.changes)assert.ok(html.includes(escaped(change)),change);}
 const changelog=fs.readFileSync(path.resolve(__dirname,'../../CHANGELOG.md'),'utf8');for(const entry of release.releases)assert.ok(changelog.includes(entry.version));assert.match(html,/Current version/);
});
test('About walks through one workspace from predefined prompts to the golden copy',()=>{
 const html=renderToStaticMarkup(React.createElement(mod.exports.AboutLapi));
 for(const text of ['My account','Contracts','Predefined prompts','Extract key terms','Supplier agreement.pdf','Structured fields','Reviewer approved','Answers with evidence','Knowledge base','Golden copy','Models mapped per workspace'])assert.ok(html.includes(text),text);
 for(const label of ['asks','indexed','approved'])assert.ok(html.includes(`data-label="${label}"`),label);
 assert.match(html,/<figure class="about-diagram golden" aria-labelledby="about-flow-title">/);assert.ok(html.includes('<mark>$48,500</mark>'));
});
