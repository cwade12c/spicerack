---
name: harvest
description: Reduce a large diff between two diverged refs (a fork and its upstream, or two long-lived branches) to a ledger of features a human can read, interrogate, and pick from, then land the picks on the base by cherry-pick, rework, or rebuild.
argument-hint: "<base-ref> <head-ref> [fresh], e.g. upstream/main origin/main"
disable-model-invocation: true
license: MIT
compatibility: Requires git and python3 (standard library only), with shell access. Built for Claude Code; runs in any agent that supports Agent Skills.
---

# Harvest

Two refs have diverged by more code than anyone will review: a fork and its upstream, or a long-lived branch and `main`. Harvest compares refs, so where they live does not matter; a fork is just a remote. **Base** is the ref receiving the work, **head** is the ref carrying it. Harvest turns the diff into a **ledger**: one bullet per **feature**, written for a human. The human reads the ledger, interrogates the bullets they care about, and picks which features to bring to base. You do the code work; the human makes every choice.

The **yardstick** is base's own stated rules and vision: `CONTRIBUTING*`, `AGENTS.md` / `CLAUDE.md`, ADRs, a glossary, the README's stated scope, and the shape of the existing code. Every judgement of fit is made against the yardstick, citing the line it rests on. Head may also carry its own **head rules** on what may be sent to base (a fork's contribution notes, a `CLAUDE.local.md`); read them too, and cite them separately from fit.

The **tree diff** `git diff merge-base head` is the source of truth for what head adds; commits only guide you to it. **Ownership** is line-level: each line the tree diff adds is blamed (`git blame merge-base..head`, merges included) to the head commit that wrote it, and the entry owning that commit, or the part of it under some paths or line ranges, owns the line. [`scripts/ledger_check.py`](scripts/ledger_check.py), in this skill (`<skill-dir>` below is the folder holding this file), computes both; run it rather than reasoning about blame by eye.

## 1. Fix the points

Run everything inside the repository holding both refs; if the working directory isn't one, find the repository whose remotes resolve both, and ask if several do. Resolve **base** and **head** from the arguments (ask if absent). Fetch both; if you can't, record `not fetched` and each ref's commit date in the ledger header. Compute `git merge-base base head`, and read the yardstick from **base**, so you judge against it as it stands today.

Set aside work base already has, in three passes:

1. `git log --cherry-pick --right-only --no-merges base...head` drops commits with a patch-equivalent on base.
2. `python3 <skill-dir>/scripts/ledger_check.py survivors base head` lists every commit that owns no tree-diff line base lacks. Set aside the ones it marks `on-base`. A `superseded` commit was rewritten by head itself: give it to the entry of the commit that rewrote it, found among the later commits the script lists. A `content-free` merge goes in the header's list of content-free merges.
3. Work rebuilt onto base and merged back into head lands below the merge-base, and often on a merge's second parent, so read every merge on base back past the oldest head commit's date (`git log --merges --format='%h %p %s' --since=<date> base`), and set aside any head work it covers that passes 1 and 2 missed.

Record each set-aside item in the ledger as an entry `### S<n>. <title>` with `Status: landed: already on base`, its commits, and the evidence in base's tree in its `Notes:`. List base merges that brought head-authored work in below the merge-base as `not in range`, so the human sees they were checked.

The ledger lives at `$(git rev-parse --git-common-dir)/harvest/<head>.md`, with every `/` in the head ref replaced by `-` (`origin/main` → `origin-main.md`): inside `.git`, so it persists across sessions without touching the tree. Its ownership map is the sidecar `<head>.owners.json` beside it, in the format `scripts/ledger_check.py` documents.

If the ledger already exists, tell the human plainly that earlier state was found: the ledger path, its header's `Updated:` time (or, if it has none, the latest date in the header and the file's modification time), the head SHA it was built from, how many feature entries (not counting `Plumbing`, `Head-only`, or set-aside items) are open, picked, left, or landed, and for each `landed: <branch>`, whether that branch still exists. Then offer the choice:

- **resume**: load the ledger, ledger only the commits head gained since the head SHA in its header, re-run the set-aside check against today's base, confirm every `landed: <branch>` branch still exists and still sits on today's base (report any that don't), and continue from the first step below whose done-check fails. Keep every existing status and note. A new commit assigned to a `landed` entry is missing from its branch: report it, and offer to land it on top.
- **fresh**: overwrite the ledger and its sidecar and start from step 2, discarding every earlier pick and note.

Wait for the human's answer. A `fresh` argument is that answer given up front: report the earlier state you are overwriting, then start fresh. When resuming, mark every entry, status, and note carried over from the earlier ledger `(earlier)` whenever you present it, and every entry built from new commits, or given one, `(new: <commits>)`, so earlier state is never mistaken for fresh findings.

Done when you can state base, head, merge-base SHA, commit count, files changed, the commits set aside and by which pass, and the yardstick documents and head rules you read.

## 2. Build the ledger

Read every commit message, and every hunk under base's source roots that isn't a test. For tests, docs, tools, and generated files, read enough to attribute each to a feature. Group the commits into features by **intent**: what a user or maintainer would say the change is _for_, not which files it touches. A commit that serves two features is split between them in the sidecar by path, or by head line range within a file. A single line serving two entries goes to the one whose commit wrote it; name it in the other entry's `Depends on:` as a line to edit if they land apart. Removed lines are assigned one owner per file, by judgement; landing re-derives them from the picked commits. Changes with no user-facing intent (formatting, dependency bumps, CI, renames) go in a single `Plumbing` entry. Work head rules forbid on base (fork docs and plans, deployment config, the fork's own persona or branding) goes in a single `Head-only` entry, offered only if the human asks; work head merely hasn't proposed yet stays a feature, with the head rule cited in its fit.

