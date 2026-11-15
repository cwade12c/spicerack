# memory-pressure

When memory fills, the machine should slow down and, at the limit, lose one process. This recipe replaces zram-only swap with **zswap in front of a disk swapfile**, corrects `vm.swappiness`, and turns on a kernel thrashing guard. It optionally adds a manual OOM-kill hotkey and desktop notifications.

`scripts/` below is this recipe's folder. Everything runs through two scripts: [`scripts/memory-pressure.sh`](scripts/memory-pressure.sh) (`diagnose`, `status`, `apply`, `revert`, `watcher`) and [`scripts/stress.sh`](scripts/stress.sh) (the test stages).

## 1. Diagnose

Run `bash scripts/memory-pressure.sh diagnose`. It needs no root and changes nothing. Read the report against these causes and tell the human which ones apply, with the value that shows it:

| Cause | The report shows |
|---|---|
| The kernel evicts program code instead of swapping idle memory | `swappiness` below 60. A value of 10 `set by: tuned profile throughput-performance` means GNOME's Performance power mode is on. |
| Swapped pages never leave RAM | The only swap device is `/dev/zram0`. |
| Nothing acts before the freeze | `min_ttl_ms=0`, and few or no `oomd kills` despite `kernel OOM kills` or reported freezes. |

A hard freeze leaves no log entry, so zero kills in the history does not rule memory out.

Done when you have told the human which causes apply, and whether `/var` is btrfs with room for the `proposed` swapfile.

## 2. Propose

Present the plan and wait for the human's answer:

- The swapfile size from `proposed` (as large as RAM, at most 32G, at most a quarter of free space on `/var`), and that they may choose another with `--size`.
- zram is switched off, because zram and zswap must not be stacked.
- The two options, each a separate yes or no: the **SysRq key** and the **watcher**. Give the costs from the reference below.

If `proposed` is 0 or `/var` is not btrfs, `apply` refuses. Say so and stop; the fallback under Reference is untested and is the human's call.

Done when the human has agreed to a size and answered both options.

## 3. Apply

Give the human this command for their own terminal, with the flags they chose, and wait for the output:

```
sudo bash <recipe-dir>/scripts/memory-pressure.sh apply [--size <G>] [--sysrq]
```

It takes effect at once, with no reboot. Then run `bash scripts/memory-pressure.sh status` yourself.

If the human said yes to the watcher, run `bash scripts/memory-pressure.sh watcher install` (no root), then `~/.local/bin/memory-watch --test` and ask whether four notifications appeared, the last one replacing the third.

Done when `status` prints no `FAIL` line.

## 4. Test

Offer the stages in this order. Before each, give the duration and risks, tell the human to save their work, and wait for a go-ahead. Each stage prints its own report.

| Stage | Command | Passes when |
|---|---|---|
| Swap-out | `bash scripts/stress.sh swap-out` | The hog releases by itself, nothing is killed, `stalls_over_500ms=0`. |
| Hotkey (only with the SysRq key) | `bash scripts/stress.sh decoy`, in the background | The human presses Alt+SysRq+F once and the report shows `sysrq: Manual OOM` and the hog killed. |
| Notifications (only with the watcher) | `bash scripts/stress.sh notify` | Three notifications on the way up, then `Memory recovered`. |
| Kill | `bash scripts/stress.sh kill` | The kernel kills the hog, nothing else dies, memory returns within seconds. |

The hog marks itself as the preferred kill target and runs in its own scope, so a kill lands on it. The stages size themselves from free RAM and swap. On a slow disk a stage can hit its time limit before it finishes; the report says so, and that is a pass for safety but not for the stage.

Tell the human two things before the hotkey stage: press it **once**, and only while the hog is running. With no hog, the key kills whichever ordinary process scores highest, which may be the agent or their browser.

The probe measures scheduling delay, so ask the human how the desktop felt.

Done when every stage the human agreed to has passed, or you have reported which failed and why.

