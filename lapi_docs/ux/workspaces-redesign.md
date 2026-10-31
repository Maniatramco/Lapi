# Lapi UX redesign: Workspaces and Collections

Status: proposal, nothing built. Written 2026-10-30 from the uncommitted working tree, so line numbers may shift.
Paths are relative to `lapi_frontend/app/` unless they start with `lapi_backend/`.

Markers: **[PD-n]** needs a product decision (listed in section 6). **[BE]** needs backend work. Anything unmarked can ship with frontend changes alone, using what the API returns today.

---

## 1. Problems in the current experience

### A. Permissions and the new model disagree

| # | Problem | Where |
|---|---|---|
| A1 | **Most people cannot create a collection on the Collections screen.** "New collection" depends on being an administrator or contributor, not on the workspace level. An Editor, or anyone in their own personal workspace, sees no button and is told "Ask your administrator to assign a collection". The API would allow it. | `page.tsx:961`, `dataset-workspace.tsx:53,56`; API rule in `lapi_backend/lapi_app/workspaces.py:103`, `lapi_backend/lapi_app/dataset_models.py:450` |
| A2 | **`/Onboard` is administrator only**, with the message "Only the administrator can onboard collections". This contradicts A1's rule and the Editor level. | `agent-v2.tsx:305,399`; `lapi_backend/lapi_app/lapi_agent/agent_workspace.py:221,229` |
| A3 | **People can be set in two places.** Members are set per workspace, but each collection still has a Members tab. A later workspace save overwrites the same grants, so the two can disagree. | `manage-dataset.tsx:21,31,73`; `lapi_backend/lapi_app/workspaces.py:229-233`; `lapi_backend/lapi_app/route_policy.py:71-72` |
| A4 | **"Share with your team" appears on personal collections and then fails.** It shows for any owner; the server refuses sharing personal collections. | `quick-start.tsx:158,318`; `lapi_backend/lapi_app/teams.py:186` |
| A5 | **Empty states still say "assigned by your administrator"**, which is no longer how access works. | `dataset-directory.tsx:65`, `dataset-workspace.tsx:56`, `dataset-dashboard.tsx:103,138`, `add-knowledge.tsx:102` |

### B. The workspace switcher does not fully scope the app

| # | Problem | Where |
|---|---|---|
| B1 | **Review, Extract and prompts ignore the workspace.** Only collections and documents are filtered; extractions and templates are not. Review can list rows reading "Collection unavailable". | `page.tsx:331-332,498,497`; `extraction-directory.tsx:13` |
| B2 | **Extract's "All collections" sends no collection filter**, so results and exports can cover every workspace. | `extract-data.tsx:16,47` |
| B3 | **Chat history is not scoped.** The Recent list mixes chats from all workspaces. | `agent-v2.tsx:421,440` |
| B4 | **"All accessible knowledge" is untrue.** The Dashboard shows that label while using only the open workspace. | `dataset-dashboard.tsx:64,93,136` |
| B5 | **Switching skips the unsaved-changes check** that every other navigation has, and does not leave a Review record from the previous workspace. | `page.tsx:674-677` vs `page.tsx:547` |
| B6 | **Verify:** whether General chat searches across workspaces, and whether the Agent clears its selected collection on a switch. `scopeCatalog` filters only the choices. | `agent-v2.tsx:54,446`, `workspace-scope.ts:29` |

### C. Login and first-run overload

| # | Problem | Where |
|---|---|---|
| C1 | **Too many first-run layers:** workspace question, first-collection dialog, Quick start, tour, three set-up questions, a next-steps card, a permanent Quick start banner, and six training cards inside the chat. This is the owner's information overload. | `workspace-gate.tsx`, `page.tsx:944-953`, `workspace-assist.tsx:148,235-247`, `agent-training.tsx:19` |
| C2 | **Quick start asks again where the documents go** straight after the person created a collection, and can default to "New collection" because it reads the list before the refresh, so a second collection is easy to create by accident. | `page.tsx:948`, `quick-start.tsx:34,37` |
| C3 | **"Which workspace?" returns in every new tab**, because "chosen" is kept in tab-only storage. | `page.tsx:676,684` |
| C4 | **"Not now" on the first collection is forgotten on reload.** | `page.tsx:328,949` |
| C5 | **Administrators get a very long workspace list.** They see every person's personal workspace, in both the question and a plain dropdown. | `lapi_backend/lapi_app/workspaces.py:91,119-123`; `workspace-gate.tsx:68`, `page.tsx:873-882` |
| C6 | **Gate dialogs declare `aria-modal` but do not trap focus.** | `workspace-gate.tsx:30` (compare `workspace-assist.tsx:48`) |

