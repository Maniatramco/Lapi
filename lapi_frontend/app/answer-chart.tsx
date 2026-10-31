"use client";
import {useId} from 'react';
import {Download} from 'lucide-react';
import {CHART_COLORS,chartCsv,chartSeries,chartSummary,formatNumber,niceTicks,pieSlices,toNumber,type AnswerChart} from './answer-chart-data';

const W=640,H=300,PAD={top:16,right:16,bottom:56,left:56};

function Axes({ticks,scale,labels,x}:{ticks:number[];scale:(v:number)=>number;labels:string[];x:(i:number)=>number}){
 const rotate=labels.length>6||labels.some(l=>l.length>10);
 return <g className="answer-chart-axes">
  {ticks.map(t=><g key={t}><line x1={PAD.left} x2={W-PAD.right} y1={scale(t)} y2={scale(t)} className={t===0?'answer-chart-zero':'answer-chart-grid'}/>
   <text x={PAD.left-8} y={scale(t)} dy="0.32em" textAnchor="end">{formatNumber(t)}</text></g>)}
  {labels.map((label,i)=><text key={i} x={x(i)} y={H-PAD.bottom+16} textAnchor={rotate?'end':'middle'} transform={rotate?`rotate(-35 ${x(i)} ${H-PAD.bottom+16})`:undefined}>{label.length>16?label.slice(0,15)+'…':label}</text>)}
 </g>;
}

function BarOrLine({chart}:{chart:AnswerChart}){
 const {labels,series}=chartSeries(chart);
 const values=series.flatMap(s=>s.values).filter((v):v is number=>v!==null);
 const ticks=niceTicks(Math.min(0,...values),Math.max(0,...values));
 const low=ticks[0],high=ticks[ticks.length-1];
 const scale=(v:number)=>PAD.top+(H-PAD.top-PAD.bottom)*(1-(v-low)/((high-low)||1));
 const band=(W-PAD.left-PAD.right)/Math.max(1,labels.length);
 const x=(i:number)=>PAD.left+band*(i+0.5);
 return <>
  <Axes ticks={ticks} scale={scale} labels={labels} x={x}/>
  {chart.type==='bar'?series.map((s,si)=>{const width=Math.max(2,band*0.72/series.length);return <g key={s.name} fill={CHART_COLORS[si%CHART_COLORS.length]}>
   {s.values.map((v,i)=>v===null?null:<rect key={i} x={x(i)-band*0.36+width*si} width={width-1} y={Math.min(scale(v),scale(0))} height={Math.max(1,Math.abs(scale(v)-scale(0)))} rx={3}><title>{`${labels[i]} · ${s.name}: ${formatNumber(v)}`}</title></rect>)}</g>;})
  :series.map((s,si)=>{const color=CHART_COLORS[si%CHART_COLORS.length];const points=s.values.map((v,i)=>v===null?null:[x(i),scale(v)] as const).filter((p):p is readonly [number,number]=>p!==null);
   return <g key={s.name}><polyline points={points.map(p=>p.join(',')).join(' ')} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round"/>
    {s.values.map((v,i)=>v===null?null:<circle key={i} cx={x(i)} cy={scale(v)} r={3.5} fill="#fff" stroke={color} strokeWidth={2}><title>{`${labels[i]} · ${s.name}: ${formatNumber(v)}`}</title></circle>)}</g>;})}
 </>;
}

function Scatter({chart}:{chart:AnswerChart}){
 const xi=chart.columns.indexOf(chart.x),yi=chart.columns.indexOf(chart.y[0]);
 const points=chart.rows.map(row=>[toNumber(row[xi]),toNumber(row[yi])] as const).filter((p):p is readonly [number,number]=>p[0]!==null&&p[1]!==null);
 const xt=niceTicks(Math.min(...points.map(p=>p[0])),Math.max(...points.map(p=>p[0]))),yt=niceTicks(Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[1])));
 const sx=(v:number)=>PAD.left+(W-PAD.left-PAD.right)*(v-xt[0])/((xt[xt.length-1]-xt[0])||1);
 const sy=(v:number)=>PAD.top+(H-PAD.top-PAD.bottom)*(1-(v-yt[0])/((yt[yt.length-1]-yt[0])||1));
 return <>
  <Axes ticks={yt} scale={sy} labels={xt.map(formatNumber)} x={i=>sx(xt[i])}/>
  <g fill={CHART_COLORS[0]} fillOpacity={0.75}>{points.map((p,i)=><circle key={i} cx={sx(p[0])} cy={sy(p[1])} r={4.5}><title>{`${chart.x}: ${formatNumber(p[0])} · ${chart.y[0]}: ${formatNumber(p[1])}`}</title></circle>)}</g>
 </>;
}

