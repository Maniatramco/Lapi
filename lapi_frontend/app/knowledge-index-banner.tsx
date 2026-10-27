"use client";
import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Loader2, RotateCcw } from "lucide-react";
import "./knowledge-index-banner.css";

type Entity = Record<string, any>;
type Api = (path: string, method?: string, body?: unknown, signal?: AbortSignal, quiet?: boolean) => Promise<any>;

/** Workspace banner for the one knowledge index: rebuild progress and failures. */
export function KnowledgeIndexBanner({ api, isAdmin, revision, onChanged }: { api: Api; isAdmin: boolean; revision: number; onChanged: () => void }) {
  const [status, setStatus] = useState<Entity | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async (signal?: AbortSignal) => {
    try { setStatus(await api("/workspace/knowledge-index", "GET", undefined, signal, true)); }
    catch { /* The banner is informational; other screens report service errors. */ }
  }, [api]);
  useEffect(() => { const controller = new AbortController(); load(controller.signal); return () => controller.abort(); }, [load, revision]);
  const building = status?.state === "building";
  useEffect(() => {
    if (!building) return;
    const timer = window.setInterval(() => { load(); }, 5000);
    return () => window.clearInterval(timer);
  }, [building, load]);
  if (!status || !["building", "attention", "conflict"].includes(status.state)) return null;
  const total = Number(status.total) || 0, indexed = Number(status.indexed) || 0;
  const percent = total ? Math.round(indexed * 100 / total) : 0;
  const failures: Entity[] = status.failures || [];
  const retry = async () => {
    setRetrying(true); setError("");
    try { await api("/workspace/knowledge-index/retry", "POST", { allow_external: true }); await load(); onChanged(); }
    catch (e) { setError(e instanceof Error ? e.message : "Retry could not be queued."); }
    finally { setRetrying(false); }
  };
  return <section className={`knowledge-index-banner notice ${status.state === "building" ? "" : "warn"}`} role="status" aria-live="polite" aria-label="Knowledge index status">
    {building ? <Loader2 size={16} className="knowledge-index-spin" aria-hidden="true" /> : <AlertCircle size={16} aria-hidden="true" />}
    <div>
      <strong>{building ? "Rebuilding the knowledge index" : status.state === "conflict" ? "Choose the Default embedding model" : "Some documents were not reindexed"}</strong>
      {total > 0 && <div className="knowledge-index-track" role="progressbar" aria-label="Knowledge index rebuild progress" aria-valuemin={0} aria-valuemax={total} aria-valuenow={indexed} aria-valuetext={`${indexed} of ${total} documents indexed`}><span style={{ width: `${percent}%` }} /></div>}
      <p>{total > 0 ? `${indexed} of ${total} documents indexed${status.failed ? ` · ${status.failed} failed` : ""}${status.model_name ? ` · ${status.model_name}` : ""}. ` : ""}{status.message}</p>
      {isAdmin && failures.length > 0 && <details className="knowledge-index-failures"><summary>{failures.length} failed {failures.length === 1 ? "document" : "documents"}</summary><ul>{failures.slice(0, 20).map(f => <li key={f.document_id}><strong>{f.name}</strong> · {f.error}</li>)}</ul></details>}
      {isAdmin && failures.length > 0 && <button className="btn" type="button" disabled={retrying} onClick={retry} title="Queue reindexing again. Document text is sent to the Default embedding model."><RotateCcw size={14} aria-hidden="true" />{retrying ? "Retrying…" : "Retry"}</button>}
      {error && <p className="field-error" role="alert">{error}</p>}
    </div>
  </section>;
}
