# responses.json (schema `harvest-responses/1`)

Written by the report page, read by the agent. It records what the human decided and asked in one
round. It never replaces the ledger: the agent ingests it into the ledger (see `ingest.md`) and the
ledger stays the single source of truth.

`render_report.py check responses.json <ledger>` validates this shape and compares it with the
current ledger.

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

## Fields

| Field | Type | Meaning |
|---|---|---|
| `schema` | string, required | Always `harvest-responses/1`. Bump the number on a breaking change. |
| `round` | integer ≥ 1, required | Round of this page. A page is round `ingested + 1`, where `ingested` is the ledger header's `Report:` line (0 if absent). |
| `created` | ISO-8601 string, required | When this file was produced. Informational. |
| `ledger.sha256` | 64 hex, required | SHA-256 of the ledger file's bytes when the page was rendered. |
| `ledger.name`, `head`, `head_sha`, `base`, `base_sha`, `updated` | strings, required | The ledger header as rendered. `head_sha` changes when `resume` pulls in new commits. |
| `entries` | object, required | Keyed by entry id (`F3`, `S1`, `Plumbing`, `Head-only`). Only entries the human touched appear. |
| `entries.<id>.title` | string, required | Title as rendered. Lets the agent tell a renamed or renumbered entry from the same one. |
| `entries.<id>.status` | string, required | The ledger's `Status:` value as rendered. Lets the agent see the ledger moved on (for example landed in chat) after the page was made. |
| `entries.<id>.mode` | `cherry-pick` \| `rework` \| `rebuild` \| `left` \| `open`, optional | Present only when the human changed the entry's mark. `open` means "undo the pick". Absent means "keep the ledger's status". Never present for an entry whose status is `landed`. |
| `entries.<id>.batch` | string \| null, optional | Present with a pick mode. `null` means the default batch, one branch per feature. A string is a batch name. |
| `entries.<id>.cuts` | array of `{dep, how}`, optional | The human picked this entry while `dep` is not picked or landed, and says how to cut the dependency. |
| `entries.<id>.comments` | array, optional | Questions and notes in the order written. Each has `id` (`r<round>.q<n>`, unique within the file), `kind` (`question` or `note`), `text`, and `created`. |
| `general_notes` | string, required (may be empty) | Notes that belong to no entry. |

Derived data is deliberately absent: the page does not export batch groupings, warning lists or
counts. The agent derives them from the entries, so there is only one thing to keep consistent.

## Rules

- A comment id is `r<round>.q<n>`; the answer in the ledger's `Notes:` carries the same id, which is
  how the page matches questions to answers in later rounds.
- A file with `round` ≤ the ledger's ingested round is stale. A file whose `ledger.sha256` differs
  from the current ledger is not necessarily stale (the agent edits the ledger between rounds); the
  per-entry `title` and `status` say whether each entry can still be applied. See `ingest.md`.
- Unknown extra keys are ignored by the agent and preserved by nobody.
