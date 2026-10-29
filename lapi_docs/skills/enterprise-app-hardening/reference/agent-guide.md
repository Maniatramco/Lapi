# Guiding plain requests before the model (Lapi v26.1.16.30)

User complaint: "if I type 'upload this one' it should guide me end to end, even if I am missing a dataset or
prompt, instead of throwing something irrelevant." The agent's model-based router guessed; the fix is a
deterministic guide layer in front of it.

- `agent-guide.ts` is pure and unit-tested: regex intents (upload / extract / dataset / prompt / start), a
  readiness check (`files`, `dataset`, `templates`, `canOnboard`, `datasets`, `promptAttached`) and the step
  to show with 1–2 chips. Commands, `#document` mentions and knowledge questions ("what is the total…") are
  never guided. Only `how do I …` questions count as intents.
- When nothing is missing the request runs with the deterministic `agent_operation` (`upload`, `extract`,
  `onboard`) so the model never has to decide whether it was a question.
- The guided step is an exchange in the thread (request bubble + agent text + chips + Dismiss); the text
  stays in the composer so "Add documents → send again" just works. Quick start accepts the attached files.
- Where a screen is hidden (phones), the chip "Write a prompt" navigates through `onReview`, which the shell
  may ignore; prefer the Guided start chip first.
- Rule of thumb for "should we add a decision API / CrewAI?": first route deterministically, ask one
  button question at most, say what is happening; only then consider multi-agent frameworks.
