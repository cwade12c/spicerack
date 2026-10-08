# Scripts

Tools for working on spicerack itself. To install skills as a user, see the [repo README](../README.md).

- `dev-link.sh [--target <dir>] [skill...]`: symlink this working copy's skills into `~/.claude/skills` (or `<dir>`), so edits are live without reinstalling. No names links every skill. Existing spicerack links are refreshed; anything else at a skill's path is left alone.
