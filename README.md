# spicerack

![Spicerack — an exploded rack of cybernetic tool modules on a dark blueprint.](assets/spicerack-banner.webp)

Agent skills, subagents, MCP configs, extensions, and workflows for coding agents.

Each item here is a spice: take the one or two you want, not the whole rack. Everything is plain files you can read before you use it.

## What's on the rack

| Name | Kind | What it does |
|---|---|---|
| [harvest](skills/harvest/) | skill | Turns a huge fork or branch diff into a ledger of features a human can read, question, and pick from, then lands the picks upstream by cherry-pick, rework, or rebuild. |

## Layout

```
skills/        Agent Skills: one folder per skill, each with a SKILL.md
agents/        Subagent definitions
mcp/           MCP server configs and notes
extensions/    Editor and harness extensions
  claude-code/   Claude Code plugins, hooks, mods, status lines
  pi/            Pi extensions
workflows/     Multi-step workflows that combine the pieces above
config/        Settings snippets and instruction-file fragments
scripts/       Tools for working on spicerack itself
```

Each folder's README says what belongs there and how to install it.

## Install a skill

Skills follow the [Agent Skills](https://agentskills.io) spec, so the [`skills`](https://skills.sh) CLI installs them into Claude Code, Codex, Cursor, Gemini CLI, OpenCode, and other compatible agents:

```bash
npx skills add cwade12c/spicerack --skill harvest                  # one skill
npx skills add cwade12c/spicerack                                  # every skill
npx skills add cwade12c/spicerack --skill harvest -a claude-code   # one agent only
```

### As a Claude Code plugin

spicerack is also a Claude Code plugin marketplace, so each item installs and updates from inside Claude Code:

```
/plugin marketplace add cwade12c/spicerack
/plugin install harvest@spicerack
```

Plugin skills are namespaced by their plugin, so installed this way harvest runs as `/harvest:harvest`. Installed with `npx skills`, it's plain `/harvest`.

### By hand

Copy a skill's folder into your agent's skills directory (`~/.claude/skills/` for Claude Code).

## Working on spicerack

`scripts/dev-link.sh` symlinks your working copy's skills into `~/.claude/skills`, so edits take effect without reinstalling:

```bash
git clone git@github.com:cwade12c/spicerack.git
cd spicerack
scripts/dev-link.sh harvest        # one skill
scripts/dev-link.sh                # every skill
```

Each item is listed in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json). When you change one, bump its `version` there: plugin users stay on the listed version until it changes. Check the file with `claude plugin validate .`.

## License

[MIT](LICENSE)
