# Raising the Lapi Agent score from 46 to 80+

The 31 October run scored the agent 46/100 over 39 prompts. The score was not spread evenly: single-fact lookups were 14/14 correct (5/5/5 in 4–7 s); 12 of 26 reasoning prompts came back empty or mangled. One mechanism caused almost all of it, so the path to 80 is short and mostly done in v26.1.16.49.

## Where the 54 lost points went

| Cause | Prompts affected | Points lost (approx.) | Status |
|---|---|---|---|
| Validator deleted correct content (dates reformatted, arithmetic, tool-built tables, user-stated facts, summaries, workflow prose) | A1, A4, S1, S2, L3, O1, T1, T3, MEM, COR, SUM, M1, C1, F2, X1, UP | 34 | **Fixed in code** (`answer_check`, `agentic_chat`, `answer_support`) |
| Spreadsheet tool could not compute derived metrics, so the model improvised (sum of quantity + sum of price) | S1, S3 | 6 | **Fixed** (`spreadsheet._derived` + prompt rule) |
| Agent upload flow needed four round-trips and a re-attach | UP | 4 | **Fixed** (`lastSentFiles`) |
| Replies in English to Hindi/Tamil | T1, T2, T3 | 3 | **Prompt rule added**; verify with real prompts |
| Generic refusal text ("couldn't find enough evidence") even when search had hits | A1, L5, P1, P2 | 3 | Partly fixed (fewer removals); wording still generic |
| Conflicting constraints not explained; JSON-only not honoured | C1, F2 | 2 | Prompt work remaining |
| Multi-step answers lost steps | M1 | 2 | Fixed by the validator change; verify |

## What to do next, in order

1. **Re-run the 26 reasoning prompts** from the report's section 3 against the deployed v26.1.16.49 and record the new scores. Expected: A1, A4, S2, L3, O1, T3, MEM, COR, SUM, M1 move from 1–2 to 4–5. That alone is roughly 46 → 72.
2. **Give the validator the tool outputs as evidence for the judge** (`answer_support`): the Decisions judge now skips sentences cited only from calculations; also send it the `reading` block (filters, metrics, matched rows) when a sentence mixes a document citation and a calculation, so it can confirm instead of guess. Expected +3.
3. **Teach the model to answer in the question's language** and test Tamil/Hindi/Tanglish again. The prompt rule exists; if gpt-4o still answers in English, add a one-line language detector before the call and put "Reply in Tamil" into the user turn. Expected +3.
4. **Refusals that say what was found.** Replace "I couldn't find enough evidence…" with a sentence that names the documents searched and the closest match ("The Kestrel plan names a COO, Priya Natarajan, but no CTO [1]."). This is a prompt rule plus allowing uncited prose when the answer is a refusal. Expected +2.
5. **Format contracts.** When the request says "JSON only" or "exactly 3 bullets", run the validator on the values but never append the removal note or trailing sources inside the JSON; put them after a blank line. Expected +2 (F2 becomes valid JSON).
6. **Conflicting constraints.** Add to the system prompt: "When two requirements cannot both be met, say which one you kept and why in one sentence, then answer." Expected +1.
7. **Memory across turns.** The validator now accepts user-stated facts. Add them to the model's context explicitly: a "Facts you told me" block built from the user's turns (names, numbers, corrections), so corrections replace earlier values reliably. Expected +2 (MEM, COR to 5).
8. **Latency.** Median 6 s is acceptable; the repair loop doubles it when it fires. With fewer false failures the loop fires less. Keep the 3-step repair cap.

Steps 1–3 take the score to about 78; steps 4–7 to the mid-80s. The measurement is the same scorecard, same prompts, same ground truth files (regenerate them with the in-page generators described in the report or from `lapi_testing/backend/data`).

## How to keep it there

- Add the 26 prompts and their expected values to `lapi_testing/backend/test_agentic_chat.py` as offline fixtures: the validator functions (`unsupported_values`, `check`, `_derivable`, `_date_keys`) are pure and can be tested without a model.
- Track `validation.removed_sentences` and `kept_despite_judge` in Token usage: a rise in removals is the early warning that a prompt or validator change regressed.
