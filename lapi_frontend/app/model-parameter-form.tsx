"use client";
import { Info, History } from "lucide-react";
import {
  type FieldMode, type ParameterField, type ParameterSchema, type ParameterValue, type ParameterValues, type StageValues,
  defaultMeaning, effectiveFor, fieldError, fieldMode, formatValue, parseStopList, resolveField, sourceLabel, withMode, withValue,
} from "./model-parameters";

type FormProps = {
  schema: ParameterSchema | null; loading: boolean; error: string;
  model: ParameterValues; stages: StageValues; scope: string;
  onScope: (scope: string) => void; onModel: (values: ParameterValues) => void; onStages: (values: StageValues) => void;
};

const modeLabels: [FieldMode, string][] = [["default", "Default"], ["provider", "Use provider default"], ["custom", "Custom value"]];

function control(field: ParameterField, value: ParameterValue, id: string, set: (value: ParameterValue) => void) {
  const described = `${id}-help`;
  if (field.type === "number" || field.type === "integer") {
    const numeric = typeof value === "number" ? value : Number.NaN;
    const parse = (text: string) => set(text.trim() === "" ? Number.NaN : Number(text));
    return <div className="parameter-number">
      {field.type === "number" && field.min !== undefined && field.max !== undefined && <input type="range" aria-label={`${field.label} slider`} min={field.min} max={field.max} step={field.step} value={Number.isFinite(numeric) ? numeric : field.min} onChange={e => parse(e.target.value)} />}
      <input id={id} type="number" min={field.min} max={field.max} step={field.step ?? (field.type === "integer" ? 1 : "any")} value={Number.isFinite(numeric) ? numeric : ""} aria-describedby={described} onChange={e => parse(e.target.value)} />
    </div>;
  }
  if (field.type === "string_list") return <textarea id={id} rows={2} spellCheck={false} aria-describedby={described} value={Array.isArray(value) ? value.join("\n") : ""} onChange={e => set(parseStopList(e.target.value))} placeholder="One per line" />;
  if (field.type === "select") return <select id={id} aria-describedby={described} value={String(value ?? "")} onChange={e => set(e.target.value)}>{(field.options || []).map(option => <option key={option} value={option}>{option}</option>)}</select>;
  if (field.type === "boolean") return <label className="check"><input id={id} type="checkbox" aria-describedby={described} checked={value === true} onChange={e => set(e.target.checked)} />{value === true ? "On" : "Off"}</label>;
  return <input id={id} type="text" aria-describedby={described} value={typeof value === "string" ? value : ""} onChange={e => set(e.target.value)} placeholder="e.g. 5m" />;
}

