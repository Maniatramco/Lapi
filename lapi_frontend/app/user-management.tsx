"use client";
import {ActionButton} from "./action-button";
import { useEffect, useRef, useState } from "react";
import { KeyRound, RefreshCw, Search, Users } from "lucide-react";
import "./user-management.css";
import { DatasetAssignments } from "./dataset-assignments";
import { SummaryTiles } from "./summary-tiles";
import { AuthenticatorSetup, MySessions } from "./account-security";

type Role = "user" | "auditor" | "administrator";
type Account = {id:string;username:string;role:Role;is_admin:boolean;is_auditor?:boolean;is_contributor?:boolean;workspace_role?:Role;sign_in?:"keycloak"|"password";created_at:number;updated_at:number;created_by?:string;updated_by?:string};
type Props = {
 api:(path:string,method?:string,body?:any)=>Promise<any>;
 user:{id:string;username:string;is_admin?:boolean;is_auditor?:boolean;sign_in?:string};
 /** Keycloak signs people in: accounts and their passwords are managed there. */
 keycloak?:boolean;
 onPasswordChanged:()=>void;
 onRoleChanged:()=>void;
};
type Operation = {kind:"create"|"reset"|"self"|"role"|"delete"|"mfa";account?:Account};
const empty = {username:"",current_password:"",password:"",confirmation:"",role:"user" as Role};

