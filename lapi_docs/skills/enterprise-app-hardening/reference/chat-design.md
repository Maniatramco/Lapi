# Chat design (Lapi Agent and the Dashboard chat) — modelled on the Claude chat layout

The user asked for the chat to feel like Claude's: roomy, readable, and clearly "working" while it answers. Take
the layout and type ideas, **keep the app's own colours, logo and name** (do not copy another product's
branding or proprietary fonts).

## What to build (Lapi: `chat-design.css`, `chat-phase.ts`, `agent-v2-chat.tsx`)
- **One stylesheet** imported by the shared answer component, loaded after older chat styles; selectors start with
  `body .shell .agent-v2` to win over earlier, very specific rules. Both chats share classes (`agent-v2-thread`,
  `-request`, `-user`, `-speaker`, `-reply`, `-composer`, `-compose-box`), so one file styles both.
- **Reading column**: thread children `max-width: 768px; margin: auto`; thread padding 32/24 px (18/14 on phones).
- **Questions**: right-aligned soft bubble (`#eef2fb`, radius 20/20/6/20, 16 px sans, max 85 %).
- **Answers**: no card; serif reading font
  `ui-serif, "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif`, **17.5 px / 1.72** (16.5 px on
  phones), ink `#1f2430`; headings in the sans; inline code and code blocks in a monospace with light backgrounds;
  citations `[n]` as small blue pills.
- **Lists**: render `- ` / `* ` / `• ` lines as bullet items and `1. ` lines as numbered items (`AnswerLine` in
  `agent-v2-chat.tsx`); blank lines become a 0.75 em gap (not `<br>` inside a div).
- **Composer**: centred under the column, radius 24 px, soft shadow, focus ring, 16 px text (`--text-input` so the
  /command highlight overlay stays aligned), orange square-rounded send button; small centred footer hint.
- **Live status while working** (the "updates and loading" part): when an answer is streaming and has no text yet,
  show three pulsing dots (orange/blue/indigo) + a shimmering line from `answerPhase(message)`:
  Thinking → Understanding your question → Searching your knowledge → Writing the answer → Checking the answer
  against its sources (from the running `answer_workflow` step). Hide the empty reply cursor and the empty token
  line during that state (`:has(.agent-thinking)`).
- New exchanges fade/slide in (0.28 s); copy action fades in on hover; `prefers-reduced-motion` turns animations off.
- **Room**: in Lapi Agent the right "Context" panel shows only at ≥ 1500 px; the history rail stays. Welcome becomes
  a calm serif greeting ("How can I help?") instead of a gradient banner (remove its `::before` grid and shadow).
- Phones: hide the floating "Ask" shortcut while the chat itself is open (it covered the composer).

## How to test without a real model
The local mock model cannot answer. In your own browser tab, replace `window.fetch` for `/dataset-chat/reply`
with a `ReadableStream` that emits SSE frames (`event: progress` with `workflow.steps` changing over ~4 s, then
`event: done` with a message that has bold text, a list, citations and follow-ups). Screenshot mid-answer (status
line only) and after (bullets, pills, spacing) at 1280 px and 375 px.

## Tests
- `lapi_testing/frontend/chat-phase.test.cjs` (status wording), `batch-progress.test.cjs` (lists render as items).
