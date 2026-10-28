"use client";
import {useCallback,useEffect,useId,useRef,useState,type KeyboardEvent as ReactKeyboardEvent,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {ArrowRight,Check,CloudUpload,Database,FileSearch,Keyboard,LayoutDashboard,Menu,MessageSquare,Search,Sparkles,Table2,Users,X} from 'lucide-react';
import {AgentLogo} from './agent-logo';
import {TOUR_SETTLED_EVENT,tourSettledFor} from './walkthrough';
import {GOALS,SOURCES,accessFor,addKnowledgeRoute,cleanPreferences,recommendNextSteps,shouldAskSetup,showNextSteps,toggleGoal,toggleSource,type Goal,type NextStep,type Preferences,type Source} from './setup-guide';
import {INITIAL_STATE,SHORTCUT_LIST,resolveShortcut,type ShortcutState} from './shortcuts';
import './workspace-assist.css';
import './mobile.css';

type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
type Entity=Record<string,any>;
/** About and the Dashboard card open the set-up questions again with this event. */
export const OPEN_SETUP_EVENT='lapi:open-setup';
const FOCUSABLE='button:not([disabled]),[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
/** Composers and searches, most specific first; the first visible, enabled one gets focus. */
const FOCUS_TARGETS=['textarea[aria-label="Message Lapi Agent"]','textarea[aria-label="Message Dataset Knowledge Chat"]','#dashboard-ask-input','main input[type="search"]','main input[aria-label^="Search"]','.workspace-page-actions button[aria-label^="Search"]'];
const visible=(el:Element|null):el is HTMLElement=>Boolean(el&&(el as HTMLElement).getClientRects().length&&!(el as HTMLButtonElement).disabled&&!el.closest('[hidden],[inert]'));
function findVisible(selectors:string[]){for(const selector of selectors){const match=Array.from(document.querySelectorAll(selector)).find(visible);if(match)return match as HTMLElement;}return null;}
/** Wait a few frames for a screen to render after navigation. */
function waitFor(selectors:string[],timeout=2500):Promise<HTMLElement|null>{
 const started=performance.now();
 return new Promise(resolve=>{const tick=()=>{const found=findVisible(selectors);if(found||performance.now()-started>timeout)resolve(found);else requestAnimationFrame(tick);};tick();});
}
/** Type into a React-controlled field the way a person would, so its state updates. */
function fill(el:HTMLElement,text:string){
 const proto=el instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
 Object.getOwnPropertyDescriptor(proto,'value')?.set?.call(el,text);
 el.dispatchEvent(new Event('input',{bubbles:true}));
}
const otherModalOpen=(own:(HTMLElement|null)[])=>Array.from(document.querySelectorAll('[aria-modal="true"]')).some(el=>!own.some(mine=>mine&&mine.contains(el)));

function useDialogFocus(ref:{current:HTMLElement|null},open:boolean){
 useEffect(()=>{
  if(!open)return;
  const opener=document.activeElement as HTMLElement|null,overflow=document.body.style.overflow;
  document.body.style.overflow='hidden';
  requestAnimationFrame(()=>(ref.current?.querySelector<HTMLElement>('[data-autofocus]')||ref.current?.querySelector<HTMLElement>(FOCUSABLE))?.focus());
  return()=>{document.body.style.overflow=overflow;if(opener?.isConnected)opener.focus();};
 },[open,ref]);
}
function trapTab(event:ReactKeyboardEvent<HTMLElement>,root:HTMLElement|null){
 if(event.key!=='Tab'||!root)return;
 const items=Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(el=>el.getClientRects().length);
 if(!items.length)return;
 const first=items[0],last=items[items.length-1];
 if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
 else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
}

const STEP_ICON:Record<string,typeof Database>={'create-dataset':Database,connect:CloudUpload,'add-knowledge':CloudUpload,upload:CloudUpload,ask:MessageSquare,research:Search,agent:Sparkles,extract:Table2};
const GOAL_ICON:Record<Goal,typeof Database>={ask:MessageSquare,extract:Table2,research:FileSearch,knowledge_base:Users};

function Choice({selected,onToggle,title,detail,icon:Icon}:{selected:boolean;onToggle:()=>void;title:string;detail?:string;icon?:typeof Database}){
 return <button type="button" role="checkbox" aria-checked={selected} aria-label={title} title={detail} className="setup-choice" data-selected={selected||undefined} onClick={onToggle}>
  {Icon&&<span className="setup-choice-icon" aria-hidden="true"><Icon size={20}/></span>}
  <span className="setup-choice-text"><strong>{title}</strong>{detail&&<small>{detail}</small>}</span>
  <span className="setup-choice-check" aria-hidden="true">{selected&&<Check size={16}/>}</span>
 </button>;
}

function SetupSheet({initial,access,onSave,onSkip,onAct,onClose}:{initial:Preferences;access:ReturnType<typeof accessFor>;onSave:(answers:Preferences)=>Promise<void>;onSkip:()=>void;onAct:(step:NextStep)=>void;onClose:()=>void}){
 const [step,setStep]=useState(0),[goals,setGoals]=useState<Goal[]>(initial.goals),[sources,setSources]=useState<Source[]>(initial.sources),[saving,setSaving]=useState(false),[error,setError]=useState('');
 const ref=useRef<HTMLDivElement>(null),titleId=useId(),stepRef=useRef<HTMLHeadingElement>(null);
 useDialogFocus(ref,true);
 useEffect(()=>{if(step)stepRef.current?.focus();},[step]);
 const guidance=recommendNextSteps({goals,sources},access);
 const finish=async()=>{setSaving(true);setError('');try{await onSave({goals,sources,completed:true,dismissed_next_steps:false});setStep(2);}catch(e){setError(e instanceof Error?e.message:'Could not save your answers.');}finally{setSaving(false);}};
 const titles=['What do you want to do with Lapi?','Where is your knowledge today?','Your first step'];
 return <div className="setup-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&step===2)onClose();}}>
  <div ref={ref} className="setup-sheet" role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();step===2?onClose():onSkip();return;}trapTab(event,ref.current);}}>
   <header className="setup-head">
    <span className="setup-eyebrow" id={titleId}>Let&apos;s set you up{step<2?` · Step ${step+1} of 2`:''}</span>
    <button type="button" className="setup-skip" onClick={step===2?onClose:onSkip}>{step===2?<><X size={16} aria-hidden="true"/>Close</>:'Skip'}</button>
   </header>
   <div className="setup-progress" aria-hidden="true"><i data-on={step>=0||undefined}/><i data-on={step>=1||undefined}/><i data-on={step>=2||undefined}/></div>
   <h2 className="setup-title" tabIndex={-1} ref={stepRef}>{titles[step]}</h2>
   {step===0&&<><p className="setup-lead">Choose one or more. This only changes what Lapi suggests.</p>
    <div className="setup-choices" role="group" aria-label="What you want to do">{GOALS.map(goal=><Choice key={goal.id} title={goal.title} detail={goal.detail} icon={GOAL_ICON[goal.id]} selected={goals.includes(goal.id)} onToggle={()=>setGoals(current=>toggleGoal(current,goal.id))}/>)}</div></>}
   {step===1&&<><p className="setup-lead">Choose one or more. Lapi reads copies; your originals are never changed.</p>
    <div className="setup-choices setup-sources" role="group" aria-label="Where your knowledge is">{SOURCES.map(source=><Choice key={source.id} title={source.title} selected={sources.includes(source.id)} onToggle={()=>setSources(current=>toggleSource(current,source.id))}/>)}</div></>}
   {step===2&&<div className="setup-result">
    <p className="setup-lead">{access.canAddKnowledge?'Based on your answers, start here:':'You can ask questions in the datasets shared with you.'}</p>
    <button type="button" className="setup-primary-step" data-autofocus onClick={()=>onAct(guidance.primary)}>
     <span className="setup-choice-icon" aria-hidden="true">{(()=>{const Icon=STEP_ICON[guidance.primary.kind]||ArrowRight;return <Icon size={20}/>;})()}</span>
     <span className="setup-choice-text"><strong>{guidance.primary.label}</strong><small>{guidance.primary.detail}</small></span><ArrowRight size={18} aria-hidden="true"/>
    </button>
    {guidance.notes.length>0&&<ul className="setup-notes">{guidance.notes.map(note=><li key={note}>{note}</li>)}</ul>}
    <p className="setup-later">Your next steps stay on the Dashboard. Change your answers there or in About.</p>
   </div>}
   {error&&<p className="setup-error" role="alert">{error}</p>}
   <footer className="setup-actions">
    {step===1&&<button type="button" className="btn" onClick={()=>setStep(0)} disabled={saving}>Back</button>}
    {step===0&&<button type="button" className="btn primary" onClick={()=>setStep(1)}>Next<ArrowRight size={16} aria-hidden="true"/></button>}
    {step===1&&<button type="button" className="btn primary" onClick={()=>void finish()} disabled={saving}>{saving?'Saving…':'Show my next step'}<ArrowRight size={16} aria-hidden="true"/></button>}
    {step===2&&<button type="button" className="btn" onClick={onClose}>Go to Dashboard</button>}
   </footer>
  </div>
 </div>;
}

