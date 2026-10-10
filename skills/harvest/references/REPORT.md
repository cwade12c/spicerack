# Review page

The review page is an optional way to run step 3 in batches. You render the ledger as one offline HTML page. On it, the human marks every entry, asks questions and writes notes, then sends the whole round back in one paste. You ingest that into the ledger, answer every question in one pass, and render the next round with the answers inline. Chat still handles follow-ups and anything that reshapes the ledger; the page handles the broad pass.

The ledger stays the single source of truth. The page is generated from it by a fixed template and never edits it; it produces a separate responses file, which you apply to the ledger and then keep as the record of what was asked. Never hand-write or edit the page's HTML.

## When to offer it

Step 2 of SKILL.md ends by asking the human whether to review on the page or in chat; you are here because they chose the page. Render it whenever they ask for it later, too. If they chose chat, don't offer it again. A session that never uses the page runs exactly as SKILL.md describes.

## 1. Render

```
python3 <skill-dir>/scripts/report.py render <ledger>
```

It writes `<head>.report-r<round>.html` beside the ledger, using `<skill-dir>/assets/report-template.html`. The round is one more than the ledger's `Report: round <N> ingested <date>` header line, or 1 without it. From round 2 on, add `--responses <head>.responses-r<N>.json`, the previous round's file, so questions the ledger has not answered yet still show.

The script prints every parse warning, and the page shows them in a banner. Each names a line that breaks a ledger format rule in SKILL.md (header keys, entry headings, `S<n>` set-aside entries, `Fit:`, `Depends on:`, `Notes:`). Fix those lines in the ledger, re-render, and tell the human what you changed. A warning you cannot fix without a judgement call goes to the human instead.

## 2. Deliver

The page is a file on your machine; the human may be somewhere else.

- If the human can open files on this machine, give them the full path and offer to open it in their default browser (`xdg-open` on Linux, `open` on macOS, `start` on Windows). Open it only if they say yes.
- In a cloud or remote session, send them the file itself with whatever file delivery the environment offers, and tell them to open it in a browser. If you can't tell which case you're in, ask.
- Publish the page somewhere hosted only when the human asks for that: it summarises unreleased work.

Either way, tell them how a round works: decide each entry with the buttons or `1` `2` `3` `X`, ask questions with `C`, then press **Finish round** and **Copy responses**, and paste the result into this chat. The page can't reach this session by itself; the paste is the hand-back. The draft is kept in that browser's storage between visits. Verified in Chromium and Firefox, desktop and phone-sized; Safari is untested.

## 3. Receive

The paste starts with a line like `Harvest responses, round 1 (origin-main.md): 7 picked, 3 left, 3 questions, 1 dependency to cut.`, followed by a fenced JSON block. The human may instead give you a downloaded `responses-r<N>.json`, or a file the page keeps in sync. Save pasted JSON beside the ledger as `<head>.responses-r<round>.json`.

## 4. Check before you touch anything

```
python3 <skill-dir>/scripts/report.py check <head>.responses-r<round>.json <ledger>
```

It validates the file and compares it with the ledger. Exit 0 means it is safe to apply; exit 1 means at least one line below must be resolved first. Report every finding in one message, once, before applying anything.

| Output | Meaning | Do |
|---|---|---|
| `STALE: responses round N …` | This round is already ingested. | Stop. Tell the human, and ask whether they meant a newer file. |
| `GAP: … an earlier round is missing` | Round N-1 was never ingested. | Ask for it, or ask to proceed without it. Do not guess. |
| `HEAD CHANGED` | `resume` ran between render and now. | Continue; entries are compared one by one. Tell the human which entries changed because of the new commits. |
| `LEDGER CHANGED` (advisory) | The ledger was edited since render (chat edits, a landing). | Continue; the per-entry lines say what moved. |
| `MISSING ENTRY <id>` | The entry was split, merged, renumbered or dropped. | Do not apply it. List its marks, questions and notes to the human, and ask where they belong. |
| `TITLE CHANGED <id>` | Same id, different feature. | Ask before applying. |
| `STATUS CHANGED <id>` | The entry's status moved since render, for example it landed. | Apply its questions and notes. Do not apply `mode` or `batch`; show the human both and ask. |
| `LANDED <id>` | A mark on something that already landed. | Skip the mark, keep the comments. |
| `STALE CUT <id>→<dep>` (advisory) | A cut whose dependency is picked or landed once this file is applied. | Drop the cut, as in section 5. |
| `DEPENDENCY <id> is picked but needs <dep>` (advisory) | A pick whose dependency is not picked, landed or cut. | Apply the marks, then ask the human how to cut it or whether to pick the dependency. |
| `SCHEMA` and its lines | The file is malformed. | Report the lines. Do not repair the file by hand. |

## 5. Apply each entry

Work in `entries` order, and leave each entry's other lines untouched.

**Marks → `Status:`**

| `mode` | Write |
|---|---|
| `cherry-pick`, `rework`, `rebuild` | `Status: picked: <mode>, batch: <batch>` |
| `left` | `Status: left` |
| `open` | `Status: open` |
| absent | leave `Status:` as it is |

`<batch>` is `batch` when it is a string. When it is `null`, or the entry was already picked and `batch` is absent, keep the existing batch, else use the default from step 3 of SKILL.md: the first four words of the title, lowercased and hyphenated. Two entries with the same batch name share a branch.

**Comments → `Notes:`.** Append each comment as a sub-bullet under the entry's `Notes:` bullet (create it if missing), dated today, in the human's words:

```
- Notes:
  - 2026-10-09 Q (r1.q2): <question as written> A: <your answer, citing file:line>
  - 2026-10-09 Note (r1.q3): <note as written>
```

