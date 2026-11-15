#!/usr/bin/env bash
# Staged memory stress tests for the memory-pressure recipe. Each stage runs a
# hog in its own systemd scope, marked as the preferred OOM-kill target, and
# reports stalls, pressure, kills and notifications.
#
#   stress.sh swap-out   fill RAM plus some swap, hold 20s, release. Nothing should die.
#   stress.sh notify     fill swap past 80%, hold 15s, release. All watcher levels should fire.
#   stress.sh kill       allocate without limit. The kernel should kill the hog.
#   stress.sh decoy      hold a small hog for 15 minutes as a target for Alt+SysRq+F.
#
# Sizes come from this machine's free RAM and swap. Every stage but decoy
# refuses to run unless 'memory-pressure.sh status' passes; --force skips that.
set -euo pipefail

here=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)
stage=${1:-}
[[ $EUID -ne 0 ]] || { echo "error: run as your own user, without sudo" >&2; exit 1; }

kb() { awk -v k="$1:" '$1==k{print $2}' /proc/meminfo; }
avail=$(kb MemAvailable)
swap_total=$(kb SwapTotal)
swap_used=$(( swap_total - $(kb SwapFree) ))
gib=1048576

case $stage in
    swap-out)
        extra=$(( (swap_total - swap_used) / 3 ))
        if (( extra > 10 * gib )); then extra=$(( 10 * gib )); fi
        size=$(( (avail + extra) / gib )) hold=20 limit=240 ;;
    notify)
        size=$(( (avail + swap_total * 83 / 100 - swap_used) / gib )) hold=15 limit=420 ;;
    kill)
        size=0 hold=0 limit=420 ;;
    decoy)
        size=$(( avail / 6 / gib ))
        if (( size > 4 )); then size=4; fi
        if (( size < 1 )); then size=1; fi
        hold=900 limit=960 ;;
    *) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac

if [[ $stage != decoy && ${2:-} != --force ]] && ! "$here/memory-pressure.sh" status >/dev/null; then
    echo "error: the recipe is not fully applied ('memory-pressure.sh status' fails)." >&2
    echo "Filling memory on an untuned machine can hard-freeze it. Pass --force to run anyway." >&2
    exit 1
fi

work=$(mktemp -d)
start=$(date +%s)
echo "stage=$stage hog=$( (( size )) && echo "${size}G" || echo unlimited) hold=${hold}s time_limit=${limit}s start=$(date +%T)"

python3 "$here/probe.py" "$work/stop" > "$work/probe.log" &
probe=$!

set +e
# shellcheck disable=SC2016  # $0..$3 are expanded by the inner sh
systemd-run --user --scope --quiet --unit="bluewasabi-hog-$start" \
    sh -c 'echo 1000 > /proc/self/oom_score_adj; exec timeout -s KILL "$0" python3 "$1" "$2" "$3"' \
    "$limit" "$here/hog.py" "$size" "$hold" | tail -2
rc=${PIPESTATUS[0]}
set -e
elapsed=$(( $(date +%s) - start ))

# Let recovery show up in the probe and give the watcher one more poll.
sleep 8
touch "$work/stop"
wait "$probe" || true

echo
case $rc in
    0) echo "hog: released its memory by itself after ${elapsed}s" ;;
    *) if (( elapsed >= limit )); then echo "hog: stopped by the ${limit}s time limit (exit $rc)"
       else echo "hog: killed after ${elapsed}s (exit $rc)"; fi ;;
esac
grep SUMMARY "$work/probe.log" || true
echo "== kernel kills and hotkey presses during the run =="
journalctl -k --since "@$start" -q --no-pager -o cat -g 'sysrq: Manual OOM|Out of memory: Killed process' 2>/dev/null || true
echo "== systemd-oomd kills during the run =="
journalctl -u systemd-oomd --since "@$start" -q --no-pager -o cat -g 'Killed .* due to' 2>/dev/null || true
echo "== watcher notifications during the run =="
journalctl --user -u memory-watch.service --since "@$start" -q --no-pager -o short -g 'notify\[' 2>/dev/null | cut -c8-15,40-400 || true
echo "== now =="
free -h | tail -2
echo "full probe log: $work/probe.log"
