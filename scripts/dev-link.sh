#!/usr/bin/env bash
# Link this working copy's skills into an agent's skills directory, so edits
# to a skill take effect without reinstalling. For authoring spicerack; to
# install skills as a user, see the README (`npx skills add`).
#
#   scripts/dev-link.sh [--target <dir>] [skill...]
#
# With no skill names, links every folder under skills/. The default target is
# ~/.claude/skills. Existing links into this repo are refreshed; anything else
# already at a skill's path is left alone and reported.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$HOME/.claude/skills"

if [[ "${1:-}" == "--target" ]]; then
  target="${2:?--target needs a directory}"
  shift 2
fi

if [[ $# -eq 0 ]]; then
  for dir in "$repo"/skills/*/; do
    set -- "$@" "$(basename "$dir")"
  done
fi

mkdir -p "$target"
for name in "$@"; do
  source="$repo/skills/$name"
  dest="$target/$name"
  if [[ ! -f "$source/SKILL.md" ]]; then
    echo "skip  $name: no skills/$name/SKILL.md" >&2
    continue
  fi
  if [[ -L "$dest" && "$(readlink "$dest")" == "$repo"/* ]]; then
    ln -sfn "$source" "$dest"
    echo "relinked  $dest"
  elif [[ -e "$dest" || -L "$dest" ]]; then
    echo "skip  $dest already exists and isn't a spicerack link" >&2
  else
    ln -s "$source" "$dest"
    echo "linked  $dest -> $source"
  fi
done
