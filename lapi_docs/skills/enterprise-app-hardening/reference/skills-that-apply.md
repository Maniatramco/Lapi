# Skills that apply themselves (Lapi v26.1.16.31)

User's ask: let people upload a skill and have the agent use it when relevant, for a document type, a domain
or a specific document, with instructions in the skill.

- Keep the existing skill model (name, description, steps, allowed_tools, output_format, scope personal /
  dataset / workspace) and add `applies_to` with four comma lists in the front matter: `document_types`,
  `domains`, `keywords`, `documents` (file-name globs). Parse, render (download) and validate them.
- Matching is deterministic and explainable (`applies()` returns "keywords: overdue"): whole words of the
  request, document types / globs against attached file names and selected documents. No model call. Cap at
  4 auto-loaded skills per request; a skill without applies_to is never automatic.
- Load matches before the answer (`_auto_skills` in the system prompt builder) and record them in
  `loaded_skills` so the existing tool-narrowing and `skills_used` keep working. Scripted agent tests that
  take "the first tool message" may need to pick the one with citations.
- Upload: multipart SKILL.md, 64 KB cap, UTF-8, name from front matter or file name (never "skill"),
  same-name upload replaces the person's own skill (`replaced: true`). Route policy + API catalog entries.
- Make the example real: give a built-in skill applies_to, add a tour scene (both device scripts, keep
  words per second <= 2.7, update timing tests), a training card, and bump TOUR_VERSION / TRAINING_VERSION.
