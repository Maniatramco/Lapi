"use client";
import {useEffect,useState} from "react";
import {LogOut,MonitorSmartphone,ShieldCheck} from "lucide-react";

type Api=(path:string,method?:string,body?:any)=>Promise<any>;
type SignedInSession={id:string;current:boolean;created_at:number;last_seen:number;client_ip:string;user_agent:string;sign_in:string};

/** A short, readable name for a browser's user-agent string. */
export function deviceName(agent:string){
 if(!agent)return "Unknown browser";
 const browser=/Edg\//.test(agent)?"Edge":/OPR\//.test(agent)?"Opera":/Firefox\//.test(agent)?"Firefox":/Chrome\//.test(agent)?"Chrome":/Safari\//.test(agent)?"Safari":/curl|python|httpx/i.test(agent)?"Script":"Browser";
 const system=/Windows/.test(agent)?"Windows":/iPhone|iPad/.test(agent)?"iOS":/Android/.test(agent)?"Android":/Mac OS X/.test(agent)?"macOS":/Linux/.test(agent)?"Linux":"";
 return system?`${browser} on ${system}`:browser;
}

const when=(seconds:number)=>seconds?new Date(seconds*1000).toLocaleString():"-";

/** Where you are signed in, with sign-out for any of them. */
export function MySessions({api,onSignedOut}:{api:Api;onSignedOut:()=>void}){
 const [sessions,setSessions]=useState<SignedInSession[]|null>(null),[idle,setIdle]=useState(30),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const load=async()=>{try{const d=await api("/me/sessions");setSessions(d.sessions);setIdle(d.idle_minutes);}catch(e){setError(e instanceof Error?e.message:"Sessions could not be loaded.");}};
 useEffect(()=>{void load();},[]);
 const act=async(fn:()=>Promise<void>)=>{setBusy(true);setError("");setNotice("");try{await fn();}catch(e){setError(e instanceof Error?e.message:"That did not work.");}finally{setBusy(false);}};
 const others=(sessions||[]).filter(s=>!s.current).length;
 return <section className="card account-security" aria-labelledby="my-sessions-title">
  <div className="account-summary"><div><h2 id="my-sessions-title"><MonitorSmartphone size={19}/> My sessions</h2>
   <p className="muted small">Where you are signed in now. Sessions end after 12 hours, or after {idle} minutes without activity.</p></div>
   <button className="btn" disabled={busy||!others} onClick={()=>void act(async()=>{const d=await api("/me/sessions/sign-out-others","POST");setNotice(`Signed out ${d.sessions_ended} other session${d.sessions_ended===1?"":"s"}.`);await load();})}><LogOut size={15}/> Sign out other sessions</button></div>
  {notice&&<div role="status" className="notice">{notice}</div>}
  {error&&<div role="alert" className="notice error">{error}</div>}
  {sessions===null?<p className="muted small" role="status">Loading sessions…</p>:<ul className="session-list">{sessions.map(s=><li key={s.id}>
   <div><strong>{deviceName(s.user_agent)}</strong>{s.current&&<span className="session-current">This browser</span>}
    <small className="muted">{s.client_ip||"Unknown address"} · signed in {when(s.created_at)} · last active {when(s.last_seen)} · {s.sign_in==="keycloak"?"Keycloak":"Password"}</small></div>
   <button className="btn" disabled={busy} aria-label={`Sign out ${deviceName(s.user_agent)}${s.current?" (this browser)":""}`}
    onClick={()=>void act(async()=>{const d=await api(`/me/sessions/${s.id}`,"DELETE");if(d.signed_out_this_browser){onSignedOut();return;}setNotice("Signed out that session.");await load();})}>Sign out</button>
  </li>)}</ul>}
 </section>;
}

