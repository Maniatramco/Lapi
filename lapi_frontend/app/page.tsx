"use client";
import {ActionButton} from "./action-button";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { SignInLayout } from "./sign-in-layout";
import { DatasetSearch } from "./dataset-directory";
import {ReviewDetail} from './review-detail';
import { ExtractionDirectory } from "./extraction-directory";
import { ExtractData } from "./extract-data";
import { PromptTemplates } from "./prompt-templates";
import { AgentSetup } from "./agent-setup";
import { ReExtractionDialog } from "./re-extract";
import { WorkspaceNavigation } from "./workspace-navigation";
import { WorkflowOverview } from "./workflow-overview";
import { DatasetDashboard } from "./dataset-dashboard";
import {DatasetKnowledgeChat,knowledgeScopeKey} from "./dataset-knowledge-chat";
import { StorageConfiguration } from "./storage-configuration";
import { ConnectionSettings } from "./connection-settings";
import { ConnectionStatus } from "./connection-status";
import { AboutLapi } from "./about-lapi";
import { WalkthroughGate } from "./walkthrough";
import { WorkspaceAssist } from "./workspace-assist";
import { OPEN_REVIEW_EVENT } from "./quick-start-flow";
import { deviceFor, viewAllowed, agentOnly, type ScreenState } from "./screens-client";
import { OperationProgress, extractionProgressJob } from "./operation-progress";
import "./workspace-flow.css";
import { DatasetWorkspace, DatasetMappings, ModelPicker, eligibleModels, modelLabel } from "./dataset-workspace";
import { ModelRegistration } from "./model-registration";
import { KnowledgeIndexBanner } from "./knowledge-index-banner";
import { UserManagement } from "./user-management";
import { AccessMap } from "./access-map";
import { AdminDocuments } from "./admin-documents";
import { TokenUsageAdmin } from "./token-usage";
import { AgentV2 } from "./agent-v2";
import { AgentLogo } from "./agent-logo";
import "./agent-shortcut.css";
import { rememberAssistantDataset } from "./agent-prompt-selection";
import {prepareFreshLoginChat} from './chat-login-session';
import { fetchWithSessionCsrf } from "./session-request";
import {pendingJobIds,mergeJobUpdates} from './workflow-polling';
import { ToggleRight,
  Activity,
  Bot,
  BookOpen,
  Check,
  ChevronRight,
  HardDrive,
  Database,
  FileSearch,
  FileText,
  Layers,
  Loader2,
  LogOut,
  Menu,
  MessageSquare,
  RefreshCw,
  Shield,
  Square,
  X,
  AlertCircle,
  CheckCircle2,
  KeyRound,
  Server,
  CloudUpload,
  Coins,
  Network,
} from "lucide-react";
import { AddKnowledge } from "./add-knowledge";
import { PageBand, PAGE_INTROS } from "./page-band";
import { EnabledModels } from "./enabled-models";
import { JobsBoard } from "./jobs-board";
import { NeedsAttentionDialog, attentionItems, onAttention, type AttentionScope } from "./needs-attention";
import { ManageDataset, onDatasetEditor, type ManageRequest } from "./manage-dataset";
import { MappingOverview } from "./mapping-overview";
import type { DatasetKnowledgeScope } from "./dataset-knowledge-picker";
import { randomId } from "./random-id";

type Entity = Record<string, any>;
type View =
  | "About"
  | "Skills & memory"
  | "Home"
  | "Datasets"
  | "Lapi agent V2"
  | "Extract"
  | "Extract Data"
  | "Extraction Review"
  | "Review"
  | "Re-extract"
  | "Prompt templates"
  | "Jobs & activity"
  | "Storage"
  | "Files & processing"
  | "Model Registration"
  | "Model Mapping"
  | "Enabled models"
  | "Users & passwords"
  | "Access map"
  | "Token usage"
  | "Add knowledge";
const sections: { name: View; icon: typeof Shield; group?: string }[] = [
  { name: "About", icon: BookOpen },
  { name: "Home", icon: Database, group: "WORKSPACE" },
  { name: "Lapi agent V2", icon: Bot, group: "WORKSPACE" },
  { name: "Skills & memory", icon: Bot, group: "WORKSPACE" },
  { name: "Users & passwords", icon: KeyRound },
  { name: "Access map", icon: Network },
  { name: "Datasets", icon: BookOpen },
  { name: "Extract", icon: FileSearch },
  { name: "Extract Data", icon: Database },
  { name: "Review", icon: FileSearch },
  { name: "Extraction Review", icon: FileSearch },
  { name: "Re-extract", icon: RefreshCw },
  { name: "Prompt templates", icon: FileText },
  { name: "Jobs & activity", icon: Activity },
  { name: "Storage", icon: HardDrive },
  { name: "Files & processing", icon: FileText },
  { name: "Token usage", icon: Coins },
  { name: "Model Registration", icon: Layers },
  { name: "Model Mapping", icon: BookOpen },
  { name: "Enabled models", icon: ToggleRight },
  { name: "Add knowledge", icon: CloudUpload },
];
// Keep saved route identifiers compatible while presenting the product names.
const viewLabel = (name: View) => name === "Home" ? "Dashboard" : name === "Lapi agent V2" ? "Lapi Agent" : name === "Extract" ? "Review" : name === "Extract Data" ? "Extract" : name;
const viewRoute = (name: View) => name === "Extract Data" ? "Extract Data" : viewLabel(name);
type ReviewReturn = {view: View; datasetId: string; agentTab: string; extractionTab: string};
const date = (v: string | number) =>
  v
    ? new Date(
        typeof v === "number" && v < 100000000000 ? v * 1000 : v,
      ).toLocaleString()
    : "—";
