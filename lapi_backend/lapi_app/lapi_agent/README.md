# Lapi Agent

This package owns Agent orchestration, semantic routing, confirmed workflows,
grounded answers, citations, context budgets, streaming and token accounting.

- `agent_graph.py`: the conversational graph and saved reply.
- `agent_workspace.py`, `agent_goals.py`: durable plan and goal lifecycle.
- `agent_tools.py`: authorized tool contracts and execution.
- `chat_agent.py`, `chat_retrieval.py`, `chat_policy.py`, `chat_knowledge.py`:
  scoped hybrid retrieval, reranking, evidence and answer validation.
- `agent_model.py`, `agent_stream.py`, `agent_context.py`: Agent tool-call
  serialization, incremental answers and context packing.
- `token_usage.py`: isolated provider-reported usage for one answer turn.
- `agentic_chat.py`, `agent_tools_v2.py`, `answer_check.py`: agentic chat
  (`LAPI_CHAT_MODE` = router | agentic | auto). One tool-calling loop with a
  prefetched search, parallel deduplicated reads and an evidence budget; v2
  tools resolve names server-side and return `{data, citations, next_offset,
  truncated, note}`; every factual sentence is checked against the sources it
  cites, repaired once, then removed with a visible count. The system prompt is
  `prompts/agent_system.md`.
- `skills.py` (+ `skills/*.md` built-ins), `chat_commands.py`, `user_memory.py`
  and `../prompt_layers.py`: skills, `/skill` `/instructions` `/optimize`,
  per-user memory and dataset instructions / model guides for agentic chat.
- `onboard_extract_agent.py`, `extractor_agent.py`, `reextract_agent.py`:
  the existing processing-agent contracts.

Model connection implementations live in the sibling `lapi_models` package.
Legacy `lapi_app.agent_*` and chat imports remain aliases to these modules;
there is only one implementation and one set of module state.

Keep the root `AGENTS.md` workflow requirement: access and dataset scope,
hybrid retrieval, reranking, generation, then answer/citation validation.
Do not alter processing agents to implement a chat-only feature.

Agentic chat keeps the same order: access and dataset scope are rechecked in
every tool, retrieval is hybrid with reranking, the model generates, and the
answer check validates citations before anything is saved. Router mode stays
the default; the OCI compose file opts into `auto`, which uses agentic chat for
cloud function-calling models (Gemini, Claude, GPT) with at least 32k context.
