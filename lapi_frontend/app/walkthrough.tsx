"use client";
import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Activity, CheckCircle2, ChevronLeft, ChevronRight, Cloud, Database, FileText, FolderOpen, KeyRound, MessageSquare, Pause, Play, RotateCcw, ScanText, ShieldCheck, Sparkles, Users, Volume2, VolumeX, X } from "lucide-react";
import { MOBILE_QUERY, TOUR_VERSION, clampScene, formatClock, nextScene, pickVoice, previousScene, sceneAt, sceneStart, scenesFor, segmentFill, shouldShowTour, totalSeconds, type Device, type SceneId } from "./walkthrough-data";
import "./walkthrough.css";

type Api = (path: string, method?: string, body?: unknown, signal?: AbortSignal, quiet?: boolean) => Promise<any>;
/** Seconds into the last scene when the "You're ready" end card appears. */
const END_CARD_AT = 4;

/** The Lapi mark, drawn inline so the tour needs no external asset. */
function LapiMark({ size = 64 }: { size?: number }) {
  return <svg className="wt-mark" width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
    <path d="M16.6 0.6H47.4A16 16 0 0 1 63.4 16.6V47.4A16 16 0 0 1 47.4 63.4H16.6A16 16 0 0 1 0.6 47.4V16.6A16 16 0 0 1 16.6 0.6Z" fill="#ffffff" stroke="#dbe5f7" strokeWidth="1.2" />
    <path d="M19.5 12H19.5A4.5 4.5 0 0 1 24 16.5V52H19.5A4.5 4.5 0 0 1 15 47.5V16.5A4.5 4.5 0 0 1 19.5 12Z" fill="#2563eb" />
    <path d="M15 43H44.5A4.5 4.5 0 0 1 49 47.5V47.5A4.5 4.5 0 0 1 44.5 52H19.5A4.5 4.5 0 0 1 15 47.5V43Z" fill="#2563eb" />
    <path d="M30 12H39A12 12 0 0 1 51 24V24A12 12 0 0 1 39 36H30A3 3 0 0 1 27 33V15A3 3 0 0 1 30 12Z" fill="#fb923c" />
    <path d="M27 30 L27 40.5 L33.5 35.5Z" fill="#fb923c" />
    <circle cx="33.6" cy="24" r="2.15" fill="#ffffff" /><circle cx="39.2" cy="24" r="2.15" fill="#ffffff" /><circle cx="44.8" cy="24" r="2.15" fill="#ffffff" />
  </svg>;
}

/** Staggered entrance: `d` is the delay in seconds from the start of the scene. */
const at = (d: number) => ({ style: { ["--d" as string]: `${d}s` } });

function Welcome() {
  return <div className="wt-scene wt-welcome">
    <div className="wt-welcome-core wt-in-zoom" {...at(0.2)}>
      <span className="wt-orbit" aria-hidden="true">{Array.from({ length: 12 }, (_, i) => <i key={i} style={{ ["--a" as string]: `${i * 30}deg` }} data-accent={i % 3 === 0 || undefined} />)}</span>
      <LapiMark size={88} />
    </div>
    <h3 className="wt-welcome-title"><span className="wt-in-up" {...at(0.9)}>Connect.</span> <span className="wt-in-up wt-unify" {...at(1.5)}>Unify.</span> <span className="wt-in-up wt-ask" {...at(2.1)}>Ask.</span></h3>
    <p className="wt-welcome-lead wt-in-up" {...at(3)}>One knowledge base for your documents, databases and apps.</p>
    <ul className="wt-welcome-steps" aria-label="Three steps">
      {["Connect your sources", "Unify into one knowledge base", "Ask with sources to check"].map((text, i) =>
        <li key={text} className="wt-in-up" {...at(3.8 + i * 0.4)}><b>{i + 1}</b>{text}</li>)}
    </ul>
  </div>;
}