function ShortcutsDialog({onClose}:{onClose:()=>void}){
 const ref=useRef<HTMLDivElement>(null),titleId=useId();
 useDialogFocus(ref,true);
 return <div className="setup-backdrop shortcuts-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget)onClose();}}>
  <div ref={ref} className="shortcuts-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();onClose();return;}trapTab(event,ref.current);}}>
   <header className="setup-head"><h2 id={titleId} className="shortcuts-title"><Keyboard size={18} aria-hidden="true"/>Keyboard shortcuts</h2><button type="button" className="btn icon" aria-label="Close keyboard shortcuts" title="Close (Esc)" onClick={onClose} data-autofocus><X size={16}/></button></header>
   <dl className="shortcuts-list">{SHORTCUT_LIST.map(item=><div key={item.action}><dt>{item.keys.map((key,i)=><span key={key}>{i>0&&<span className="shortcuts-then"> then </span>}<kbd>{key}</kbd></span>)}</dt><dd>{item.action}</dd></div>)}</dl>
   <p className="shortcuts-note">Shortcuts do nothing while you type in a field. Press <kbd>?</kbd> any time to see this list.</p>
  </div>
 </div>;
}

export function WorkspaceAssist({api,user,view,datasets,onNavigate,onOpenNavigation}:{api:Api;user:Entity;view:string;datasets:Entity[];onNavigate:(view:string)=>unknown;onOpenNavigation:()=>void}){
 const userId=String(user?.id||user?.username||'');
 const access=accessFor(user,datasets);
 const [preferences,setPreferences]=useState<Preferences|null>(null);
 const [sheetOpen,setSheetOpen]=useState(false),[helpOpen,setHelpOpen]=useState(false);
 const [tourDone,setTourDone]=useState(()=>tourSettledFor()===String(user?.id||''));
 const [announcement,setAnnouncement]=useState(''),[mounted,setMounted]=useState(false);
 const sequence=useRef<ShortcutState>(INITIAL_STATE),own=useRef<HTMLDivElement>(null);
 const say=useCallback((text:string)=>{setAnnouncement('');requestAnimationFrame(()=>setAnnouncement(text));},[]);
 useEffect(()=>setMounted(true),[]);
 // Answers are per person: load them once per sign-in.
 useEffect(()=>{
  setPreferences(null);setSheetOpen(false);
  if(!userId)return;
  let live=true;
  api('/me/preferences','GET',undefined,undefined,true).then(value=>{if(live)setPreferences(cleanPreferences(value));}).catch(()=>undefined);
  return()=>{live=false;};
 },[api,userId]);
 useEffect(()=>{
  const id=String(user?.id||'');setTourDone(tourSettledFor()===id);
  const settled=(event:Event)=>{if((event as CustomEvent).detail===id)setTourDone(true);};
  window.addEventListener(TOUR_SETTLED_EVENT,settled);return()=>window.removeEventListener(TOUR_SETTLED_EVENT,settled);
 },[user?.id]);
 // Ask first: after the tour, on the Dashboard, until answered or skipped once.
 useEffect(()=>{if(view==='Home'&&tourDone&&shouldAskSetup(preferences))setSheetOpen(true);},[view,tourDone,preferences]);
 useEffect(()=>{const open=()=>{setHelpOpen(false);setSheetOpen(true);};window.addEventListener(OPEN_SETUP_EVENT,open);return()=>window.removeEventListener(OPEN_SETUP_EVENT,open);},[]);
 const save=useCallback(async(next:Preferences)=>{const saved=cleanPreferences(await api('/me/preferences','PUT',next,undefined,true));setPreferences(saved);return saved;},[api]);
 const skip=()=>{setSheetOpen(false);const next={...(preferences||cleanPreferences({})),completed:true};setPreferences(next);void save(next).catch(()=>undefined);say('Set-up skipped. You can answer later from the Dashboard or About.');};
 const dismissCard=()=>{if(!preferences)return;const next={...preferences,dismissed_next_steps:true};setPreferences(next);void save(next).catch(()=>undefined);say('Next steps hidden. Open About to change your answers.');};

 const go=useCallback((target:string)=>{if(view!==target)onNavigate(target);},[view,onNavigate]);
 const focusComposer=useCallback(async(text?:string)=>{
  const el=await waitFor(FOCUS_TARGETS,view==='Home'||view==='Lapi agent V2'?600:300);
  if(!el)return false;
  el.scrollIntoView?.({block:'center',behavior:'smooth'});
  if(el.tagName==='BUTTON'){el.click();return true;}
  el.focus();
  if(text!==undefined&&(el instanceof HTMLTextAreaElement||el instanceof HTMLInputElement)){fill(el,text);el.setSelectionRange?.(text.length,text.length);}
  return true;
 },[view]);
 const ask=useCallback(async(text?:string)=>{
  go('Home');
  const el=await waitFor(['#dashboard-ask-input','textarea[aria-label="Message Dataset Knowledge Chat"]']);
  if(!el||(el as HTMLTextAreaElement).disabled){go('Lapi agent V2');const agent=await waitFor(['textarea[aria-label="Message Lapi Agent"]']);agent?.focus();if(agent&&text)fill(agent,text);return;}
  el.scrollIntoView?.({block:'center',behavior:'smooth'});el.focus();if(text)fill(el,text);
 },[go]);
 const newChat=useCallback(async()=>{
  go('Lapi agent V2');
  const button=await waitFor(['button[aria-label="New agent conversation"]']);
  if(button&&!(button as HTMLButtonElement).disabled)button.click();
  (await waitFor(['textarea[aria-label="Message Lapi Agent"]']))?.focus();
  say('New chat in Lapi Agent.');
 },[go,say]);
 const act=useCallback(async(step:NextStep)=>{
  setSheetOpen(false);
  switch(step.kind){
   case 'create-dataset':go('Datasets');say('Datasets opened. Create your first dataset here.');break;
   case 'connect':window.location.hash=addKnowledgeRoute(step.provider);say(`${step.label}: the step-by-step guide is open.`);break;
   case 'add-knowledge':go('Add knowledge');break;
   case 'extract':go('Extract Data');break;
   case 'agent':go('Lapi agent V2');(await waitFor(['textarea[aria-label="Message Lapi Agent"]']))?.focus();break;
   case 'upload':{
    go('Lapi agent V2');
    const card=await waitFor(['.agent-workflow-card[data-operation="upload"]'],1500);
    if(card)card.click();else{const box=await waitFor(['textarea[aria-label="Message Lapi Agent"]']);if(box){box.focus();fill(box,'/Upload ');}}
    say('Attach files with the plus button, then send your request.');break;
   }
   case 'research':await ask('Compare details across sources');break;
   default:await ask();
  }
 },[go,ask,say]);

 // Keyboard shortcuts: never while typing, with modifiers, or while another dialog is open.
 useEffect(()=>{
  const onKey=(event:KeyboardEvent)=>{
   if(event.defaultPrevented)return;
   const ours=[own.current];
   if(event.key!=='Escape'&&(sheetOpen||otherModalOpen(ours))&&!helpOpen)return;
   const {state,command}=resolveShortcut(event,sequence.current,access,performance.now());
   sequence.current=state;
   if(!command)return;
   switch(command.type){
    case 'escape':if(helpOpen){event.preventDefault();setHelpOpen(false);}return;
    case 'pending':say('G: press D for Dashboard, A for Lapi Agent, K for Add knowledge, S for Datasets or U for Users & passwords.');return;
    case 'help':event.preventDefault();setHelpOpen(open=>!open);return;
    case 'denied':event.preventDefault();say(command.message);return;
    case 'go':event.preventDefault();setHelpOpen(false);go(command.view);say(`${command.label} opened.`);return;
    case 'new-chat':event.preventDefault();setHelpOpen(false);void newChat();return;
    case 'focus':event.preventDefault();setHelpOpen(false);void focusComposer().then(found=>{if(!found)say('Nothing to search on this page.');});return;
   }
  };
  document.addEventListener('keydown',onKey);
  return()=>document.removeEventListener('keydown',onKey);
 },[access.isAdmin,access.canAddKnowledge,sheetOpen,helpOpen,go,newChat,focusComposer,say]);

 // Phones hide the bottom bar while the on-screen keyboard is likely open.
 useEffect(()=>{
  const body=document.body;body.dataset.tabBar='on';
  const typing=()=>{const el=document.activeElement;body.dataset.typing=el&&/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)&&!/^(checkbox|radio|button|submit|file)$/i.test((el as HTMLInputElement).type||'')?'on':'';};
  const left=()=>requestAnimationFrame(typing);
  document.addEventListener('focusin',typing);document.addEventListener('focusout',left);
  return()=>{delete body.dataset.tabBar;delete body.dataset.typing;document.removeEventListener('focusin',typing);document.removeEventListener('focusout',left);};
 },[]);

 const guidance=preferences?recommendNextSteps(preferences,access):null;
 const goalNames=preferences?.goals.map(id=>GOALS.find(g=>g.id===id)?.title).filter(Boolean)||[];
 const sourceNames=preferences?.sources.map(id=>SOURCES.find(s=>s.id===id)?.title).filter(Boolean)||[];
 const card=view==='Home'&&showNextSteps(preferences)&&guidance?<section className="next-steps-card" aria-labelledby="next-steps-title">
  <header><div><h2 id="next-steps-title">Your next steps</h2><p>{goalNames.length||sourceNames.length?[goalNames.length?`For: ${goalNames.join(', ')}`:'',sourceNames.length?`Knowledge in: ${sourceNames.join(', ')}`:''].filter(Boolean).join(' · '):'Suggested for your access'}</p></div>
   <button type="button" className="btn icon next-steps-hide" aria-label="Hide next steps" title="Hide next steps" onClick={dismissCard}><X size={16}/></button></header>
  <ul className="next-steps-actions">{guidance.steps.map(step=>{const Icon=STEP_ICON[step.kind]||ArrowRight;return <li key={step.kind+(step.provider||'')}><button type="button" onClick={()=>void act(step)}><span className="setup-choice-icon" aria-hidden="true"><Icon size={18}/></span><span className="setup-choice-text"><strong>{step.label}</strong><small>{step.detail}</small></span><ArrowRight size={16} aria-hidden="true"/></button></li>;})}</ul>
  {guidance.notes.length>0&&<ul className="setup-notes">{guidance.notes.map(note=><li key={note}>{note}</li>)}</ul>}
  <button type="button" className="text-button next-steps-change" onClick={()=>setSheetOpen(true)}>Change my answers</button>
 </section>:null;

 const tab=(target:string,label:string,Icon:typeof Database|null)=>{const current=view===target;return <button type="button" className="tab-bar-item" aria-label={label} aria-current={current?'page':undefined} onClick={()=>go(target)}>{Icon?<Icon size={22} aria-hidden="true"/>:<AgentLogo size={24}/>}<span>{label}</span></button>;};
 const layer:ReactNode=<div ref={own} className="workspace-assist-layer">
  <nav className="mobile-tab-bar" aria-label="Quick navigation">
   {tab('Home','Dashboard',LayoutDashboard)}
   {tab('Lapi agent V2','Ask',null)}
   {access.canAddKnowledge&&tab('Add knowledge','Add',CloudUpload)}
   <button type="button" className="tab-bar-item" aria-label="More pages" aria-haspopup="dialog" aria-controls="workspace-navigation" onClick={onOpenNavigation}><Menu size={22} aria-hidden="true"/><span>More</span></button>
  </nav>
  {view==='Home'&&!sheetOpen&&<button type="button" className="mobile-ask-fab" aria-label="Ask a question" onClick={()=>void ask()}><MessageSquare size={20} aria-hidden="true"/><span>Ask</span></button>}
  {sheetOpen&&preferences&&<SetupSheet initial={preferences} access={access} onSave={async answers=>{await save(answers);}} onSkip={skip} onAct={step=>void act(step)} onClose={()=>setSheetOpen(false)}/>}
  {helpOpen&&<ShortcutsDialog onClose={()=>setHelpOpen(false)}/>}
  <p className="sr-only" aria-live="polite" role="status">{announcement}</p>
 </div>;
 return <>{card}{mounted&&createPortal(layer,document.body)}</>;
}
