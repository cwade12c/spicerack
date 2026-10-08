# Landing

Each batch is one branch off base, named `harvest/<batch-name>` as agreed in step 3. Land batches in dependency order; a batch that depends on a feature in another batch branches off that batch's branch instead. Within a batch, cherry-pick in head's commit order across all its features: head's order already respects their dependencies, and following it avoids resolving the same lines twice.

Commit as the human, or as head rules say. When a commit carries work whose head author differs from the committer, add a `Co-authored-by:` trailer for the head author.

## cherry-pick

1. `git cherry-pick -x` the batch's whole commits, in head's order.
2. For a commit the sidecar splits, apply only the batch's paths or line ranges: `git show <sha> -- <paths> | git apply --3way`, then trim any line range, and edit any mixed line a `Depends on:` names, by hand; list each as an edit.
3. Resolve conflicts as a merge. For each one, tell the human where the conflicting lines come from (base's changes since the merge-base, base work head merged after this commit was written, or another ledger entry whose code this commit was written on top of), what head changed, and your proposed resolution. Ask when the two intents genuinely compete; resolve the mechanical ones yourself and list them.
4. Search the batch's diff for names from entries outside the batch (their symbols, settings, glossary terms, and prose mentioning them) and cut or reword each. Search too for references only true in head's tree: mutation-waiver ids, line numbers, counts of policies or settings. Re-verify or cut each. Test fixture labels that merely reuse a word may stay; list them.
5. Commit the edits from step 4 separately, after the batch's commits, each titled as an edit, so the cherry-picks stay traceable to head. Keep head's original messages on the cherry-picks, adjusted only where a resolution changed what the commit does.

## rework

1. Restate the feature's intent in one paragraph and list the yardstick lines head's version sits in tension with. Propose the reworked design and get the human's agreement before writing code.
2. Write the reworked version on the batch branch, using head's code as reference for behaviour and edge cases, and porting head's tests to pin that behaviour.

## rebuild

1. Write an implementation brief and save it beside the ledger as `<head>.briefs/<batch>.md`. It holds the intent, the behaviour to preserve (drawn from head's code and tests), the enhancements the human asked for, the yardstick constraints, and the **acceptance test**: the behaviour, driven through base's public surface, that fails on base and must pass on the branch. For each acceptance case, name the code path it reaches; a case the public surface can't make fail belongs in unit tests instead. Leave out head's file layout and code; settings and persona fields are public surface and keep head's names unless the human renames them.
2. Show the brief to the human and revise until they approve it.
3. Hand the brief to a fresh subagent that has not read head's code, and have it implement test-first from the brief alone, in a clone that holds only base, so head's code is out of reach rather than off limits: `git init <dir> && git -C <dir> fetch <repo> <base>:refs/heads/harvest/<batch> && git -C <dir> checkout harvest/<batch>`. Fetch the finished branch back into the repository. If no subagent is available, implement it yourself and say in the batch report that the implementer had read head's code.

## Done

A batch is landed when, on its branch:

- base's tests, linters, and type checks pass;
- each feature's intent holds, shown by a test that drives the feature through base's public surface (a setting, a command, a message in) and fails on base **by assertion**, not by import or collection error, then passes on the branch **deterministically**: seed or fix every random draw it depends on. Run the base side in a separate worktree of base with its own environment, never the branch's, and say whether each run took the happy path (no exceptions logged) or why errors are expected;
- the branch contains only this batch's work. For cherry-pick, `python3 <skill-dir>/scripts/ledger_check.py batch base <branch> <the batch's head commits> <the branch's edit and test commits>` lists every added line none of those commits wrote; each must be a listed resolution. For every mode, no symbol, setting, or glossary term belonging to an entry outside the batch appears in the diff's code, settings, or docs.

Then set each entry's status to `landed: <branch>`, update the ledger's `Updated:` time, and report the branch to the human with the list of resolutions and edits.
