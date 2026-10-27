// Offline mirror of the supported keys, used until the backend parameter
// schema (GET /model-registrations/parameter-schema) has loaded. The backend
// remains authoritative for keys, ranges and defaults.
export function supportedModelParameters(protocol: string, category: string, connection: Record<string, any> = {}): string[] {
  if (category === "embedding") {
    if (protocol === "ollama") return ["keep_alive"];
    if (["openai-compatible", "azure-openai"].includes(protocol)) return ["encoding_format"];
    if (protocol === "bedrock" && (connection.embedding_format || "titan") === "titan") return ["normalize"];
    return [];
  }
  const parameters: Record<string, string[]> = {
    ollama: ["temperature", "top_p", "top_k", "min_p", "repeat_penalty", "repeat_last_n", "seed", "stop", "keep_alive"],
    "openai-compatible": ["temperature", "top_p", "frequency_penalty", "presence_penalty", "seed", "stop", "reasoning_effort"],
    "azure-openai": ["temperature", "top_p", "frequency_penalty", "presence_penalty", "seed", "stop", "reasoning_effort"],
    anthropic: [],
    bedrock: ["temperature", "topP", "stopSequences"],
    vertex: ["temperature", "topP", "topK", "stopSequences", "seed", "presencePenalty", "frequencyPenalty"],
    oci: ["temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty", "seed", connection.chat_format === "cohere" ? "stop_sequences" : "stop"],
  };
  return parameters[protocol] || [];
}

export function parseModelParameters(text: string, supported: string[]): Record<string, unknown> {
  let value;
  try { value = JSON.parse(text.trim() || "{}"); }
  catch { throw new Error("Enter valid JSON, for example {\"temperature\": 0.2}."); }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Extra parameters must be a JSON object.");
  if (Object.keys(value).length > 20) throw new Error("Use at most 20 extra parameters.");
  if (Object.keys(value).some(key => !supported.includes(key))) throw new Error("Use only the supported keys listed above. Token limits have their own fields.");
  return value;
}

export type ParameterValue = number | string | boolean | string[] | null;
export type ParameterValues = Record<string, ParameterValue>;
export type StageValues = Record<string, ParameterValues>;
export type ParameterField = {
  key: string; label: string; type: "number" | "integer" | "string_list" | "select" | "duration" | "boolean";
  help: string; min?: number; max?: number; step?: number; options?: string[]; pattern?: string;
  max_items?: number; max_length?: number; default: ParameterValue | undefined; default_note: string;
};
export type ParameterStage = { key: string; label: string; help: string; lapi_defaults: ParameterValues; suggested: ParameterValues };
export type ParameterSchema = {
  protocol: string; category: string; accepts_overrides: boolean; notice: string | null;
  fields: ParameterField[]; stages: ParameterStage[]; model_lapi_defaults: ParameterValues;
};
/** A field is on "default" (key absent), "provider" (null: send nothing) or "custom". */
export type FieldMode = "default" | "provider" | "custom";
export type Source = "stage" | "model" | "lapi_default" | "provider_default";

export function schemaPath(protocol: string, category: string, connection: Record<string, any> = {}, model = ""): string {
  const query = new URLSearchParams({ protocol, category, chat_format: connection.chat_format || "generic", embedding_format: connection.embedding_format || "titan", model });
  return "/model-registrations/parameter-schema?" + query.toString();
}

export function fieldMode(values: ParameterValues | undefined, key: string): FieldMode {
  if (!values || !Object.prototype.hasOwnProperty.call(values, key)) return "default";
  return values[key] === null ? "provider" : "custom";
}

export function initialValue(field: ParameterField, fallback?: ParameterValue): ParameterValue {
  if (fallback !== undefined && fallback !== null) return fallback;
  if (field.default !== undefined && field.default !== null) return field.default;
  if (field.type === "boolean") return false;
  if (field.type === "string_list") return [];
  if (field.type === "select") return field.options?.[0] ?? "";
  if (field.type === "duration") return "5m";
  return field.min !== undefined && field.min > 0 ? field.min : 0;
}

/** Copy of values with one field set to a mode; custom keeps an existing value. */
export function withMode(values: ParameterValues | undefined, field: ParameterField, mode: FieldMode, fallback?: ParameterValue): ParameterValues {
  const next: ParameterValues = { ...(values || {}) };
  if (mode === "default") delete next[field.key];
  else if (mode === "provider") next[field.key] = null;
  else next[field.key] = fieldMode(values, field.key) === "custom" ? next[field.key] : initialValue(field, fallback);
  return next;
}

export function withValue(values: ParameterValues | undefined, key: string, value: ParameterValue): ParameterValues {
  return { ...(values || {}), [key]: value };
}

