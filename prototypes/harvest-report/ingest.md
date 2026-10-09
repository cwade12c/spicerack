# Ingesting a responses file

Load this when the human gives you a `responses.json` (a path, or pasted JSON) from the report
page. The ledger stays the source of truth: everything in the file ends up as ledger text, and the
file is then spent.

## 1. Check before you touch anything

Save pasted JSON beside the ledger as `<head>.responses-r<round>.json`, then run:

```
python3 <skill-dir>/scripts/render_report.py check <responses.json> <ledger>
```

It validates the shape and compares the file with the ledger. Read its output and decide:

| Output | Meaning | Do |
|---|---|---|
| `STALE: responses round N …` | This round is already ingested. | Stop. Tell the human, and ask whether they meant a newer file. |
| `GAP: … an earlier round is missing` | Round N-1 was never ingested. | Ask for it, or ask to proceed without. Do not guess. |
| `HEAD CHANGED` | `resume` ran between render and now. | Continue; entries are compared one by one below. Tell the human which entries changed because of the new commits. |
| `LEDGER CHANGED` | The ledger was edited since render (chat edits, a landing). | Continue; per-entry lines say what moved. |
| `MISSING ENTRY <id>` | The entry was split, merged, renumbered or dropped. | Do not apply that entry. List its marks, questions and notes to the human, and ask where they belong. |
| `TITLE CHANGED <id>` | Same id, different feature. | Ask before applying. |
| `STATUS CHANGED <id>` | The ledger status moved since render (for example it landed). | Apply questions and notes. Do not apply `mode` or `batch`; show the human both and ask. |
| `DEPENDENCY <id> is picked but needs <dep>` | A pick whose dependency is not picked, landed or cut. Advisory: exit stays 0. | Apply the marks anyway, then ask the human how to cut it or whether to pick the dependency. |
| `LANDED <id>` | Marked something that already landed. | Skip the mark, keep the comments. |
| schema errors | The file is malformed. | Report the lines. Do not repair it by hand. |

Exit 0 means nothing to resolve. Report every conflict in one message, once, before applying anything.

## 2. Apply each entry

Work in `entries` order. Make every ledger edit with the entry's other lines untouched.

**Marks → `Status:`**

| `mode` | Write |
|---|---|
| `cherry-pick`, `rework`, `rebuild` | `Status: picked: <mode>, batch: <batch>` |
| `left` | `Status: left` |
| `open` | `Status: open` |
| absent | leave `Status:` as it is |

`<batch>` is `batch` when it is a string. When it is `null`, or the entry was already picked and
`batch` is absent, use the existing batch, else the default: the first four words of the title,
lowercased, hyphenated (`harvest/` plus that is the branch). Two entries with the same batch name
share a branch.

**Comments → `Notes:`.** For each comment, append a sub-bullet under the entry's `Notes:` bullet
(create the bullet if missing), dated today:

```
- Notes:
  - 2026-10-09 Q (r1.q2): <question text as written> A: <your answer, with file:line>
  - 2026-10-09 Note (r1.q3): <note text as written>
```

A `question` becomes a `Q (r<round>.q<n>)` line and is answered in the same line (step 3). A `note`
becomes a `Note (r<round>.q<n>)` line. Keep the human's words; do not paraphrase. Keep earlier
`Notes:` lines as they are.

**Cuts.** A `cuts` item means the human accepts picking the entry without the dependency. Add to the
entry's `Depends on:` line `; cut: <how>` after the dependency's text, and add a `Note` line recording
the human's words. Landing reads the cut when it orders work.

**Dependencies.** After applying, recheck step 3's done-condition: every picked entry's
dependencies are picked, landed, or cut. List the ones that are not. Do not "fix" them by picking
the dependency yourself.

**General notes.** Add each as a line under the ledger header: `Note (r<round>): <text>`. Act on
anything in it that is an instruction (an ordering preference, an entry to skip) and say what you
did.

## 3. Answer every question, in one pass

Answer each `question` from the code, citing file and line, exactly as step 3 of SKILL.md asks, and
keep head's reasoning separate from your own opinion. If an answer changes the picture (a feature
splits, a hidden dependency surfaces, ownership was wrong, fit changes) update the entry and the
sidecar and re-run the coverage check, then say so at the top of your reply rather than burying it in
a note. An answer you cannot give yet is written as `A: pending (<what you need>)`.

Do all answers before replying. The point of a round is that the human reads them together.

## 4. Close the round

1. Set the header's `Updated:` to now and add or update the line `Report: round <N> ingested <date>`.
2. Re-run `render_report.py render <ledger> --responses <responses.json> -o <report.html>` so the
   next page is round N+1 with the answers inline, and tell the human where the file is.
3. Reply with: counts (picked, left, open), the batches as the agent will land them, conflicts and what
   you did about each, every answer in short form (the full text is in the ledger), and anything from
   the answers that needs a decision. Follow-ups that are not worth a round go straight to chat.

Do not delete the responses file. It is the record of what the human asked.
