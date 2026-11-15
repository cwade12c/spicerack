---
name: bluewasabi
description: Tune a Bluefin or other Fedora Atomic desktop with tested recipes that leave the image pristine. Recipes so far: memory-pressure (ends hard freezes when RAM runs out).
argument-hint: "[recipe], e.g. memory-pressure"
disable-model-invocation: true
license: MIT
compatibility: A Fedora Atomic desktop (Bluefin, Aurora, Bazzite, Silverblue, Kinoite) with bash and python3, and an agent with shell access. Root steps are run by the human with sudo.
---

# Bluewasabi

Bluewasabi tunes an image-based desktop without fighting the image. Each tuning is a **recipe**: a folder under [`recipes/`](recipes/) holding a `RECIPE.md` and the scripts it runs. You run the recipe; the human approves every change and runs every root command.

A change is **pristine** when it leaves the image untouched: no layered packages, no edits under `/usr`, nothing an update will fight. Every recipe stays pristine, and the placement table below says where each kind of change goes.

## 1. Pick the recipe

| Recipe | Reach for it when |
|---|---|
| [memory-pressure](recipes/memory-pressure/RECIPE.md) | The machine hard-freezes or stalls when memory fills, apps get OOM-killed, or the human asks about swap, zram, zswap or OOM. |

Match the argument, or the human's complaint, to one row. If no row fits, say so, and offer to work the problem by the rules below and then capture it as a new recipe with [`references/ADDING-A-RECIPE.md`](references/ADDING-A-RECIPE.md).

Done when one recipe is named and the human has agreed to it.

## 2. Confirm the machine

Check `/run/ostree-booted` exists and read `/etc/os-release` (and `/usr/share/ublue-os/image-info.json` on Universal Blue images). On a machine that is not image-based, stop and say the recipes do not apply. Run `ujust --list` and prefer a recipe the image already ships for the same job.

Done when you can state the image, its version, and that no `ujust` recipe already covers the job.

## 3. Run the recipe

Read the recipe's `RECIPE.md` and follow it. Every recipe has the same shape: **diagnose** read-only, **propose** and wait for the human, **apply** through one script, **verify** with its `status` command, then **test** in stages the human agrees to one at a time.

Done when the recipe's own done-checks pass.

## 4. Close out

Tell the human what changed and where, how to revert it, and what to check after the next reboot (the recipe's `status` command). If you have a persistent memory, offer to save that reboot check there.

Done when `status` passes and the human has the revert command and the reboot check.

## Rules every recipe follows

**Placement.** Put each change on the first row that fits.

| The change is | It goes in |
|---|---|
| A system setting with a default under `/usr/lib` or `/usr/etc` | A file or drop-in of the same name under `/etc` |
| A kernel tunable under `/proc/sys` | `/etc/sysctl.d/*.conf` |
| A kernel knob under `/sys` | `/etc/tmpfiles.d/*.conf` with `w` lines |
| System state or data | `/var` |
| Anything for one user | `~/.config`, `~/.local`, a systemd user unit |
| A command-line tool | Homebrew |
| A graphical app | Flatpak |
| A development environment | Distrobox or a devcontainer |
| A kernel argument | `rpm-ostree kargs`, only when no runtime knob exists; it needs a reboot |
| A host package | `rpm-ostree install`, only with the human's explicit agreement; Bluefin discourages it |

**Verify, then act.** A recipe records what was true on the machines it was tested on. Check each assumption on this machine before relying on it (the filesystem, a kernel option, where a value is set), and say which assumptions you could not check.

**One root hand-off.** `sudo` usually needs a password you cannot type. Put all root work in one script run, give the human the exact command for their own terminal, and verify the result yourself afterwards.

**Reversible.** Back up every file before changing it, and give the human a revert command that restores the earlier state.

**Staged tests.** A test that loads the machine can cost unsaved work. Before each stage, say what it does, how long it takes and what could go wrong, and wait for a go-ahead. Run the mildest stage first.