function fieldRow(props: FormProps, field: ParameterField, stage: string | null, values: ParameterValues, update: (values: ParameterValues) => void) {
  const { schema, model, stages, scope } = props;
  if (!schema) return null;
  const mode = fieldMode(values, field.key);
  const id = `parameter-${scope}-${field.key}`;
  const current = resolveField(schema, field.key, model, stages, stage).value;
  const value = values[field.key];
  const error = mode === "custom" && value !== undefined ? fieldError(field, value) : "";
  return <div className={`parameter-field${mode === "custom" ? " custom" : ""}`} key={field.key}>
    <div className="parameter-field-head">
      <label htmlFor={mode === "custom" ? id : `${id}-mode`}>{field.label}<code>{field.key}</code></label>
      <select id={`${id}-mode`} aria-label={`${field.label} setting`} value={mode} onChange={e => update(withMode(values, field, e.target.value as FieldMode, current))}>
        {modeLabels.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select>
    </div>
    {mode === "custom" && value !== undefined && control(field, value, id, next => update(withValue(values, field.key, next)))}
    <small id={`${id}-help`}>{field.help}{field.type === "number" || field.type === "integer" ? ` Range ${field.min} to ${field.max}.` : ""} {mode === "default" ? defaultMeaning(schema, field, model, stages, stage) : mode === "provider" ? `Nothing is sent; the provider decides. ${field.default_note}` : ""}</small>
    {error && <small role="alert" className="parameter-error">{error}</small>}
  </div>;
}

export function ParameterForm(props: FormProps) {
  const { schema, loading, error, model, stages, scope, onScope, onModel, onStages } = props;
  if (error) return <p role="alert" className="parameter-error">{error}</p>;
  if (loading && !schema) return <p className="muted small">Loading parameter settings…</p>;
  if (!schema) return null;
  if (!schema.accepts_overrides) return <div className="notice parameter-none" role="note"><Info size={17} /><div>{schema.notice}</div></div>;
  const stageInfo = schema.stages.find(s => s.key === scope) || null;
  const stage = stageInfo ? stageInfo.key : null;
  const values = stage ? stages[stage] || {} : model;
  const update = (next: ParameterValues) => stage ? onStages({ ...stages, [stage]: next }) : onModel(next);
  const effective = effectiveFor(schema, model, stages, stage);
  const suggested = stageInfo ? Object.entries(stageInfo.suggested) : [];
  return <div className="parameter-form">
    {!!schema.stages.length && <div className="parameter-scopes" role="tablist" aria-label="Parameter scope">
      {[{ key: "model", label: "All stages" }, ...schema.stages].map(s => {
        const count = Object.keys(s.key === "model" ? model : stages[s.key] || {}).length;
        return <button key={s.key} id={`parameter-scope-${s.key}`} type="button" role="tab" aria-selected={(stage || "model") === s.key} className={`parameter-scope${(stage || "model") === s.key ? " selected" : ""}`} onClick={() => onScope(s.key)}>{s.label}{count > 0 && <span className="parameter-count" aria-label={`${count} set`}>{count}</span>}</button>;
      })}
    </div>}
    <p className="muted small parameter-scope-help">{stageInfo ? `${stageInfo.help} A field on Default uses the model value, then the documented Lapi default for this stage.` : "Model-wide values apply to every stage unless a stage sets its own. A value you set always wins over Lapi defaults."}</p>
    {stageInfo && suggested.length > 0 && <div className="parameter-suggested"><span>Suggested start: {suggested.map(([key, value]) => `${key} ${formatValue(value)}`).join(", ")}. You decide.</span><button type="button" className="btn" onClick={() => update({ ...values, ...stageInfo.suggested })}>Use suggested values</button></div>}
    <div className="parameter-fields">{schema.fields.map(field => fieldRow(props, field, stage, values, update))}</div>
    <div className="parameter-effective" role="region" aria-label="Effective settings">
      <h4>Sent {stageInfo ? `for ${stageInfo.label}` : "by default for every stage"}</h4>
      <table><thead><tr><th scope="col">Parameter</th><th scope="col">Value</th><th scope="col">From</th></tr></thead>
        <tbody>{schema.fields.map(field => { const item = effective[field.key]; return <tr key={field.key} className={item.source === "provider_default" ? "muted" : ""}><th scope="row">{field.label}</th><td>{item.source === "provider_default" ? "not sent" : formatValue(item.value)}</td><td>{sourceLabel[item.source]}</td></tr>; })}</tbody>
      </table>
    </div>
  </div>;
}

type HistoryEntry = { version: number; at: number; author?: { id?: string; username?: string | null }; event: string;
  changes: { scope: string; key: string; from: { mode: string; value?: ParameterValue }; to: { mode: string; value?: ParameterValue } }[] };

const describe = (side: { mode: string; value?: ParameterValue }) => side.mode === "custom" ? formatValue(side.value) : side.mode === "provider_default" ? "provider default" : "default";

export function ParameterHistory({ history, error }: { history: HistoryEntry[] | null; error: string }) {
  if (error) return <p role="alert" className="parameter-error">{error}</p>;
  if (!history) return <p className="muted small">Loading history…</p>;
  if (!history.length) return <p className="muted small">No parameter changes recorded yet. The next save records author and time.</p>;
  return <ol className="parameter-history" aria-label="Parameter history">
    {history.map(entry => <li key={entry.version}>
      <div className="parameter-history-head"><History size={14} aria-hidden="true" /><strong>Version {entry.version}</strong><span>{new Date(entry.at * 1000).toLocaleString()}</span><span>{entry.author?.username || entry.author?.id || "Unknown author"}</span>{entry.event === "registered" && <span className="pill">Registered</span>}</div>
      {entry.changes.length ? <ul>{entry.changes.map(change => <li key={change.scope + change.key}><code>{change.key}</code> {change.scope === "model" ? "(all stages)" : `(${change.scope.replace("_", " ")})`}: {describe(change.from)} → <strong>{describe(change.to)}</strong></li>)}</ul> : <p className="muted small">All fields on default.</p>}
    </li>)}
  </ol>;
}
