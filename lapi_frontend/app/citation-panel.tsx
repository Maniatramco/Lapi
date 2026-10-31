"use client";
import {ActionButton} from "./action-button";
import {useEffect,useRef,useState} from 'react';
import {X} from 'lucide-react';
import {citationRequest,recordedPage,extractionCitationId,citedValues,evidenceExcerpt} from './citation-source';
import {citedRows} from './answer-reading';
import './citation-panel.css';
type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
export function CitationPanel({source,api,onClose,onReview}:{source:Entity;api:Api;onClose:()=>void;onReview?:(id:string)=>void}){
 const dialog=useRef<HTMLDialogElement>(null),[published,setPublished]=useState<Entity|null>(null),[evidence,setEvidence]=useState<Entity|null>(null),[selected,setSelected]=useState(0),[loading,setLoading]=useState(true),[error,setError]=useState(''),[imageFailed,setImageFailed]=useState(false);
 const extractedValues=source.kind==='extraction';
 useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close();},[]);
 useEffect(()=>{
  const controller=new AbortController();let active=true;setLoading(true);setError('');
  void(async()=>{
   const extractionId=extractionCitationId(source);
   const loadEvidence=async()=>{
    const params=new URLSearchParams({record_index:String(Math.max(0,source.record_index||0))});
    const version=source.source_version||source.version;if(version)params.set('version',String(version));
    return api(`/extractions/${extractionId}/source-evidence?${params}`,'GET',undefined,controller.signal,true);
   };
   if(extractedValues&&extractionId){
    const detail=await loadEvidence();if(active){setEvidence(detail);setPublished({title:detail.extraction_name,source_version:detail.version,value:detail.fields});}
   }else{
    const path=citationRequest(source);if(!path)throw new Error('This citation has no available source reference.');
    const saved=await api(path,'GET',undefined,controller.signal,true);if(!active)return;
    const chunk=saved.chunks?.find((c:Entity)=>c.id===source.chunk_id);
    setPublished(chunk?{...saved,text:chunk.text,page:chunk.page}:saved);
    if(extractionId){const detail=await loadEvidence();if(active)setEvidence(detail);}
   }
  })().catch(err=>{if(active)setError(err.message);}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;controller.abort();};
 },[source,api]);
 const sources:Entity[]=evidence?.sources||((published?.document_id||source.document_id)?[{document_id:published?.document_id||source.document_id,document_name:published?.document?.name||published?.title||source.document_name,page:recordedPage(published?.page??source.page),source_base:`/documents/${published?.document_id||source.document_id}`,excerpt:published?.text||source.text||source.excerpt,ocr:published?.ocr||source.ocr}]:[]);
 const origin=sources[selected]||sources[0],page=recordedPage(origin?.page),pdf=/\.pdf$/i.test(origin?.document_name||''),base=origin?.source_base;
 const values=citedValues(evidence?.fields,source.requested_fields);
 const [pageText,setPageText]=useState('');
 useEffect(()=>{
  setPageText('');if(!base||!page||origin?.excerpt)return;
  const controller=new AbortController();let active=true;
  void api(`${base}/preview`,'GET',undefined,controller.signal,true).then(preview=>{
   const chunks=(preview.chunks||[]).filter((chunk:Entity)=>recordedPage(chunk.page)===page);
   if(active)setPageText(chunks.map((chunk:Entity)=>chunk.text||'').join('\n\n'));
  }).catch(()=>{});
  return()=>{active=false;controller.abort();};
 },[base,page,origin?.excerpt,api]);
 useEffect(()=>{setImageFailed(false);},[base,page]);
 // Spreadsheet citations also open their row and everything connected to it.
 const [tab,setTab]=useState('source'),[rowChoice,setRowChoice]=useState(0),[rowData,setRowData]=useState<Entity|null>(null),[rowError,setRowError]=useState('');
 const cited=extractedValues?null:citedRows(source,published),citedDocument=published?.document_id||source.document_id,citedRow=cited?.rows[rowChoice]??cited?.rows[0],citedSheet=cited?.sheet;
 useEffect(()=>{
  setRowData(null);setRowError('');if(!citedSheet||!citedRow||!citedDocument)return;
  const controller=new AbortController();let active=true;
  void api(`/documents/${citedDocument}/row-context?sheet=${encodeURIComponent(citedSheet)}&row=${citedRow}`,'GET',undefined,controller.signal,true).then(value=>{if(active)setRowData(value);}).catch(err=>{if(active)setRowError(err.message);});
  return()=>{active=false;controller.abort();};
 },[citedSheet,citedRow,citedDocument,api]);
 const tabs=rowData?[['source','Source'],['row','Row'],['attached',`Attached · ${rowData.attached?.length||0}`],['linked',`Linked · ${rowData.linked_rows?.length||0}`]]:[];
 return <dialog ref={dialog} className="citation-panel" aria-labelledby="citation-panel-title" onClose={onClose} onCancel={onClose}>
  <header><div><span className="citation-panel-eyebrow">Citation [{source.index}]</span><h2 id="citation-panel-title">Source evidence</h2></div><button title="Close citation source" className="btn icon" aria-label="Close citation source" onClick={()=>dialog.current?.close()}><X size={18}/></button></header>
  <div className="citation-panel-body">
   {loading&&<p role="status">Loading the saved source…</p>}{error&&<p className="review-error" role="alert">{error}</p>}
   {tabs.length>0&&<div className="citation-tabs" role="tablist" aria-label="What is connected to this row">{tabs.map(([id,label])=><button key={id} type="button" role="tab" aria-selected={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</div>}
   {rowError&&tab!=='source'&&<p className="review-error" role="alert">{rowError}</p>}
   {rowData&&tab!=='source'&&(cited?.rows.length||0)>1&&<label className="citation-page-picker">Row<select aria-label="Cited row" value={rowChoice} onChange={event=>setRowChoice(Number(event.target.value))}>{cited!.rows.map((row,index)=><option key={row} value={index}>{cited!.sheet} · row {row}</option>)}</select></label>}
   {rowData&&tab==='row'&&<section><h3>{rowData.sheet} · row {rowData.row}</h3><dl className="citation-row-values">{Object.entries(rowData.values||{}).map(([name,value])=><div key={name}><dt>{name}</dt><dd>{String(value)||'—'}</dd></div>)}</dl>{rowData.notes?.length>0&&<><h3>Notes</h3><ul className="citation-row-notes">{rowData.notes.map((note:string)=><li key={note}>{note}</li>)}</ul></>}</section>}
   {rowData&&tab==='attached'&&<section>{rowData.attached?.length?rowData.attached.map((item:Entity)=><article className="citation-row-item" data-differs={item.differs?true:undefined} key={item.id}><h3>{item.id} · {item.where}</h3><p>{item.content}</p>{item.differs&&<p className="citation-row-differs" role="alert">Amounts differ: the {item.kind} shows {(item.differs.item||[]).join(', ')}, the row says {Object.entries(item.differs.row||{}).map(([name,value])=>`${name} ${value}`).join(', ')}. Check the original.</p>}{item.agrees?.length>0&&<p className="citation-panel-note">Matches {item.agrees.join(', ')}.</p>}<p className="citation-panel-note">Connected {item.how} ({item.strength}). Image text is OCR: check it against the original.</p></article>):<p>Nothing is attached to this row.</p>}</section>}
   {rowData&&tab==='linked'&&<section>{rowData.linked_rows?.length?rowData.linked_rows.map((link:Entity)=><article className="citation-row-item" key={link.sheet+link.row}><h3>{link.sheet} · row {link.row}</h3><p className="citation-panel-note">Through {link.through} ({link.strength})</p><dl className="citation-row-values">{Object.entries(link.values||{}).map(([name,value])=><div key={name}><dt>{name}</dt><dd>{String(value)||'—'}</dd></div>)}</dl></article>):<p>No linked rows.</p>}</section>}
   {!loading&&!error&&published&&(tab==='source'||!rowData)&&<>
    <dl className="citation-panel-metadata"><div><dt>Document / source</dt><dd>{origin?.document_name||published.title||source.document_name||'Application metadata'}</dd></div><div><dt>Page</dt><dd>{page||'Not recorded'}</dd></div><div><dt>Saved version</dt><dd>{evidence?.version||published.source_version||source.version||'—'}</dd></div>{evidence&&<div><dt>Extraction</dt><dd>{evidence.extraction_name}<small>{evidence.extraction_id}</small></dd></div>}</dl>
    {sources.length>1&&<label className="citation-page-picker">Recorded document / page<select aria-label="Citation document and page" value={selected} onChange={event=>setSelected(Number(event.target.value))}>{sources.map((s,index)=><option key={index} value={index}>{s.document_name} · {s.page?`page ${s.page}`:'page not recorded'}{s.field?` · ${s.field}`:''}</option>)}</select></label>}
    <section><h3>{extractedValues?'Cited extracted values':evidence?'Cited extraction metadata':'Cited source passage'}</h3><pre className="citation-panel-values">{extractedValues&&evidence?JSON.stringify(values,null,2):published.text||source.text||source.excerpt||JSON.stringify(published.value??published,null,2)}</pre></section>
    {evidence&&!extractedValues&&<p className="citation-panel-note">This citation contains extraction metadata. The related original preview shows the first saved record.</p>}
    {origin?.excerpt&&evidence&&<section><h3>{origin.field_evidence?'Recorded field evidence':'Retrieved document passage'}</h3><blockquote>{evidenceExcerpt(origin.excerpt,Object.values(values||{}))}</blockquote></section>}
    {!origin?.excerpt&&pageText&&<section><h3>Indexed text · page {page}</h3><blockquote>{evidenceExcerpt(pageText,Object.values(values||{}))}</blockquote><p className="citation-panel-note">Text from the recorded page, shown around matching values. This is not a saved field-level quote.</p></section>}
    {origin?.ocr&&<p className="citation-panel-note">AI OCR transcription. Compare it against the original page.</p>}
    {pdf&&base&&<section className="citation-original"><h3>Original document · page {page||1}</h3>{!page&&<p className="citation-panel-note">The extraction page was not recorded. Page 1 is shown for browsing.</p>}{imageFailed?<p role="alert">The original page could not be displayed. Use Open original below.</p>:<img src={`/api${base}/page-image?page=${page||1}`} alt={`Original ${origin.document_name} page ${page||1}`} onError={()=>setImageFailed(true)}/>}</section>}
    {evidence&&!sources.some(s=>s.field_evidence)&&<p className="citation-panel-note">No exact field-level quote was saved. Retrieved passages do not verify every extracted value.</p>}
    {!origin&&<p className="citation-panel-note">This citation refers to application metadata, not a document page.</p>}
   </>}
  </div>
  <footer>{!error&&published&&base&&<a className="btn" href={`/api${base}/${/\.(pdf|txt|json|png|jpe?g|webp)$/i.test(origin?.document_name||'')?'source':'download'}${pdf?`#page=${page||1}`:''}`} target="_blank" rel="noopener noreferrer">{/\.(pdf|txt|json|png|jpe?g|webp)$/i.test(origin?.document_name||'')?'Open original':'Download original'}</a>}{evidence&&onReview&&<ActionButton className="btn primary" onClick={()=>{dialog.current?.close();onReview(evidence.extraction_id);}} label="Open Review" action="review"/>}<ActionButton className="btn" onClick={()=>dialog.current?.close()} label="Close" action="close"/></footer>
 </dialog>;
}