## 5. Hand over

Give the human the revert command (`sudo bash <recipe-dir>/scripts/memory-pressure.sh revert`, plus `watcher remove`) and the reboot check: after the next reboot, `bash scripts/memory-pressure.sh status` should print no `FAIL` line. The watcher starts at login, not at boot.

## Reference

### What apply changes

| Change | File | Why |
|---|---|---|
| Swapfile in its own btrfs subvolume, labelled `swapfile_t`, mounted `nofail` | `/var/swap/swapfile`, `/etc/fstab` | Idle memory can leave RAM. Its own subvolume keeps it out of snapshots. |
| zswap on: zstd, 20% pool, shrinker on | `/etc/tmpfiles.d/90-memory-pressure.conf` | A compressed cache absorbs swap writes in RAM and spills cold pages to disk. |
| Thrashing guard: MGLRU `min_ttl_ms` = 1000 | same file | The kernel OOM-kills when it cannot keep the last second's working set, instead of locking up. |
| `vm.swappiness = 100` | `/etc/sysctl.d/90-memory-pressure.conf` | Anonymous memory and file cache are reclaimed at equal cost. |
| zram off | `/etc/systemd/zram-generator.conf`, no devices | zram under zswap compresses twice and pins pages in RAM. |
| `kernel.sysrq` gains bit 64 (`--sysrq`) | `/etc/sysctl.d/90-sysrq.conf` | Alt+SysRq+F runs the kernel OOM killer once, even on a frozen desktop. |

Backups go to `/var/lib/bluewasabi/memory-pressure/`. The zswap values match what Bluefin ships in its Dakota builds.

### Traps

- **zstd is a module on the Fedora kernel.** A `zswap.compressor=zstd` kernel argument is parsed before modules can load and silently falls back to lzo. That is why zswap is set through tmpfiles.
- **tuned sets swappiness.** It re-applies `/etc/sysctl.d` after its profile (`reapply_sysctl=1` in `/etc/tuned/tuned-main.conf`), so the recipe's file wins. If `diagnose` still shows another source after apply, check that setting.
- **SELinux.** A swapfile labelled `var_t` works for swapping but trips other policy; `apply` labels it `swapfile_t`.
- **Kills are not selective.** The kernel kills the process with the highest OOM score, by memory use. systemd-oomd kills a whole cgroup, which can be an entire terminal tab.

### The options and their costs

- **SysRq key.** Bit 64 also enables Alt+SysRq+E and +I, which signal every process and end the session. Anyone at the keyboard can use them, including at the lock screen.
- **Watcher.** `memory-watch` polls every 5 seconds and notifies at three levels: available RAM under 15%, swap 50% used, swap 80% used (critical, stays on screen). The critical notice names the process that would be killed next and is replaced by `Memory recovered` once swap falls below 70%. Thresholds are set with an `Environment=` line in `~/.config/systemd/user/memory-watch.service`. GNOME shows non-critical notifications for a few seconds and then keeps them in the notification list.

### Tuning afterwards

- Kills come too early: lower `min_ttl_ms` in the tmpfiles file to 500, or 0 to turn the guard off.
- A process must survive, or should go first: set `OOMScoreAdjust=` on its systemd unit (negative values need root).
- systemd-oomd is left at the distribution's defaults.

### Without a swapfile (untested)

Where there is no room or `/var` is not btrfs, raising `vm.swappiness` to 100 or more with zram still in place addresses the first cause alone. This recipe does not automate it and it has not been tested.

### Evidence

Built and tested on one Bluefin desktop in November 2026: btrfs on a fast SSD, SELinux enforcing. An incompressible allocation larger than RAM was absorbed with a 12 ms worst stall and no kill; an unbounded one was killed by the kernel once swap was full, with a 2 ms worst stall and nothing else killed. Other filesystems, slow disks, small-RAM machines and hibernation are untested.