function Pie({chart}:{chart:AnswerChart}){
 const {labels,series}=chartSeries(chart);
 const slices=pieSlices(labels,series[0]?.values||[]);
 const cx=170,cy=H/2,r=110;
 const arc=(a:number)=>[cx+r*Math.cos(a),cy+r*Math.sin(a)];
 return <>
  {slices.map((s,i)=>{const [x1,y1]=arc(s.start),[x2,y2]=arc(s.end-1e-6);const large=s.end-s.start>Math.PI?1:0;
   return <path key={s.label} d={slices.length===1?`M ${cx} ${cy-r} A ${r} ${r} 0 1 1 ${cx-0.01} ${cy-r} Z`:`M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`}
    fill={CHART_COLORS[i%CHART_COLORS.length]} stroke="#fff" strokeWidth={2}><title>{`${s.label}: ${formatNumber(s.value)} (${Math.round(s.share*100)}%)`}</title></path>;})}
  <g className="answer-chart-legend">{slices.map((s,i)=><g key={s.label} transform={`translate(330 ${40+i*30})`}>
   <rect width={14} height={14} rx={3} fill={CHART_COLORS[i%CHART_COLORS.length]}/>
   <text x={22} y={11}>{(s.label.length>22?s.label.slice(0,21)+'…':s.label)+' · '+formatNumber(s.value)+' ('+Math.round(s.share*100)+'%)'}</text></g>)}</g>
 </>;
}

/** A chart from an exact spreadsheet calculation, with its data table and a CSV download. */
export function AnswerChartView({chart,onSource}:{chart:AnswerChart;onSource?:(index:number)=>void}){
 const titleId=useId();
 const {series}=chartSeries(chart);
 const download=()=>{const url=URL.createObjectURL(new Blob(['﻿'+chartCsv(chart)],{type:'text/csv;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download=(chart.title||'chart').replace(/[^\w\- ]+/g,'').trim().slice(0,60)+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 return <figure className="answer-chart" aria-labelledby={titleId}>
  <figcaption id={titleId} className="answer-chart-title">{chart.title}</figcaption>
  {chart.type!=='pie'&&series.length>1&&<ul className="answer-chart-key">{series.map((s,i)=><li key={s.name}><i style={{background:CHART_COLORS[i%CHART_COLORS.length]}}/>{s.name}</li>)}</ul>}
  <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={chartSummary(chart)} className="answer-chart-svg">
   {chart.type==='pie'?<Pie chart={chart}/>:chart.type==='scatter'?<Scatter chart={chart}/>:<BarOrLine chart={chart}/>}
  </svg>
  <div className="answer-chart-foot">
   <span>{chart.source||'Calculated from your spreadsheet'}{chart.source_index?<> <button type="button" className="agent-citation" aria-label={`Open citation ${chart.source_index}`} onClick={()=>onSource?.(chart.source_index!)}>[{chart.source_index}]</button></>:null}{chart.truncated?' · first rows only':''}</span>
   <button type="button" className="text-button" onClick={download}><Download size={14}/> Download data</button>
  </div>
  <details className="answer-chart-data"><summary>Show the numbers</summary>
   <div className="answer-chart-table" tabIndex={0}><table><thead><tr>{chart.columns.map(c=><th key={c} scope="col">{c}</th>)}</tr></thead>
    <tbody>{chart.rows.map((row,i)=><tr key={i}>{row.map((v,j)=><td key={j}>{typeof v==='number'?formatNumber(v):v===null?'':String(v)}</td>)}</tr>)}</tbody></table></div>
  </details>
 </figure>;
}