const json = (v: unknown) => JSON.stringify(v, null, 2);
// Codes the Keycloak callback adds to /?sign_in_error= (lapi_app/keycloak_auth.py).
const SIGN_IN_ERRORS: Record<string, string> = {
  denied: "Sign-in was cancelled.",
  expired: "That sign-in took too long or was started in another tab. Try again.",
  unavailable: "The sign-in service is unreachable right now. Try again in a minute.",
  account_conflict: "A local Lapi account already uses your username. Ask an administrator to rename or delete it.",
  mfa_required: "Administrators must sign in with an authenticator code. Set up your authenticator app in your account security settings, then sign in again.",
  failed: "Sign-in did not complete. Try again, or ask an administrator to check the server log.",
};
/** The provider's own mark on its sign-in button (brand colours, as their sign-in guidelines ask). */
function ProviderMark({alias}:{alias:string}){
  if(alias==="microsoft")return <svg width="18" height="18" viewBox="0 0 21 21" aria-hidden="true"><rect x="1" y="1" width="9" height="9" fill="#f25022"/><rect x="11" y="1" width="9" height="9" fill="#7fba00"/><rect x="1" y="11" width="9" height="9" fill="#00a4ef"/><rect x="11" y="11" width="9" height="9" fill="#ffb900"/></svg>;
  if(alias==="google")return <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>;
  if(alias==="github")return <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true"><path fill="#181717" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>;
  // Any other provider (GitLab, Okta, SAML …) gets a key icon and its label.
  return <KeyRound size={17} aria-hidden="true"/>;
}
/** With Keycloak, Lapi's password form is only the local administrators' break-glass path. */
function BreakGlass({ on, children }: { on: boolean; children: ReactNode }) {
  return on ? <details className="login-breakglass"><summary>Emergency administrator sign-in</summary>{children}</details> : <>{children}</>;
}
function Status({ value }: { value: string }) {
  const green = [
    "ready",
    "completed",
    "succeeded",
    "healthy",
    "connected",
    "available",
  ].includes(value);
  const red = ["failed", "error", "unavailable", "cancelled"].includes(value);
  return (
    <span className={`pill ${green ? "green" : red ? "red" : "amber"}`}>
      <span className="dot" />
      {(value || "unknown").replaceAll("_", " ")}
    </span>
  );
}
function Empty({
  title,
  detail,
  icon: Icon = FileText,
}: {
  title: string;
  detail: string;
  icon?: typeof Shield;
}) {
  return (
    <div className="empty">
      <Icon size={32} strokeWidth={1.3} />
      <h3>{title}</h3>
      <p className="small">{detail}</p>
    </div>
  );
}
function Field({
  label,
  help,
  children,
}: {
  label: string;
  help?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {help && <small>{help}</small>}
    </div>
  );
}
function Notice({
  children,
  tone = "info",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <div
      className={`notice ${tone === "error" ? "error" : tone === "warn" ? "warn" : ""}`}
    >
      <AlertCircle size={16} />
      <div>{children}</div>
    </div>
  );
}
export default function App() {
  const [view, setView] = useState<View>("Home");
  const [homeSearch,setHomeSearch]=useState('');
  const [dashboardDatasetId,setDashboardDatasetId]=useState('');
  // Newly vectorized documents handed from Add knowledge to the Dashboard chat.
  const [dashboardHandoff,setDashboardHandoff]=useState<(DatasetKnowledgeScope&{key:number})|null>(null);
  const agentWorkspace=view==='Lapi agent V2';
  const [directorySearch,setDirectorySearch]=useState('');
  const [datasetDirectoryVisible,setDatasetDirectoryVisible]=useState(true);
  useEffect(()=>{if(view!=="Datasets"||!datasetDirectoryVisible)setDirectorySearch('');},[view,datasetDirectoryVisible]);
  useEffect(()=>{if(view!=='Home')setHomeSearch('');},[view]);
  const [agentTab,setAgentTab]=useState("Chat");
  const [user, setUser] = useState<Entity | null>(null);
  // Screens this person may see on this device (OpenFGA, /api/me/screens); re-read every minute and when the device class changes.
  const [screens, setScreens] = useState<ScreenState | null>(null);
  useEffect(() => {
    if (!user) { setScreens(null); return; }
    let stopped = false, device = deviceFor(window.innerWidth);
    const read = () => fetch(`/api/me/screens?device=${device}`, { credentials: "include" }).then(r => r.ok ? r.json() : null).then(state => { if (!stopped && state) setScreens(state); }).catch(() => undefined);
    void read();
    const timer = window.setInterval(() => void read(), 60000);
    const resized = () => { const next = deviceFor(window.innerWidth); if (next !== device) { device = next; void read(); } };
    window.addEventListener("resize", resized);
    return () => { stopped = true; window.clearInterval(timer); window.removeEventListener("resize", resized); };
  }, [user?.id]);
  const allowedView = (name: string) => viewAllowed(name, screens, Boolean(user?.is_admin));
  const phoneAgentOnly = agentOnly(screens, Boolean(user?.is_admin));
  const [authChecked, setAuthChecked] = useState(false);
  const [csrf, setCsrf] = useState("");
  const authSession = useRef({ userId: user?.id as string | undefined, csrf });
  authSession.current = { userId: user?.id, csrf };
  const [setupRequired, setSetupRequired] = useState(false);
  const [keycloak, setKeycloak] = useState(false);
  // Company sign-in providers configured in Keycloak (Microsoft, Google): one button each.
  const [providers, setProviders] = useState<{alias:string;label:string}[]>([]);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  // Accounts with an authenticator app: the server asks for the 6-digit code after a correct password.
  const [totpCode, setTotpCode] = useState(""), [needsCode, setNeedsCode] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [passwordChangedNotice, setPasswordChangedNotice] = useState(false);
  const [roleChangedNotice, setRoleChangedNotice] = useState(false);
  const [signInErrors, setSignInErrors] = useState<{ username?: string; password?: string }>({});
  const [busy, setBusy] = useState(false);
  const operationLock=useRef(false);
  const [loading, setLoading] = useState(false);
  const [requests, setRequests] = useState<{id:string;label:string}[]>([]);
  const [visibleExtractionJobId,setVisibleExtractionJobId]=useState<string|null>(null);
  const [reextractSource,setReextractSource]=useState<Entity|null>(null);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [mobile, setMobile] = useState(false);
  const [compactNavigation, setCompactNavigation] = useState(false);
  const navigationRef = useRef<HTMLElement>(null);
  const navigationTrigger = useRef<HTMLButtonElement>(null);
  const navigationIsDrawer = compactNavigation || view === 'Lapi agent V2' || view === 'Home';
  const drawerOpen = mobile && navigationIsDrawer;
  useEffect(() => { setMobile(false); }, [view]);
  useEffect(() => { if (user && screens && !allowedView(view)) navigate("Home"); }, [view, screens, user?.id]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 960px)");
    const sync = () => {
      setCompactNavigation(media.matches);
      if (!media.matches) setMobile(false);
    };
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  useEffect(() => {
    if (!drawerOpen || !user) return;
    const drawer = navigationRef.current;
    if (!drawer) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(drawer.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], [tabindex='0']")).filter(el => el.getClientRects().length);
    focusable()[0]?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setMobile(false); }
      if (event.key !== "Tab") return;
      const controls = focusable();
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    drawer.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      drawer.removeEventListener("keydown", onKey);
      if (navigationIsDrawer) navigationTrigger.current?.focus();
    };
  }, [drawerOpen, user, navigationIsDrawer]);
  const [adminNavigation, setAdminNavigation] = useState(false);
  const [extractionTab, setExtractionTab] = useState("History");
  const [refresh, setRefresh] = useState(0);
  const [docs, setDocs] = useState<Entity[]>([]);
  // A list response started before an upload must not erase its accepted result.
  const uploadRevision = useRef(0);
  const [kbs, setKbs] = useState<Entity[]>([]);
  const [kb, setKb] = useState("");
  const [jobs, setJobs] = useState<Entity[]>([]);
  const [attention, setAttention] = useState<AttentionScope | null>(null);
  useEffect(() => onAttention(scope => setAttention(scope)), []);
  const [manage, setManage] = useState<ManageRequest | null>(null);
  useEffect(() => onDatasetEditor(request => { setAttention(null); setManage(request); }), []);
  useEffect(() => setAttention(null), [view]);
  const [agentVisibleJobIds, setAgentVisibleJobIds] = useState<string[]>([]);
  const onAgentJobs = useCallback((updates: Entity[]) => setJobs(previous => [...updates, ...previous.filter(job => !updates.some(update => update.id === job.id))]), []);
  const [settings, setSettings] = useState<Entity>({});
  const [modal, setModal] = useState<{
    title: string;
    data: Entity | string;
  } | null>(null);
  const [confirm, setConfirm] = useState<{
    title: string;
    body: string;
    action: () => Promise<void>;
  } | null>(null);
  const [models, setModels] = useState<Entity[]>([]);
  const [extractModelId, setExtractModelId] = useState("");
  const [, setDocumentPollError] = useState(false);
  const [scope, setScope] = useState<string[]>([]);
  const [templates, setTemplates] = useState<Entity[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [extractions, setExtractions] = useState<Entity[]>([]);
  const [extraction, setExtraction] = useState<Entity | null>(null);
  const [reviewOpenRequest, setReviewOpenRequest] = useState(0);
  const [reviewRouteId, setReviewRouteId] = useState("");
  const [reviewReturn, setReviewReturn] = useState<ReviewReturn | null>(null);
  const reviewReturnKey = `lapi-review-return-${user?.username || ''}`;
  useEffect(() => {
    setReviewReturn(null);
    if (!user) return;
    try {
      const saved = JSON.parse(sessionStorage.getItem(reviewReturnKey) || 'null');
      if (saved && saved.view !== 'Review' && sections.some(section => section.name === saved.view) && typeof saved.datasetId === 'string' && typeof saved.agentTab === 'string' && typeof saved.extractionTab === 'string') setReviewReturn(saved);
    } catch { sessionStorage.removeItem(reviewReturnKey); }
  }, [reviewReturnKey, user?.username]);
  const reviewProgressJob = view === "Review" && extraction?.status !== "ready" ? extractionProgressJob(extraction, jobs) : undefined;
  const reviewDirty = useRef(false);
  const templateDirty = useRef(false);
  const onTemplateDirty = useCallback((dirty: boolean) => { templateDirty.current = dirty; }, []);
  const onReviewDirty = useCallback((dirty: boolean) => { reviewDirty.current = dirty; }, []);
  const [externalExtract, setExternalExtract] = useState(false);
  const api = useCallback(
    async (
      path: string,
      method = "GET",
      body?: unknown,
      signal?: AbortSignal,
      quiet = false,
    ) => {
      const requestId=randomId();
      const resource=path.split('/')[1]||'workspace';
      const section=({overview:'workspace summary',jobs:'workflow status',settings:'workspace settings',conversations:'chats',models:'available models',templates:'prompt templates'} as Record<string,string>)[resource]||resource.replaceAll('-',' ');
      const testingModel=path==='/model-registrations/test';
      const planningAgent=path==='/agent-v2/plans'&&method==='POST';
      const label=path==='/templates/validate'?'Validating prompt JSON…':path.startsWith('/temporary-chat/')?(path==='/temporary-chat/messages'?'Answering from the temporary document…':method==='DELETE'?'Clearing temporary document…':body instanceof FormData?'Reading temporary document…':'Loading temporary document…'):testingModel?'Testing model connection…':path.startsWith('/datasets/')&&path.endsWith('/models')&&method==='PUT'?'Applying dataset model mappings…':`${method==='GET'?'Loading':method==='POST'&&body instanceof FormData?'Uploading':'Saving'} ${section}…`;
      if(!quiet)setRequests(previous=>[...previous,{id:requestId,label}]);
      const timeout=AbortSignal.timeout(planningAgent?630000:testingModel?Math.min(630000,(Number((body as Entity)?.timeout)||60)*1000+30000):method==='GET'?30000:120000);
      try {
      const headers: Record<string, string> = {};
      if (body && !(body instanceof FormData))
        headers["Content-Type"] = "application/json";
      const session = authSession.current;
      if (session.csrf) headers["X-CSRF-Token"] = session.csrf;
      const r = await fetchWithSessionCsrf(`/api${path}`, {
        method,
        headers,
        credentials: "include",
        body:
          body instanceof FormData
            ? body
            : body
              ? JSON.stringify(body)
              : undefined,
        signal: signal ? AbortSignal.any([signal,timeout]) : timeout,
      }, session, token => { authSession.current = { ...authSession.current, csrf: token }; setCsrf(token); });
      let data;
      try {
        data = await r.json();
      } catch {
        data = {
          detail: `Request failed (${r.status}). Check the API service.`,
        };
      }
      if (!r.ok) {
        throw Object.assign(new Error(
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail || data),
        ), { status: r.status });
      }
      return data;
      } catch(error) {
        if(error instanceof Error&&error.name==='TimeoutError')throw new Error('The request timed out. Check the service and refresh to confirm whether your operation completed before retrying.');
        throw error;
      } finally {
        if(!quiet)setRequests(previous=>previous.filter(r=>r.id!==requestId));
      }
    },
    [],
  );
  const agentStream = useCallback((path:string,body:unknown,signal:AbortSignal)=>{
    const session=authSession.current;
    return fetchWithSessionCsrf(`/api${path}`,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf||''},body:JSON.stringify(body),signal},session,token=>{authSession.current={...authSession.current,csrf:token};setCsrf(token);});
  },[]);
  const run = async (fn: () => Promise<void>) => {
    if(operationLock.current)return;
    operationLock.current=true;
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      operationLock.current=false;
      setBusy(false);
    }
  };
  const notify = (s: string) => {
    setToast(s);
    setTimeout(() => setToast(""), 5500);
  };
  useEffect(() => {
    const failure = new URLSearchParams(window.location.search).get("sign_in_error");
    if (failure) {
      setError(SIGN_IN_ERRORS[failure] || SIGN_IN_ERRORS.failed);
      window.history.replaceState(null, "", window.location.pathname);
    }
    fetch("/api/auth/me", { credentials: "include",signal:AbortSignal.timeout(15000) })
      .then(async (r) => {
        const d = await r.json();
        if (r.ok) {
          prepareFreshLoginChat(sessionStorage,(d.user||d).username,d.chat_session_id||'');
          setUser(d.user || d);
          setCsrf(d.csrf_token || "");
        }
      })
      .catch(() => setError('Could not reach Lapi. Check the API service, then reload this page.'))
      .finally(() => setAuthChecked(true));
    fetch("/api/auth/status",{signal:AbortSignal.timeout(15000)})
      .then((r) => (r.ok ? r.json() : {}))
      .then((d: Entity) => {
        setSetupRequired(!!d.setup_required);
        setKeycloak(!!d.keycloak);
        setProviders(Array.isArray(d.providers) ? d.providers : []);
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!user) return;
    let active = true;
    setLoading(true);
    const controller=new AbortController();
    const revision=uploadRevision.current;
    const list=(value:Entity|Entity[],key:string)=>Array.isArray(value)?value:value[key]||[];
    const tasks:[string,(value:any)=>void][]=[
      ['/documents',value=>{if(revision===uploadRevision.current)setDocs(list(value,'documents'));setDocumentPollError(false);}],
      ['/datasets',value=>setKbs(list(value,'datasets'))],['/jobs',value=>{if(revision===uploadRevision.current)setJobs(list(value,'jobs'));}],
      ['/settings',setSettings],['/templates',value=>setTemplates(list(value,'templates'))],
      ['/extractions',value=>setExtractions(list(value,'extractions'))],
      ['/models',value=>setModels(list(value,'models'))],
    ];
    Promise.allSettled(tasks.map(async([path,update])=>{
      try {const value=await api(path,'GET',undefined,controller.signal,true);if(active)update(value);}
      catch(error){if(active)setError(error instanceof Error?error.message:'Could not refresh workspace.');}
    })).finally(()=>{if(active)setLoading(false);});
    return () => {
      active = false;
      controller.abort();
    };
  }, [user, refresh, api]);
  const pendingJobs=pendingJobIds(jobs);
  const jobStatusVersion=jobs.map(job=>job.id+':'+job.status).sort().join(',');
  const observedJobStatus=useRef(new Map<string,string>());
  useEffect(()=>{
    const previous=observedJobStatus.current;
    const changed=jobs.some(job=>previous.has(job.id)&&previous.get(job.id)!==job.status);
    observedJobStatus.current=new Map(jobs.map(job=>[job.id,job.status]));
    if(!user||!changed)return;
    const controller=new AbortController();const revision=uploadRevision.current;
    // Separate from the polling lifetime: the final completed status stops
    // polling, but must not abort its document/result refresh.
    void Promise.all([api('/documents','GET',undefined,controller.signal,true),api('/extractions','GET',undefined,controller.signal,true)])
      .then(([documents,runs])=>{if(!controller.signal.aborted&&revision===uploadRevision.current){setDocs(Array.isArray(documents)?documents:documents.documents||[]);setExtractions(Array.isArray(runs)?runs:runs.extractions||[]);setDocumentPollError(false);}})
      .catch(()=>{if(!controller.signal.aborted)setDocumentPollError(true);});
    return()=>controller.abort();
  },[user,api,jobStatusVersion]);
  useEffect(() => {
    if (!user||!pendingJobs) return;
    let active=true, inFlight=false;let timer:ReturnType<typeof setTimeout>;
    const controller=new AbortController();
    const poll = async () => {
      if(!active||inFlight)return;
      if(document.visibilityState==='hidden'){timer=setTimeout(poll,10000);return;}
      inFlight=true;
      const revision=uploadRevision.current;
      try {
        const d=await api('/jobs?ids='+encodeURIComponent(pendingJobs),'GET',undefined,controller.signal,true);
        if(!active||revision!==uploadRevision.current)return;
        const next=Array.isArray(d)?d:d.jobs||[];
        setJobs(previous=>mergeJobUpdates(previous,next));
      }catch{if(active)setDocumentPollError(true);}finally{inFlight=false;if(active)timer=setTimeout(poll,4000);}
    };
    const visible=()=>{if(document.visibilityState==='visible'){clearTimeout(timer);void poll();}};
    timer=setTimeout(poll,1000);document.addEventListener('visibilitychange',visible);
    return () => {active=false;controller.abort();clearTimeout(timer);document.removeEventListener('visibilitychange',visible);};
  }, [user, api,pendingJobs]);
  const navigate = (name: View, reviewSection = "History", reviewId = "") => {
    if ((reviewDirty.current || templateDirty.current) && !window.confirm("Discard unsaved changes before leaving?")) return false;
    reviewDirty.current = false; templateDirty.current = false;
    const destination=["Extraction Review","Re-extract"].includes(name)?"Extract":name;
    if(destination!=="Extract")setReextractSource(null);
    if (destination === 'Review' && view !== 'Review') {
      const origin = {view, datasetId: kb, agentTab, extractionTab};
      setReviewReturn(origin); sessionStorage.setItem(reviewReturnKey, JSON.stringify(origin));
    } else if (view === 'Review' && destination !== 'Review') {
      setReviewReturn(null); sessionStorage.removeItem(reviewReturnKey);
    }
    if(destination==="Extract")setExtractionTab(reviewSection);
    if(destination==="Review")setReviewRouteId(reviewId);
    window.location.hash = encodeURIComponent(destination==="Review"&&reviewId?`Review/${reviewId}`:destination==="Extract"&&reviewSection==="Create"?"Review/create":viewRoute(destination));
    setView(destination);
    if (destination !== "Home") setDashboardHandoff(null);
    if (!["About", "Home", "Datasets", "Lapi Agent", "Lapi agent V2", "Skills & memory", "Extract", "Extract Data", "Review", "Extraction Review", "Re-extract", "Prompt templates", "Add knowledge"].includes(name)) setAdminNavigation(true);
    setError("");
    setMobile(false);
    return true;
  };
  const selectedDataset = kbs.find(d => d.id === kb);
  const extractionModels = eligibleModels(selectedDataset, "extraction");
  const selectedExtractModel = extractionModels.find(m => m.id === extractModelId);
  const extractionNeedsConsent=!!selectedExtractModel&&!['ollama','mock'].includes(selectedExtractModel.provider);
  const datasetDocs = docs.filter(d => (d.dataset_id || d.kb_id) === kb);
  const changeDataset = (id: string) => {
    if(user)rememberAssistantDataset(sessionStorage,user.username,id);
    if (id === kb) return;
    setKb(id);
    setTemplateId('');
    setScope([]);
    setExtractModelId("");
    setExternalExtract(false);
  };
  const returnFromReview = () => {
    const origin = reviewReturn || {view: 'Extract' as View, datasetId: kb, agentTab: 'Chat', extractionTab: 'History'};
    if (!navigate(origin.view, origin.extractionTab)) return;
    changeDataset(origin.datasetId);
    setAgentTab(origin.agentTab); setExtractionTab(origin.extractionTab);
  };
  const openReview = (id: string) => {
    if (!navigate('Review', 'History', id)) return false;
    setExtraction(null);
    setReviewOpenRequest(n=>n+1);
    return true;
  };
  // Other screens (Quick start) open an extraction's Review with an event.
  const openReviewRef = useRef(openReview);
  openReviewRef.current = openReview;
  useEffect(()=>{
    const open=(event:Event)=>{const id=(event as CustomEvent<{id?:string}>).detail?.id;if(id)openReviewRef.current(id);};
    window.addEventListener(OPEN_REVIEW_EVENT,open);return()=>window.removeEventListener(OPEN_REVIEW_EVENT,open);
  },[]);
  useEffect(()=>{
    if(!user || view!=='Review' || !reviewRouteId || extraction?.id===reviewRouteId)return;
    let active=true;
    api(`/extractions/${encodeURIComponent(reviewRouteId)}`).then(value=>{
      if(!active)return;
      setExtraction(value);setReviewOpenRequest(n=>n+1);
    }).catch(err=>{if(active)setError(err.message);});
    return()=>{active=false;};
  },[user?.id,view,reviewRouteId,api,extraction?.id]);
  const routeHandler = useRef<(hash: string) => void>(() => {});
  routeHandler.current = (hash: string) => {
    if ((reviewDirty.current || templateDirty.current) && !window.confirm("Discard unsaved changes before leaving?")) { window.history.replaceState(null, "", "#" + encodeURIComponent(view==='Review'&&reviewRouteId?`Review/${reviewRouteId}`:view==='Extract'&&extractionTab==='Create'?'Review/create':viewRoute(view))); return; }
    reviewDirty.current = false; templateDirty.current = false;
    let route: string;
    try { route = decodeURIComponent(hash.slice(1)); } catch { route = "Home"; }
    if (["connections","services & migration"].includes(route.toLowerCase())) {route="Storage";window.history.replaceState(null,"","#Storage");}
    if (route.toLowerCase()==="onboard dataset") {route="Datasets";window.history.replaceState(null,"","#Datasets");}
    if (["dashboard","home"].includes(route.toLowerCase())) {route="Home";window.history.replaceState(null,"","#Dashboard");}
    if (["setup","api documentation","adp documentation","index inspector"].includes(route.toLowerCase())) {
      route = "Home";
      window.history.replaceState(null, "", "#Dashboard");
    }
    if (["review","review/list","review/create","extract","extract/create","extraction review","re-extract","lapi agent/extract","document chat/extract"].includes(route.toLowerCase())) {
      const create=route.toLowerCase().endsWith('/create')||route.toLowerCase().endsWith('/extract');
      setExtractionTab(create?"Create":"History");setView("Extract");
      window.history.replaceState(null,"","#"+encodeURIComponent(create?'Review/create':'Review'));
    } else if (route.toLowerCase().startsWith("review/")) {
      setReviewRouteId(route.slice(7));setView("Review");
    } else if (route.startsWith("dataset/")) {
      changeDataset(route.slice(8));
      setView("Datasets");
      window.history.replaceState(null,"","#Datasets");
    } else {
      if(["ask lapi","lapi assistant","lapi agent"].includes(route.toLowerCase()))route="Lapi agent V2";
      if(route.toLowerCase()==="document chat")route="Lapi agent V2";
      if(/^add knowledge\//i.test(route))route="Add knowledge"; // Add knowledge reads the provider from the hash.
      const next = sections.find(s => s.name.toLowerCase() === (route.toLowerCase() === "templates" ? "prompt templates" : route.toLowerCase()))?.name || "Home";
      if(next === "Review")setReviewRouteId("");
      setView(next);
      if(next==="Lapi agent V2")window.history.replaceState(null,"","#"+encodeURIComponent(viewLabel(next)));
      if (!["About", "Home", "Datasets", "Lapi Agent", "Lapi agent V2", "Skills & memory", "Extract", "Extract Data", "Review", "Extraction Review", "Re-extract", "Prompt templates"].includes(next)) setAdminNavigation(true);
    }
    setMobile(false);
    setError("");
  };
  useEffect(() => {
    const followHash = () => routeHandler.current(window.location.hash);
    followHash();
    window.addEventListener("hashchange", followHash);
    return () => window.removeEventListener("hashchange", followHash);
  }, []);
  useEffect(() => {
    const dataset = kbs.find(d => d.id === kb);
    const pick = (current: string, capability: string, defaultKey: string) => {
      const available = eligibleModels(dataset, capability);
      if (available.some(m => m.id === current)) return current;
      if (available.some(m => m.id === dataset?.[defaultKey])) return dataset![defaultKey];
      return available.length === 1 ? available[0].id : "";
    };
    setExtractModelId(current => pick(current, "extraction", "default_extraction_model_id"));
  }, [kb, kbs]);
  useEffect(() => {
    setScope(current => current.filter(id => docs.some(d => d.id === id && (d.dataset_id || d.kb_id) === kb && d.status === "ready" && !d.requires_reindex)));
  }, [kb, docs]);
  useEffect(() => { setExternalExtract(false); }, [kb, extractModelId, selectedExtractModel?.version, selectedExtractModel?.connection_profile_version]);
  const selectDoc = (id: string) =>
    setScope((s) => (s.includes(id) ? s.filter((v) => v !== id) : [...s, id]));
  const reload = () => setRefresh((v) => v + 1);
  const authenticate = () =>
    run(async () => {
      let d;
      try {
        d = await api("/auth/login", "POST", needsCode&&totpCode ? { username, password, code: totpCode } : { username, password });
      } catch (e) {
        if (e instanceof Error && /authenticator/i.test(e.message)) { setNeedsCode(true); setTotpCode(""); window.setTimeout(()=>document.getElementById("login-code")?.focus(),0); }
        throw e;
      }
      setNeedsCode(false); setTotpCode("");
      prepareFreshLoginChat(sessionStorage,d.user.username,d.chat_session_id||'');
      navigate("Home");
      setUser(d.user);
      setPasswordChangedNotice(false);
      setRoleChangedNotice(false);
      setCsrf(d.csrf_token || "");
      setPassword("");
    });
  const chooseTemplate = (id: string) => setTemplateId(id);
  const extract = () =>
    run(async () => {
      if (!kb || !selectedExtractModel) throw new Error("Choose a dataset and an eligible extraction model.");
      if (!scope.length || !templateId)
        throw new Error("Select at least one document and a template.");
      if (extractionNeedsConsent && !externalExtract)
        throw new Error("Approve the external processing notice first.");
      const d = await api("/extractions", "POST", {
        dataset_id: kb,
        model_id: extractModelId,
        document_ids: scope,
        template_id: templateId,
        allow_external: externalExtract,
      });
      setExtraction(d);
      navigate("Review", "History", d.id);
      setReviewOpenRequest(n=>n+1);
      notify(
        "Extraction submitted. Review the job status before using the result.",
      );
      reload();
    });
  const docSelection = (
    <div className="selection">
      {datasetDocs.length ? (
        datasetDocs.map((d) => (
          <label key={d.id}>
            <input
              type="checkbox"
              checked={scope.includes(d.id)}
              disabled={d.status !== "ready" || !!d.requires_reindex}
              onChange={() => selectDoc(d.id)}
            />
            <span>
              {d.name} <span className="muted">· {d.status === "ready" && d.requires_reindex ? "reindex required" : d.status}</span>
            </span>
          </label>
        ))
      ) : (
        <p className="small muted">
          {kb ? "Add documents to this dataset first." : "Choose a dataset to see its documents."}
        </p>
      )}
    </div>
  );
  const externalNotice = (model: Entity | undefined) => `I approve sending this extraction request and selected document content to ${modelLabel(model)} (${model?.provider || 'model provider'}), using the dataset’s configured embedding and retrieval providers. External API usage is billed separately.`;
  const datasetSelect = (label: string) => <select aria-label={label} value={kb} onChange={e => changeDataset(e.target.value)}><option value="">Choose a dataset</option>{kbs.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select>;
  const configureDataset = () => { navigate("Model Mapping"); };

  if (!authChecked)
    return (
      <div className="auth-form" style={{ minHeight: "100vh" }}>
        <Loader2 className="animate-spin" size={26} />
      </div>
    );
  if (!user)
    return (
      <SignInLayout>
          <h1 id="login-heading" className="screen-heading">Welcome back</h1>
          <p className="login-description">{roleChangedNotice ? "Your role changed. Sign in again to use your updated access." : passwordChangedNotice ? "Password changed. Sign in with your new password." : keycloak && providers.length > 0 ? "Choose how you want to sign in." : keycloak ? "Sign in with your work account." : "Sign in to your workspace."}</p>
          {setupRequired && <div className="login-setup-notice" role="status">No administrator exists yet. Create one on the server with <code>lapi_local_use/lapi_scripts/create-admin.sh</code>, then sign in here.</div>}
          {error && <div className="login-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><span>{error}</span></div>}
          {keycloak && providers.length > 0 && <div className="login-providers">
            {providers.map(provider => <a key={provider.alias} className="btn login-provider" href={`/api/auth/keycloak/start?provider=${encodeURIComponent(provider.alias)}`}>
              <ProviderMark alias={provider.alias}/>Sign in with {provider.label}</a>)}
            <a className="login-keycloak-other" href="/api/auth/keycloak/start">Sign in with a username and password instead</a>
          </div>}
          {keycloak && !providers.length && <a className="btn primary login-submit login-keycloak" href="/api/auth/keycloak/start">
            <KeyRound size={17} aria-hidden="true" />Sign in with your work account</a>}
          <BreakGlass on={keycloak}>
          <form noValidate aria-busy={busy} onSubmit={e => {
            e.preventDefault();
            if (busy) return;
            const next: { username?: string; password?: string } = {};
            if (!username.trim()) next.username = "Enter your username.";
            if (!password) next.password = "Enter your password.";
            setSignInErrors(next);
            if (Object.keys(next).length) {
              document.getElementById(next.username ? "login-username" : "login-password")?.focus();
              return;
            }
            setShowPassword(false);
            authenticate();
          }}>
            <div className="field">
              <label htmlFor="login-username">Username</label>
              <input id="login-username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} required
                aria-invalid={!!signInErrors.username} aria-describedby={signInErrors.username ? "login-username-error" : undefined}
                onChange={e => { setUsername(e.target.value); setSignInErrors(current => ({ ...current, username: undefined })); setError(""); }} />
              {signInErrors.username && <small className="field-error" id="login-username-error">{signInErrors.username}</small>}
            </div>
            <div className="field">
              <label htmlFor="login-password">Password</label>
              <div className="login-password-entry">
                <input id="login-password" autoComplete="current-password" type={showPassword ? "text" : "password"}
                  value={password} required minLength={1} maxLength={200}
                  aria-invalid={!!signInErrors.password} aria-describedby={signInErrors.password ? "login-password-error" : undefined}
                  onChange={e => { setPassword(e.target.value); setSignInErrors(current => ({ ...current, password: undefined })); setError(""); }} />
                <button title={showPassword ? "Hide password" : "Show password"} type="button" className="login-password-toggle" aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-controls="login-password" aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)} disabled={busy}>
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
              {signInErrors.password && <small className="field-error" id="login-password-error">{signInErrors.password}</small>}
            </div>
            {needsCode && <div className="field">
              <label htmlFor="login-code">Authenticator code</label>
              <input id="login-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={totpCode}
                placeholder="6 digits" onChange={e => { setTotpCode(e.target.value.replace(/\D/g, "").slice(0, 6)); setError(""); }} />
              <small className="muted">From the authenticator app on your phone.</small>
            </div>}
            <button className="btn primary login-submit" type="submit" disabled={busy}>
              {busy && <Loader2 size={17} className="animate-spin" aria-hidden="true" />}
              {busy ? "Signing in..." : "Sign in"}
            </button>
          </form>
          <a className="recovery-entry" href="/recover-password">Forgot password?</a>
          </BreakGlass>
      </SignInLayout>
    );

  return (
    <>
      {drawerOpen && <div className="navigation-backdrop" aria-hidden="true" onClick={() => setMobile(false)} />}
      <aside id="workspace-navigation" ref={navigationRef} className={`sidebar ${view === 'Lapi agent V2' || view === 'Home' ? 'agent-navigation-drawer' : ''} ${drawerOpen ? "open" : ""}`} role={drawerOpen ? "dialog" : undefined} aria-modal={drawerOpen ? true : undefined} aria-label="Workspace navigation" inert={navigationIsDrawer && !drawerOpen}>
        <button title="Close navigation"
          className="btn icon mobile-close"
          onClick={() => setMobile(false)}
          aria-label="Close navigation"
        >
          <X size={15} />
        </button>
        <div className="brand">
          <span className="brandmark">
            <img src="/lapi-mark.svg" alt="" width={40} height={40} />
          </span>
          <span className="brand-name">Lapi</span>
        </div>
        <div className="brand-sub">AI Data Platform</div>
        <WorkspaceNavigation view={view} isAdmin={Boolean(user.is_admin)} allowed={allowedView} onNavigate={navigate} adminOpen={adminNavigation} onAdminToggle={()=>setAdminNavigation(!adminNavigation)} adminItems={sections.filter(s=>allowedView(s.name)&&!["About","Home","Datasets","Add knowledge","Lapi Agent","Lapi agent V2","Skills & memory","Extract","Extract Data","Review","Extraction Review","Re-extract","Prompt templates","Model Registration","Model Mapping","Enabled models"].includes(s.name)&&(user.is_admin||["Users & passwords","Jobs & activity"].includes(s.name)||(Boolean((user as {is_auditor?:boolean}).is_auditor)&&s.name==="Access map")))}/>

        <div className="nav-footer">
          <div className="row" style={{ marginBottom: 9 }}>
            <Server size={14} />
            <span>Private workspace</span>
          </div>
          Originals protected. Insights grounded.
        </div>
      </aside>
      <div className={`shell ${view === "Lapi agent V2" ? "assistant-shell" : view === "Home" ? "notebook-shell" : view === "Extract Data" ? "extract-data-shell" : ""}`} inert={drawerOpen} data-agent-only={phoneAgentOnly || undefined}>
        <header className="topbar">
          <div className="breadcrumb">
            <button title="Open navigation"
              className="btn icon menu-toggle"
              onClick={() => setMobile(true)}
              aria-label="Open navigation"
              ref={navigationTrigger}
              aria-expanded={drawerOpen}
              aria-controls="workspace-navigation"
            >
              <Menu size={17} />
            </button>
            <img className="header-logo" src="/lapi-mark.svg" alt="Lapi" width={40} height={40} /><span className="crumb-workspace">Workspace</span>
            <ChevronRight size={13} />
            <h1 className="workspace-title">{viewLabel(view)}</h1>
          </div>
          <div className="top-actions">
            {view !== "Lapi agent V2" && !(view === 'Review' && extraction) && <div className="workspace-page-actions" role="toolbar" aria-label={`${viewLabel(view)} actions`}>
              {view==='Home'&&<DatasetSearch value={homeSearch} onChange={setHomeSearch}/>}
              {view==='Datasets'&&datasetDirectoryVisible&&<DatasetSearch value={directorySearch} onChange={setDirectorySearch}/>}
              <button
                className="btn icon"
                onClick={reload}
                disabled={loading}
                aria-label="Refresh workspace"
                title="Refresh workspace"
              >
                <RefreshCw
                  size={14}
                  className={loading ? "animate-spin" : ""}
                />
              </button>
            </div>}
            <span className="pill">
              <span className="dot" />
              Private workspace
            </span>
            <div className="avatar" title={user.username}>
              {(user.username || "A").slice(0, 2).toUpperCase()}
            </div>
            <button
              className="btn icon"
              title="Sign out"
              aria-label="Sign out"
              onClick={() =>
                run(async () => {
                  const result = await api("/auth/logout", "POST");
                  setUser(null);
                  setCsrf("");
                  // End the Keycloak session too, or the next sign-in would skip the password.
                  if (result?.logout_url) window.location.assign(result.logout_url);
                })
              }
            >
              <LogOut size={14} />
            </button>
          </div>
        </header>
        <main aria-label={viewLabel(view)} className={`workspace workspace-region${view==='Home'?' home-page-shell':''}${view === "Lapi agent V2" ? " agent-v2-workspace" : view === "Extract" ? " extract-page-shell" : view === "Extract Data" ? " extract-data-workspace" : ""}${view === 'Review' ? ` review-page-shell${extraction?' has-review':''}` : ''}${PAGE_INTROS[view]?' has-page-band':''}`}>
          {!(view === 'Review' && extraction) && <PageBand view={view}/>}
          <KnowledgeIndexBanner api={api} isAdmin={Boolean(user.is_admin)} revision={refresh} onChanged={reload}/>
          {error && view !== "Home" && (
            <Notice tone="error">
              {error}
              <button title="Dismiss error"
                className="btn icon"
                onClick={() => setError("")}
                style={{ marginLeft: 12 }}
                aria-label="Dismiss error"
              >
                <X size={12} />
              </button>
            </Notice>
          )}
          <WorkspaceAssist api={api} user={user} view={view} datasets={kbs} onNavigate={v => navigate(v as View)} onOpenNavigation={() => setMobile(true)} onChanged={reload} agentOnly={phoneAgentOnly} onSelectDataset={changeDataset} documents={docs} jobs={jobs} datasetId={dashboardDatasetId||kb}/>
          {(view === "Home" || (view === 'Review' && reviewReturn?.view === 'Home')) && <div hidden={view!=='Home'}><DatasetDashboard key={dashboardHandoff?.key||0} startScope={dashboardHandoff} metadataApi={api} onMetadataReview={openReview} username={user.username} selectedId={dashboardDatasetId} onSelect={id=>{setDashboardDatasetId(id);changeDataset(id);}} datasets={kbs} documents={docs} loading={loading} search={homeSearch} onClearSearch={()=>setHomeSearch('')} canManage={Boolean(user.is_admin||user.is_contributor)} onBrowse={()=>navigate("Datasets")} onAddNew={()=>navigate("Add knowledge")} guide={<WorkflowOverview isAdmin={Boolean(user.is_admin)} onNavigate={navigate}/>} renderAgent={(id,onBusy,sourceScope,_onSourceChange,knowledgeScope,options)=>{const scope=knowledgeScope||{datasetIds:[id],documentIds:sourceScope};return <DatasetKnowledgeChat key={knowledgeScopeKey(scope)} scope={scope} onOpenAgent={()=>navigate('Lapi agent V2')} onBusy={onBusy} catalogRevision={refresh} api={api} stream={agentStream} username={user.username} onReview={openReview} {...options}/>;}}/></div>}
          {view === "About" && <AboutLapi/>}
          <WalkthroughGate api={api} active={view === "Home"} userId={user.id as string | undefined}/>
          {view === "Skills & memory" && <AgentSetup api={api} datasets={kbs} selectedDataset={kb} isAdmin={Boolean(user.is_admin)} onNotify={notify}/>}
          {view === "Add knowledge" && <AddKnowledge api={api} datasets={kbs} documents={docs} selectedDataset={kb} onChanged={reload} onBack={()=>navigate("Home")} onExtract={()=>navigate("Extract Data")} onAsk={scope=>{if(navigate("Home")){setDashboardDatasetId('');setDashboardHandoff({...scope,key:Date.now()});}}}/>}
          {view === "Files & processing" && (user.is_admin?<AdminDocuments api={api} onChanged={reload} onReview={openReview}/>:<div className="panel" role="alert">Administrator access is required to manage files and processing.</div>)}
          {view === "Token usage" && (user.is_admin?<TokenUsageAdmin api={api}/>:<div className="panel" role="alert">Administrator access is required to view token usage.</div>)}
          {view === "Access map" && (user.is_admin||(user as {is_auditor?:boolean}).is_auditor?<AccessMap api={api}/>:<div className="panel" role="alert">Administrator or Auditor access is required to view the access map.</div>)}
          {view === "Users & passwords" && <UserManagement api={api} keycloak={keycloak} user={user as {id:string;username:string;is_admin?:boolean;is_auditor?:boolean;sign_in?:string}} onPasswordChanged={()=>{setUser(null);setCsrf("");setPassword("");setPasswordChangedNotice(true);}} onRoleChanged={()=>{setUser(null);setCsrf("");setPassword("");setRoleChangedNotice(true);setPasswordChangedNotice(false);}} />}
          {(view === "Lapi agent V2" || (view === 'Review' && reviewReturn?.view === 'Lapi agent V2')) && <div className="agent-v2-view" hidden={view !== 'Lapi agent V2'}><AgentV2 renderManage={({datasetId,onClose,onCommand})=>{const d=kbs.find(x=>x.id===datasetId);return d?<ManageDataset variant="inline" dataset={d} models={models} documents={docs} templates={templates} isAdmin={Boolean(user.is_admin)} api={api} reload={reload} notify={notify} onClose={onClose} onCommand={onCommand} onNavigate={v=>{changeDataset(datasetId);navigate(v as View);}}/>:<p className="small muted">This dataset is still loading. Try again in a moment.</p>;}} catalogRevision={refresh} onWorkspaceChanged={reload} api={api} stream={agentStream} username={user.username} onDatasetChange={view === 'Lapi agent V2' ? changeDataset : undefined} maxUploadMb={Number(settings.max_upload_mb || 25)} onJobs={onAgentJobs} onVisibleJobs={setAgentVisibleJobIds} onPromptSaved={d => setTemplates(previous=>[d,...previous.filter(t=>t.id!==d.id)])} onReview={openReview} /></div>}
          {view === "Datasets" && <DatasetWorkspace directorySearch={directorySearch} onClearDirectorySearch={()=>setDirectorySearch('')} onDirectoryVisibilityChange={setDatasetDirectoryVisible} canManage={Boolean(user.is_admin||user.is_contributor)} datasets={kbs} models={models} documents={docs}
            storageKey={`lapi-new-dataset:${user.id}`} defaults={selectedDataset} onSelect={changeDataset} onCreated={d=>{setKbs(current=>[...current.filter(item=>item.id!==d.id),d]);changeDataset(d.id);}}
            api={api} reload={reload} notify={notify} onUse={navigate}/>
          }
          {(view === "Extract Data" || view === "Extract" && extractionTab !== "Create") && <div className="screen-actions"><ActionButton className="btn primary" onClick={()=>navigate('Extract','Create')} label="New extraction" action="add" showLabel/></div>}
          {(view === "Extract" || (view === "Review" && reviewReturn?.view === "Extract")) && <div hidden={view !== "Extract" || extractionTab !== "History"}>
            <ExtractionDirectory datasets={kbs} extractions={extractions} documents={docs} templates={templates} selectedDataset={view === 'Review'?reviewReturn?.datasetId||'':kb} busy={busy} onDatasetChange={changeDataset} onOpen={openReview} onReExtract={id=>run(async()=>{setReextractSource(await api(`/extractions/${id}`));})}/>
          </div>}
          {(view === "Extract Data" || (view === "Review" && reviewReturn?.view === "Extract Data")) && <div className="extract-data-view" hidden={view !== "Extract Data"}>
            <ExtractData datasets={kbs} templates={templates} selectedDataset={view === 'Review'?reviewReturn?.datasetId||'':kb} onDatasetChange={changeDataset} onReview={openReview} api={api} revision={extractions}/>
          </div>}
          {view === "Review" && <div className="review-page">
            <ReviewDetail routeId={reviewRouteId} extraction={extraction} datasets={kbs} templates={templates} extractions={extractions} documents={docs} jobs={jobs} api={api} openRequest={reviewOpenRequest} onOpen={openReview} onBeforeChange={()=>{if(reviewDirty.current&&!window.confirm('Discard unsaved changes before switching results?'))return false;reviewDirty.current=false;return true;}} onDirty={onReviewDirty} onSaved={d=>{setExtraction(d);setExtractions(previous=>[d,...previous.filter(e=>e.id!==d.id)]);}} back={<ActionButton className="btn" onClick={returnFromReview} label={`Back to ${viewLabel(reviewReturn?.view || 'Extract')}`} action="back"/>}/>
          </div>}
          {view === "Extract" && extractionTab === "Create" && (
            <>
              <div className="review-return-bar"><ActionButton className="btn" onClick={()=>navigate('Extract')} label="Back to Review" action="back"/></div>
              <div className="extraction-focus">
                <section className="panel" hidden={extractionTab !== "Create"}>
                  <h2>Create an extraction</h2>
                  <p className="muted small">
                    Select a prompt template and documents. Review extracted values and
                    their evidence.
                  </p>
                  <Field label="Dataset">{datasetSelect("Extraction dataset")}</Field>
                  <ModelPicker dataset={selectedDataset} capability="extraction" value={extractModelId} onChange={setExtractModelId} onConfigure={configureDataset} />
                  <Field label="Prompt template">
                    <select
                      aria-label="Prompt template"
                      value={templateId}
                      onChange={(e) => chooseTemplate(e.target.value)}
                    >
                      <option value="">Select a prompt template</option>
                      {templates.filter(t=>!t.dataset_id||t.dataset_id===kb).map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name} · v{t.version || 1}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Source documents">{docSelection}</Field>
                  {extractionNeedsConsent && <label className="check" style={{ marginBottom: 20 }}>
                    <input
                      type="checkbox"
                      checked={externalExtract}
                      onChange={(e) => setExternalExtract(e.target.checked)}
                    />
                    <span className="muted small">{externalNotice(selectedExtractModel)}</span>
                  </label>}
                  <ActionButton
                    className="btn primary"
                    disabled={
                      busy || (extractionNeedsConsent && !externalExtract) || !templateId || !scope.length || !selectedExtractModel
                    }
                    onClick={extract}
                   label="Run extraction" action="activate"/>
                </section>
              </div>
            </>
          )}
          {view === "Prompt templates" && <PromptTemplates templates={templates} datasets={kbs} selectedDataset={kb} api={api} initialId={templateId} onDirty={onTemplateDirty} onSaved={d => { setTemplates(previous=>[d,...previous.filter(t=>t.id!==d.id)]); chooseTemplate(d.id); notify("Prompt template saved."); }} onUse={id => { const saved=templates.find(t=>t.id===id); if(saved?.dataset_id&&saved.dataset_id!==kb)changeDataset(saved.dataset_id); chooseTemplate(id); navigate("Extract", "Create"); }} />}
          {view === "Extract" && reextractSource && <ReExtractionDialog key={reextractSource.id} source={reextractSource} documents={docs} datasets={kbs} templates={templates} extractions={extractions} jobs={jobs} api={api} onRefresh={reload} onProgressVisibilityChange={setVisibleExtractionJobId} onConfigure={id=>{changeDataset(id);navigate('Model Mapping');}} onReview={d=>openReview(d.id)} onClose={()=>setReextractSource(null)}/>}

          {view === "Jobs & activity" && (
            <JobsBoard jobs={jobs} documents={docs} datasets={kbs} extractions={extractions} busy={busy} formatDate={date}
              onRetry={j=>run(async()=>{await api(`/jobs/${j.id}/retry`,"POST");notify("Retry requested.");reload();})}
              onCancel={j=>setConfirm({title:"Cancel processing job?",body:"Cancellation is best-effort. A request already sent to a model provider may continue and incur usage charges.",action:async()=>{await api(`/jobs/${j.id}/cancel`,"POST");notify("Cancellation requested.");reload();}})}
              empty={<Empty icon={Activity} title="No processing jobs yet" detail="Document uploads, reindexing, and extractions will be tracked here."/>}/>
          )}
          {view === "Model Registration" && <ModelRegistration models={models} settings={settings} api={api} run={run} busy={busy}
            onSaved={model => { setModels(current => current.some(m => m.id === model.id) ? current.map(m => m.id === model.id ? model : m) : [model, ...current]); notify("Model saved. New runs use the updated connection; re-apply an edited Default embedding model to rebuild the knowledge index."); reload(); }}
            onDefaultsChanged={() => { notify("Workspace Default saved."); reload(); }}
            onMapping={() => navigate("Model Mapping")} />}
          {view === "Enabled models" && <EnabledModels models={models} api={api} onRegistration={() => navigate("Model Registration")}
            onChanged={model => { setModels(current => current.map(m => m.id === model.id ? model : m)); notify(`${model.name} is ${model.enabled === false ? "off" : "on"}.`); reload(); }} />}
          {view === "Model Mapping" && <section className="panel model-mapping-screen">
            <MappingOverview datasets={kbs} selected={selectedDataset?.id || ""} busy={busy} onSelect={changeDataset} />
            <div className="field mapping-dataset-select"><label htmlFor="mapping-dataset">Dataset</label><select id="mapping-dataset" value={selectedDataset?.id || ""} onChange={e => changeDataset(e.target.value)} disabled={busy}><option value="">Choose a dataset</option>{kbs.map(d => <option key={d.id} value={d.id}>{d.name}{d.active === false ? " · Inactive" : ""}</option>)}</select></div>
            {selectedDataset ? <DatasetMappings key={selectedDataset.id} dataset={selectedDataset} models={models} api={api} run={run} busy={busy} reload={reload} notify={notify} onConnections={() => navigate("Model Registration")} /> : <p className="muted">Choose a dataset to configure its Embedding, Chat, Extraction, and OCR models.</p>}
            {!kbs.length && <button className="btn" onClick={() => navigate("Datasets")}>Open Datasets to create one</button>}
          </section>}
          {view === "Storage" && user.is_admin && <StorageConfiguration api={api} connections={<ConnectionSettings api={api} onChanged={reload} onModels={()=>navigate("Model Registration")}/>} onChanged={reload} onFreshStart={()=>{changeDataset('');setExtraction(null);setReviewReturn(null);Object.keys(sessionStorage).filter(key=>key.startsWith('lapi-agent-v2:')||key.startsWith('lapi-review-return-')).forEach(key=>sessionStorage.removeItem(key));}}/>}
        </main>
        <ConnectionStatus api={api} revision={refresh} datasets={kbs} datasetId={selectedDataset?.id}/>
      </div>
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={17} />
          {toast}
          <button title="Dismiss notification"
            style={{ border: 0, background: "none", color: "white" }}
            onClick={() => setToast("")}
            aria-label="Dismiss notification"
          >
            <X size={15} />
          </button>
        </div>
      )}
      {modal && (
        <div className="modal-bg" onClick={() => setModal(null)}>
          <section
            className="modal wide"
            role="dialog"
            aria-modal="true"
            aria-label={modal.title}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="panel-head">
              <h2>{modal.title}</h2>
              <button title="Close preview"
                className="btn icon"
                onClick={() => setModal(null)}
                aria-label="Close preview"
              >
                <X size={17} />
              </button>
            </div>
            {typeof modal.data === "string" ? (
              <pre className="code mono">{modal.data}</pre>
            ) : (
              <>
                <pre className="code mono" style={{ maxHeight: "55vh" }}>
                  {modal.data.text ||
                    modal.data.excerpt ||
                    modal.data.chunk_text ||
                    json(modal.data)}
                </pre>
                {modal.data.chunks?.length > 0 && (
                  <details>
                    <summary>{modal.data.chunks.length} source chunks</summary>
                    <pre className="code mono">{json(modal.data.chunks)}</pre>
                  </details>
                )}
              </>
            )}
          </section>
        </div>
      )}
      {manage && kbs.some(d => d.id === manage.datasetId) && (
        <ManageDataset key={manage.datasetId + (manage.tab || "")} dataset={kbs.find(d => d.id === manage.datasetId)!} tab={manage.tab} models={models} documents={docs} templates={templates} isAdmin={Boolean(user.is_admin)} api={api} reload={reload} notify={notify}
          onClose={() => setManage(null)}
          onNavigate={v => { const id = manage.datasetId; setManage(null); changeDataset(id); navigate(v as View); }} />
      )}
      {attention && (
        <NeedsAttentionDialog items={attentionItems(docs, jobs, kbs, attention)} isAdmin={Boolean(user.is_admin)} busy={busy}
          onClose={() => setAttention(null)}
          onRetry={j => run(async () => { await api(`/jobs/${j.id}/retry`, "POST"); notify("Retry requested. Progress appears in Jobs & activity."); setAttention(null); reload(); })}
          onNavigate={v => { setAttention(null); navigate(v as View); }} />
      )}
      {confirm && (
        <div className="modal-bg">
          <section
            className="modal"
            style={{ maxWidth: 490 }}
            role="dialog"
            aria-modal="true"
            aria-label={confirm.title}
          >
            <h2>{confirm.title}</h2>
            <p
              className="muted"
              style={{ lineHeight: 1.8, margin: "18px 0 24px" }}
            >
              {confirm.body}
            </p>
            <div className="row" style={{ justifyContent: "flex-end" }}>
              <button
                className="btn"
                disabled={busy}
                onClick={() => setConfirm(null)}
              >
                Cancel
              </button>
              <button
                className="btn primary"
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    await confirm.action();
                    setConfirm(null);
                  })
                }
              >
                {busy ? (
                  <Loader2 className="animate-spin" size={14} />
                ) : (
                  <Check size={14} />
                )}
                Confirm
              </button>
            </div>
          </section>
        </div>
      )}
      {!agentWorkspace&&view!=='Home'&&<button type="button" className={`agent-shortcut${view === 'Review' ? ' in-review' : ''}`} aria-label="Open Lapi Agent" title="Lapi Agent" onClick={()=>navigate('Lapi agent V2')}>
        <AgentLogo size={40}/>
        <span className="agent-shortcut-badge" aria-hidden="true"><MessageSquare size={11}/></span>
        <span className="agent-shortcut-label" aria-hidden="true">Lapi Agent</span>
      </button>}
      {view !== "Storage" && <OperationProgress agentWorkspace={agentWorkspace} compact={view === "Review" || view === "Extract" || agentWorkspace} workspaceLoading={loading} requests={requests} jobs={jobs} documents={docs} visibleJobIds={agentWorkspace ? agentVisibleJobIds : []} visibleJobId={reviewProgressJob?.id || (view === "Extract" ? visibleExtractionJobId : null)}/>}
    </>
  );
}
