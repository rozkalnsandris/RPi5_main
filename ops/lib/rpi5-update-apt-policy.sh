#!/usr/bin/env bash
# APT metadata policy for the reviewed RPi5 maintenance updater.

readonly RPI5_APT_METADATA_SKIPPED_RC=10

rpi5_prepare_apt_metadata() {
    local mode="${1:-}"
    shift || true

    case "$mode" in
        run)
            apt-get "$@" --error-on=any update
            ;;
        check)
            return "$RPI5_APT_METADATA_SKIPPED_RC"
            ;;
        *)
            return 2
            ;;
    esac
}

rpi5_cached_apt_list_age_seconds() {
    local lists_dir="${1:-/var/lib/apt/lists}"
    local now_epoch="${2:-$(date +%s)}"
    local newest_mtime
    local newest_epoch

    [[ -d "$lists_dir" ]] || return 1
    [[ "$now_epoch" =~ ^[0-9]+$ ]] || return 2

    newest_mtime="$(
        find "$lists_dir" \
            -maxdepth 1 \
            -type f \
            ! -name lock \
            -printf '%T@\n' 2>/dev/null |
            sort -nr |
            head -1
    )"
    [[ "$newest_mtime" =~ ^[0-9]+([.][0-9]+)?$ ]] || return 1

    newest_epoch="${newest_mtime%%.*}"
    (( newest_epoch <= now_epoch )) || return 1

    printf '%s\n' "$((now_epoch - newest_epoch))"
}