### D. Workspace management is hidden or wrongly worded

| # | Problem | Where |
|---|---|---|
| D1 | **There is no workspace page.** People management is an option inside the switcher dropdown, only for team-workspace owners. Actions inside a `<select>` are hard to find and awkward for screen readers. | `page.tsx:873-882` |
| D2 | **The people screen talks about collections while editing a workspace**: "Saved who can open this collection", "Only administrators can open this collection so far". It repeats instruction text and needs add, then choose level, then save. | `dataset-members.tsx:26,31,34,36,41`, `access-map-data.ts:19` |
| D3 | **Only owners can see who is in a workspace.** Viewers and Editors have no way to know who else can read the documents. **[BE]** | `lapi_backend/lapi_app/workspaces.py:194` |
| D4 | **Every workspace owner gets the full list of usernames and teams.** Since anyone can create a team workspace, anyone can read the directory. **[PD-4]** | `lapi_backend/lapi_app/workspaces.py:197-199` |
| D5 | **No rename, delete, leave, or transfer of a workspace; no move of a collection between workspaces.** The API has four workspace routes only. **[BE]** | `lapi_backend/lapi_app/route_policy.py:132-135` |
| D6 | **The "Organization" workspace breaks the stated model.** People see only the collections they hold, the count includes ones they cannot see, and the level shown defaults to Viewer. **Its Owner is whoever's collection was placed first**, and an owner's member change applies to every collection inside. Please review this with the backend engineer as an access risk, not just a wording issue. **[PD-5] [BE]** | `lapi_backend/lapi_app/workspaces.py:83,114-123,229-233` |

### E. Type tags are half built

| # | Problem | Where |
|---|---|---|
| E1 | **No filter by type anywhere.** Collections shows the tag inside the Description column; search matches it there but not on the Dashboard. | `dataset-directory.tsx:22,33`, `dataset-dashboard.tsx:62` |
| E2 | **A type cannot be changed after creation.** No field in Manage; the API does not accept it. **[BE]** | `manage-dataset.tsx:53-59`; `lapi_backend/lapi_app/dataset_models.py:336-338` |
| E3 | **Free text creates near-duplicates** ("finance" and "Finance"). | `workspace-gate.tsx:59`, `quick-start.tsx:199`, `lapi_backend/lapi_app/dataset_models.py:452` |

### F. Phones, foldables and tablets

| # | Problem | Where |
|---|---|---|
| F1 | **"Agent and Quick Extract only" is not true for everyone.** Administrators and anyone with extra screen grants get a third "More" tab and a full drawer. **[PD-1]** | `screens-client.ts:33`, `workspace-assist.tsx:256` |
| F2 | **Chat loses height to chrome:** top bar (switcher, Private pill, avatar, sign out), then a collection row with up to four buttons, then a composer whose model picker takes a full row, then the tab bar. | `page.tsx:858-926`, `agent-v2.tsx:445-452,556`, `phone-design.css:24-28,110` |
| F3 | **Words point to a missing screen:** "Keep asking on the Dashboard" on touch devices. | `quick-start.tsx:315` |
| F4 | **Viewers get a tab bar with one tab**, which uses height for nothing. | `workspace-assist.tsx:254-256` |
| F5 | **The Review list is a computer table on a phone.** Only the single-record view has a phone layout. | `extraction-directory.tsx:63`, `phone-design.css:53-75` |
| F6 | **Chat text is about 14px on phones.** A later rule overrides the earlier 15px. Tab labels are 11px, under the 13px minimum set in `mobile.css`. | `phone-design.css:13,120,127,128`, `mobile.css:7` |
| F7 | **Three sizing systems compete:** fixed `--text-*`, fluid `--fit-*`, and hard-coded pixels, with many `!important` rules. Each new screen picks its own. | `typography.css:11-17`, `phone-design.css:120`, `workspace-gate.css:5-7`, `mobile.css:8` |

