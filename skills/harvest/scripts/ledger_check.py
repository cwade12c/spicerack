#!/usr/bin/env python3
"""Mechanical checks for a harvest ledger. Reads only git and the owners map.

    python3 scripts/ledger_check.py survivors <base> <head>
    python3 scripts/ledger_check.py coverage  <base> <head> <owners.json>
    python3 scripts/ledger_check.py batch     <base> <branch> <commit>...

Run inside the repository. Ownership is line-level: every line the tree diff
`merge-base..head` adds is blamed (`git blame merge-base..head`) to the head
commit that wrote it, merges included, and the owners map says which entry
owns that commit, or the part of it under some paths or head line ranges.

survivors
    Pass 2 of step 1. For every commit in merge-base..head, count the lines it
    still owns in the tree diff, ignoring lines whose text already appears in
    base's copy of the file (boilerplate a later commit re-added). A commit
    owning none is reported `on-base` when most of its own added lines appear
    in base's tree (set it aside) or `superseded` when they don't (head
    rewrote it; give it to the entry of the commit that did).

coverage
    Step 2's gate. Exits 0 only when every section prints empty:
    FILES     every changed file has an owned line or a removals owner
    LINES     every added line is owned by exactly one entry
    COMMITS   every commit is owned, set aside, or listed as content-free
    SET_ASIDE every set-aside commit owns only lines base already has
    REMOVALS  every file with removed lines names one entry that owns them
    UNUSED    every commit spec names a commit in range and owns at least one line
    Blank lines are ignored throughout.

batch
    LANDING's cherry-pick check. Lists every non-blank line the branch adds
    over base that none of the given commits added (head's commits for the
    batch, plus the branch's own edit commits): what's left must be listed
    resolutions, edits, and the acceptance tests. Earlier versions of lines
    that head later rewrote pass, because the batch's own commits wrote them.

owners.json:
    {
      "entries": {
        "F1": [{"commit": "0817aec"},
               {"commit": "7d57ea9", "paths": ["src/a.py"]},
               {"commit": "a90a42d", "paths": ["src/b.py"], "lines": ["105-112"]}],
        "Plumbing": [...], "Head-only": [...]
      },
      "set_aside": ["9670ff6"],
      "content_free": ["b17527a"],
      "removals": {"src/c.py": "F3"}
    }
A file whose owned lines all belong to one entry needs no `removals` line.
"""

from __future__ import annotations

import collections
import json
import re
import subprocess
import sys


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def changed_files(mb: str, head: str) -> list[str]:
    out = git("diff", "--name-only", "--no-renames", mb, head)
    return [line for line in out.splitlines() if line]