const FORMATS = ["PDF", "DOCX", "TXT", "JSON", "Images"];
const CLOUDS = ["Amazon S3", "Azure Blob", "Google Cloud Storage", "OCI Object Storage"];
const APPS = ["Google Drive", "SharePoint"];
function Connect({ mobile = false }: { mobile?: boolean }) {
  return <div className="wt-scene wt-connect">
    <div className="wt-sources">
      <div className="wt-group wt-in-left" {...at(0.2)}><span className="wt-group-title"><FileText size={14} aria-hidden="true" />Upload files</span>
        <div className="wt-tags">{FORMATS.map((f, i) => <span key={f} className="wt-tag wt-in-pop" {...at(0.6 + i * 0.15)}>{f}</span>)}</div></div>
      <div className="wt-group wt-in-left" {...at(1.4)}><span className="wt-group-title"><Cloud size={14} aria-hidden="true" />Cloud storage</span>
        <div className="wt-tags">{CLOUDS.map((f, i) => <span key={f} className="wt-tag wt-in-pop" {...at(1.8 + i * 0.2)}>{f}</span>)}</div></div>
      <div className="wt-group wt-in-left" {...at(2.8)}><span className="wt-group-title"><FolderOpen size={14} aria-hidden="true" />Apps</span>
        <div className="wt-tags">{APPS.map((f, i) => <span key={f} className="wt-tag wt-in-pop" {...at(3.2 + i * 0.2)}>{f}</span>)}</div></div>
    </div>
    <div className="wt-flow" aria-hidden="true">{[0, 1, 2, 3, 4].map(i => <i key={i} style={{ ["--d" as string]: `${1 + i * 0.45}s` }} />)}</div>
    <div className="wt-panel wt-addk wt-in-right" {...at(0.6)}>
      <span className="wt-panel-head"><Sparkles size={15} aria-hidden="true" />{mobile ? "Add" : "Add knowledge"}</span>
      <ol className="wt-guide">
        {(mobile ? ["Tap Add", "Take a photo or choose files", "Merge pages into one"] : ["Choose a source", "Follow the connector guide", "Test and connect"]).map((step, i) =>
          <li key={step} className="wt-in-up" {...at(4 + i * 1.2)}><CheckCircle2 size={15} aria-hidden="true" className="wt-tick" style={{ ["--d" as string]: `${4.6 + i * 1.2}s` }} />{step}</li>)}
      </ol>
      <span className="wt-kb wt-in-pop" {...at(7.8)}><Database size={14} aria-hidden="true" />Into one knowledge base</span>
    </div>
  </div>;
}

const DOCS = [{ name: "Supplier agreement.pdf", ocr: false }, { name: "Renewals.docx", ocr: false }, { name: "Scanned invoice.png", ocr: true }];
const MODELS = [["Chat", "answers questions"], ["Extraction", "fills fields"], ["Embedding", "indexes knowledge"], ["OCR", "reads scans and images"]];
function Unify() {
  return <div className="wt-scene wt-unify">
    <div className="wt-panel wt-dataset wt-in-left" {...at(0.2)}>
      <span className="wt-panel-head"><FolderOpen size={15} aria-hidden="true" />Contracts dataset</span>
      <ul className="wt-docs">{DOCS.map((doc, i) => <li key={doc.name} className="wt-in-up" {...at(0.8 + i * 0.6)}>
        <span className="wt-doc-name">{doc.ocr ? <ScanText size={14} aria-hidden="true" /> : <FileText size={14} aria-hidden="true" />}{doc.name}{doc.ocr && <em className="wt-ocr">OCR<i className="wt-scanline" aria-hidden="true" /></em>}</span>
        <span className="wt-bar" aria-hidden="true"><i style={{ ["--d" as string]: `${1.4 + i * 1.3}s` }} /></span>
        <span className="wt-indexed wt-in-pop" {...at(3.4 + i * 1.3)}><CheckCircle2 size={13} aria-hidden="true" />Indexed</span>
      </li>)}</ul>
    </div>
    <div className="wt-panel wt-models wt-in-right" {...at(4.5)}>
      <span className="wt-panel-head"><Sparkles size={15} aria-hidden="true" />Workspace models</span>
      <ul>{MODELS.map(([name, role], i) => <li key={name} className="wt-in-up" {...at(5.4 + i * 0.9)}><strong>{name}</strong><span>{role}</span><CheckCircle2 size={14} aria-hidden="true" className="wt-tick" style={{ ["--d" as string]: `${5.9 + i * 0.9}s` }} /></li>)}</ul>
    </div>
  </div>;
}