### G. Words and screen structure on computers

| # | Problem | Where |
|---|---|---|
| G1 | **Jargon a layman would not know:** Onboard, Vectorize, Indexed, Reindex, Embedding, Knowledge, Authorized, Prompt template, Metadata Relationships, Agent Model, "Originals protected. Insights grounded." | `workspace-navigation.tsx:21,23`, `add-knowledge.tsx:38,146`, `dataset-dashboard.tsx:99,134`, `manage-dataset.tsx:23,61`, `agent-v2.tsx:556`, `page.tsx:854` |
| G2 | **Extract and Review have swapped internal names** and overlapping purposes. The route `Extract` displays as Review; `Extract Data` displays as Extract. | `page.tsx:128`, `workspace-navigation.tsx:23` |
| G3 | **Two different chats:** Dashboard "Collection Knowledge Chat" and Lapi Agent. **[PD-2]** | `dataset-dashboard.tsx:141`, `agent-v2.tsx` |
| G4 | **The Dashboard is crowded:** greeting, ask box, chips, suggestions, four stats, two banners, three panels, and a "How Lapi works" section. | `dataset-dashboard.tsx:99-157`, `workspace-assist.tsx:235-247` |
| G5 | **Every screen has an explanatory band** with "Step 1 of 4", implying a sequence that people do not have to follow. | `page-band.tsx:6-22`, `page.tsx:929` |
| G6 | **The Agent has three controls for one action** (New conversation twice, plus Clear chat), and a right-hand Context panel takes width from the chat. | `agent-v2.tsx:438,450,451,568-590` |
| G7 | **The top bar repeats itself:** "Lapi > page name" beside a logo, a "Private" pill, and a separate sidebar footer saying Private. | `page.tsx:870-872,901-904,849-855` |

---

## 2. Proposed information architecture

### Model in one line (for all copy)

**A workspace is a shared space. A collection is a folder of documents inside it.**

### Computer

```
Top bar:  [Lapi mark]  [Workspace name  v]            [activity dot]  [Avatar v]
Left:     Dashboard
          Agent
          Collections
          Extract
          Review
          ------------
          Settings
Avatar:   My account · Help and tour · About · Sign out
```

- **Flattened nav.** The Onboard group goes away. Sidebar collapses to icons; on the Agent screen it starts collapsed (already a drawer at `page.tsx:282`).
- **Workspace switcher** is a real menu, not a `<select>`: groups "Mine", "Shared with me", and for administrators "Other people's", with a search box above 8 entries. Footer actions: "Create a team workspace" (when `can_create_team`) and "Manage this workspace" (Owner on a team workspace).
- **Type filtering** lives on Collections as chips, built from the types in the open workspace, matched without regard to case. Also offered in the Agent's collection picker as groups. Chips show only when 2 or more types exist.
- **People management** lives at Settings > Workspace > People, one click from the switcher. The per-collection Members tab goes, except for the Organization workspace until **[PD-5]** is settled.
- **Adding documents** has one main door: the "Add documents" button on Collections and on a collection's page. It offers "From this computer" and "From cloud storage". The Agent's attach button stays as the shortcut. The "Add knowledge" nav entry goes.
- **Field lists** (prompt templates) move under Extract as a secondary tab, and stay reachable from a collection. **[PD-3]** covers the name.
- **Settings** has three groups, each shown only when relevant:
  - *Workspace:* Details, People.
  - *My account:* Password or sign-in, sessions, Agent skills and memory.
  - *Administration* (administrators, auditors for Access map): AI models, Users, Access map, Activity, Storage, Usage and cost, Files.

### Phone, foldable, tablet

Device rule stays as today: `(max-width: 640px), (pointer: coarse) and (max-width: 1100px)` (`screens-client.ts:9`).

