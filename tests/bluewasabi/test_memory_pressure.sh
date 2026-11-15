#!/usr/bin/env bash
# Checks for the bluewasabi memory-pressure recipe that are safe anywhere:
# lint, syntax, and the swapfile sizing rule. Nothing here changes the system
# or loads it.
#
#   bash tests/bluewasabi/test_memory_pressure.sh
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
scripts=$repo/skills/bluewasabi/recipes/memory-pressure/scripts
fail=0

if command -v shellcheck >/dev/null; then
    shellcheck "$scripts/memory-pressure.sh" "$scripts/stress.sh" "$scripts/memory-watch" || fail=1
else
    echo "skip  shellcheck is not installed"
fi

for f in memory-pressure.sh stress.sh memory-watch; do
    bash -n "$scripts/$f" || fail=1
done
python3 -c 'import ast, sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]' \
    "$scripts/hog.py" "$scripts/probe.py" || fail=1

# ram_gb free_gb expected_swapfile_gb
while read -r ram free want; do
    got=$(bash "$scripts/memory-pressure.sh" propose-size "$ram" "$free")
    if [[ $got == "$want" ]]; then
        echo "ok    propose-size $ram $free -> $got"
    else
        echo "FAIL  propose-size $ram $free -> $got, want $want"
        fail=1
    fi
done <<'EOF'
32 600 32
64 900 32
16 100 16
16 40 10
8 20 5
8 15 0
4 500 4
2 500 0
EOF

exit "$fail"
