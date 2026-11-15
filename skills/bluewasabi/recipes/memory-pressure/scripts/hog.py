#!/usr/bin/env python3
"""Memory hog for testing. usage: hog.py <limit_gib|0 for unlimited> <hold_seconds>"""
import os, sys, time

limit_gib = float(sys.argv[1])
hold = float(sys.argv[2])
CHUNK = 256 * 1024 * 1024
# Each 4K page is random, so zswap/zstd cannot compress it (worst case).
block = os.urandom(1024 * 1024)
chunks = []
t0 = time.time()
while limit_gib == 0 or len(chunks) * CHUNK < limit_gib * 2**30:
    chunks.append(block * (CHUNK // len(block)))
    if len(chunks) % 8 == 0:
        print(f"hog {time.time()-t0:6.1f}s allocated {len(chunks)*CHUNK/2**30:5.1f}G", flush=True)
print(f"hog reached {len(chunks)*CHUNK/2**30:.1f}G in {time.time()-t0:.1f}s, holding {hold:.0f}s", flush=True)
time.sleep(hold)
print("hog releasing", flush=True)
