/** Where people reach a person when the bot cannot help, or something went wrong. */
export const SUPPORT_EMAIL='maniatramco@gmail.com';
export const SUPPORT_NAME='Mani';

/** A ready-to-send email in the person's own mail app, with the details that help. */
export function helpMailto({message,name,workspace,page,version,error}:{message:string;name?:string;workspace?:string;page?:string;version?:string;error?:string}){
 const subject=`Lapi help: ${message.trim().slice(0,60)||'a question'}`;
 const lines=[message.trim(),'',`From: ${name||'(no name yet)'}`,workspace?`Workspace: ${workspace}`:'',page?`Screen: ${page}`:'',version?`Lapi version: ${version}`:'',error?`Error shown: ${error}`:'',typeof navigator!=='undefined'?`Device: ${navigator.userAgent}`:''].filter(line=>line!==undefined&&line!==null);
 return `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(lines.join('\n'))}`;
}
