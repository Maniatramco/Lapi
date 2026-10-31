# Lapi model integrations

`catalog.py` supplies the authenticated frontend Provider choices: Ollama,
OpenAI, direct Anthropic Claude, Gemini API, Azure OpenAI v1, Bedrock, Vertex AI, OCI and another
OpenAI-compatible API. The form initializes endpoint/authentication defaults
and requires a successful synthetic test before saving. Chat tests validate
function calling; extraction tests validate JSON Schema; embedding tests
validate vectors. Save the model, then enable it for the dataset in Model Mapping.

Agent tool calling supports all these protocol families. Native serializers
live in the provider `agent.py` files (Claude uses `lapi_anthropic/native.py`)
and execute through `agent_connection.py`.
Claude/Vertex signatures and Bedrock assistant state survive private graph checkpoints
without appearing in the final answer. Native completed responses use the
existing event channel; incremental token streaming remains specific to the
Ollama and OpenAI-compatible transports.

The account must already expose the model/deployment and grant inference
access. Chat models must support function calling; extraction and embedding
models must support their requested contracts. Another model using an existing
API needs no source changes. A different API still requires an adapter.

All provider contracts have HTTP/SDK mock coverage. Gemini has live free-tier
verification. Other accounts need their own successful registration tests;
no Anthropic, Azure, AWS, Vertex or OCI model credentials are bundled with Lapi.