/** An authenticator app as a second factor for password sign-in (break-glass administrators). */
export function AuthenticatorSetup({api}:{api:Api}){
 const [status,setStatus]=useState<{enabled:boolean;pending:boolean}|null>(null),[step,setStep]=useState<"idle"|"password"|"scan"|"disable">("idle");
 const [password,setPassword]=useState(""),[code,setCode]=useState(""),[setup,setSetup]=useState<{secret:string;uri:string}|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const load=async()=>{try{setStatus(await api("/auth/totp"));}catch(e){setError(e instanceof Error?e.message:"Status could not be loaded.");}};
 useEffect(()=>{void load();},[]);
 const reset=()=>{setStep("idle");setPassword("");setCode("");setSetup(null);};
 const act=async(fn:()=>Promise<void>)=>{setBusy(true);setError("");setNotice("");try{await fn();}catch(e){setError(e instanceof Error?e.message:"That did not work.");}finally{setBusy(false);}};
 const digits=(value:string)=>value.replace(/\D/g,"").slice(0,6);
 return <section className="card account-security" aria-labelledby="authenticator-title">
  <div className="account-summary"><div><h2 id="authenticator-title"><ShieldCheck size={19}/> Authenticator app</h2>
   <p className="muted small">{status?.enabled?"On: signing in with your password also needs a 6-digit code from your phone.":"Off: add a second step to password sign-in with an app such as Microsoft Authenticator, Google Authenticator or 1Password."}</p></div>
   {step==="idle"&&status&&(status.enabled
    ?<button className="btn" onClick={()=>{reset();setStep("disable");}}>Turn off</button>
    :<button className="btn primary" onClick={()=>{reset();setStep("password");}}>Set up</button>)}</div>
  {notice&&<div role="status" className="notice">{notice}</div>}
  {error&&<div role="alert" className="notice error">{error}</div>}
  {step==="password"&&<form className="account-form" onSubmit={e=>{e.preventDefault();void act(async()=>{setSetup(await api("/auth/totp/setup","POST",{current_password:password}));setPassword("");setStep("scan");});}}>
   <fieldset disabled={busy}><label htmlFor="totp-password">Your current password<input id="totp-password" type="password" autoComplete="current-password" value={password} required maxLength={200} onChange={e=>setPassword(e.target.value)}/></label>
    <div className="row"><button className="btn primary" type="submit">Continue</button><button className="btn" type="button" onClick={reset}>Cancel</button></div></fieldset></form>}
  {step==="scan"&&setup&&<form className="account-form" onSubmit={e=>{e.preventDefault();void act(async()=>{await api("/auth/totp/confirm","POST",{code});reset();setNotice("Authenticator app is on. Keep your phone safe; if you lose it, another administrator can reset it.");await load();});}}>
   <ol className="totp-steps">
    <li>In your authenticator app, add an account and choose <strong>Enter a setup key</strong> (or open the link on your phone).</li>
    <li>Account name: <strong>Lapi</strong>. Key: <code className="totp-secret">{setup.secret.replace(/(.{4})/g,"$1 ").trim()}</code> (time-based).</li>
    <li>Type the 6-digit code the app shows.</li>
   </ol>
   <p className="small"><a href={setup.uri}>Open in authenticator app</a></p>
   <fieldset disabled={busy}><label htmlFor="totp-code">6-digit code<input id="totp-code" inputMode="numeric" autoComplete="one-time-code" value={code} required pattern="[0-9]{6}" onChange={e=>setCode(digits(e.target.value))}/></label>
    <div className="row"><button className="btn primary" type="submit">Turn on</button><button className="btn" type="button" onClick={reset}>Cancel</button></div></fieldset></form>}
  {step==="disable"&&<form className="account-form" onSubmit={e=>{e.preventDefault();void act(async()=>{await api("/auth/totp/disable","POST",{current_password:password,code});reset();setNotice("Authenticator app is off.");await load();});}}>
   <fieldset disabled={busy}><label htmlFor="totp-off-password">Your current password<input id="totp-off-password" type="password" autoComplete="current-password" value={password} required maxLength={200} onChange={e=>setPassword(e.target.value)}/></label>
    <label htmlFor="totp-off-code">Current 6-digit code<input id="totp-off-code" inputMode="numeric" autoComplete="one-time-code" value={code} required pattern="[0-9]{6}" onChange={e=>setCode(digits(e.target.value))}/></label>
    <div className="row"><button className="btn primary" type="submit">Turn off</button><button className="btn" type="button" onClick={reset}>Cancel</button></div></fieldset></form>}
 </section>;
}