```
Top row (one, 48px):  [Workspace name v]                 [Avatar]
                      ---------- chat ----------
Composer:             [All collections v]
                      [Ask anything...]
                      [+]  [mic]  [settings]       [send]
Bottom tabs (56px):   Agent | Quick Extract
```

- **Tabs:** Agent and Quick Extract only. Hide the bar for Viewers (one tab) and while the keyboard is open (`data-typing` already exists at `workspace-assist.tsx:225`). No Dashboard. No drawer, subject to **[PD-1]**.
- **Switcher:** bottom sheet with the same groups as computer.
- **Collection picker:** a chip in the composer that opens a sheet with type chips, then collection names, then "Choose documents".
- **Model picker, info, history:** collapse behind one settings icon and a history icon in the same sheet. This removes the separate collection row and the model row.
- **Avatar sheet:** Help, Sign out, and "Open Lapi on a computer to manage people and settings."
- **Adding documents:** Agent attach button, and Quick Extract's "Take a photo" and "Choose files". Cloud storage connection is computer only.
- **People and workspace management:** computer only. A phone shows who you are in the workspace but changes nothing. Creating a team workspace is computer only too, while the first-collection step stays on phones since it is the only way out of an empty workspace.
- **Review** is reachable only through Quick Extract's result and the status line, never as a tab. Give its list a card layout (F5).

### Text sizes

Replace the competing systems with one set of tokens. Fields stay 16px on touch so phones do not zoom.

| Token | Phone (360-640) | Foldable, tablet (641-1100 touch) | Computer |
|---|---|---|---|
| Greeting | 22px | 26px | 28px |
| Page or sheet title | 18px | 20px | 20px |
| Chat and reading text | 15px | 16px | 15px |
| Controls and table text | 14px | 15px | 14px |
| Secondary | 13px | 13px | 13px |
| Tab label | 13px | 13px | n/a |

Chat text suggestion: `clamp(.9375rem, .9rem + .15vw, 1rem)` replaces `--fit-body`. Text never falls under 13px.

### Colour

Blue `#2563eb` on white is 5.2:1: fine for buttons and links. **Orange `#fb923c` with white text is 2.3:1, so never use white on it.** Use ink `#14213d` on orange (7.1:1), and keep orange for "needs your attention" only, such as dots and the to-check count. Everything else uses ink and blue, in Inter.

---

## 3. Screen-by-screen changes

### Login

- Sign-in page: no change.
- **"Which workspace?"** shows after sign-in only when there is more than one choice. Key "chosen" to the login session rather than the tab, using `chat_session_id` from `/api/auth/me` (`page.tsx:471`), to fix C3. Rows: name, then "Team · 3 collections · Editor". Omit level on personal. Preselect the last used. No body text.
- **Empty workspace, can add:** one dialog with only name and optional type, then go straight to the documents step of Quick start with that collection already chosen (fixes C2; needs an `initialDatasetId` prop). "Not now" is remembered per workspace on this device (fixes C4).
- **Empty workspace, Viewer:** no dialog. Empty state on the Agent (section 4).
- **Nothing else opens automatically.** Tour, set-up questions and training cards become opt-in from Help (fixes C1). **[PD-6]**

### Agent

- Computer: chat column is the default focus. Recent rail is collapsible and remembered. Remove the Context panel; its content moves to a popover on the collection chip. Keep one "New chat" button; drop Clear chat and the duplicate.
- Phone: as in section 2. Only one chrome row on top.
- Opening screen: greeting, three suggestions, nothing else. "What can you do?" stays as the only route to training.
- Scope history to the workspace **[BE if conversations do not record their collection; verify]**.
- Decide what General chat means once B6 is verified. Suggested default label: "All collections", searching only the open workspace.
- `/Onboard` becomes available to Owners and Editors of the open workspace **[BE: `can_onboard_datasets` is administrator only]**. Slash commands stay available for experts but are not shown as the main path.

### Collections (computer only)