def added_and_removed(mb: str, head: str, path: str) -> tuple[set[int], int]:
    """Head line numbers the tree diff adds to path, and the count it removes."""
    out = git("diff", "--no-renames", "-U0", mb, head, "--", path)
    added: set[int] = set()
    removed = 0
    for match in re.finditer(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", out, re.M):
        removed += int(match.group(1) if match.group(1) is not None else 1)
        start = int(match.group(2))
        count = int(match.group(3) if match.group(3) is not None else 1)
        added.update(range(start, start + count))
    return added, removed


def blame(mb: str, head: str, path: str) -> dict[int, tuple[str, str]]:
    """Map each head line of path to (commit, text) for lines a head commit wrote."""
    out = git("blame", "--porcelain", f"{mb}..{head}", "--", path, check=False)
    lines: dict[int, tuple[str, str]] = {}
    boundary: set[str] = set()
    sha = ""
    lineno = 0
    for raw in out.splitlines():
        header = re.match(r"^([0-9a-f]{40}) \d+ (\d+)", raw)
        if header:
            sha, lineno = header.group(1), int(header.group(2))
        elif raw == "boundary":
            boundary.add(sha)
        elif raw.startswith("\t"):
            lines[lineno] = (sha, raw[1:])
    # Lines blamed to the boundary are text from before mb that the diff saw as
    # moved or re-added; no head commit wrote them.
    return {n: v for n, v in lines.items() if v[0] not in boundary}


def base_lines(base: str, path: str) -> set[str]:
    text = git("show", f"{base}:{path}", check=False)
    return {line.strip() for line in text.splitlines()}


def commits(mb: str, head: str) -> list[str]:
    return git("rev-list", "--reverse", f"{mb}..{head}").split()


def owned_lines(mb: str, head: str) -> dict[str, list[tuple[int, str, str]]]:
    """Per file, the tree diff's non-blank added lines as (head line, commit, text)."""
    owned: dict[str, list[tuple[int, str, str]]] = {}
    for path in changed_files(mb, head):
        added, _ = added_and_removed(mb, head, path)
        if not added:
            continue
        blamed = blame(mb, head, path)
        # Blank lines carry no intent; a merge's spacing would otherwise need an owner.
        owned[path] = [(n, *blamed[n]) for n in sorted(added) if n in blamed and blamed[n][1].strip()]
    return owned


def survivors(base: str, head: str) -> int:
    mb = git("merge-base", base, head).strip()
    surviving: collections.Counter[str] = collections.Counter()
    for path, lines in owned_lines(mb, head).items():
        on_base = base_lines(base, path)
        for _, sha, text in lines:
            if text.strip() and text.strip() not in on_base:
                surviving[sha] += 1
    print(f"merge-base {mb}")
    for sha in commits(mb, head):
        if surviving[sha]:
            continue
        subject = git("log", "-1", "--format=%s", sha).strip()
        parents = git("log", "-1", "--format=%P", sha).split()
        if len(parents) > 1:
            print(f"content-free  {sha[:7]}  {subject}")
            continue
        own = own_added(sha)
        found = sum(1 for path, text in own if text in base_lines(base, path))
        verdict = "on-base" if own and found * 2 >= len(own) else "superseded"
        line = f"{verdict:<12}  {sha[:7]}  {found}/{len(own)} lines on base  {subject}"
        if verdict == "superseded":
            paths = sorted({path for path, _ in own})
            later = git("log", "--reverse", "--format=%h", f"{sha}..{head}", "--", *paths).split()
            line += f"  (later commits on its files: {', '.join(later[:5]) or 'none'})"
        print(line)
    return 0


def own_added(sha: str) -> list[tuple[str, str]]:
    """Non-blank lines a commit adds over its first parent, as (path, stripped text)."""
    out = git("diff", "--no-renames", "-U0", f"{sha}^1", sha)
    path = ""
    added: list[tuple[str, str]] = []
    for raw in out.splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else ""
        elif raw.startswith("+") and path and raw[1:].strip():
            added.append((path, raw[1:].strip()))
    return added


def spec_matches(spec: dict, sha: str, path: str, lineno: int) -> bool:
    if not sha.startswith(spec["commit"]):
        return False
    if "paths" in spec and not any(path == p or path.startswith(p.rstrip("/") + "/") for p in spec["paths"]):
        return False
    if "lines" in spec:
        spans = [tuple(int(x) for x in span.split("-")) for span in spec["lines"]]
        return any(lo <= lineno <= hi for lo, hi in spans)
    return True


def coverage(base: str, head: str, owners_path: str) -> int:
    with open(owners_path) as handle:
        owners = json.load(handle)
    mb = git("merge-base", base, head).strip()
    entries: dict[str, list[dict]] = owners["entries"]
    set_aside = owners.get("set_aside", [])
    content_free = owners.get("content_free", [])
    removal_owner: dict[str, str] = owners.get("removals", {})

    def listed(sha: str, prefixes: list[str]) -> bool:
        return any(sha.startswith(p) for p in prefixes)

    names = ("FILES", "LINES", "COMMITS", "SET_ASIDE", "REMOVALS", "UNUSED")
    sections: dict[str, list[str]] = {k: [] for k in names}
    changed = changed_files(mb, head)
    for path, owner in removal_owner.items():
        if owner not in entries:
            sections["REMOVALS"].append(f"{path}: owner {owner} is not an entry")
        if path not in changed:
            sections["REMOVALS"].append(f"{path}: not a changed file")
    lacking: collections.Counter[str] = collections.Counter()
    used: set[tuple[str, int]] = set()
    owning_commits: set[str] = set()
    owned = owned_lines(mb, head)
    for path in changed:
        _, removed = added_and_removed(mb, head, path)
        file_entries: set[str] = set()
        on_base = base_lines(base, path)
        for lineno, sha, text in owned.get(path, []):
            owning_commits.add(sha)
            if listed(sha, set_aside):
                if text.strip() not in on_base:
                    lacking[sha] += 1
                continue
            hits = [
                (name, i)
                for name, specs in entries.items()
                for i, spec in enumerate(specs)
                if spec_matches(spec, sha, path, lineno)
            ]
            names = sorted({name for name, _ in hits})
            used.update(hits)
            file_entries.update(names)
            if len(names) != 1:
                who = ", ".join(names) or "no entry"
                sections["LINES"].append(f"{path}:{lineno} ({sha[:7]}) owned by {who}")
        if removed:
            if path in removal_owner and removal_owner[path] in entries:
                file_entries.add(removal_owner[path])
            elif len(file_entries) != 1:
                sections["REMOVALS"].append(f"{path}: {removed} removed lines, owner unclear")
        if not file_entries and not all(listed(s, set_aside) for _, s, _ in owned.get(path, [])):
            sections["FILES"].append(path)
    for sha, count in lacking.items():
        sections["SET_ASIDE"].append(f"{sha[:7]} is set aside but owns {count} lines base lacks")
    for sha in commits(mb, head):
        claimed = any(spec["commit"] and sha.startswith(spec["commit"]) for specs in entries.values() for spec in specs)
        if not (claimed or listed(sha, set_aside) or listed(sha, content_free)):
            note = "owns lines" if sha in owning_commits else "owns no lines"
            sections["COMMITS"].append(f"{sha[:7]} unaccounted ({note})")
    in_range = commits(mb, head)
    for name, specs in entries.items():
        for i, spec in enumerate(specs):
            if not re.fullmatch(r"[0-9a-f]{7,40}", spec["commit"]):
                sections["UNUSED"].append(f"{name}: {spec['commit']!r} is not a 7-40 digit sha")
                continue
            if not any(sha.startswith(spec["commit"]) for sha in in_range):
                sections["UNUSED"].append(f"{name}: {spec['commit']} is not in merge-base..head")
                continue
            writes_lines = any(sha.startswith(spec["commit"]) for sha in owning_commits)
            if (name, i) not in used and writes_lines:
                sections["UNUSED"].append(f"{name}: {json.dumps(spec)}")
    failed = False
    for name, problems in sections.items():
        print(f"== {name}: {len(problems)}")
        for problem in problems[:50]:
            print(f"   {problem}")
        if len(problems) > 50:
            print(f"   ... {len(problems) - 50} more")
        failed = failed or bool(problems)
    return 1 if failed else 0


def batch(base: str, branch: str, shas: list[str]) -> int:
    """Lines branch adds over base that none of the given commits added."""
    written: set[tuple[str, str]] = set()
    for sha in shas:
        written.update(own_added(sha))
    out = git("diff", "--no-renames", "-U0", base, branch)
    path = ""
    extra: dict[str, list[str]] = collections.defaultdict(list)
    for raw in out.splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else ""
        elif raw.startswith("+") and path and raw[1:].strip():
            if (path, raw[1:].strip()) not in written:
                extra[path].append(raw[1:].strip())
    total = sum(len(lines) for lines in extra.values())
    print(f"== EXTRA: {total} lines no listed commit wrote")
    for path, lines in sorted(extra.items()):
        print(f"   {path}: {len(lines)}")
        for line in lines[:3]:
            print(f"      + {line[:100]}")
    return 1 if total else 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "survivors":
        sys.exit(survivors(sys.argv[2], sys.argv[3]))
    if len(sys.argv) == 5 and sys.argv[1] == "coverage":
        sys.exit(coverage(*sys.argv[2:]))
    if len(sys.argv) >= 5 and sys.argv[1] == "batch":
        sys.exit(batch(sys.argv[2], sys.argv[3], sys.argv[4:]))
    sys.exit(__doc__)