Protocol references: [Bedrock Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-client-side.html),
[Vertex function calling](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling),
[Vertex signatures](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thought-signatures),
[OCI SDK](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai_inference.html),
[Claude Messages](https://platform.claude.com/docs/en/api/messages/create).

`registration.py` manages model registration and encrypted, versioned
credentials. `registry.py` manages registration identity and consolidation.
`parameters.py` validates model settings. `validation.py` owns destination,
protocol and credential policy. `connection.py` is the guarded execution
facade: bounded HTTPS transport, generation schema checks and vector checks.

`provider_registry.py` selects fixed implementation modules from saved
protocol IDs. It never imports a path supplied by a user or substitutes a
different provider after a failure. Providers are:

| Folder | Implementation |
| --- | --- |
| `providers/lapi_local` | Existing Ollama transport and model operations |
| `providers/lapi_gcp` | Gemini Developer API compatibility and native Vertex |
| `providers/lapi_azure` | Azure OpenAI v1, sharing the compatible wire contract |
| `providers/lapi_openai` | Shared OpenAI-compatible generation and embeddings |
| `providers/lapi_anthropic` | Direct Claude Messages and native Chat tool calls; no embeddings or extraction |
| `providers/lapi_aws` | Native Bedrock client, generation and embeddings |
| `providers/lapi_oci` | Native OCI and existing Enterprise AI adapters |

Optional cloud SDKs load only when the corresponding client is used. Local
Ollama execution continues through `lapi_local/ollama.py`; it is not silently
routed through the cloud facade. Legacy root imports alias the canonical
modules, preserving older callers and saved protocol/configuration formats.

## Model parameters per stage

Model Registration edits sampling values in a typed form built from
`GET /api/model-registrations/parameter-schema` (`parameters.parameter_schema`,
also `supported_parameters(..., schema=True)`): each field's type, range,
provider default and help, the stages of the category and suggested starting
values. Ranges are the validation ranges (temperature 0–2, 0–1 on Bedrock).
A provider without sampling overrides (direct Claude) returns a notice.

A Chat or Extraction model stores `extra_parameters` (model-wide) and
`stage_parameters` for `chat`, `tool_step`, `extraction` and `optimize`. A
missing key means Default; `null` means Use provider default (nothing is
sent). Call sites resolve one field at a time with
`parameters.for_stage(cfg, stage)`: stage value, then model value, then the
documented Lapi default in `LAPI_DEFAULTS`. Admin values always win.

| Lapi default | Where it used to be hard-coded |
| --- | --- |
| Ollama, every stage: top_p 0.8, top_k 20, repeat_penalty 1.1, seed 42; Optimize temperature 0.7 | Ollama adapter sampling |
| Ollama Chat answer and Tool steps: temperature 0 | `agent_model`, `chat_agent`, `dataset_chat_general` |
| Ollama Extraction: temperature 0.2 | Ollama extraction |
| OpenAI-compatible and Azure GPT-4o Tool steps: temperature 0 | `agent_model` strict tool choice |
| Cloud OCR (Extraction stage): temperature 0.1 | OpenAI and Gemini OCR |

Local Ollama OCR has no registered model and keeps `OLLAMA_OCR_OPTIONS`.
Calls infer their stage (tools offered: `tool_step`; schema: `extraction`;
otherwise `chat`); `with parameters.use_stage('optimize'):` chooses it
explicitly. `parameters.effective()` returns the parameters and sources of
the latest call for usage records. The connection test reports them per
stage and, with `test_stages`, runs one sample prompt per answer stage.
Every saved change appends a `parameter_history` entry (author, time, full
set, field changes), served by `GET /api/model-registrations/{id}/parameter-history`.

## Direct Claude Chat

Choose `anthropic` for direct Claude API keys, not Bedrock, Vertex or the
OpenAI compatibility protocol. Only Chat is exposed. The official endpoint
`https://api.anthropic.com/v1` is recognized without an environment allowlist;
custom hosts are rejected for this protocol, including otherwise approved gateways.
The key comes exclusively from the pinned encrypted registration profile.
Optional `workspace_id` supplies `anthropic-workspace-id`; workspace-scoped
keys can leave it blank. No global Anthropic environment credentials are read.

Requests use `x-api-key`, explicit API version `2026-10-21`, native tool schemas,
assistant content blocks and user-role tool results. The adapter uses `auto`
tool choice because forced modes are model-specific; Lapi still rejects missing
required calls, unknown tools and invalid tool schemas. No sampling overrides
are exposed in this API version. Refused, truncated, malformed and inconsistent
responses fail closed without exposing the provider body. Reported input usage
includes cache creation/read tokens when present. Thinking signatures are
retained privately for subsequent tool turns and never become answer text.

Registration, Agent routing/grounded generation and Dashboard routing/general
and grounded generation have isolated mock HTTP coverage. A real key/model
must pass Test Connection and an authorized live chat check before its account
readiness is established. Existing Embedding/Extraction mappings and processing
agents keep their contracts. Publish backend and frontend together when a live
release is requested; no database schema change is needed.

## Cloud OCR and cloud-only datasets

Model Mapping exposes a separate `ocr_model_id` choice. A registered compatible
OpenAI/Gemini extraction model can be selected independently of the extraction
default. `null` uses a compatible cloud extraction default. Local OCR choices
are rejected, and dataset image processing never falls back to Ollama. A dataset
without a cloud vision selection can still read native text; scanned content
requires choosing an eligible cloud OCR registration. The selected model must be enabled, mapped and
accessible to the dataset owner; embeddings and chat-only registrations are
ineligible. Legacy clients omitting the field preserve its saved value. Changing
OCR does not change embeddings or index generation; reindex documents to rerun OCR.

A dataset mapped to a `gemini-*` extraction model on the Gemini Developer API
also uses that registration for scanned PDF pages and embedded DOCX images.
Index jobs pin its model, profile version and encrypted credential reference;
the API key is never copied into jobs or document metadata. Upload approval
lists Gemini OCR as an image destination.

Datasets whose default extraction registration uses GPT-4o or GPT-4o Mini on
`https://api.openai.com/v1` use that saved OpenAI connection for scanned PDF
pages and embedded DOCX images. Dated GPT-4o and GPT-4o Mini snapshots are
supported too. OpenAI OCR is disclosed as an image destination, including when
embeddings are local. Consent identities include the OCR endpoint, model and
pinned credential-profile version. Unsupported OpenAI extraction models fail
before inference; embedding models cannot transcribe images.

Other datasets retain their own local OCR setup. Cloud OCR failures never fall
back to Ollama. The embedding registration remains independent: changing OCR
does not change dataset embeddings or index generation. Previously queued jobs
retain their saved configuration, including job retries. Use the document's
Reindex action after release to create a new cloud OCR snapshot.

The adapter in `providers/lapi_gcp/ocr.py` uses Google's
[image input API](https://ai.google.dev/gemini-api/docs/openai#image-understanding).
The shared OCR path still rejects incomplete, invalid, unreadable and blank
transcriptions, retains original/native text and labels OCR as unverified.
Cloud cache identities pin configuration versions, not unavailable weight
digests. OCR output/context limits also respect the extraction registration.

Gemini routing declares union-shaped tool contracts as separate bounded
functions. Returned arguments are validated against the selected branch and
the original canonical schema before any agent acts.

## Add another model using a supported protocol

Use Lapi Model Registration: name, category, protocol, endpoint, model or
deployment ID, authentication and supported limits. Run the synthetic
connection test, save, then assign the model in Model Mapping. No folder or
new adapter is needed for another model using the same protocol. Register
chat and extraction roles separately. An embedding change requires applying
the mapping and reindexing existing documents.

Azure OpenAI v1 uses `https://RESOURCE.openai.azure.com/openai/v1` and the
Azure **deployment name** in Model / deployment ID. Enter the key through
Authentication. Verify tool calling for Agent chat and structured output for
extraction with the deployed model. A custom gateway requires a specific
server-approved hostname. Local Ollama models must already be available at
the approved local service.

## Add a provider with a different API protocol

1. Implement `generate(connection, instruction, text, schema, output_tokens,
   extra)` and `embed(connection, texts, query, dimensions, extra)` in its
   provider folder. Generation returns text; embeddings return raw vectors.
   The shared facade retains completion, schema and vector validation.
2. Add its fixed module and authentication modes to `provider_registry.py`.
   Add endpoint/credential validation and permitted inference parameters.
3. Expose the supported protocol and fields in backend registration schemas
   and the frontend Model Registration form. If its tool-call protocol is
   different, add the Agent transport/serialization support explicitly;
   generation support alone does not imply Agent support.
4. Test generation, embeddings, schema failures, vector count/order/dimensions,
   credentials, immutable queued profiles and endpoint restrictions without
   real secrets. Then perform a small authorized live smoke test.

Do not copy dataset/storage logic into provider implementations. Do not add
an arbitrary endpoint, insecure transport, implicit credential reuse or
automatic provider fallback to make a test pass.

## OpenAI Decisions API

`decisions.py` calls `POST /v1/decisions` (OpenAI, `gpt-6-luna`) through the pinned
connection. Decisions returns typed answers: a predicate's probability, a choice
with its confidence, or a score. Any question can come back as a refusal. Lapi
uses it only to judge, never to write text.

Decisions is a model use of its own in Model Registration, for `api.openai.com`
connections only, registered without other uses. Test connection asks two
predicates with known answers. The workspace Decisions Default is optional and
can be cleared with `DELETE /api/workspace/defaults/decisions`. Without it, every
caller keeps its previous behaviour.

With the Default set:

- `lapi_agent/answer_support.py` checks each cited sentence of a chat answer
  against the sources it cites, after citation validation. Unsupported answers
  get one repair from the same evidence and are refused if still unsupported.
  In the Lapi Agent's agentic chat, rejected sentences are repaired once and
  then removed, like other citation-check failures.
- `dataset_chat_general.knowledge_check` can send a Dashboard chat request to
  knowledge lookup before a direct answer. It never skips lookup.
- `setup_assist.decide` reads yes, no and option answers in the set-up chat.

Thresholds, the timeout and the number of sentences checked per answer are in
`runtime.toml` under `[decisions]`. Each result records what actually ran:
`not_configured`, `skipped`, `unavailable`, `passed` or `unsupported`.