const CITES = ["Supplier agreement.pdf · p. 2", "Renewals.docx", "SharePoint · Contracts"];
function Ask() {
  return <div className="wt-scene wt-ask-scene">
    <div className="wt-chat wt-in-up" {...at(0.2)}>
      <div className="wt-chat-head"><LapiMark size={30} /><span><strong>Lapi Agent</strong><small>Answers with citations</small></span></div>
      <div className="wt-chat-body">
        <p className="wt-bubble wt-q wt-in-right" {...at(1.2)}>Which contracts renew this quarter?</p>
        <span className="wt-typing" aria-hidden="true"><i /><i /><i /></span>
        <div className="wt-bubble wt-a wt-in-up" {...at(4.4)}>
          <p>Three contracts renew before 30 June: <b>Northwind</b>, <b>Blue Harbor</b> and <b>Fabrikam</b>.{" "}{[1, 2, 3].map(n => <sup key={n} className="wt-ref wt-in-pop" {...at(5.4 + n * 0.3)}>{n}</sup>)}</p>
          <span className="wt-sources-label wt-in-up" {...at(6.6)}>Sources</span>
          <div className="wt-cites">{CITES.map((c, i) => <span key={c} className="wt-cite wt-in-pop" {...at(7 + i * 0.45)}><b>{i + 1}</b>{c}</span>)}</div>
        </div>
      </div>
      <p className="wt-verified wt-in-up" {...at(9)}><ShieldCheck size={15} aria-hidden="true" />Every answer shows its sources</p>
    </div>
  </div>;
}

const FIELDS = [["Party", "Northwind Supplies Ltd"], ["Total fee", "$48,500"], ["Due date", "30 Jun 2027"], ["Renewal", "12 months"]];
function Extract() {
  return <div className="wt-scene wt-extract">
    <div className="wt-panel wt-template wt-in-left" {...at(0.2)}>
      <span className="wt-panel-head"><ScanText size={15} aria-hidden="true" />Prompt template</span>
      <strong className="wt-template-name">Extract key terms</strong>
      <ul>{FIELDS.map(([f], i) => <li key={f} className="wt-in-up" {...at(0.8 + i * 0.25)}>{f}</li>)}</ul>
    </div>
    <div className="wt-review wt-in-right" {...at(1.6)}>
      <div className="wt-panel wt-source-doc">
        <span className="wt-panel-head"><FileText size={15} aria-hidden="true" />Supplier agreement.pdf · p. 2</span>
        <p>Made between <mark style={{ ["--d" as string]: "2.6s" }}>Northwind Supplies Ltd</mark> and the Customer, for a total fee of <mark style={{ ["--d" as string]: "3.3s" }}>$48,500</mark>, due by <mark style={{ ["--d" as string]: "4s" }}>30 June 2027</mark>. Renews for <mark style={{ ["--d" as string]: "4.7s" }}>12 months</mark>.</p>
      </div>
      <div className="wt-panel wt-fields">
        <span className="wt-panel-head"><CheckCircle2 size={15} aria-hidden="true" />Review side by side</span>
        <dl>{FIELDS.map(([f, v], i) => <div key={f} className="wt-in-up" {...at(2.8 + i * 0.7)}><dt>{f}</dt><dd>{v}</dd></div>)}</dl>
        <span className="wt-approved wt-in-pop" {...at(6.6)}><CheckCircle2 size={14} aria-hidden="true" />Reviewer approved · trusted result</span>
      </div>
    </div>
  </div>;
}