/** Same checks as lapi_models/parameters.py; returns an error message or "". */
export function fieldError(field: ParameterField, value: ParameterValue): string {
  if (value === null) return "";
  if (field.type === "number" || field.type === "integer") {
    if (typeof value !== "number" || !Number.isFinite(value)) return `${field.label} must be a number.`;
    if (field.type === "integer" && !Number.isInteger(value)) return `${field.label} must be a whole number.`;
    if ((field.min !== undefined && value < field.min) || (field.max !== undefined && value > field.max)) return `${field.label} must be between ${field.min} and ${field.max}.`;
    return "";
  }
  if (field.type === "string_list") {
    if (!Array.isArray(value) || value.length > (field.max_items ?? 16) || value.some(v => typeof v !== "string" || !v.length || v.length > (field.max_length ?? 256))) return `${field.label}: up to ${field.max_items ?? 16} entries of 1–${field.max_length ?? 256} characters.`;
    return "";
  }
  if (field.type === "boolean") return typeof value === "boolean" ? "" : `${field.label} must be on or off.`;
  if (field.type === "select") return field.options?.includes(String(value)) ? "" : `Choose a ${field.label.toLowerCase()} option.`;
  if (field.type === "duration") return typeof value === "string" && new RegExp(`^(?:${field.pattern || "(?:0|[0-9]{1,3}(?:ms|s|m|h))"})$`).test(value) ? "" : `${field.label} must look like 5m, 30s or 0.`;
  return "";
}

export function valuesError(schema: ParameterSchema | null, values: ParameterValues | undefined): string {
  if (!schema || !values) return "";
  for (const [key, value] of Object.entries(values)) {
    const field = schema.fields.find(f => f.key === key);
    if (!field) return "Use only the parameters listed for this provider.";
    const error = fieldError(field, value);
    if (error) return error;
  }
  return "";
}

export function parseStopList(text: string): string[] {
  return text.split("\n").map(line => line.trim()).filter(Boolean);
}

export function formatValue(value: ParameterValue | undefined): string {
  if (value === undefined || value === null) return "provider default";
  if (Array.isArray(value)) return value.length ? value.map(v => JSON.stringify(v)).join(", ") : "none";
  if (typeof value === "boolean") return value ? "on" : "off";
  return String(value);
}

/** Mirror of parameters.resolve: stage → model-wide → Lapi default → provider. */
export function resolveField(schema: ParameterSchema, key: string, model: ParameterValues, stages: StageValues, stage: string | null): { value: ParameterValue | undefined; source: Source } {
  const staged = stage ? stages[stage] : undefined;
  if (staged && Object.prototype.hasOwnProperty.call(staged, key)) return staged[key] === null ? { value: undefined, source: "provider_default" } : { value: staged[key], source: "stage" };
  if (Object.prototype.hasOwnProperty.call(model, key)) return model[key] === null ? { value: undefined, source: "provider_default" } : { value: model[key], source: "model" };
  const defaults = stage ? schema.stages.find(s => s.key === stage)?.lapi_defaults : schema.model_lapi_defaults;
  if (defaults && Object.prototype.hasOwnProperty.call(defaults, key)) return { value: defaults[key], source: "lapi_default" };
  return { value: undefined, source: "provider_default" };
}

/** The values a stage sends, as the effective-settings preview shows them. */
export function effectiveFor(schema: ParameterSchema, model: ParameterValues, stages: StageValues, stage: string | null): Record<string, { value: ParameterValue | undefined; source: Source }> {
  const result: Record<string, { value: ParameterValue | undefined; source: Source }> = {};
  for (const field of schema.fields) result[field.key] = resolveField(schema, field.key, model, stages, stage);
  return result;
}

export const sourceLabel: Record<Source, string> = {
  stage: "this stage", model: "model value", lapi_default: "Lapi default", provider_default: "provider default",
};

/** What "Default" means for a field at this scope, in one line. */
export function defaultMeaning(schema: ParameterSchema, field: ParameterField, model: ParameterValues, stages: StageValues, stage: string | null): string {
  const resolved = stage ? resolveField(schema, field.key, model, { ...stages, [stage]: {} }, stage) : resolveField(schema, field.key, {}, {}, null);
  if (resolved.source === "model") return `Default here: the model value ${formatValue(resolved.value)}.`;
  if (resolved.source === "lapi_default") return `Default here: Lapi sends ${formatValue(resolved.value)} (documented Lapi default).`;
  return `Default here: nothing is sent. ${field.default_note}`;
}

/** Stage values kept for the request: only known stages, without empty ones. */
export function cleanStages(schema: ParameterSchema | null, stages: StageValues): StageValues {
  const allowed = schema ? schema.stages.map(s => s.key) : Object.keys(stages);
  const result: StageValues = {};
  for (const [stage, values] of Object.entries(stages)) if (allowed.includes(stage) && Object.keys(values || {}).length) result[stage] = values;
  return result;
}

/** Stages the connection test should sample: answer stages the admin changed. */
export function testStages(category: string, model: ParameterValues, stages: StageValues): string[] {
  if (category !== "chat") return [];
  const changed = (stage: string) => Object.keys(stages[stage] || {}).length > 0;
  const result = ["chat", "optimize"].filter(changed);
  if (Object.keys(model).length && !result.includes("chat")) result.unshift("chat");
  return result;
}
