/** The words of the first-sign-in chat with Lapi: name, a team workspace, which workspace, the first
 * collection and its type, then what to pull out, the documents, reading and the first results.
 * Pure, so the steps can be tested without a screen. */
import {COLLECTION_TYPES} from './workspace-scope';
import {SUPPORT_NAME} from './support';
import {fieldKey,type Field,type FieldType} from './quick-start-flow';

type Entity=Record<string,any>;
export type Stage='help'|'email'|'sent'|'name'|'team'|'team-name'|'choose'|'collection'|'type'|'interest'|'fields'|'change'|'documents'|'consent'|'reading'|'extracting'|'results'|'done';
export type Quick={label:string;value:string};
export type Prompt={text:string;quick?:Quick[];typing?:boolean};

const YES=/^(y|yes|yeah|yep|sure|ok|okay|please|go ahead|create|looks good|fine|good|great|perfect)/i;
const NO=/^(n|no|nope|not now|later|skip|maybe later|no thanks|change)/i;
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

/** What the person wants from the Help Bot, in their own words. */
export type HelpWish='collection'|'team'|'extract'|'email'|'';
export function helpWish(answer:string):HelpWish{
 const t=answer.trim().toLowerCase();if(!t)return '';
 if(/email|mail|help|support|wrong|error|problem|bug|broken|stuck|contact|human|person/.test(t))return 'email';
 if(/team|share|colleague|invite|people/.test(t))return 'team';
 if(/extract|pull|data|field|total|invoice|read|scan/.test(t))return 'extract';
 if(/collection|folder|new|create|add/.test(t))return 'collection';
 return '';
}

/* ---- What to pull out: prefilled fields from everyday words ---- */
type Preset={match:RegExp;name:string;fields:[string,FieldType,string][]};
const PRESETS:Preset[]=[
 {match:/invoice|bill|receipt|expense|payment|finance|accounts?/i,name:'Invoices',fields:[['Invoice number','text','The invoice or bill number, exactly as printed.'],['Vendor','text','Who issued it: the company or person being paid.'],['Invoice date','date','The date on the invoice.'],['Total amount','number','The total payable, numbers only.'],['Currency','text','The currency of the total, such as USD or INR.'],['Due date','date','When payment is due.']]},
 {match:/resume|cv|candidate|applicant|hiring|recruit|hr\b/i,name:'Candidates',fields:[['Full name','text','The person’s full name.'],['Email','text','Their email address.'],['Phone','text','Their phone number.'],['Current role','text','Their latest job title.'],['Years of experience','number','Total years of work experience.'],['Skills','list','The skills they list.'],['Education','text','Highest qualification and institution.']]},
 {match:/contract|agreement|lease|nda|legal|terms/i,name:'Contracts',fields:[['Parties','list','Who signs the agreement.'],['Effective date','date','When it starts.'],['End date','date','When it ends or renews.'],['Contract value','number','The total value, numbers only.'],['Governing law','text','Which law or jurisdiction applies.'],['Notice period','text','How much notice ends it.']]},
 {match:/purchase order|\bpo\b|order/i,name:'Purchase orders',fields:[['PO number','text','The purchase order number.'],['Supplier','text','Who the order is placed with.'],['Order date','date','The date of the order.'],['Total','number','The order total, numbers only.'],['Items','list','Each line item with its quantity.']]},
 {match:/bank|statement|transaction/i,name:'Bank statements',fields:[['Account number','text','The account number as shown.'],['Statement period','text','The period the statement covers.'],['Opening balance','number','Balance at the start.'],['Closing balance','number','Balance at the end.'],['Transactions','list','Each transaction: date, description, amount.']]},
 {match:/passport|identity|\bid\b|licen[cs]e|aadhaar|pan card/i,name:'Identity documents',fields:[['Full name','text','The name on the document.'],['Document number','text','The ID number.'],['Date of birth','date','Date of birth.'],['Expiry date','date','When it expires.'],['Nationality','text','Nationality or issuing country.']]},
 {match:/report|summary|minutes|memo/i,name:'Reports',fields:[['Title','text','The document title.'],['Date','date','The date of the report.'],['Author','text','Who wrote it.'],['Summary','text','A two-sentence summary.'],['Key figures','list','The main numbers mentioned.']]},
];
const make=(label:string,type:FieldType,description:string,taken:string[]):Field=>({key:fieldKey(label,taken),label,type,description});