/** A SKILL.md taking effect: its "when it applies" lines, then the agent using it on a matching request. */
function Skills() {
  const lines = ["name: invoice-review", "document_types: invoice, bill", "keywords: overdue, duplicate", "1. Total by supplier.", "2. Flag duplicates and late ones."];
  return <div className="wt-scene wt-skills">
    <div className="wt-panel wt-skill-file wt-in-up" {...at(0.2)}>
      <span className="wt-panel-head"><Sparkles size={15} aria-hidden="true" />SKILL.md</span>
      <pre>{lines.map((line, i) => <span key={line} className="wt-in-up" {...at(0.6 + i * 0.55)}>{line}{"\n"}</span>)}</pre>
    </div>
    <div className="wt-panel wt-skill-use wt-in-up" {...at(4.2)}>
      <span className="wt-panel-head"><MessageSquare size={15} aria-hidden="true" />Lapi Agent</span>
      <p className="wt-skill-ask">Which invoices are overdue?</p>
      <p className="wt-skill-using wt-in-pop" {...at(5.4)}><Sparkles size={13} aria-hidden="true" />Using skill: invoice-review</p>
      <p className="wt-in-up" {...at(6.4)}>3 overdue, 1 duplicate · totals by supplier below</p>
    </div>
  </div>;
}

function Secure({ endCard }: { endCard: ReactNode }) {
  const items = [
    { icon: KeyRound, title: "Single sign-on", text: "Sign in once with Keycloak" },
    { icon: Users, title: "Access per dataset", text: "Viewer, Editor or Owner roles, checked by OpenFGA" },
    { icon: Activity, title: "Activity audit", text: "Every change is recorded" },
  ];
  return <div className="wt-scene wt-secure">
    <ul className="wt-badges">{items.map(({ icon: Icon, title, text }, i) => <li key={title} className="wt-in-up" {...at(0.2 + i * 0.6)}>
      <span className="wt-badge-icon"><Icon size={18} aria-hidden="true" /></span><span><strong>{title}</strong><small>{text}</small></span></li>)}</ul>
    {endCard}
  </div>;
}

/** "mobile" on phone-sized screens, else "desktop"; follows rotation and window resizing. */
function useDevice(): Device {
  const [device, setDevice] = useState<Device>("desktop");
  useEffect(() => {
    const query = typeof window !== "undefined" && window.matchMedia ? window.matchMedia(MOBILE_QUERY) : null;
    if (!query) return;
    const update = () => setDevice(query.matches ? "mobile" : "desktop");
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return device;
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
    if (!query) return;
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return reduced;
}

/** Voice-over with the browser's own speech synthesis: no service, no keys. Each scene's caption is
 * its line. Browsers only speak after a tap, so an automatic start may come back `blocked`. */
const VOICE_KEY = "lapi:tour-voice";
function useNarration() {
  const supported = typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";
  const [enabled, setEnabled] = useState(() => { try { return localStorage.getItem(VOICE_KEY) !== "0"; } catch { return true; } });
  const [blocked, setBlocked] = useState(false);
  // True from speak() until the line ends: the timeline waits for it before the next scene.
  const speaking = useRef(false);
  const startedAt = useRef(0);
  const voice = useRef<SpeechSynthesisVoice | undefined>(undefined);
  useEffect(() => {
    if (!supported) return;
    const load = () => { voice.current = pickVoice(window.speechSynthesis.getVoices()); };
    load();
    window.speechSynthesis.addEventListener?.("voiceschanged", load);
    return () => { window.speechSynthesis.removeEventListener?.("voiceschanged", load); window.speechSynthesis.cancel(); };
  }, [supported]);
  const stop = useCallback(() => { speaking.current = false; if (supported) window.speechSynthesis.cancel(); }, [supported]);
  const speak = useCallback((text: string) => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    const line = new SpeechSynthesisUtterance(text);
    if (voice.current) { line.voice = voice.current; line.lang = voice.current.lang; } else line.lang = "en-US";
    line.rate = 1; line.pitch = 1;
    line.onstart = () => setBlocked(false);
    line.onend = () => { speaking.current = false; };
    line.onerror = event => { speaking.current = false; if (event.error === "not-allowed") setBlocked(true); };
    speaking.current = true; startedAt.current = performance.now();
    window.speechSynthesis.speak(line);
  }, [supported]);
  const toggle = useCallback(() => setEnabled(value => {
    try { localStorage.setItem(VOICE_KEY, value ? "0" : "1"); } catch { /* per-device preference only */ }
    if (value) stop();
    return !value;
  }), [stop]);
  /** Still speaking (with a safety limit, in case a browser never reports the end). */
  const busy = useCallback((limitSeconds: number) => speaking.current && performance.now() - startedAt.current < limitSeconds * 1000, []);
  return { supported, enabled, blocked, setBlocked, speak, stop, toggle, busy };
}

const FOCUSABLE = 'button:not([disabled]),[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export type WalkthroughProps = {
  mode?: "inline" | "modal";
  /** Modal: Close / Skip / Esc. */
  onClose?: () => void;
  /** The end card's "Go to Dashboard" action; in a modal it defaults to closing. */
  onFinish?: () => void;
  autoPlay?: boolean;
};

