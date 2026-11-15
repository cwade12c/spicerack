#!/usr/bin/env bash
# memory-pressure: end hard freezes under memory exhaustion on a Fedora Atomic
# desktop (Bluefin, Aurora, Bazzite, Silverblue) with zswap in front of a disk
# swapfile. Changes live in /etc, /var and the home directory only.
#
#   memory-pressure.sh diagnose                    read-only report (no root)
#   memory-pressure.sh status                      verify the applied state (no root); exits 1 on any FAIL
#   sudo memory-pressure.sh apply [--size <G>] [--sysrq]
#   sudo memory-pressure.sh revert
#   memory-pressure.sh watcher install|remove      desktop notifications (no root)
#
# apply is safe to re-run. It needs /var on btrfs.
set -euo pipefail

SWAP_DIR=/var/swap
SWAP_FILE=$SWAP_DIR/swapfile
SYSCTL_FILE=/etc/sysctl.d/90-memory-pressure.conf
TMPFILES_FILE=/etc/tmpfiles.d/90-memory-pressure.conf
SYSRQ_FILE=/etc/sysctl.d/90-sysrq.conf
ZRAM_CONF=/etc/systemd/zram-generator.conf
BACKUP_DIR=/var/lib/bluewasabi/memory-pressure
ZSWAP=/sys/module/zswap/parameters
MIN_TTL=/sys/kernel/mm/lru_gen/min_ttl_ms
WATCH_BIN=$HOME/.local/bin/memory-watch
WATCH_UNIT=$HOME/.config/systemd/user/memory-watch.service
here=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)

die() { echo "error: $*" >&2; exit 1; }
need_root() { [[ $EUID -eq 0 ]] || die "run this with sudo, in your own terminal"; }
need_user() { [[ $EUID -ne 0 ]] || die "run this as your own user, without sudo"; }
meminfo_gb() { awk -v k="$1:" '$1==k{printf "%d", ($2+1048575)/1048576}' /proc/meminfo; }
swap_active() { swapon --show=NAME --noheadings | grep -qx "$1"; }
zram_swaps() { swapon --show=NAME --noheadings | grep '^/dev/zram' || true; }
var_fstype() { findmnt -no FSTYPE -T /var; }
var_free_gb() { df --output=avail -BG /var | tail -1 | tr -dc 0-9; }
val_is() { [[ "$(cat "$1" 2>/dev/null)" == "$2" ]]; }
sysctl_is() { [[ "$(sysctl -n "$1" 2>/dev/null)" == "$2" ]]; }

# Swapfile size in G for a machine with <ram_gb> RAM and <free_gb> free on
# /var: as large as RAM, at most 32G, at most a quarter of free space.
# Prints 0 when that leaves less than 4G, meaning there is no room.
propose_size() {
    local size=$1 free=$2
    if (( size > 32 )); then size=32; fi
    if (( size > free / 4 )); then size=$(( free / 4 )); fi
    if (( size < 4 )); then size=0; fi
    echo "$size"
}