- Remove the band and the four tiles. Keep title, search, type chips, and "New collection" (shown from the workspace level, fixes A1).
- Cards rather than a six-column table: name, type tag, document count, and one status word (Ready, Reading, Needs attention, Empty). Buttons: Ask, Add documents, and a menu for Edit and Delete.
- Viewers see the same list with Ask only.
- Clicking a collection opens one page with Documents and Field lists. Details are in the menu. Models tab: administrators only, labelled "AI models".
- Type field added to Edit once the API accepts it **[BE, E2]**. Until then, show the tag read-only.
- Bulk move between workspaces: not proposed; would need **[BE, D5]**.

### Quick Extract

- Keep the guided flow. On phone and tablet, it opens directly at the first useful step: skip "Choose where it goes" when the workspace has exactly one collection the person can add to, and when arriving from the first-collection dialog.
- Collection step: type chips above the list when 2 or more types exist.
- Two consent ticks become one, placed before first send. Showing it once per collection per device is frontend only; remembering it across devices needs **[BE]**. Security owner should confirm **[PD-7]**.
- Remove the step-rail note and the "Enlarge" button on phones.
- End screen: "Check the results" (primary), "Add more documents", "Back to chat". Remove "Keep asking on the Dashboard" on touch devices (F3). "Share with your team" only in team workspaces, and it opens Settings > People on a computer (A4).

### Review

- Filter to the open workspace first (B1). Extract gets the same treatment: "All collections" means all in this workspace. Backend filter: **[BE]** needed for `/extract-data` and its export (B2), unless the screen requires a chosen collection, which is the frontend-only fallback.
- Merge into one screen **[PD-8]**: tabs "To check" (today's Review) and "All data" (today's Extract table with export). Until decided, only rename and filter.
- Replace the three dropdowns with one search box and two filters: Collection and Field list. Extraction IDs and version numbers go behind "Details".
- Tiles become one line: "4 to check · 12 checked · 1 failed", each a filter. Orange only on "to check".
- Phone: list becomes cards (document, collection, status). Record view stays as designed in `phone-design.css:53-75`.
- Viewers read but do not see Save. Check this against the API while building.

### Settings

- New Workspace group: **Details** (name, type of workspace, your level, and rename/delete/leave **[BE, D5]**) and **People**.
- People screen, for Owners:
  - One row per person or team: name, level dropdown, Remove. The workspace creator and "Administrators" appear as fixed rows. Creator's identity is not in the response today; **[BE, small]**.
  - Add box: type a name, pick it, pick a level (default Viewer), Add. Each change saves at once with a short "Saved" and "Undo", replacing Save and Reset. This uses the existing `PUT .../members`, which already accepts partial changes.
  - Levels are explained by the dropdown options alone (section 4). Remove the instruction paragraph.
- Non-Owners: read-only list **[BE, D3]**. Until then: "Only owners can see the list of people."
- Personal workspace: no People entry; a single line, "Only you can see this workspace."
- Email invitations: **not supported.** People must already have a Lapi account. Accounts are created by administrators or through company sign-in (`lapi_backend/lapi_app/route_policy.py:57`). Inviting by email needs **[BE]**: invitation records, email sending, a pending state, and an acceptance flow. Until then use the copy in section 4.
- Administration: rename the items (section 4). Model mapping and "Available models" keep technical detail but behind "Advanced". Long OCR and embedding paragraphs (`dataset-workspace.tsx:150,167`) move to a help link.

---

## 4. Exact wording

### Terms

| Today | Use |
|---|---|
| Dataset, Knowledge Source, Knowledge | Collection; documents |
| Add knowledge, Add Collection Knowledge | Add documents |
| Onboard | (removed) |
| Vectorize, Index | Read |
| Indexed, Ready to ask | Ready |
| Processing, Indexing | Reading |
| Reindex required | Needs reading again |
| Failed, Need attention | Needs attention |
| Prompt template, Prompt | Field list **[PD-3]** |
| Extraction | Extracted data |
| Pending review / Reviewed | To check / Checked |
| Agent Model, Model | AI model |
| Authorized collections | Your collections |
| All accessible knowledge | All collections |
| Metadata Relationships | Links between documents |
| Jobs & activity | Activity |
| Model Registration / Enabled models / Model Mapping | AI models / AI models on or off / AI models per collection |
| Users & passwords | People and sign-in |
| Token usage | Usage and cost |
| Files & processing | All files |
| Private pill, "Originals protected. Insights grounded." | (removed) |
| Agent nav "Lapi Agent" | Agent |

