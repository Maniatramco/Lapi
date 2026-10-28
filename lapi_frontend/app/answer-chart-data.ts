/** Charts the agent draws from exact spreadsheet calculations (query_table): pure helpers, unit tested.
 * The numbers always come from the computed rows sent with the answer, never from the model's text. */
export type ChartType='bar'|'line'|'pie'|'scatter';
export type Cell=string|number|boolean|null;
export type AnswerChart={type:ChartType;title:string;x:string;y:string[];columns:string[];rows:Cell[][];source?:string;source_index?:number;truncated?:boolean};
export type Series={name:string;values:(number|null)[]};

export const CHART_COLORS=['#2563eb','#fb923c','#5b5fe8','#0f9d8a','#c0759a','#64748b','#eab308','#1e3a8a'];

export function toNumber(value:Cell):number|null{
 if(typeof value==='number')return Number.isFinite(value)?value:null;
 if(typeof value==='string'&&value.trim()!==''){const n=Number(value.replace(/,/g,''));return Number.isFinite(n)?n:null;}
 return null;
}

/** Category labels from the x column and one numeric series per y column. */
export function chartSeries(chart:AnswerChart):{labels:string[];series:Series[]}{
 const xi=chart.columns.indexOf(chart.x);
 const labels=chart.rows.map(row=>{const v=xi>=0?row[xi]:null;return v===null||v===''?'(empty)':String(v);});
 const series=chart.y.map(name=>({name,index:chart.columns.indexOf(name)})).filter(s=>s.index>=0)
  .map(({name,index})=>({name,values:chart.rows.map(row=>toNumber(row[index]))}));
 return {labels,series};
}

/** Round axis ticks covering min..max (always including 0 for bars). */
export function niceTicks(min:number,max:number,count=5):number[]{
 if(!Number.isFinite(min)||!Number.isFinite(max))return [0,1];
 if(min===max){if(min===0)return [0,1];min=Math.min(0,min);max=Math.max(0,max);}
 const raw=(max-min)/Math.max(1,count-1),power=10**Math.floor(Math.log10(raw)),step=[1,2,2.5,5,10].map(f=>f*power).find(s=>s>=raw)||raw;
 const start=Math.floor(min/step)*step,end=Math.ceil(max/step)*step,ticks:number[]=[];
 for(let v=start;v<=end+step/2;v+=step)ticks.push(Number(v.toPrecision(12)));
 return ticks;
}

export type Slice={label:string;value:number;share:number;start:number;end:number};
/** Pie slices (positive values only) with angles in radians, starting at the top. */
export function pieSlices(labels:string[],values:(number|null)[]):Slice[]{
 const items=labels.map((label,i)=>({label,value:values[i]??0})).filter(item=>item.value>0);
 const total=items.reduce((sum,item)=>sum+item.value,0);
 let angle=-Math.PI/2;
 return items.map(item=>{const share=total?item.value/total:0,start=angle;angle+=share*Math.PI*2;return {...item,share,start,end:angle};});
}

export function formatNumber(value:number|null):string{
 if(value===null)return '–';
 const abs=Math.abs(value);
 if(abs>=1e9)return (value/1e9).toFixed(abs>=1e10?0:1).replace(/\.0$/,'')+'B';
 if(abs>=1e6)return (value/1e6).toFixed(abs>=1e7?0:1).replace(/\.0$/,'')+'M';
 if(abs>=1e4)return Math.round(value).toLocaleString('en');
 return Number.isInteger(value)?value.toLocaleString('en'):value.toLocaleString('en',{maximumFractionDigits:2});
}

/** The chart's data as CSV (quoted where needed), for "Download data". */
export function chartCsv(chart:AnswerChart):string{
 const cell=(v:Cell)=>{
  if(typeof v==='number'||typeof v==='boolean')return String(v);
  let text=v===null?'':String(v);
  // Text that a spreadsheet would run as a formula is kept as text.
  if(/^[=+\-@\t\r]/.test(text)&&toNumber(text)===null)text="'"+text;
  return /[",\n\r]/.test(text)?'"'+text.replace(/"/g,'""')+'"':text;
 };
 return [chart.columns,...chart.rows].map(row=>row.map(cell).join(',')).join('\r\n');
}

/** One sentence describing the chart for screen readers. */
export function chartSummary(chart:AnswerChart):string{
 const {labels,series}=chartSeries(chart);
 const first=series[0];
 if(!first||!labels.length)return chart.title;
 const values=first.values.filter((v):v is number=>v!==null);
 const max=Math.max(...values),min=Math.min(...values);
 return `${chart.title}: ${chart.type} chart of ${first.name} by ${chart.x}, ${labels.length} points, from ${formatNumber(min)} to ${formatNumber(max)}.`;
}
