# bluewasabi

**Tuning recipes for Bluefin and other Fedora Atomic desktops that leave the image alone.**

Bluefin is built so you never have to tune it. Sometimes you still do, and the usual Linux advice (install a package, edit a file under `/usr`, add a kernel argument) either fails on an image-based system or works until the next update. `bluewasabi` is an [agent skill](https://agentskills.io) holding recipes for those cases. Each recipe diagnoses before it changes anything, keeps its changes in `/etc`, `/var` and your home directory, comes with a revert command, and is tested in stages you agree to.

The agent does the reading, the checking and the testing. You approve each change and run the one command that needs your password.

## Recipes

| Recipe | Fixes |
|---|---|
| [memory-pressure](recipes/memory-pressure/RECIPE.md) | Hard freezes when memory runs out. Replaces zram-only swap with zswap and a disk swapfile, corrects swappiness, and adds a kernel thrashing guard. Optional: a manual OOM-kill hotkey, and desktop notifications as RAM and swap fill up. |

## Quick start

```
/bluewasabi memory-pressure
```

That's the Claude Code form. Installed as a Claude Code plugin, it's `/bluewasabi:bluewasabi`. In other agents, invoke the skill however your agent does, or just describe the problem: "my Bluefin machine freezes when I run out of memory".

## What a session looks like

Abbreviated, from a memory-pressure session on a Bluefin desktop.

**1. The agent diagnoses, read-only.**

> Three causes apply. `vm.swappiness` is 10, set by the tuned profile behind GNOME's Performance power mode, so the kernel drops program code instead of swapping idle memory. Your only swap is zram, which stays in RAM. And nothing acts before the freeze: the journal shows a kernel OOM kill last week that systemd-oomd missed.

**2. It proposes, and you choose.**

> A swapfile on `/var` as large as your RAM (there is plenty of free disk), zswap in front of it, zram off, swappiness 100, and the thrashing guard on. Two options: a manual OOM-kill hotkey, and notifications as memory fills. Want either?

**3. You run one command.**

```
sudo bash ~/.claude/skills/bluewasabi/recipes/memory-pressure/scripts/memory-pressure.sh apply --sysrq
```

It takes effect immediately. The agent then checks every setting itself.

**4. It tests, one stage at a time, with your go-ahead.**

> Swap-out: an incompressible allocation larger than RAM absorbed, worst stall 12 ms, nothing killed.
> Kill: unbounded allocation killed by the kernel once swap was full, worst stall 2 ms, nothing else died, memory free again within 3 seconds.

## Use the scripts without an agent

Each recipe's scripts stand on their own:

```bash
cd recipes/memory-pressure/scripts
bash memory-pressure.sh diagnose        # read-only report
sudo bash memory-pressure.sh apply      # add --size <G> or --sysrq
bash memory-pressure.sh status          # verify, also after a reboot
bash memory-pressure.sh watcher install # notifications, no root
sudo bash memory-pressure.sh revert
```

## Requirements

- A Fedora Atomic desktop: Bluefin, Aurora, Bazzite, Silverblue or Kinoite. Built and tested on Bluefin only.
- `bash` and `python3` (both in the base image).
- A coding agent that supports [Agent Skills](https://agentskills.io) and can run shell commands. Tested in Claude Code.
- The skill installed, either way:
  - `npx skills add cwade12c/spicerack --skill bluewasabi`
  - or, in Claude Code, `/plugin marketplace add cwade12c/spicerack` and `/plugin install bluewasabi@spicerack`.

In Claude Code, bluewasabi is user-invoked: it only runs when you type it.

## Limits

- Each recipe says which machines it was tested on. So far that is one desktop per recipe; treat the rest as untested.
- memory-pressure needs `/var` on btrfs with at least 16G free, and refuses to run otherwise.
- The stress tests fill your memory on purpose. Save your work first.

## Adding a recipe

A recipe is one folder under `recipes/` with a `RECIPE.md` and a script that offers `diagnose`, `status`, `apply` and `revert`. [`references/ADDING-A-RECIPE.md`](references/ADDING-A-RECIPE.md) has the contract.

## Files

| File | For |
|---|---|
| [`SKILL.md`](SKILL.md) | The agent: pick a recipe, confirm the machine, run it, close out, and the rules every recipe follows. |
| [`recipes/memory-pressure/RECIPE.md`](recipes/memory-pressure/RECIPE.md) | The agent: the memory-pressure steps, traps and evidence. |
| [`recipes/memory-pressure/scripts/memory-pressure.sh`](recipes/memory-pressure/scripts/memory-pressure.sh) | Diagnose, status, apply, revert, and the watcher installer. |
| [`recipes/memory-pressure/scripts/stress.sh`](recipes/memory-pressure/scripts/stress.sh) | The four test stages, using `hog.py` and `probe.py`. |
| [`recipes/memory-pressure/scripts/memory-watch`](recipes/memory-pressure/scripts/memory-watch) | The notification watcher and its user unit, `memory-watch.service`. |
| [`references/ADDING-A-RECIPE.md`](references/ADDING-A-RECIPE.md) | The agent, or you: the contract for a new recipe. |
| `README.md` | You. |