/** The animated 1-minute Lapi tour: six auto-advancing scenes with captions and player controls. */
export function Walkthrough({ mode = "inline", onClose, onFinish, autoPlay = mode === "modal" }: WalkthroughProps) {
  const reduced = useReducedMotion();
  const device = useDevice();
  const SCENES = scenesFor(device);
  const TOTAL = totalSeconds(SCENES);
  const voice = useNarration();
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [run, setRun] = useState(0);
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const playRef = useRef<HTMLButtonElement>(null);
  const { index, offset } = sceneAt(elapsed, SCENES);
  const scene = SCENES[index];
  const ended = elapsed >= TOTAL;
  const finish = onFinish || onClose;

  useEffect(() => { if (autoPlay && !reduced) setPlaying(true); }, [autoPlay, reduced]);
  useEffect(() => { if (reduced) setPlaying(false); }, [reduced]);
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now(), step = (now - last) / 1000;
      last = now;
      setElapsed(value => {
        const at = sceneAt(value, SCENES).index;
        // Wait at the end of a scene while its line is still being spoken.
        const limit = voice.busy(SCENES[at].seconds + 8) ? (at === SCENES.length - 1 ? TOTAL : sceneStart(at + 1, SCENES)) - 0.05 : TOTAL;
        return Math.min(limit, value + step);
      });
    }, 100);
    return () => window.clearInterval(timer);
  }, [playing, voice.busy, SCENES, TOTAL]);
  // Narrate each scene as it starts; pausing stops the voice.
  const narrating = playing && voice.enabled && voice.supported && !reduced;
  useEffect(() => {
    if (!narrating) { voice.stop(); return; }
    voice.speak(SCENES[index].caption);
  }, [narrating, index, run, SCENES]);
  useEffect(() => () => voice.stop(), []);
  useEffect(() => { if (ended) setPlaying(false); }, [ended]);

  const goTo = useCallback((target: number) => {
    setElapsed(sceneStart(clampScene(target, SCENES), SCENES));
    setRun(value => value + 1);
  }, [SCENES]);
  const replay = useCallback(() => { setElapsed(0); setRun(value => value + 1); if (!reduced) setPlaying(true); }, [reduced]);
  const toggle = useCallback(() => {
    if (reduced) return;
    if (ended) { replay(); return; }
    // Resuming with the voice on repeats this scene's line from its start, so words and pictures match.
    if (!playing && voice.enabled && voice.supported) { setElapsed(sceneStart(index, SCENES)); setRun(value => value + 1); }
    setPlaying(value => !value);
  }, [ended, reduced, replay, playing, voice.enabled, voice.supported, index, SCENES]);
  // The tap browsers need before they speak: restart this scene with the voice on.
  const enableVoice = useCallback(() => {
    if (!voice.enabled) voice.toggle();
    voice.setBlocked(false);
    setElapsed(sceneStart(index, SCENES)); setRun(value => value + 1); setPlaying(true);
    voice.speak(SCENES[index].caption);
  }, [voice, index, SCENES]);

  // Modal: remember the opener, start on the play control, lock page scroll, and give focus back on close.
  useEffect(() => {
    if (mode !== "modal") return;
    const opener = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    (playRef.current || dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE) || dialogRef.current)?.focus();
    return () => { document.body.style.overflow = overflow; if (opener && opener.isConnected) opener.focus(); };
  }, [mode]);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const target = event.target as HTMLElement;
    const native = /^(BUTTON|A|INPUT|SELECT|TEXTAREA)$/.test(target.tagName);
    if (event.key === "Escape" && mode === "modal") { event.preventDefault(); event.stopPropagation(); onClose?.(); return; }
    if (event.key === "ArrowRight") { event.preventDefault(); goTo(nextScene(index, SCENES)); return; }
    if (event.key === "ArrowLeft") { event.preventDefault(); goTo(previousScene(index, SCENES)); return; }
    if ((event.key === " " || event.key === "Spacebar") && !native) { event.preventDefault(); toggle(); return; }
    if (event.key === "Tab" && mode === "modal" && dialogRef.current) {
      const items = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(el => el.offsetParent !== null || el === document.activeElement);
      if (!items.length) { event.preventDefault(); return; }
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogRef.current)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  };

  // Paused at the very start of a scene (or reduced motion): show the scene's finished state, not a blank first frame.
  const still = reduced || (!playing && offset < 0.05);
  const fills = reduced ? SCENES.map((_, i) => (i <= index ? 1 : 0)) : segmentFill(elapsed, SCENES);
  const showEnd = index === SCENES.length - 1 && (still || ended || offset >= END_CARD_AT);
  const endCard = <div className="wt-end" data-show={showEnd || undefined}>
    <LapiMark size={40} />
    <p className="wt-end-title">You're ready: start on your Dashboard</p>
    {showEnd && <div className="wt-end-actions">
      {finish && <button type="button" className="wt-button wt-primary" onClick={finish}>Go to Dashboard</button>}
      <button type="button" className="wt-button" onClick={replay}><RotateCcw size={15} aria-hidden="true" />Replay</button>
    </div>}
  </div>;
  const scenes: Record<SceneId, ReactNode> = { welcome: <Welcome />, connect: <Connect mobile={device === "mobile"} />, unify: <Unify />, ask: <Ask />, extract: <Extract />, skills: <Skills />, secure: <Secure endCard={endCard} /> };

  const player = <div className="wt-player" data-mode={mode} data-device={device} data-playing={playing || undefined} data-still={still || undefined} data-reduced={reduced || undefined}>
    <header className="wt-top">
      <h2 id={titleId} className="wt-title"><LapiMark size={22} />Lapi in one minute</h2>
      <span className="wt-top-actions">
        {voice.supported && !reduced && (voice.blocked && voice.enabled
          ? <button type="button" className="wt-button wt-voice wt-voice-on" onClick={enableVoice}><Volume2 size={15} aria-hidden="true" />Turn on voice</button>
          : <button type="button" className="wt-button wt-voice" onClick={voice.toggle} aria-pressed={voice.enabled} aria-label={voice.enabled ? "Turn voice-over off" : "Turn voice-over on"} title={voice.enabled ? "Voice on" : "Voice off"}>
              {voice.enabled ? <Volume2 size={15} aria-hidden="true" /> : <VolumeX size={15} aria-hidden="true" />}<span>{voice.enabled ? "Voice on" : "Voice off"}</span></button>)}
        {mode === "modal" && <button type="button" className="wt-button wt-skip" onClick={onClose}><X size={15} aria-hidden="true" />{ended ? "Close" : "Skip tour"}</button>}
      </span>
    </header>
    <div className="wt-stage" data-scene={scene.id}>
      <span className="wt-stage-label" aria-hidden="true">{index + 1} / {SCENES.length} · {scene.title}</span>
      <div key={`${index}-${run}`} className="wt-stage-inner">{scenes[scene.id]}</div>
    </div>
    <p className="wt-caption" aria-live="polite"><span className="visually-hidden-wt">Scene {index + 1} of {SCENES.length}, {scene.title}: </span>{scene.caption}</p>
    <div className="wt-controls">
      <ol className="wt-segments" aria-label="Scenes">{SCENES.map((item, i) => <li key={item.id}>
        <button type="button" className="wt-segment" aria-label={`Scene ${i + 1} of ${SCENES.length}: ${item.title}`} aria-current={i === index ? "step" : undefined} onClick={() => goTo(i)}>
          <span className="wt-segment-name">{item.title}</span>
          <span className="wt-segment-track"><i style={{ transform: `scaleX(${fills[i]})` }} /></span>
        </button></li>)}</ol>
      <div className="wt-buttons">
        <button type="button" className="wt-button wt-icon" onClick={() => goTo(previousScene(index, SCENES))} disabled={index === 0} aria-label="Previous scene"><ChevronLeft size={18} aria-hidden="true" /></button>
        {!reduced && <button ref={playRef} type="button" className="wt-button wt-play" onClick={toggle} aria-label={ended ? "Replay tour" : playing ? "Pause tour" : "Play tour"}>
          {ended ? <RotateCcw size={18} aria-hidden="true" /> : playing ? <Pause size={18} aria-hidden="true" /> : <Play size={18} aria-hidden="true" />}<span>{ended ? "Replay" : playing ? "Pause" : "Play"}</span></button>}
        <button type="button" className="wt-button wt-icon" onClick={() => goTo(nextScene(index, SCENES))} disabled={index === SCENES.length - 1} aria-label="Next scene"><ChevronRight size={18} aria-hidden="true" /></button>
        {reduced
          ? <span className="wt-time">Scene {index + 1} of {SCENES.length}</span>
          : <span className="wt-time"><span className="visually-hidden-wt">Elapsed </span><time>{formatClock(elapsed)}</time> / <time>{formatClock(TOTAL)}</time></span>}
      </div>
    </div>
  </div>;

  if (mode === "modal") {
    return <div className="wt-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose?.(); }}>
      <div ref={dialogRef} className="wt-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} onKeyDown={onKeyDown}>{player}</div>
    </div>;
  }
  return <section className="wt-inline" aria-labelledby={titleId} onKeyDown={onKeyDown}>{player}</section>;
}

