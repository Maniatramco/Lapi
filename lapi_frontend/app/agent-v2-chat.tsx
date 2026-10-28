"use client";
import {useState} from 'react';
import {Copy,FileText,Save} from 'lucide-react';
import './agent-setup.css';
import './chat-design.css';
import {answerPhase} from './chat-phase';
import {AnswerChartView} from './answer-chart';
import {attachmentSize} from './agent-attachments';
import {CitationPanel} from './citation-panel';
import {extractionCitationId} from './citation-source';
import {agentTokenUsage,agentTokenSteps} from './agent-token-usage';
type Entity=Record<string,any>;
export function AgentRequest({text,attachments=[],pending=false}:{text:string;attachments:{name:string;size?:number}[];pending?:boolean}){
 return <div className={`agent-v2-request${pending?' agent-v2-pending':''}`}>
  {attachments.length>0&&<ul className="agent-v2-submitted-files" aria-label="Files sent with this message">{attachments.map((file,index)=><li className="agent-v2-submitted-file" key={index}><FileText size={18} aria-hidden="true"/><span><strong title={file.name}>{file.name}</strong>{file.size!==undefined&&<small>{attachmentSize(file.size)}</small>}</span></li>)}</ul>}
  {text&&<div className="agent-v2-user">{text}</div>}
 </div>;
}
export function conversationExchanges(conversation:Entity){
 const entries:Entity[]=[];
 for(const message of conversation.messages||[]){
  if(message.role==='user')entries.push({id:'history-'+message.id,historical:true,request:message.text,messageAttachments:message.attachments||[],runtime:conversation.runtime,calls:[],dataset_id:conversation.dataset_id||'',document_ids:conversation.document_ids||[],answer_mode:conversation.mode==='general'?'general':'documents',planner:{id:message.model_selection?.model_id||'',name:message.model_selection?.model_name||'Saved chat'},conversation_id:conversation.id});
  else if(message.role==='assistant'&&entries.length)entries[entries.length-1].chat=message;
 }
 return entries;
}
type AnswerLinks={citations?:Entity[];onCitation?:(source:Entity)=>void;extractionIds?:string[];onReview?:(id:string)=>void};
function visibleAnswerText(text:string,reviewActions:Entity[]=[]){
 const reviewIds=new Set(reviewActions.map(action=>String(action.extraction_id).toLowerCase()));
 // Saved conversations can still contain the old navigation footer. Keep its
 // recorded IDs, but show the Review buttons as the single navigation entry.
 return text.split(/```/g).map((part,index)=>index%2?part:part.replace(/^Extraction IDs?:[^\r\n]*/gim,line=>{
  const ids=line.match(/\b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b/gi)||[];
  return ids.length&&ids.every(id=>reviewIds.has(id.toLowerCase()))?'':line;
 })).join('```').trim();
}
function InlineText({text,citations=[],onCitation,extractionIds=[],onReview}:{text:string}&AnswerLinks){
 return <>{text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[\d+\]|\b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b)/gi).map((part,index)=>{
  const source=/^\[\d+\]$/.test(part)?citations.find(s=>s.index===Number(part.slice(1,-1))):undefined;
  const extractionId=extractionIds.find(id=>id.toLowerCase()===part.toLowerCase());
  const links={citations,onCitation,extractionIds,onReview};
  return source?<button title={`Open citation ${source.index}`} className="agent-citation" key={index} aria-label={`Open citation ${source.index}`} onClick={()=>onCitation?.(source)}>{part}</button>:extractionId?<a className="agent-extraction-link" key={index} href={`#${encodeURIComponent(`Review/${extractionId}`)}`} aria-label={`Review extraction ${extractionId}`} onClick={event=>{if(onReview&&!event.button&&!event.metaKey&&!event.ctrlKey&&!event.shiftKey&&!event.altKey){event.preventDefault();onReview(extractionId);}}}>{part}</a>:part.startsWith('**')?<strong key={index}><InlineText text={part.slice(2,-2)} {...links}/></strong>:part.startsWith('`')?<code key={index}><InlineText text={part.slice(1,-1)} {...links}/></code>:part;
 })}</>;
}
/** One line of an answer: a heading, a bulleted or numbered list item, a blank line, or plain text. */
function AnswerLine({line,links}:{line:string;links:AnswerLinks}){
 if(line.startsWith('#'))return <p><strong><InlineText text={line.replace(/^#+\s*/,'')} {...links}/></strong></p>;
 const bullet=line.match(/^\s*[-*•]\s+(.*)$/);
 if(bullet)return <div className="agent-reply-li"><InlineText text={bullet[1]} {...links}/></div>;
 const numbered=line.match(/^\s*(\d{1,3})[.)]\s+(.*)$/);
 if(numbered)return <div className="agent-reply-li" data-number={numbered[1]}><InlineText text={numbered[2]} {...links}/></div>;
 if(!line.trim())return <div className="agent-reply-gap" aria-hidden="true"/>;
 return <div><InlineText text={line} {...links}/></div>;
}
export function AgentAnswerText({text,...links}:{text:string}&AnswerLinks){
 return <div className="agent-v2-reply">{text.split(/```/g).map((part,index)=>index%2?<pre key={index}><code>{part.replace(/^\w*\n/,'')}</code></pre>:<div key={index}>{part.split('\n').map((line,row)=><AnswerLine key={row} line={line} links={links}/>)}</div>)}</div>;
}
function InstructionProposal({proposal,api,onError}:{proposal:Entity;api:(path:string,method?:string,body?:unknown)=>Promise<any>;onError:(error:string)=>void}){
 const [state,setState]=useState<'open'|'saving'|'saved'>('open');
 const save=async()=>{setState('saving');try{await api(`/datasets/${proposal.dataset_id}/instructions`,'PUT',{text:proposal.after,summary:proposal.summary||'',expected_version:proposal.current_version});setState('saved');}catch(e){setState('open');onError(e instanceof Error?e.message:'Could not save the instructions.');}};
 return <div className="agent-setup-card" aria-label="Proposed dataset instructions">
  <strong>Proposed dataset instructions{proposal.summary?` · ${proposal.summary}`:''}</strong>
  {proposal.warnings?.length>0&&<p className="agent-setup-warning small">Check before saving: {proposal.warnings.join('; ')}.</p>}
  <div className="agent-instruction-diff"><div><span className="small muted">Now (version {proposal.current_version||0})</span><pre>{proposal.before||'(none)'}</pre></div><div><span className="small muted">Proposed</span><pre>{proposal.after}</pre></div></div>
  {state==='saved'?<p className="small" role="status">Saved. New answers in this dataset use these instructions.</p>:<div className="agent-setup-actions"><button className="btn primary" disabled={state==='saving'} onClick={()=>void save()}><Save size={15}/>Save instructions</button></div>}
 </div>;
}
/** Per-answer token line; tap to expand the per-call steps when the provider reported them. */
export function AnswerTokenUsage({usage,status}:{usage:Entity|undefined;status:string}){
 const line=agentTokenUsage(usage,status);
 const steps=status==='streaming'?[]:agentTokenSteps(usage);
 if(!steps.length)return <p className="small muted agent-token-usage" aria-label="Answer token usage" title={line.title}>{line.text}</p>;
 return <details className="small muted agent-token-usage agent-token-details">
  <summary aria-label={`Answer token usage: ${line.text}. Show each model call`} title={line.title}>{line.text}</summary>
  <div className="agent-token-steps" role="region" aria-label="Model calls for this answer" tabIndex={0}>
   <table><thead><tr><th scope="col">Step</th><th scope="col">Model</th><th scope="col">Input</th><th scope="col">Cached</th><th scope="col">Output</th><th scope="col">Reasoning</th><th scope="col">Time</th><th scope="col">Approx. cost</th></tr></thead>
    <tbody>{steps.map((row,index)=><tr key={index}><th scope="row">{row.stage}</th><td className="agent-token-model" title={row.model}>{row.model}</td><td>{row.input}</td><td>{row.cached}</td><td>{row.output}</td><td>{row.reasoning}</td><td>{row.latency}</td><td>{row.cost}</td></tr>)}</tbody>
   </table>
   <p className="agent-token-note">Tokens as reported by each provider. Costs are approximate list-price estimates, not a bill.</p>
  </div>
 </details>;
}
export function AgentChatAnswer({message,api,onError,onReview,onRecovery,onFollowUp}:{message:Entity;api:(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;onError:(error:string)=>void;onReview?:(id:string)=>void;onRecovery?:(action:Entity)=>void;onFollowUp?:(question:string)=>void}){
 const [citation,setCitation]=useState<Entity|null>(null);
 const answerText=visibleAnswerText(message.text||'',message.review_actions||[]);
 const openCitation=(source:Entity)=>setCitation({...source,requested_fields:message.review_actions?.find((action:Entity)=>action.extraction_id===extractionCitationId(source))?.fields||[]});
 // Only result IDs recorded in the answer's sources/actions become Review links.
 const extractionIds=Array.from(new Set<string>([...(message.review_actions||[]).map((action:Entity)=>action.extraction_id),...(message.citations||[]).map(extractionCitationId)].filter((id:unknown):id is string=>typeof id==='string'&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(id))));
 const route=message.request_route||{};
 return <div className="agent-v2-chat-answer" data-streaming={message.status==='streaming'}>
  {message.plan?.length>0&&<ol className="agent-plan" aria-label="Plan">{message.plan.map((step:Entity,index:number)=><li key={index} data-status={step.status}>{step.status==='done'?'✓':step.status==='skipped'?'–':'○'} {step.text}</li>)}</ol>}
  {message.status==='streaming'&&!answerText&&<p className="agent-thinking" role="status" aria-live="polite"><span className="agent-thinking-mark" aria-hidden="true"><i/><i/><i/></span><span className="agent-thinking-text">{answerPhase(message)}…</span></p>}
  <AgentAnswerText text={answerText} citations={message.citations||[]} onCitation={openCitation} extractionIds={extractionIds} onReview={onReview}/>
  {message.charts?.length>0&&<div className="answer-charts">{message.charts.map((chart:Entity,index:number)=><AnswerChartView key={index} chart={chart as any} onSource={n=>{const source=(message.citations||[]).find((s:Entity)=>s.index===n);if(source)openCitation(source);}}/>)}</div>}
  <AnswerTokenUsage usage={message.token_usage} status={message.status}/>
  {(route.answer_revised||message.skills_used?.length>0)&&<p className="small muted">{route.answer_revised?'Answer revised after the citation check. ':''}{message.skills_used?.length?`Skill: ${message.skills_used.join(', ')}`:''}</p>}
  {message.instruction_proposal&&<InstructionProposal proposal={message.instruction_proposal} api={api} onError={onError}/>}
  {message.citations?.some((source:Entity)=>source.ocr)&&<p className="small muted" role="status">Some sources use AI OCR. Verify names, numbers and tables against the originals.</p>}
  {message.recovery_actions?.length>0&&<div className="agent-v2-result-actions">{message.recovery_actions.map((action:Entity,index:number)=><button className="btn" key={index} onClick={()=>onRecovery?.(action)}>{action.label}</button>)}</div>}
  {message.review_actions?.some((action:Entity)=>action.fields?.length>0)&&<p className="muted small">This answer uses selected fields. Review opens the complete saved results.</p>}
  {message.review_actions?.length>0&&<div className="agent-v2-result-actions">{message.review_actions.map((action:Entity)=><button className="btn" key={action.extraction_id} onClick={()=>onReview?.(action.extraction_id)} title={`${action.name} — version ${action.version}`}>{action.label||'Review result'} <code>{action.extraction_id.slice(0,8)}</code></button>)}</div>}
  {message.status==='aborted'&&<p className="small muted">{message.text?'Stopped · partial answer kept':'Stopped before an answer was generated'}</p>}
  {message.error&&<p role="alert" className="agent-v2-error">{message.error.detail||'The answer could not finish.'}</p>}
  {message.citations?.length>0&&<details className="agent-v2-sources"><summary>Sources · {message.citations.length}</summary>{message.citations.map((source:Entity,index:number)=><section key={source.knowledge_id||source.chunk_id||index}><button className="text-button" onClick={()=>openCitation(source)}>[{source.index}] {source.document_name||source.title||'Source'}{source.section?` · ${source.section.replace(/^Sheet: /,'sheet ')}`:source.page?` · page ${source.page}`:''}</button><p className="small muted">{source.kind==='extraction'?`Saved extraction · version ${source.version}`:source.source_type||'Document passage'}</p>{source.snippet&&<p className="muted agent-source-snippet">{source.snippet}</p>}</section>)}</details>}
  {message.follow_ups?.length>0&&message.status!=='streaming'&&onFollowUp&&<div className="agent-follow-ups" aria-label="Suggested follow-up questions">{message.follow_ups.map((question:string)=><button key={question} className="btn" onClick={()=>onFollowUp(question)}>{question}</button>)}</div>}
  {citation&&<CitationPanel source={citation} api={api} onClose={()=>setCitation(null)} onReview={onReview}/>}
  {!!answerText&&message.status!=='streaming'&&<div className="agent-v2-chat-actions"><button title="Copy agent answer" className="btn icon" aria-label="Copy agent answer" onClick={()=>void navigator.clipboard.writeText(answerText).catch(()=>onError('The browser could not copy this answer.'))}><Copy size={14}/></button></div>}
 </div>;
}