Write the ledger to its path from step 1. Its header records base, head, merge-base, the base and head SHAs it was built from, an `Updated:` time rewritten on every save, the content-free merges, and which files were read in full versus only attributed. Write each header field as one `Key: value` line, with `Base:` and `Head:` as `<ref> @ <sha>` (`Base: upstream/main @ 4be19e2`). A ledger reviewed on the review page also carries `Report: round <N> ingested <date>`. Then one entry per feature:

```markdown
### F3. Retry failed webhook deliveries with backoff

Webhooks that fail are retried up to 5 times with exponential backoff, instead of being dropped.
Why: <head's reason, from commit messages or code comments; "unstated" if none>

- Size: +240 / -12 across 6 files
- Commits: a1b2c3d, e4f5a6b (partial: src/webhooks/queue.py)
- Files: 6 (2 shared). Source: src/webhooks/retry.py (new), src/webhooks/queue.py (shared with F1)
- Depends on: F1 (adds `_retry_delay` to F1's queue)
- Fit: tension. Adds a background thread; ADR-004 says the worker is single-threaded.
- Status: open
- Notes:
  - 2026-10-09 Q: Why a thread and not the job queue? A: <answer, citing file:line>
  - 2026-10-09 Note: <something the human said worth keeping>
```

**Files** gives the count and only the non-test source files; the sidecar holds the full list. **Fit** starts with `aligned`, `tension`, or `conflict`, followed by the yardstick line it cites. **Depends on** lists entry ids first, each named on its own (`F2, F3, F4`, not `F2-F4`) and optionally followed by its reason in parentheses; it is `none` when there are none. Further prose goes after a `;`, and a dependency the human agreed to cut is recorded there as `cut: <how>`. It also names any code this entry adds inside another entry's files, so landing in another order knows to carry it. **Status** starts `open`, becomes `picked: <mode>, batch: <name>` or `left` in step 3, and `landed: <branch>` in step 4. **Notes** holds dated sub-bullets, a question with its answer on one `Q:` line; a question asked on the review page keeps its id, as `Q (r1.q2):` or `Note (r1.q3):`.

The `Plumbing` and `Head-only` entries use the same template, headed `### Plumbing. <title>` and `### Head-only. <title>`.

Then run the **coverage check**: `python3 <skill-dir>/scripts/ledger_check.py coverage base head <head>.owners.json`. It confirms every added line is owned by exactly one entry, every commit is owned, set aside, or content-free, every set-aside commit owns only lines base already has, every file's removed lines have one owner, and every claim in the sidecar owns something. The check proves the ownership map is complete and consistent; whether the commits are grouped by the right intent is yours to judge, and the human's to interrogate.

Done when the coverage check exits 0 and every entry has its title, description, `Why:` line, and the six required bullets.

Present the ledger to the human as a table: title, one-line description, fit, and dependencies, ordered by dependency so features come before the ones that build on them, with `Plumbing` and `Head-only` last. The full entries stay in the ledger file.

After the table, ask how the human wants to review, and wait for the answer. Use your multiple-choice question tool if you have one, with the same question and two options, the review page first and marked recommended. Otherwise end your message with this, where `<N>` is the number of feature entries:

```markdown
### How do you want to review these <N> features?

1. **Review page**: mark all <N> in your browser, ask questions as you go, and send the round back in one paste.
2. **Chat**: question and pick entries here, one at a time.

Reply 1 or 2.
```

For the review page, read [references/REPORT.md](references/REPORT.md). For chat, carry on with step 3.

## 3. Interrogate

The human now drives. They will ask you to elaborate a bullet, show its hunks, defend or question a design choice, compare it with how base would do it, or check it against the yardstick. Answer from the code, citing file and line, and keep head's reasoning separate from your own opinion. Record each question and its answer in the entry's `Notes:`. If the human asks to review on a page, or pastes a block starting `Harvest responses, round`, read [references/REPORT.md](references/REPORT.md). When an answer changes the picture (a feature splits, a hidden dependency surfaces, ownership was wrong, fit changes) update the entry and sidecar on the spot and re-run the coverage check.

The human closes this step by marking each picked feature with a **landing mode**:

- **cherry-pick**: bring head's code over as written.
- **rework**: keep the intent, refactor the code into a design that fits the yardstick.
- **rebuild**: turn the intent into an implementation brief, add the enhancements the human asks for, and implement from scratch.

Then ask how the picks should be **batched**: one branch per feature (the default, so each lands as one reviewable intent), or named batches the human groups by hand. Propose each batch's branch name (`harvest/` plus the batch name, or for a one-feature batch, the first four words of its title, lowercased and hyphenated) in the same question, and record each picked entry's batch in its Status line, e.g. `picked: rework, batch: webhooks`.

Done when every entry's status is `picked: <mode>, batch: <name>`, `landed: <branch>`, or `left`, and every picked feature's dependencies are also picked or landed (or the human has said how to cut the dependency).

## 4. Land

Read [references/LANDING.md](references/LANDING.md), then land the picked features one at a time, in dependency order, onto the batch branches the human chose. Confirm before pushing anything or opening a PR.

Done when every picked entry is `landed: <branch>` and has passed LANDING.md's done-checks.
