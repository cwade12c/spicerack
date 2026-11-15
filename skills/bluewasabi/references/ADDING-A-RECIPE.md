# Adding a recipe

A recipe is one folder under `recipes/`. Adding one touches that folder and one table row in `SKILL.md`; nothing else in the skill changes.

## Layout

```
recipes/<name>/
  RECIPE.md        the steps and reference the agent follows
  scripts/         everything the recipe runs
    <name>.sh      diagnose | status | apply | revert
```

Name the recipe after the problem it solves (`memory-pressure`), since that is what the human will describe.

## The script contract

One script per recipe, named after it, with these subcommands. `SKILL.md` step 3 relies on them.

| Subcommand | Root | Does |
|---|---|---|
| `diagnose` | no | Prints a read-only report of every value the recipe's decisions rest on, and ends with `status`. |
| `status` | no | Prints one `ok` or `FAIL` line per expected setting and exits 1 on any `FAIL`. It is the post-apply check and the reboot check. |
| `apply` | yes | Makes every root change in one run. Backs up each file it changes to `/var/lib/bluewasabi/<name>/`. Safe to re-run. Refuses, with the reason, on a machine it was not built for. |
| `revert` | yes | Restores the backed-up state. |

Per-user parts (a user unit, a file under the home directory) get their own subcommand that runs without root. Options a human may decline are flags on `apply`, off by default.

Name every file the recipe installs after the recipe (`/etc/sysctl.d/90-<name>.conf`), so its origin is obvious.

## RECIPE.md

Write the steps in the order `SKILL.md` step 3 names: diagnose, propose, apply, test, hand over. Give each step a done-check. Below the steps, keep a Reference section with:

- **What apply changes**: each change, its file, and why.
- **Traps**: what went wrong while building it, and what looks right but is not.
- **Evidence**: the machines it was tested on, what was measured, and what is untested.

A recipe with a test that loads the machine ships that test as a script with stages, mildest first, and each stage refuses to run when `status` fails.

## Register it

1. Add a row to the table in `SKILL.md` step 1: the recipe, and the complaints that should lead to it.
2. Add it to the description in `SKILL.md` frontmatter and to this skill's `README.md`.
3. Bump the `bluewasabi` version in the repository's `.claude-plugin/marketplace.json`.
4. Add its checks to `tests/bluewasabi/` in the repository.