### Labels

| Place | Text |
|---|---|
| Switcher, screen reader label | Current workspace |
| Switcher groups | Mine · Shared with me · Other people's |
| Personal workspace row | My workspace |
| Switcher actions | Create a team workspace · Manage this workspace |
| Login question | Which workspace? |
| Row detail | Team · 3 collections · Editor |
| Levels: Viewer | Viewer: can ask and read |
| Levels: Editor | Editor: can also add documents and pull out data |
| Levels: Owner | Owner: can also manage people |
| Remove | Remove from workspace |
| Type field | Type (optional) |
| Type filter | All · Finance · Resume · ... |
| New collection name | Collection name, placeholder "Invoices 2026" |
| Team workspace name | Workspace name, placeholder "Finance team" |
| Composer picker default | All collections |
| Composer placeholder | Ask anything... |
| Tabs | Agent · Quick Extract |
| Add documents choices | From this computer · From cloud storage |
| Review tabs | To check · All data |
| Consent | Lapi sends this to the AI service your organization has set up. OK? |
| Save toast | Saved. Undo |

### Dialog titles and buttons

| Moment | Title | Body | Buttons |
|---|---|---|---|
| Create team workspace | Create a team workspace | (none) | Create · Cancel |
| After creating | Add people | (none) | Done |
| First collection | Create your first collection | (none) | Create · Not now |
| Limit reached (replaces 409 text) | You already have a team workspace | Each person can have one. | OK |
| Switch with unsaved changes | Leave without saving? | (none) | Leave · Stay |
| Remove person | Remove {name}? | They lose access to every collection here. | Remove · Cancel |

### Empty states

Maximum one short line of text and one button.

| Screen and person | Text | Button |
|---|---|---|
| Agent, no collections, can add | No documents here yet. | Add documents |
| Agent, no collections, Viewer | Nothing here yet. The workspace owner adds documents. | (none) |
| Collections, can add | No collections yet. | New collection |
| Collections, Viewer | No collections yet. | (none) |
| Collection with no documents, can add | This collection is empty. | Add documents |
| Collection with no documents, Viewer | This collection is empty. | (none) |
| Type filter no result | No collections of this type. | Show all |
| Search no result | Nothing found. | Clear search |
| Dashboard, empty workspace, can add | Start by creating a collection. | New collection |
| Dashboard, Viewer | Nothing here yet. | (none) |
| Quick Extract, Viewer | (tab hidden) | |
| Review "To check" | Nothing to check. | Extract data (when allowed) |
| Review "All data" | No extracted data yet. | Extract data (when allowed) |
| Field lists | No field lists yet. | New field list |
| People, only owner | Only you so far. | Add people |
| People, person not listed | Don't see someone? They need a Lapi account first. Ask your administrator. | (none) |
| Personal workspace | Only you can see this workspace. | (none) |
| Avatar sheet, phone | Open Lapi on a computer to manage people and settings. | (none) |

---

## 5. Prioritized steps

Each can ship alone. S is under a day, M is a few days, L is larger. Coordinate with the engineer holding uncommitted changes in these files.

### First: broken or misleading

1. **S** Show "New collection" and Delete by workspace level, not role (A1). `page.tsx`, `dataset-workspace.tsx`.
2. **S** Correct empty states and "assigned" wording (A5). Section 4 copy.
3. **S** Hide "Share with your team" in personal workspaces (A4).
4. **S** Pass the new collection into Quick start, skip its first step (C2).
5. **S** Remember the workspace choice per login and "Not now" per workspace (C3, C4).
6. **S** Add the unsaved-changes check when switching; leave Review on switch (B5).
7. **M** Filter Review, field lists and Extract to the open workspace on the frontend (B1, B2 fallback). Label fixes for B4.
8. **Backend review** Organization workspace owner and access (D6), counts per person.

### Second: owner's stated wishes

