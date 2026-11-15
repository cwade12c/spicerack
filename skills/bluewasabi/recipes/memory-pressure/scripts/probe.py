#!/usr/bin/env python3
"""Sample the machine every 0.5s until <stopfile> exists, then print a summary.

Each sample records the scheduling stall (how late the 0.5s sleep woke up),
memory pressure, available RAM and swap used. usage: probe.py <stopfile>
"""
import os
import sys
import time

stopfile = sys.argv[1]
t0 = last = time.time()
worst = long_stalls = peak_psi = peak_swap = 0.0
low_avail = float("inf")


def meminfo():
    fields = dict(line.split(":") for line in open("/proc/meminfo"))
    return {k: int(v.split()[0]) / 2**20 for k, v in fields.items()}


while not os.path.exists(stopfile):
    time.sleep(0.5)
    now = time.time()
    stall = now - last - 0.5
    last = now
    mem = meminfo()
    swap = mem["SwapTotal"] - mem["SwapFree"]
    psi = float(open("/proc/pressure/memory").readline().split()[1].split("=")[1])
    worst = max(worst, stall)
    long_stalls += stall > 0.5
    peak_psi = max(peak_psi, psi)
    peak_swap = max(peak_swap, swap)
    low_avail = min(low_avail, mem["MemAvailable"])
    print(f"{now - t0:6.1f}s stall={stall * 1000:5.0f}ms psi_some10={psi:5.1f} "
          f"avail={mem['MemAvailable']:5.1f}G swap_used={swap:5.1f}G", flush=True)

print(f"SUMMARY worst_stall={worst * 1000:.0f}ms stalls_over_500ms={int(long_stalls)} "
      f"peak_pressure={peak_psi:.0f}% peak_swap={peak_swap:.1f}G lowest_available={low_avail:.1f}G")
