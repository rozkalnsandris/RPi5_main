#!/usr/bin/env bash
# Pure path-ownership policy for custom V24 updater retention cleanup.

# Print the owned artifact class for an exact path, or return nonzero when the
# path is outside this updater's custom retention ownership boundary.
rpi5_cleanup_owned_path_kind() {
    local path="${1:-}"
    local relative

    case "$path" in
        /tmp/rpi5-update-*)
            relative="${path#/tmp/}"
            [[ -n "$relative" && "$relative" != */* ]] || return 1
            printf '%s' 'tmp_directory'
            ;;
        /var/log/rpi5-update.log.*)
            relative="${path#/var/log/}"
            [[ -n "$relative" && "$relative" != */* ]] || return 1
            printf '%s' 'log_rotation'
            ;;
        *)
            return 1
            ;;
    esac
}
