# Skills

One folder per skill, following the [Agent Skills](https://agentskills.io) layout: a `SKILL.md` with YAML frontmatter, plus any reference files or scripts it points to. A `README.md` in a skill's folder is for humans; agents read `SKILL.md`.

Install with `npx skills add cwade12c/spicerack --skill <skill>`, or as a Claude Code plugin with `/plugin install <skill>@spicerack`; see the [repo README](../README.md). A new skill also needs an entry in [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json).

| Skill | Invoked by | Summary |
|---|---|---|
| [harvest](harvest/) | you, as `/harvest` | Fork or branch diff → feature ledger → pick → land |

Skills may also carry Claude Code's frontmatter extensions, such as `disable-model-invocation` and `argument-hint`. Other agents ignore them, but strict validation with [`skills-ref`](https://github.com/agentskills/agentskills/tree/main/skills-ref) reports them as unexpected fields.
