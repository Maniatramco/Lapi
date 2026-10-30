/** Keyboard shortcuts for the workspace: pure key handling, so it can be tested without a browser. */
export type GoTarget={key:string;view:string;label:string;admin?:boolean;needsAddKnowledge?:boolean};
export const GO_TARGETS:GoTarget[]=[
 {key:'d',view:'Home',label:'Dashboard'},
 {key:'a',view:'Lapi agent V2',label:'Lapi Agent'},
 {key:'k',view:'Add knowledge',label:'Add knowledge',needsAddKnowledge:true},
 {key:'s',view:'Datasets',label:'Collections'},
 {key:'u',view:'Users & passwords',label:'Users & passwords'},
];
/** Rows of the "Keyboard shortcuts" dialog. */
export const SHORTCUT_LIST:{keys:string[];action:string}[]=[
 {keys:['?'],action:'Show keyboard shortcuts'},
 {keys:['/'],action:'Search, or type in the chat'},
 ...GO_TARGETS.map(t=>({keys:['G',t.key.toUpperCase()],action:`Go to ${t.label}`})),
 {keys:['N'],action:'New chat in Lapi Agent'},
 {keys:['Esc'],action:'Close a dialog'},
];
/** Tooltip suffix for a navigation item, for example " (G then D)". */
export function shortcutHint(view:string){const target=GO_TARGETS.find(t=>t.view===view);return target?` (G then ${target.key.toUpperCase()})`:'';}

export type ShortcutAccess={isAdmin:boolean;canAddKnowledge:boolean};
export type Command=
 |{type:'help'}|{type:'focus'}|{type:'new-chat'}|{type:'escape'}
 |{type:'go';view:string;label:string}
 |{type:'denied';message:string}
 |{type:'pending'};
export type ShortcutState={pending:boolean;at:number};
export const INITIAL_STATE:ShortcutState={pending:false,at:0};
/** "g" waits this long for the second key. */
export const SEQUENCE_MS=1500;
type KeyEventLike={key:string;ctrlKey?:boolean;metaKey?:boolean;altKey?:boolean;repeat?:boolean;isComposing?:boolean;target?:unknown};
type ElementLike={tagName?:string;isContentEditable?:boolean;type?:string;getAttribute?:(name:string)=>string|null;closest?:(selector:string)=>unknown};
const NOT_TEXT=['checkbox','radio','button','submit','reset','range','color','file','image'];
/** True while the person is typing: text inputs, text areas, selects and editable content. */
export function isTypingTarget(target:unknown):boolean{
 const el=target as ElementLike|null;
 if(!el||typeof el!=='object')return false;
 const tag=(el.tagName||'').toUpperCase();
 if(tag==='TEXTAREA'||tag==='SELECT')return true;
 if(tag==='INPUT')return !NOT_TEXT.includes(String(el.type||el.getAttribute?.('type')||'text').toLowerCase());
 if(el.isContentEditable)return true;
 const editable=el.getAttribute?.('contenteditable');
 if(editable!=null&&editable!=='false')return true;
 const role=el.getAttribute?.('role');
 return role==='textbox'||role==='combobox';
}
/** Decide what a key press does. Returns the next state and a command (null: let the page handle the key). */
export function resolveShortcut(event:KeyEventLike,state:ShortcutState,access:ShortcutAccess,now:number):{state:ShortcutState;command:Command|null}{
 const idle=INITIAL_STATE;
 if(event.key==='Escape')return {state:idle,command:{type:'escape'}};
 if(event.ctrlKey||event.metaKey||event.altKey||event.isComposing||isTypingTarget(event.target))return {state:idle,command:null};
 const key=event.key.length===1?event.key.toLowerCase():event.key;
 if(state.pending&&now-state.at<=SEQUENCE_MS){
  const target=GO_TARGETS.find(t=>t.key===key);
  if(!target)return {state:idle,command:null};
  if(target.admin&&!access.isAdmin)return {state:idle,command:{type:'denied',message:`${target.label} is for administrators.`}};
  if(target.needsAddKnowledge&&!access.canAddKnowledge)return {state:idle,command:{type:'denied',message:'Adding knowledge needs Editor access to a collection. Ask a collection owner or administrator.'}};
  return {state:idle,command:{type:'go',view:target.view,label:target.label}};
 }
 if(event.repeat)return {state:idle,command:null};
 if(key==='g')return {state:{pending:true,at:now},command:{type:'pending'}};
 if(key==='?')return {state:idle,command:{type:'help'}};
 if(key==='/')return {state:idle,command:{type:'focus'}};
 if(key==='n')return {state:idle,command:{type:'new-chat'}};
 return {state:idle,command:null};
}