# Where the live vm.swappiness comes from. tuned re-applies /etc/sysctl.d after
# its profile (reapply_sysctl=1), so /etc beats tuned and tuned beats /usr/lib.
swappiness_source() {
    local f profile
    f=$(grep -lsE '^\s*vm\.swappiness' /etc/sysctl.d/*.conf /run/sysctl.d/*.conf /etc/sysctl.conf | tail -1 || true)
    if [[ -n $f ]]; then echo "$f"; return; fi
    if command -v tuned-adm >/dev/null; then
        profile=$(tuned-adm active 2>/dev/null | sed -n 's/^Current active profile: //p')
        for f in "/etc/tuned/profiles/$profile/tuned.conf" "/usr/lib/tuned/profiles/$profile/tuned.conf"; do
            if grep -qsE '^\s*vm\.swappiness' "$f"; then echo "tuned profile $profile"; return; fi
        done
    fi
    f=$(grep -lsE '^\s*vm\.swappiness' /usr/lib/sysctl.d/*.conf | tail -1 || true)
    if [[ -n $f ]]; then echo "$f"; else echo "kernel default"; fi
}

failed=0
check() { # description, command...
    local desc=$1
    shift
    if "$@" >/dev/null 2>&1; then echo "ok    $desc"; else echo "FAIL  $desc"; failed=1; fi
}

cmd_status() {
    failed=0
    check "swapfile $SWAP_FILE is active" swap_active "$SWAP_FILE"
    check "swapfile is in /etc/fstab" grep -q "^$SWAP_FILE " /etc/fstab
    check "no zram swap device" test -z "$(zram_swaps)"
    check "zswap enabled" val_is "$ZSWAP/enabled" Y
    check "zswap compressor is zstd" val_is "$ZSWAP/compressor" zstd
    check "vm.swappiness is 100" sysctl_is vm.swappiness 100
    if [[ -e $MIN_TTL ]]; then check "thrashing guard min_ttl_ms is 1000" val_is "$MIN_TTL" 1000; fi
    if [[ -f $SYSRQ_FILE ]]; then
        check "kernel.sysrq matches $SYSRQ_FILE" sysctl_is kernel.sysrq "$(sed -n 's/^kernel\.sysrq *= *//p' "$SYSRQ_FILE")"
    fi
    if [[ $EUID -ne 0 && -f $WATCH_UNIT ]]; then
        check "memory-watch.service is active" systemctl --user is-active memory-watch.service
    fi
    return "$failed"
}

cmd_diagnose() {
    local ram free zstd profile
    ram=$(meminfo_gb MemTotal)
    free=$(var_free_gb)
    zstd=$(sed -n 's/^CONFIG_CRYPTO_ZSTD=//p' "/usr/lib/modules/$(uname -r)/config" 2>/dev/null)
    profile=$(tuned-adm active 2>/dev/null | sed -n 's/^Current active profile: //p' || true)

    echo "== machine =="
    if [[ -f /usr/share/ublue-os/image-info.json ]]; then
        echo "image:        $(sed -n 's/.*"image-name": *"\([^"]*\)".*/\1/p' /usr/share/ublue-os/image-info.json)"
    fi
    # shellcheck source=/dev/null
    echo "os:           $(. /etc/os-release && echo "$NAME $VERSION")"
    echo "atomic:       $(if [[ -e /run/ostree-booted ]]; then echo yes; else echo "no (/run/ostree-booted is missing)"; fi)"
    echo "ram:          ${ram}G total, $(meminfo_gb MemAvailable)G available"
    echo "selinux:      $(getenforce 2>/dev/null || echo "not present")"

    echo "== swap =="
    swapon --show 2>/dev/null | sed 's/^/  /'
    [[ -n $(swapon --show --noheadings) ]] || echo "  (none)"
    echo "zram swap:    $(zram_swaps | paste -sd' ' | sed 's/^$/none/')"
    echo "zram config:  $(if [[ -f $ZRAM_CONF ]]; then echo "$ZRAM_CONF (overrides the image default)"; else echo "image default"; fi)"
    if [[ -d $ZSWAP ]]; then
        echo "zswap:        enabled=$(cat $ZSWAP/enabled) compressor=$(cat $ZSWAP/compressor) pool=$(cat $ZSWAP/max_pool_percent)%"
    else
        echo "zswap:        not available in this kernel"
    fi
    echo "zstd:         ${zstd:-not built} (m = module: a zswap.compressor=zstd kernel argument would fall back to the default)"

    echo "== reclaim =="
    echo "swappiness:   $(sysctl -n vm.swappiness), set by: $(swappiness_source)"
    echo "tuned:        ${profile:-not running}"
    if [[ -e $MIN_TTL ]]; then
        echo "mglru:        enabled=$(cat /sys/kernel/mm/lru_gen/enabled) min_ttl_ms=$(cat $MIN_TTL)"
    else
        echo "mglru:        not available (the thrashing guard will be skipped)"
    fi
    echo "oomd:         $(systemctl is-active systemd-oomd 2>/dev/null || true)"
    echo "sysrq:        $(sysctl -n kernel.sysrq) (manual OOM key needs bit 64, or 1 for all)"

    echo "== disk =="
    echo "/var:         $(var_fstype), ${free}G free"
    if [[ -f $SWAP_FILE ]] || swap_active "$SWAP_FILE"; then
        echo "swapfile:     $SWAP_FILE already exists"
    else
        echo "proposed:     $(propose_size "$ram" "$free")G swapfile (0 = not enough room)"
    fi

    echo "== history, last 30 days =="
    echo "kernel OOM kills:  $(journalctl -k --since "-30 days" -q -g 'Out of memory: Killed process' 2>/dev/null | wc -l)"
    echo "oomd kills:        $(journalctl -u systemd-oomd --since "-30 days" -q -g 'Killed .* due to' 2>/dev/null | wc -l)"

    echo "== recipe state =="
    cmd_status || true
}

cmd_apply() {
    need_root
    local size="" sysrq=0 cur
    while (( $# )); do
        case $1 in
            --size) size=${2:?--size needs a number of G}; size=${size%[gG]}; shift 2 ;;
            --sysrq) sysrq=1; shift ;;
            *) die "unknown option: $1" ;;
        esac
    done
    [[ -d $ZSWAP ]] || die "this kernel has no zswap"
    [[ $(var_fstype) == btrfs ]] || die "/var is $(var_fstype); this recipe is only built for btrfs"

    if [[ ! -f $SWAP_FILE ]]; then
        [[ -n $size ]] || size=$(propose_size "$(meminfo_gb MemTotal)" "$(var_free_gb)")
        [[ $size =~ ^[0-9]+$ ]] || die "--size must be a whole number of G"
        (( size > 0 )) || die "not enough free space on /var for a swapfile (needs 4G within a quarter of free space); pass --size to override"
    fi

    echo ">> Backups in $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    [[ -f $BACKUP_DIR/fstab ]] || cp -a /etc/fstab "$BACKUP_DIR/fstab"
    if [[ ! -f $BACKUP_DIR/zram-generator.conf && ! -f $BACKUP_DIR/zram-generator.conf.absent ]]; then
        if [[ -f $ZRAM_CONF ]]; then cp -a "$ZRAM_CONF" "$BACKUP_DIR/zram-generator.conf"; else touch "$BACKUP_DIR/zram-generator.conf.absent"; fi
    fi

    echo ">> Swapfile $SWAP_FILE"
    if [[ ! -d $SWAP_DIR ]]; then
        # Its own subvolume, so the swapfile is never part of a snapshot.
        btrfs subvolume create "$SWAP_DIR"
        chmod 700 "$SWAP_DIR"
    fi
    [[ -f $SWAP_FILE ]] || btrfs filesystem mkswapfile --size "${size}g" --uuid clear "$SWAP_FILE"
    if command -v semanage >/dev/null; then
        semanage fcontext -a -t swapfile_t "$SWAP_FILE" 2>/dev/null || semanage fcontext -m -t swapfile_t "$SWAP_FILE"
        restorecon "$SWAP_DIR" "$SWAP_FILE"
    fi
    grep -q "^$SWAP_FILE " /etc/fstab || echo "$SWAP_FILE none swap defaults,nofail 0 0" >> /etc/fstab

    echo ">> $SYSCTL_FILE"
    cat > "$SYSCTL_FILE" <<'EOF'
# A low vm.swappiness (tuned's throughput-performance profile sets 10) makes
# the kernel evict file cache, which is program code, instead of swapping idle
# memory. Under pressure that turns "slow" into a hard freeze. With zswap in
# front of the swapfile swapping is cheap, so weigh both equally.
# tuned re-applies /etc/sysctl.d after its profile, so this value wins.
vm.swappiness = 100
EOF

    echo ">> $TMPFILES_FILE"
    cat > "$TMPFILES_FILE" <<'EOF'
# zswap: a compressed RAM cache in front of the disk swapfile. Cold pages are
# written out to disk under pressure (zram would pin them in RAM).
# Set here, not as kernel arguments: zstd is a module on the Fedora kernel and
# is not loadable when kernel arguments are parsed.
w /sys/module/zswap/parameters/compressor       - - - - zstd
w /sys/module/zswap/parameters/max_pool_percent - - - - 20
w /sys/module/zswap/parameters/shrinker_enabled - - - - Y
w /sys/module/zswap/parameters/enabled          - - - - Y
EOF
    if [[ -e $MIN_TTL ]]; then
        cat >> "$TMPFILES_FILE" <<'EOF'
# MGLRU thrashing guard: when the last second's working set cannot be kept in
# memory, run the OOM killer instead of letting the desktop lock up.
w /sys/kernel/mm/lru_gen/min_ttl_ms             - - - - 1000
EOF
    fi

    echo ">> $ZRAM_CONF (zram off: it must not be stacked with zswap)"
    cat > "$ZRAM_CONF" <<'EOF'
# Intentionally has no devices: overrides /usr/lib/systemd/zram-generator.conf.
# Swap is zswap + /var/swap/swapfile. See /etc/tmpfiles.d/90-memory-pressure.conf.
EOF

    if (( sysrq )); then
        cur=$(sysctl -n kernel.sysrq)
        if (( cur != 1 )); then cur=$(( cur | 64 )); fi
        echo ">> $SYSRQ_FILE (kernel.sysrq = $cur)"
        printf '# Bit 64 enables Alt+SysRq+F: run the kernel OOM killer once.\n# It also enables Alt+SysRq+E and +I, which signal every process.\nkernel.sysrq = %s\n' "$cur" > "$SYSRQ_FILE"
        sysctl -q -p "$SYSRQ_FILE"
    fi

    echo ">> Activating"
    systemctl daemon-reload
    swap_active "$SWAP_FILE" || swapon "$SWAP_FILE"
    sysctl -q -p "$SYSCTL_FILE"
    systemd-tmpfiles --create "$TMPFILES_FILE"
    for dev in $(zram_swaps); do
        swapoff "$dev"
        systemctl stop "systemd-zram-setup@${dev#/dev/}.service" 2>/dev/null || true
    done

    echo
    swapon --show
    cmd_status
}

cmd_revert() {
    need_root
    echo ">> Reverting"
    if swap_active "$SWAP_FILE"; then swapoff "$SWAP_FILE"; fi
    sed -i "\|^$SWAP_FILE |d" /etc/fstab
    rm -f "$SWAP_FILE" "$SYSCTL_FILE" "$TMPFILES_FILE" "$SYSRQ_FILE"
    if [[ -d $SWAP_DIR ]]; then btrfs subvolume delete "$SWAP_DIR" || rmdir "$SWAP_DIR" || true; fi
    if command -v semanage >/dev/null; then semanage fcontext -d "$SWAP_FILE" 2>/dev/null || true; fi
    if [[ -f $BACKUP_DIR/zram-generator.conf ]]; then
        cp -a "$BACKUP_DIR/zram-generator.conf" "$ZRAM_CONF"
    else
        rm -f "$ZRAM_CONF"
    fi
    echo N > "$ZSWAP/enabled"
    if [[ -e $MIN_TTL ]]; then echo 0 > "$MIN_TTL"; fi
    sysctl -q --system
    systemctl daemon-reload
    systemctl start systemd-zram-setup@zram0.service 2>/dev/null || true
    swapon --show
    echo ">> Reverted. A tuned profile's own sysctl values return at the next profile switch or reboot."
    echo ">> The notification watcher is per-user: remove it with 'memory-pressure.sh watcher remove'."
}

cmd_watcher() {
    need_user
    case ${1:-} in
        install)
            install -Dm755 "$here/memory-watch" "$WATCH_BIN"
            install -Dm644 "$here/memory-watch.service" "$WATCH_UNIT"
            systemctl --user daemon-reload
            systemctl --user enable memory-watch.service
            systemctl --user restart memory-watch.service
            echo "memory-watch.service: $(systemctl --user is-active memory-watch.service)"
            ;;
        remove)
            systemctl --user disable --now memory-watch.service 2>/dev/null || true
            rm -f "$WATCH_BIN" "$WATCH_UNIT"
            systemctl --user daemon-reload
            echo "memory-watch removed"
            ;;
        *) die "usage: memory-pressure.sh watcher install|remove" ;;
    esac
}

case ${1:-} in
    diagnose) cmd_diagnose ;;
    status) cmd_status ;;
    apply) shift; cmd_apply "$@" ;;
    revert) cmd_revert ;;
    watcher) shift; cmd_watcher "$@" ;;
    propose-size) propose_size "${2:?ram_gb}" "${3:?free_gb}" ;;
    *) sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