/** Fields to prefill from what the person wants, or from the collection's type when the words give nothing. */
export function suggestFields(interest:string,collectionType=''):{name:string;fields:Field[]}{
 const text=`${interest} ${collectionType}`;
 const preset=PRESETS.find(p=>p.match.test(interest))||PRESETS.find(p=>p.match.test(text));
 const taken:string[]=[];const fields:Field[]=[];
 if(preset){for(const [label,type,description] of preset.fields){const f=make(label,type,description,taken);taken.push(f.key);fields.push(f);}}
 // Words of their own become fields too: "vendor, total and due date".
 const mentioned=interest.split(/,|\band\b|\bplus\b|&/i).map(s=>s.trim().replace(/^(the|their|its|each|every|all)\s+/i,'')).filter(s=>s&&s.length<=40&&/^[\w\s'/-]+$/.test(s));
 // A mention the preset already covers ("totals" → Total amount, "due dates" → Due date) adds nothing.
 const stem=(w:string)=>w.toLowerCase().replace(/s$/,'');
 const covered=(label:string)=>fields.some(f=>f.label.split(/\s+/).map(stem).some(w=>w.length>2&&label.split(/\s+/).map(stem).includes(w)));
 if(!preset||mentioned.length>1){for(const label of mentioned){const nice=label[0].toUpperCase()+label.slice(1);if(covered(nice)||fields.some(f=>f.label.toLowerCase()===nice.toLowerCase()||f.key===fieldKey(nice)))continue;const f=make(nice,/date|when|due/i.test(nice)?'date':/amount|total|price|cost|number of|count|qty|quantity|age|years/i.test(nice)?'number':/list|items|skills|names/i.test(nice)?'list':'text',`${nice}, exactly as written.`,taken);taken.push(f.key);fields.push(f);}}
 return {name:preset?.name||(interest.trim().slice(0,60)||'Extraction'),fields:fields.slice(0,15)};
}

/** "add due date, remove currency" / "without the address" / a plain list that replaces everything. */
export function applyChange(fields:Field[],answer:string):Field[]{
 const text=answer.trim();if(!text)return fields;
 const parts=text.split(/(?=\b(?:add|also|include|plus|remove|drop|without|delete|no|not)\b)/i).map(s=>s.trim()).filter(Boolean);
 let next=[...fields],touched=false;
 for(const part of parts){
  const m=part.match(/^(add|also|include|plus|remove|drop|without|delete|no|not)\b\s*(.*)$/i);if(!m)continue;
  touched=true;const removing=/^(remove|drop|without|delete|no|not)$/i.test(m[1]);
  for(const raw of m[2].split(/,|\band\b/i).map(s=>s.trim().replace(/^(the|a|an)\s+/i,'')).filter(Boolean)){
   if(removing)next=next.filter(f=>!f.label.toLowerCase().includes(raw.toLowerCase()));
   else if(!next.some(f=>f.label.toLowerCase()===raw.toLowerCase())){const nice=raw[0].toUpperCase()+raw.slice(1);next.push(make(nice,/date|when|due/i.test(nice)?'date':/amount|total|price|cost|years/i.test(nice)?'number':'text',`${nice}, exactly as written.`,next.map(f=>f.key)));}
  }
 }
 if(!touched)return suggestFields(text).fields.length?suggestFields(text).fields:fields;  // A fresh list replaces the old one.
 return next.slice(0,15);
}

export function interestSuggestions(collectionType:string):Quick[]{
 const t=collectionType.toLowerCase();
 const picks=/finance|invoice/.test(t)?['Invoice totals and due dates','Vendor, amount and currency']:/resume|hr/.test(t)?['Names, roles and skills','Contact details and experience']:/legal|contract/.test(t)?['Parties, dates and value','Notice period and governing law']:/report/.test(t)?['Title, date and key figures']:['Invoice totals and due dates','Names and contact details','Dates and amounts'];
 return picks.map(p=>({label:p,value:p}));
}

export const fieldList=(fields:Field[])=>fields.map(f=>f.label).join(', ');

/** What Lapi says at each stage. */
export function prompt(stage:Stage,ctx:{name:string;workspaces:Entity[];current?:Entity;canCreateTeam:boolean;teamName?:string;collectionName?:string;collectionType?:string;fields?:Field[];files?:string[];progress?:string;results?:string;lastError?:string}):Prompt{
 const me=first(ctx.name);
 switch(stage){
  case 'help':return {text:`Hi${me?` ${me}`:''}, what can I do for you?`,quick:[{label:'Add a collection',value:'collection'},...(ctx.canCreateTeam?[{label:'A team workspace',value:'team'}]:[]),{label:'Pull out data',value:'extract'},{label:`Email ${SUPPORT_NAME} for help`,value:'email'}],typing:true};
  case 'email':return {text:`${ctx.lastError?`I saw this: "${ctx.lastError}". `:''}Tell me what happened, or what you need, and I'll put it in an email to ${SUPPORT_NAME} with the details.`,typing:true};
  case 'sent':return {text:`I've opened your email app with everything filled in. Send it and ${SUPPORT_NAME} will get back to you. Anything else?`,quick:[{label:'No, thanks',value:'close'},{label:'Something else',value:'help'}]};
  case 'name':return {text:"Hi, I'm Lapi. I'll set things up with you in a minute. What should I call you?",typing:true};
  case 'team':return {text:`Nice to meet you, ${me}. Your own workspace, ${ctx.current?.name||`${me}'s workspace`}, is ready for your documents. Would you also like a team workspace, to share collections with other people?`,quick:[{label:'Yes, a team workspace',value:'yes'},{label:'Not now',value:'no'}]};
  case 'team-name':return {text:'What should the team workspace be called? For example: Finance team.',typing:true};
  case 'choose':return {text:`Which workspace do you want to use${me?`, ${me}`:''}?`,quick:ctx.workspaces.map(w=>({label:w.name,value:w.id}))};
  case 'collection':return {text:`A collection holds related documents in ${ctx.current?.name||'your workspace'}. What should your first one be called? For example: Invoices 2026.`,quick:[{label:'Skip for now',value:'skip'}],typing:true};
  case 'type':return {text:`What kind of documents go in ${ctx.collectionName||'it'}? Pick one or type your own.`,quick:[...COLLECTION_TYPES.map(t=>({label:t,value:t})),{label:'Skip',value:'skip'}],typing:true};
  case 'interest':return {text:`What would you like to pull out of these documents first? Say it in your own words and I'll suggest the fields.`,quick:[...interestSuggestions(ctx.collectionType||''),{label:'Skip for now',value:'skip'}],typing:true};
  case 'fields':return {text:`I'd pull out: ${fieldList(ctx.fields||[])}. Shall I go with these, or change anything?`,quick:[{label:'Looks good',value:'yes'},{label:'Change them',value:'change'}],typing:true};
  case 'change':return {text:'Tell me what to add or remove. For example: add due date, remove currency.',typing:true};
  case 'documents':return {text:`Now add the documents. Take a photo of a paper one, or choose files from your ${/Android|iPhone/.test(typeof navigator==='undefined'?'':navigator.userAgent)?'phone':'computer'}.`,quick:[{label:'Take a photo',value:'camera'},{label:'Choose files',value:'files'},{label:'Skip for now',value:'skip'}]};
  case 'consent':return {text:`Got ${ctx.files?.length||0} ${ctx.files?.length===1?'file':'files'}: ${(ctx.files||[]).join(', ')}. Can I send ${ctx.files?.length===1?'it':'them'} to the AI services set up for ${ctx.collectionName||'this collection'} to read and index?`,quick:[{label:'Yes, read them',value:'yes'},{label:'Add more first',value:'more'},{label:'Start over',value:'no'}]};
  case 'reading':return {text:ctx.progress||'Reading your documents… this usually takes under a minute.'};
  case 'extracting':return {text:ctx.progress||`Pulling out ${fieldList(ctx.fields||[])}…`};
  case 'results':return {text:ctx.results||'Done.',quick:[{label:'Open Review',value:'review'},{label:'Finish',value:'finish'}]};
  case 'done':return {text:`All set${me?`, ${me}`:''}. Add more documents whenever you're ready, and ask me anything about them.`,quick:[{label:"Let's go",value:'go'}]};
 }
}

/** The stage after `stage`, given what exists now. */
export function after(stage:Stage,ctx:{workspaces:Entity[];current?:Entity;canCreateTeam:boolean;chosen:boolean;created?:boolean}):Stage{
 const order:Stage[]=['name','team','choose','collection','interest','done'];
 const base:Stage=stage==='team-name'?'team':stage==='type'?'collection':stage;
 let i=order.indexOf(base)+1;
 for(;i<order.length;i++){
  const next=order[i];
  if(next==='team'&&!ctx.canCreateTeam)continue;
  if(next==='choose'&&(ctx.workspaces.length<2||ctx.chosen))continue;
  if(next==='collection'&&(!ctx.current||ctx.current.collection_count>0||!['owner','editor'].includes(ctx.current.my_access)))continue;
  if(next==='interest'&&!ctx.created)continue;  // The guided first round follows a collection made here.
  return next;
 }
 return 'done';
}
