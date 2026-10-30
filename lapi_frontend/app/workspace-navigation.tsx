"use client";
import {useEffect,useState} from 'react';
import {BookOpen,ChevronRight,ToggleRight,CloudUpload,Database,FileSearch,FileText,FolderPlus,Info,Layers,Settings2,Sparkles,Table2} from 'lucide-react';
import {AgentLogo} from './agent-logo';
import {shortcutHint} from './shortcuts';

type Item={name:string;icon:typeof Database};
export function WorkspaceNavigation({view,isAdmin,allowed=()=>true,onNavigate,adminItems,adminOpen,onAdminToggle}:{view:string;isAdmin:boolean;allowed?:(name:string)=>boolean;onNavigate:(name:any)=>void;adminItems:Item[];adminOpen:boolean;onAdminToggle:()=>void}){
 const onboardViews=['Datasets','Prompt templates','Extract','Extract Data','Review','Add knowledge'],modelViews=['Model Registration','Model Mapping','Enabled models'];
 const [onboardOpen,setOnboardOpen]=useState(onboardViews.includes(view));
 useEffect(()=>{if(onboardViews.includes(view))setOnboardOpen(true);},[view]);
 const link=(name:string,label:string,Icon:typeof Database)=>{
  if(!allowed(name))return null;  // Screens switched off for this person and device (Access map → Screens).
  const selected=view===name||(name==='Extract'&&view==='Review');
  return <button key={name} className={`nav-item${selected?' selected':''}`} aria-label={label} title={label+shortcutHint(name)} aria-current={selected?'page':undefined} onClick={()=>onNavigate(name)}>{name==='Lapi agent V2'?<AgentLogo size={24}/>:<Icon size={18}/>}<span className="nav-item-label">{label}</span></button>;
 };
 return <nav aria-label="Workspace pages">
  {link('Home','Dashboard',Database)}
  {link('Lapi agent V2','Lapi Agent',Database)}
  {link('Skills & memory','Skills & memory',Sparkles)}
  <button className={`nav-item nav-group-toggle${onboardViews.includes(view)?' group-active':''}`} aria-label="Onboard" aria-expanded={onboardOpen} aria-controls="onboard-navigation" onClick={()=>setOnboardOpen(!onboardOpen)}><FolderPlus size={18}/><span className="nav-item-label">Onboard</span><ChevronRight size={14} className={onboardOpen?'rotated':''}/></button>
  <div id="onboard-navigation" className="nav-submenu" hidden={!onboardOpen}>
   {link('Datasets','Dataset',BookOpen)}{link('Prompt templates','Prompt',FileText)}{link('Extract Data','Extract',Table2)}{link('Extract','Review',FileSearch)}{link('Add knowledge','Add knowledge',CloudUpload)}
  </div>
  {(isAdmin||adminItems.length>0)&&<button className={`nav-item nav-more${modelViews.includes(view)?' group-active':''}`} aria-label="Manage workspace" aria-expanded={adminOpen} aria-controls="admin-navigation" onClick={onAdminToggle}><Settings2 size={18}/><span className="nav-item-label">Manage workspace</span><ChevronRight size={14} className={adminOpen?'rotated':''}/></button>}
  {adminOpen&&(isAdmin||adminItems.length>0)&&<div id="admin-navigation" className="admin-navigation">{isAdmin&&<>{link('Model Registration','Model Registration',Layers)}{link('Model Mapping','Model Mapping',BookOpen)}{link('Enabled models','Enabled models',ToggleRight)}</>}{adminItems.map(item=>link(item.name,item.name,item.icon))}</div>}
  {link('About','About',Info)}
 </nav>;
}
