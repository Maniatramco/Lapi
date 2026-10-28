/** Which screens this person sees on this device (decided by OpenFGA, served by /api/me/screens),
 * and the short agent training. Pure helpers, unit tested. */
export type Device='phone'|'computer';
export type ScreenState={device:Device;screens:string[];views:string[];core:string[];administrator:boolean};

/** Phones are narrower than 640 px, the same breakpoint as the app's phone layout. */
export const deviceFor=(width:number):Device=>width<640?'phone':'computer';

/** Views that never need a grant: the Dashboard and Lapi Agent (Quick start is a dialog on them). */
export const CORE_VIEWS=['Home','Lapi agent V2'];

/** Whether a view may be shown. Administrators always may; before the state has loaded, everything may. */
export function viewAllowed(view:string,state:ScreenState|null,isAdmin:boolean):boolean{
 if(isAdmin||!state)return true;
 return CORE_VIEWS.includes(view)||state.views.includes(view);
}

/** The phone shows only Dashboard, Agent and Quick start: no "More" menu, no drawer. */
export const agentOnly=(state:ScreenState|null,isAdmin:boolean)=>Boolean(state&&state.device==='phone'&&!isAdmin&&state.views.length===0);

export type TrainingAction='ask'|'attach'|'quick-start'|'none';
export type TrainingCard={id:string;title:string;text:string;tryLabel?:string;action:TrainingAction;example?:string};
/** Five short cards shown in the agent, each with something real to try. */
export const TRAINING_CARDS:TrainingCard[]=[
 {id:'ask',title:'Ask in plain words',text:'Ask anything about your documents. Every answer shows the sources it came from, so you can check it.',tryLabel:'Try: what documents do I have?',action:'ask',example:'What documents do I have?'},
 {id:'add',title:'Add documents',text:'Tap the paper-clip for a photo or files, or use Quick start for a guided first upload. Several pages can be merged into one document.',tryLabel:'Open Quick start',action:'quick-start'},
 {id:'extract',title:'Pull out data',text:'Say what you need and I suggest the fields, extract them, and show every value next to its source for you to review.',tryLabel:'Try: pull out invoice totals',action:'ask',example:'/Extract the invoice number, date and total from my documents'},
 {id:'numbers',title:'Exact numbers and charts',text:'From spreadsheets I calculate exactly on the table, and I can draw bar, line or pie charts when you ask.',tryLabel:'Try: chart revenue by month',action:'ask',example:'Chart total revenue by month'},
 {id:'trust',title:'What I never do',text:'I never send your passwords or tokens to an AI model, never show you data beyond your access, and I ask before anything goes to an external service.',action:'none'},
];
export const TRAINING_VERSION=1;
