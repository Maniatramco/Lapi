const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../lapi_frontend/app/answer-chart-data.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {chartSeries,niceTicks,pieSlices,chartCsv,formatNumber,chartSummary,toNumber}=compiled.exports;
const chart={type:'bar',title:'Revenue by region',x:'Region',y:['sum of Revenue'],columns:['Region','sum of Revenue','Count'],rows:[['North',250,2],['South',120.5,2],[null,'1,000',1]]};

test('series take labels from x and numbers from the y columns only',()=>{
 const {labels,series}=chartSeries(chart);
 assert.deepEqual(labels,['North','South','(empty)']);
 assert.deepEqual(series,[{name:'sum of Revenue',values:[250,120.5,1000]}]);
 assert.equal(toNumber('abc'),null);assert.equal(toNumber(true),null);
});

test('axis ticks are round and include zero for bars',()=>{
 assert.deepEqual(niceTicks(0,250),[0,100,200,300]);
 assert.deepEqual(niceTicks(-10,40),[-20,0,20,40]);
 assert.deepEqual(niceTicks(0,0),[0,1]);
});

test('pie slices share the whole and skip zero or negative values',()=>{
 const slices=pieSlices(['A','B','C'],[30,10,0]);
 assert.deepEqual(slices.map(s=>[s.label,s.share]),[['A',0.75],['B',0.25]]);
 assert.ok(Math.abs(slices[1].end-slices[0].start-Math.PI*2)<1e-9);
});

test('CSV download keeps numbers, quotes text, and neutralises spreadsheet formulas',()=>{
 const csv=chartCsv({...chart,rows:[['=HYPERLINK("x")',-10,1],['Acme, Inc',2.5,null]]});
 assert.equal(csv,'Region,sum of Revenue,Count\r\n"\'=HYPERLINK(""x"")",-10,1\r\n"Acme, Inc",2.5,');
});

test('numbers read well and the chart has a spoken summary',()=>{
 assert.equal(formatNumber(1234567),'1.2M');assert.equal(formatNumber(12345),'12,345');assert.equal(formatNumber(2.345),'2.35');assert.equal(formatNumber(null),'–');
 assert.equal(chartSummary(chart),'Revenue by region: bar chart of sum of Revenue by Region, 3 points, from 120.5 to 1,000.');
});
