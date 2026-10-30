/** Which screens this person sees on this device (decided by OpenFGA, served by /api/me/screens),
 * and the short agent training. Pure helpers, unit tested. */
export type Device='phone'|'computer';
export type ScreenState={device:Device;screens:string[];views:string[];core:string[];administrator:boolean};

/** Phones are narrower than 640 px. Foldables and tablets count as phones too: touch screens up to 1100 px.
 * A narrow window on a computer stays a computer. Matches PHONE_LAYOUT in the phone style sheets. */
export const deviceFor=(width:number,touch=false):Device=>width<640||(touch&&width<=1100)?'phone':'computer';
export const PHONE_LAYOUT='(max-width: 640px), (pointer: coarse) and (max-width: 1100px)';
/** This window's device; 'computer' where there is no window. */
export function currentDevice():Device{
 if(typeof window==='undefined')return 'computer';
 return deviceFor(window.innerWidth,Boolean(window.matchMedia?.('(pointer: coarse)').matches));
}

/** Views that never need a grant: the Dashboard and Lapi Agent (Quick start is a dialog on them). */
export const CORE_VIEWS=['Home','Lapi agent V2'];

/** Quick Extract hands its result to Review, so phones can always open it. */
const PHONE_VIEWS=['Lapi agent V2','Extract','Review','Extraction Review'];
/** Phones have no Dashboard for anyone: they open on Lapi Agent. */
export const phoneRedirect=(view:string,device:Device)=>device==='phone'&&view==='Home';

/** Whether a view may be shown. Administrators always may; before the state has loaded, everything may. */
export function viewAllowed(view:string,state:ScreenState|null,isAdmin:boolean):boolean{
 if(state?.device==='phone'&&view==='Home')return false;
 if(isAdmin||!state)return true;
 if(state.device==='phone'&&PHONE_VIEWS.includes(view))return true;
 return CORE_VIEWS.includes(view)||state.views.includes(view);
}

/** The phone shows only Agent and Quick Extract: no "More" menu, no drawer. */
export const agentOnly=(state:ScreenState|null,isAdmin:boolean)=>Boolean(state&&state.device==='phone'&&!isAdmin&&state.views.length===0);

export type TrainingAction='ask'|'attach'|'quick-start'|'none';
export type TrainingCard={id:string;title:string;text:string;tryLabel?:string;action:TrainingAction;example?:string};
/** Five short cards shown in the agent, each with something real to try. */
export const TRAINING_CARDS:TrainingCard[]=[
 {id:'ask',title:'Ask in plain words',text:'Ask anything about your documents. Every answer shows the sources it came from, so you can check it.',tryLabel:'Try: what documents do I have?',action:'ask',example:'What documents do I have?'},
 {id:'add',title:'Add documents',text:'Tap the paper-clip for a photo or files, or use Quick start for a guided first upload. Several pages can be merged into one document.',tryLabel:'Open Quick start',action:'quick-start'},
 {id:'extract',title:'Pull out data',text:'Say what you need and I suggest the fields, extract them, and show every value next to its source for you to review.',tryLabel:'Try: pull out invoice totals',action:'ask',example:'/Extract the invoice number, date and total from my documents'},
 {id:'numbers',title:'Exact numbers and charts',text:'From spreadsheets I calculate exactly on the table, and I can draw bar, line or pie charts when you ask.',tryLabel:'Try: chart revenue by month',action:'ask',example:'Chart total revenue by month'},
 {id:'skills',title:'Teach me with a skill',text:'A skill is a short playbook: when it applies (document types, keywords or documents) and the steps. Upload a SKILL.md or write one in Skills & memory; I use it by myself when a request matches.',tryLabel:'Try: list my skills',action:'ask',example:'/skill'},
 {id:'trust',title:'What I never do',text:'I never send your passwords or tokens to an AI model, never show you data beyond your access, and I ask before anything goes to an external service.',action:'none'},
];
export const TRAINING_VERSION=2;
