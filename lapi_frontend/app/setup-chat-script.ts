/** The words of the first-sign-in chat with Lapi: name, a team workspace, which workspace, the first
 * collection and its type. Pure, so the steps can be tested without a screen. */
import {COLLECTION_TYPES} from './workspace-scope';

type Entity=Record<string,any>;
export type Stage='name'|'team'|'team-name'|'choose'|'collection'|'type'|'done';
export type Quick={label:string;value:string};
export type Prompt={text:string;quick?:Quick[];typing?:boolean};

const YES=/^(y|yes|yeah|yep|sure|ok|okay|please|go ahead|create)/i;
const NO=/^(n|no|nope|not now|later|skip|maybe later|no thanks)/i;
export const yes=(answer:string)=>YES.test(answer.trim());
export const no=(answer:string)=>NO.test(answer.trim());

export function cleanName(answer:string){
 // "I'm Mani" / "call me Mani" / "Mani here" → "Mani"
 const bare=answer.trim().replace(/^(hi|hello|hey)[,!. ]*/i,'').replace(/^(i am|i'm|im|it's|its|this is|call me|my name is|you can call me|name is)\s+/i,'').replace(/[.!,]+$/,'').replace(/\s+here$/i,'').trim();
 const words=bare.split(/\s+/).filter(Boolean).slice(0,3);
 return words.map(w=>w.length>1&&w===w.toLowerCase()?w[0].toUpperCase()+w.slice(1):w).join(' ').slice(0,60);
}

export function matchWorkspace(workspaces:Entity[],answer:string):Entity|undefined{
 const wanted=answer.trim().toLowerCase();if(!wanted)return undefined;
 return workspaces.find(w=>w.id===answer)||workspaces.find(w=>String(w.name).toLowerCase()===wanted)||workspaces.find(w=>String(w.name).toLowerCase().includes(wanted)||wanted.includes(String(w.name).toLowerCase()));
}

export function matchType(answer:string){
 const wanted=answer.trim().toLowerCase();if(!wanted||NO.test(wanted))return '';
 return COLLECTION_TYPES.find(t=>t.toLowerCase()===wanted)||COLLECTION_TYPES.find(t=>wanted.includes(t.toLowerCase()))||answer.trim().slice(0,40);
}

export const first=(name:string)=>name.trim().split(/\s+/)[0]||'';

/** What Lapi says at each stage. */
export function prompt(stage:Stage,ctx:{name:string;workspaces:Entity[];current?:Entity;canCreateTeam:boolean;teamName?:string;collectionName?:string}):Prompt{
 const me=first(ctx.name);
 switch(stage){
  case 'name':return {text:"Hi, I'm Lapi. I'll set things up with you in a minute. What should I call you?",typing:true};
  case 'team':return {text:`Nice to meet you, ${me}. Your own workspace, ${ctx.current?.name||`${me}'s workspace`}, is ready for your documents. Would you also like a team workspace, to share collections with other people?`,quick:[{label:'Yes, a team workspace',value:'yes'},{label:'Not now',value:'no'}]};
  case 'team-name':return {text:'What should the team workspace be called? For example: Finance team.',typing:true};
  case 'choose':return {text:`Which workspace do you want to use${me?`, ${me}`:''}?`,quick:ctx.workspaces.map(w=>({label:w.name,value:w.id}))};
  case 'collection':return {text:`A collection holds related documents in ${ctx.current?.name||'your workspace'}. What should your first one be called? For example: Invoices 2026.`,typing:true};
  case 'type':return {text:`What kind of documents go in ${ctx.collectionName||'it'}? Pick one or type your own.`,quick:[...COLLECTION_TYPES.map(t=>({label:t,value:t})),{label:'Skip',value:'skip'}],typing:true};
  case 'done':return {text:`All set${me?`, ${me}`:''}. Add your documents whenever you're ready, and ask me anything about them.`,quick:[{label:"Let's go",value:'go'}]};
 }
}

/** The stage after `stage`, given what exists now. */
export function after(stage:Stage,ctx:{workspaces:Entity[];current?:Entity;canCreateTeam:boolean;chosen:boolean}):Stage{
 const order:Stage[]=['name','team','choose','collection','done'];
 let i=order.indexOf(stage==='team-name'?'team':stage==='type'?'collection':stage)+1;
 for(;i<order.length;i++){
  const next=order[i];
  if(next==='team'&&!ctx.canCreateTeam)continue;
  if(next==='choose'&&(ctx.workspaces.length<2||ctx.chosen))continue;
  if(next==='collection'&&(!ctx.current||ctx.current.collection_count>0||!['owner','editor'].includes(ctx.current.my_access)))continue;
  return next;
 }
 return 'done';
}