/** Fires when the tour has closed, or was not needed, for a person; the set-up questions wait for it. */
export const TOUR_SETTLED_EVENT='lapi:tour-settled';
let settledFor='';
export const tourSettledFor=()=>settledFor;
function settle(userId:string){settledFor=userId;if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent(TOUR_SETTLED_EVENT,{detail:userId}));}

/** Shows the tour once per user on the Dashboard; the server remembers it, so other browsers do not repeat it. */
export function WalkthroughGate({ api, active, userId }: { api: Api; active: boolean; userId?: string }) {
  const [open, setOpen] = useState(false);
  const checked = useRef("");
  const current = useRef(userId);
  current.current = userId;
  useEffect(() => {
    if (!active || !userId || checked.current === userId) return;
    checked.current = userId;
    api("/me/walkthrough", "GET", undefined, undefined, true).then(status => {
      if (current.current !== userId) return;
      if (!shouldShowTour(status)) { settle(userId); return; }
      setOpen(true);
      const version = Number(status?.version) || TOUR_VERSION;
      api("/me/walkthrough", "POST", { version }, undefined, true).catch(() => undefined);
    }).catch(() => { checked.current = ""; });
  }, [active, userId, api]);
  useEffect(() => { if (!userId) setOpen(false); }, [userId]);
  return open ? <Walkthrough mode="modal" onClose={() => { setOpen(false); if (userId) settle(userId); }} /> : null;
}
