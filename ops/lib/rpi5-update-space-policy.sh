#!/usr/bin/env bash
# Free-space/inode policy for the weekly updater modes.

# Returns success when the normal minimum free-space/inode gate must be applied.
# cleanup mode intentionally bypasses that minimum so it can reclaim space.
rpi5_enforce_normal_space_gate() {
    local mode="${1:?missing updater mode}"

    case "$mode" in
        run|check)
            return 0
            ;;
        cleanup)
            return 1
            ;;
        *)
            return 2
            ;;
    esac
}