The id is what lets the next page put the answer under its question. Keep earlier `Notes:` lines as they are.

**Cuts.** A `cuts` item `{dep, how}` sets how the entry lands without `dep`. If the entry's `Depends on:` line already has a `cut <dep>:` clause, replace its text; otherwise append `; cut <dep>: <how>` at the end of the line, after its ids and any prose. Keep cut clauses last, write the how on one line, and change any `;` in it to `,`. Add a `Note` line with the human's words. Landing reads the cut when it orders work, and the next page shows the dependency as cut.

**Stale cuts.** A cut whose dependency is now picked or landed no longer applies, whether the pick came from this file or from chat. Delete its `cut <dep>:` clause and add a `Note` saying so; `check` lists each one as `STALE CUT`. A cut on an entry that is no longer picked stays, in case it is picked again.

**General notes.** Add each as a header line `Note (r<round>): <text>`. Act on anything in it that is an instruction (an ordering preference, an entry to skip) and say what you did.

**Dependencies.** After applying, recheck step 3's done-condition: every picked entry's dependencies are picked, landed, or cut. List the ones that are not. Do not fix them by picking the dependency yourself.

## 6. Answer every question, in one pass

Answer each `question` from the code, citing file and line, as step 3 of SKILL.md asks, and keep head's reasoning separate from your own opinion. If an answer changes the picture (a feature splits, a hidden dependency surfaces, ownership was wrong, fit changes), update the entry and the sidecar, re-run the coverage check, and say so at the top of your reply. An answer you cannot give yet is written as `A: pending (<what you need>)`.

Write every answer before replying: the point of a round is that the human reads them together.

## 7. Close the round

1. Set the header's `Updated:` to now, and add or update `Report: round <N> ingested <date>`.
2. Render round N+1 with `--responses <the file you just applied>` and deliver it as in section 2.
3. Reply with the counts (picked, left, open), the batches in landing order, each `check` finding and what you did about it, every answer in short form (the full text is in the ledger), and anything from the answers that needs a decision. Follow-ups too small for a round go straight to chat.

Keep the responses file: it is the record of what the human asked.

## The responses file

Schema `harvest-responses/1`, written by the page and read by `check` and by you:

```json
{
  "schema": "harvest-responses/1",
  "round": 1,
  "created": "2026-10-09T04:55:31.552Z",
  "ledger": {
    "name": "origin-main.md",
    "sha256": "96e8f5957b…(64 hex)",
    "head": "origin/main",   "head_sha": "8c1d2e0",
    "base": "upstream/main", "base_sha": "4be19e2",
    "updated": "2026-10-02 16:40"
  },
  "entries": {
    "F5": {
      "title": "Dead-letter queue for exhausted retries",
      "status": "open",
      "mode": "rebuild",
      "batch": null,
      "cuts": [{"dep": "F4", "how": "land with a manual retry hook"}],
      "comments": [
        {"id": "r1.q2", "kind": "question", "text": "Shares the job table's retention?", "created": "2026-10-09T04:55:30.137Z"},
        {"id": "r1.q3", "kind": "note",     "text": "Manual retry hook is fine.",       "created": "2026-10-09T04:55:30.253Z"}
      ]
    }
  },
  "general_notes": "Land storage before anything that reads the job table."
}
```

| Field | Type | Meaning |
|---|---|---|
| `schema` | string, required | Always `harvest-responses/1`. |
| `round` | integer ≥ 1, required | The page's round: the ledger's ingested round plus one. |
| `created` | ISO-8601 string, required | When the file was produced. Informational. |
| `ledger.sha256` | 64 hex, required | SHA-256 of the ledger file when the page was rendered. |
| `ledger.name`, `head`, `head_sha`, `base`, `base_sha`, `updated` | strings, required | The ledger header as rendered. `head_sha` changes when `resume` pulls in new commits. |
| `entries` | object, required | Keyed by entry id (`F3`, `S1`, `Plumbing`, `Head-only`). Only entries the human touched appear. |
| `entries.<id>.title` | string, required | The title as rendered, so a renamed or renumbered entry shows. |
| `entries.<id>.status` | string, required | The ledger's `Status:` value as rendered, so a status that moved since shows. |
| `entries.<id>.mode` | `cherry-pick` \| `rework` \| `rebuild` \| `left` \| `open`, optional | Present only when the human changed the mark. `open` undoes a pick. Absent means keep the ledger's status. Never present on a landed entry. |
| `entries.<id>.batch` | string \| null, optional | With a pick mode: a batch name, or `null` for the default (one branch per feature). |
| `entries.<id>.cuts` | array of `{dep, how}`, optional | Each sets how the entry lands without `dep`: a new cut, or new text for a cut the ledger already has. A cut that matches the ledger's is not repeated. |
| `entries.<id>.comments` | array, optional | In the order written. Each has `id` (`r<round>.q<n>`, unique in the file), `kind` (`question` or `note`), `text`, and `created`. |
| `general_notes` | string, required (may be empty) | Notes that belong to no entry. |

The file carries no derived data (batch groupings, warnings, counts): derive them from the entries, so there is one thing to keep consistent. A file with `round` at or below the ledger's ingested round is stale. A changed `ledger.sha256` alone is not: you edit the ledger between rounds, and each entry's `title` and `status` say whether it still applies. Ignore unknown keys.

## Limits

- Verified in current Chromium and Firefox (desktop, and a 390 px phone viewport). Not verified: Safari, screen readers, and the real file-sync picker (Chromium only; it rewrites a chosen file on every change).
- The page reads only the ledger, so it cites `store.py:22` but cannot show the hunk. Show hunks in chat.
- The dependency map does not route long edges around rows; selecting an entry dims everything off its chain.