9. **S** Phone: remove "More" and the drawer once **[PD-1]** is settled; hide the bar for Viewers (F1, F4).
10. **M** Phone: one chrome row. Move collection into the composer chip and model/info into a sheet (F2).
11. **S** Text tokens for chat and tab labels (F6).
12. **M** Consolidate to one token set across gate, Quick start and Agent, then other screens (F7).
13. **S** Stop auto-opening tour, set-up questions, training cards; add Help in the avatar menu (C1, **[PD-6]**).
14. **S** Remove the page bands and "Step n of 4" (G5).
15. **S** Terms pass: navigation and buttons first. Keep route IDs unchanged (`page.tsx:127-129`).
16. **S** Touch-device copy that mentions the Dashboard (F3).
17. **S** Agent: one New chat button, collapsible rail, remove Context panel (G6).

### Third: structure

18. **M** Real switcher menu with groups and search; focus trap on gate dialogs (D1, C5, C6).
19. **S** Type chips on Collections, case-insensitive grouping (E1, E3).
20. **M** Settings > Workspace > People with instant save; remove the collection Members tab (D2, A3, gated on **[PD-5]**).
21. **M** Flatten the nav; move Add documents and Field lists (section 2).
22. **M** Collections cards, single collection page.
23. **M** Dashboard reduced to overview, per **[PD-2]** (G3, G4).
24. **M** Review: new filters, one-line summary, phone cards (F5). Tabs merge per **[PD-8]** (G2).
25. **S** Settings renames and "Advanced" for model detail.

### Backend items, in suggested order

| Item | Size | For |
|---|---|---|
| Accept `collection_type` on `PATCH /api/datasets/{id}` | S | E2 |
| `can_onboard_datasets` based on workspace level | S | A2 |
| Workspace owner name in `/api/workspaces` and members response | S | Settings, switcher |
| Per-person collection counts | S | D6 |
| `workspace_id` filter on `/api/extract-data`, export, `/api/extractions`, `/api/templates` | M | B1, B2 |
| Conversations by workspace | M | B3 |
| Read-only members list for all members | S | D3 |
| Rename, delete, leave, transfer workspace | M | D5 |
| Move a collection between workspaces (grants must be rewritten) | M | D5 |
| Limit the directory, or search by exact name | S to M | D4 |
| Remember last workspace and consent on the server | S | Across devices |
| Email invitations | L | Section 3 |

---

## 6. Product decisions needed

| ID | Decision | Recommendation |
|---|---|---|
| PD-1 | Do administrators and people with screen grants also lose "More" on phones? The Enabled models page intends phone use (`page-band.tsx:13`). | Yes for everyone, as the owner stated. If administrators need it on phones, keep one route: Avatar > AI models on or off. |
| PD-2 | Does the Dashboard keep its own chat? | No. Dashboard ask box opens the Agent with the question. Check first that Agent covers multi-collection and per-document selection (`dataset-knowledge-picker.tsx`), which Dashboard chat offers. |
| PD-3 | Layman name for "prompt template". | "Field list". Alternatives: "Template", "Form". |
| PD-4 | May any team workspace owner see all usernames? | No: search by full username or email only. Needs backend work. |
| PD-5 | What is the Organization workspace long term? It conflicts with "members see every collection". | Convert shared collections into real team workspaces with an administrator migration, then retire it. Until then, label it "Older shared collections". |
| PD-6 | Remove auto-opening of tour and training? | Yes, opt-in only. Possible legal or onboarding reasons to keep a first-use notice should be checked. |
| PD-7 | May AI consent be remembered instead of asked each time? | Yes, per collection, if compliance agrees. |
| PD-8 | Merge Extract and Review? | Yes, into "Review" with two tabs. Owner's stated "Quick Extract" name stays on touch devices. |
| PD-9 | Should workspace creation be available on phones? | No, computer only, as drafted. |
| PD-10 | Fixed list of types or free text? Today free text with suggestions. | Keep free text, with suggestions drawn from types already in the workspace. |

---

## 7. Not checked

Nothing was run: this comes from reading code only, with no live screens. Not verified: General chat scope and Agent state on switching (B6), Viewer controls in Review, delete permissions (`lapi_backend/lapi_app/dataset_lifecycle.py`), and whether conversations record a collection. Test on a real phone, foldable and tablet before finalising sizes in section 2.