export function UserManagement({api,user,keycloak=false,onPasswordChanged,onRoleChanged}:Props){
 const [accounts,setAccounts]=useState<Account[]>([]),[search,setSearch]=useState("");
 const [operation,setOperation]=useState<Operation|null>(null),[values,setValues]=useState(empty);
 const [mappingAccount,setMappingAccount]=useState<Account|null>(null);
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const formRef=useRef<HTMLFormElement>(null),mounted=useRef(true);
 const isAdmin=Boolean(user.is_admin);
 // Auditors see people and their access, read-only.
 const canRead=isAdmin||Boolean(user.is_auditor);
 // Keycloak accounts have no Lapi password; a sign-in within ten minutes confirms changes instead.
 const viaKeycloak=user.sign_in==="keycloak";
 async function load(){
  setLoading(true);
  try{const rows=await api("/users");if(mounted.current)setAccounts(rows);}
  catch(e){if(mounted.current)setError(e instanceof Error?e.message:"Unable to load users.");}
  finally{if(mounted.current)setLoading(false);}
 }
 useEffect(()=>{mounted.current=true;if(canRead)void load();return()=>{mounted.current=false;};},[canRead,user.id]);
 useEffect(()=>{if(operation){formRef.current?.scrollIntoView({block:"nearest"});formRef.current?.querySelector<HTMLInputElement>("input")?.focus();}},[operation]);
 function open(next:Operation){
  setMappingAccount(null);
  setValues({...empty,role:next.kind==="role"&&!next.account?.is_admin?"administrator":"user"});
  setError("");setNotice("");setOperation(next);
 }
 function cancel(){setValues({...empty});setOperation(null);setError("");}
 async function submit(event:React.FormEvent){
  event.preventDefault();if(busy||!operation)return;
  if(!["role","delete","mfa"].includes(operation.kind)&&(values.password.length<12||values.password.length>200)){setError("Use a password of 12-200 characters.");return;}
  if(!["role","delete","mfa"].includes(operation.kind)&&values.password!==values.confirmation){setError("Passwords do not match. Nothing changed.");return;}
  if(operation.kind==="delete"&&values.username!==operation.account!.username){setError("Type the exact username to confirm deletion. Nothing changed.");return;}
  if(operation.kind!=="create"&&!viaKeycloak&&!values.current_password){setError("Enter your current password.");return;}
  setBusy(true);setError("");
  try{
   const passwords={password:values.password,confirmation:values.confirmation};
   const current_password=values.current_password||(viaKeycloak?"keycloak-session":"");
   if(operation.kind==="create"){
    await api("/users","POST",{username:values.username,...passwords});
    setNotice("Created "+values.username+". Share its password privately and assign datasets using Dataset access.");
   }else if(operation.kind==="mfa"){
    await api("/users/"+encodeURIComponent(operation.account!.id)+"/totp/reset","POST",{current_password});
    setNotice("Removed the authenticator of "+operation.account!.username+" and signed them out. They can set up a new one after signing in.");
   }else if(operation.kind==="delete"){
    await api("/users/"+encodeURIComponent(operation.account!.id),"DELETE",{username:values.username,current_password});
    setAccounts(rows=>rows.filter(account=>account.id!==operation.account!.id));
    setNotice("Deleted "+operation.account!.username+". Sign-in sessions and dataset access were removed. Shared documents and results are preserved.");
   }else if(operation.kind==="reset"){
    await api("/users/"+encodeURIComponent(operation.account!.id)+"/password","POST",{...passwords,current_password});
    setNotice("Password reset for "+operation.account!.username+". All its sessions were signed out. Documents and results are preserved.");
   }else if(operation.kind==="role"){
    const result=await api("/users/"+encodeURIComponent(operation.account!.id)+"/role","PATCH",{role:values.role,current_password});
    if(result.sessions_revoked&&operation.account!.id===user.id){setValues({...empty});setOperation(null);onRoleChanged();return;}
    setNotice(operation.account!.username+" is now "+(result.user.is_admin?"an Administrator":"a User")+"."+(result.sessions_revoked?" Their sessions were signed out; ask them to sign in again.":""));
   }else{
    await api("/auth/password","POST",{...passwords,current_password});
    setValues({...empty});setOperation(null);onPasswordChanged();return;
   }
   setValues({...empty});setOperation(null);await load();
  }catch(e){setError(e instanceof Error?e.message:"The change failed. Try again.");}
  finally{setBusy(false);}
 }
 const names=new Map(accounts.map(account=>[account.id,account.username]));
 const stamp=(value:number)=>value?new Date(value*1000).toLocaleString():"-";
 return <div className="user-management">
  <section className="card account-summary">
   <div><h2><KeyRound size={19}/> My password</h2><p className="muted small">Signed in as <strong>{user.username}</strong>. Passwords are never displayed or retrievable here.</p></div>
   {viaKeycloak?<p className="muted small">You sign in with Keycloak; change your password there.</p>:<ActionButton className="btn" disabled={busy} onClick={()=>open({kind:"self"})} label="Change my password" action="password"/>}
  </section>
  <MySessions api={api} onSignedOut={()=>window.location.reload()}/>
  {!viaKeycloak&&<AuthenticatorSetup api={api}/>}
  {notice&&<div role="status" className="notice">{notice}</div>}
  {isAdmin&&mappingAccount&&<DatasetAssignments api={api} account={mappingAccount} onClose={()=>setMappingAccount(null)}/>}
  {operation&&<form ref={formRef} className="card account-form" onSubmit={submit} aria-label={operation.kind==="mfa"?"Reset authenticator":operation.kind==="delete"?"Delete user":operation.kind==="role"?"Change user role":operation.kind==="create"?"Create user":operation.kind==="reset"?"Reset user password":"Change my password"}>
   <h2>{operation.kind==="mfa"?"Reset authenticator — "+operation.account!.username:operation.kind==="delete"?"Delete user — "+operation.account!.username:operation.kind==="role"?"Change role — "+operation.account!.username:operation.kind==="create"?"Create user":operation.kind==="reset"?"Reset password — "+operation.account!.username:"Change my password"}</h2>
   <p className="muted small">{operation.kind==="mfa"?"Use this when someone lost the phone with their authenticator app. Their sessions are signed out and they can set up a new authenticator after signing in with their password.":operation.kind==="delete"?"Delete this account and remove all sign-in sessions and dataset assignments. Shared documents and results are preserved. Private history is archived outside the active workspace. Accounts owning shared content must transfer it first.":operation.kind==="role"?"Administrators can manage users, passwords, every dataset, and model configuration. Auditors can see people, access and activity but change nothing and open no dataset content. A role change signs this user out. Saved dataset assignments are retained. At least one administrator must remain.":operation.kind==="create"?"New users see only datasets assigned by an administrator and cannot manage other accounts.":"All sessions for this account will be signed out after saving. Documents and results stay available."}</p>
   <fieldset disabled={busy}>
    {operation.kind==="create"?<label htmlFor="account-username">Username<input id="account-username" value={values.username} maxLength={120} pattern={"[A-Za-z0-9][A-Za-z0-9_.@\\-]*"} autoComplete="off" required onChange={e=>setValues({...values,username:e.target.value})}/><small>Letters, numbers, periods, underscores, @ and hyphens; no spaces.</small></label>:viaKeycloak?<p className="muted small">You signed in with Keycloak, so no password is needed. If your sign-in is older than ten minutes, sign out and in again first.</p>:<label htmlFor="account-current-password">{["reset","role","delete","mfa"].includes(operation.kind)?"Your administrator password":"Current password"}<input id="account-current-password" type="password" autoComplete="current-password" value={values.current_password} maxLength={200} required onChange={e=>setValues({...values,current_password:e.target.value})}/></label>}
    {operation.kind==="mfa"?null:operation.kind==="delete"?<label htmlFor="account-delete-username">Type {operation.account!.username} to confirm<input id="account-delete-username" value={values.username} autoComplete="off" maxLength={120} required onChange={e=>setValues({...values,username:e.target.value})}/></label>:operation.kind==="role"?<label htmlFor="account-role">New role<select id="account-role" value={values.role} onChange={e=>setValues({...values,role:e.target.value as Role})}><option value="user">User</option><option value="auditor">Auditor (read-only: people, access and activity)</option><option value="administrator">Administrator</option></select></label>:<>
     <label htmlFor="account-new-password">New password<input id="account-new-password" type="password" autoComplete="new-password" value={values.password} minLength={12} maxLength={200} required onChange={e=>setValues({...values,password:e.target.value})}/><small>Use 12-200 characters. Save it in your password manager.</small></label>
     <label htmlFor="account-confirm-password">Confirm new password<input id="account-confirm-password" type="password" autoComplete="new-password" value={values.confirmation} minLength={12} maxLength={200} required onChange={e=>setValues({...values,confirmation:e.target.value})}/></label>
    </>}
    <div className="row"><button className={operation.kind==="delete"?"btn account-delete-confirm":"btn primary"} type="submit">{busy?"Saving.":operation.kind==="mfa"?"Reset authenticator and sign out":operation.kind==="delete"?"Delete user and remove access":operation.kind==="role"?"Save role":operation.kind==="create"?"Create user":operation.kind==="reset"?"Reset password":"Save password and sign out"}</button><button className="btn" type="button" onClick={cancel}>Cancel</button></div>
   </fieldset>
   {error&&<div role="alert" className="notice error">{error}</div>}
  </form>}
  {!operation&&error&&<div role="alert" className="notice error">{error}</div>}
  {canRead&&accounts.length>0&&<SummaryTiles label="User summary" tiles={[
   {label:"People",value:accounts.length,detail:"with an Lapi account",tone:""},
   {label:"Administrators",value:accounts.filter(a=>a.is_admin).length,detail:"access every dataset",tone:"info"},
   {label:"Auditors",value:accounts.filter(a=>a.is_auditor).length,detail:"read-only access review",tone:""},
   {label:"Users",value:accounts.filter(a=>!a.is_admin).length,detail:"access assigned datasets",tone:"ok"},
  ]}/>}
  {canRead&&<section className="card account-directory">
   <div className="account-summary"><h2><Users size={19}/> Users</h2><div className="row"><button title="Refresh users" className="btn" disabled={loading||busy} onClick={()=>void load()} aria-label="Refresh users"><RefreshCw size={15}/></button>{!keycloak&&isAdmin&&<ActionButton className="btn primary" disabled={busy} onClick={()=>open({kind:"create"})} label="Add user" action="add" showLabel/>}</div></div>
   <label className="account-search" htmlFor="account-search"><Search size={16}/><input id="account-search" placeholder="Search usernames" value={search} onChange={e=>setSearch(e.target.value)}/></label>
   <div className="account-table"><table><thead><tr><th>Username</th><th>Access</th><th>Created</th><th>Last updated</th><th>Manage</th></tr></thead><tbody>{accounts.filter(account=>account.username.toLowerCase().includes(search.toLowerCase())).map(account=><tr key={account.id}>
    <td><strong>{account.username}</strong>{account.id===user.id&&<div className="muted small">You</div>}{account.sign_in==="keycloak"&&<div className="muted small">Keycloak</div>}</td>
    <td>{account.is_admin?"Administrator":[account.is_contributor&&"Contributor",account.is_auditor&&"Auditor"].filter(Boolean).join(" · ")||"User"}</td>
    <td>{stamp(account.created_at)}<div className="muted small">{names.get(account.created_by||"")||"Creator not recorded"}</div></td>
    <td>{stamp(account.updated_at)}<div className="muted small">{names.get(account.updated_by||"")||"Updater not recorded"}</div></td>
    <td>{!isAdmin?<small className="muted">Read-only</small>:<div className="row">
     {account.sign_in==="keycloak"?<small className="muted">Password and role in Keycloak</small>:<>
     <ActionButton className="btn" disabled={busy} onClick={()=>open(account.id===user.id?{kind:"self"}:{kind:"reset",account})} label={`${account.id===user.id?"Change password":"Reset password"} for ${account.username}`} action="password"/>
     <ActionButton className="btn" disabled={busy} aria-label={"Change role for "+account.username} onClick={()=>open({kind:"role",account})} label="Change role" action="role"/></>}
     {account.id!==user.id&&<button className="btn" disabled={busy} title={"Sign "+account.username+" out of every browser"} onClick={()=>{if(!window.confirm(`Sign ${account.username} out of every browser now? They can sign in again.`))return;setBusy(true);setError("");api("/users/"+encodeURIComponent(account.id)+"/sessions/sign-out","POST").then(r=>setNotice(`Signed ${account.username} out of ${r.sessions_ended} session${r.sessions_ended===1?"":"s"}.`)).catch(e=>setError(e instanceof Error?e.message:"Sign-out failed.")).finally(()=>setBusy(false));}}>Sign out everywhere</button>}
     {account.sign_in!=="keycloak"&&account.id!==user.id&&<button className="btn" disabled={busy} onClick={()=>open({kind:"mfa",account})}>Reset authenticator</button>}
     <ActionButton className="btn" disabled={busy||account.is_admin} title={account.is_admin?"Administrators can access every dataset":undefined} onClick={()=>{cancel();setNotice("");setMappingAccount(account);}} label="Dataset access" action="access"/>
     <ActionButton className="btn account-delete" disabled={busy||account.id===user.id||(account.is_admin&&accounts.filter(row=>row.is_admin).length<=1)} title={account.id===user.id?"You cannot delete your signed-in account":account.is_admin&&accounts.filter(row=>row.is_admin).length<=1?"Keep at least one administrator":"Delete user and remove access"} onClick={()=>open({kind:"delete",account})} label={"Delete user "+account.username} action="remove"/>
    </div>}{account.is_admin&&<small className="muted">All datasets</small>}</td>
   </tr>)}</tbody></table></div>
   {!loading&&!accounts.some(account=>account.username.toLowerCase().includes(search.toLowerCase()))&&<p className="muted">No users match this search.</p>}
   {loading&&<p role="status" className="muted">Loading users.</p>}
  </section>}
 </div>;
}
