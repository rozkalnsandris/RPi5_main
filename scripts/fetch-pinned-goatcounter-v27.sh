#!/usr/bin/env bash

readonly GOATCOUNTER_URL="https://github.com/arp242/goatcounter/releases/download/v2.7.0/goatcounter-v2.7.0-linux-amd64.gz"
readonly GOATCOUNTER_EXPECTED_BYTES="13935060"
readonly GOATCOUNTER_EXPECTED_SHA256="98d221cb9c8ef2bf76d8daa9cca647839f8d8b0bb5bc7400ff9337c5da834511"
readonly GOATCOUNTER_FETCH_MAX_ATTEMPTS="3"
readonly GOATCOUNTER_FETCH_CONNECT_TIMEOUT_SECONDS="15"
readonly GOATCOUNTER_FETCH_ATTEMPT_MAX_SECONDS="45"

CURRENT_ATTEMPT_FILE=""

is_retryable_http_status() {
  case "${1:-}" in
    408|429|5[0-9][0-9])
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_retryable_curl_code() {
  case "${1:-}" in
    7|18|28|52|56)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

verify_download_integrity() {
  local file="${1:?file required}"
  local expected_bytes="${2:?expected bytes required}"
  local expected_sha256="${3:?expected sha256 required}"
  local actual_bytes actual_sha256

  actual_bytes="$(wc -c < "$file")" || return 1
  [[ "$actual_bytes" == "$expected_bytes" ]] || return 1

  actual_sha256="$(sha256sum -- "$file" | awk '{print $1}')" || return 1
  [[ "$actual_sha256" == "$expected_sha256" ]]
}

fetch_verified_release() {
  local url="${1:?url required}"
  local output="${2:?output required}"
  local expected_bytes="${3:?expected bytes required}"
  local expected_sha256="${4:?expected sha256 required}"
  local output_dir attempt http_code curl_rc delay

  output_dir="$(dirname -- "$output")"
  [[ -d "$output_dir" ]] || {
    echo "GoatCounter fetch: FAIL: output directory is unavailable" >&2
    return 1
  }
  [[ ! -e "$output" && ! -L "$output" ]] || {
    echo "GoatCounter fetch: FAIL: refusing to overwrite output" >&2
    return 1
  }

  for ((attempt = 1; attempt <= GOATCOUNTER_FETCH_MAX_ATTEMPTS; attempt++)); do
    CURRENT_ATTEMPT_FILE="$(mktemp "${output}.attempt.${attempt}.XXXXXX")" || {
      echo "GoatCounter fetch: FAIL: unable to create attempt file" >&2
      return 1
    }

    if http_code="$(curl --disable --silent --show-error --location --max-redirs 5 \
      --proto '=https' --proto-redir '=https' --tlsv1.2 \
      --connect-timeout "$GOATCOUNTER_FETCH_CONNECT_TIMEOUT_SECONDS" \
      --max-time "$GOATCOUNTER_FETCH_ATTEMPT_MAX_SECONDS" \
      --output "$CURRENT_ATTEMPT_FILE" --write-out '%{http_code}' "$url")"; then
      curl_rc=0
    else
      curl_rc=$?
    fi

    if [[ "$curl_rc" -eq 0 && "$http_code" == "200" ]]; then
      if ! verify_download_integrity "$CURRENT_ATTEMPT_FILE" "$expected_bytes" "$expected_sha256"; then
        rm -f -- "$CURRENT_ATTEMPT_FILE"
        CURRENT_ATTEMPT_FILE=""
        echo "GoatCounter fetch: FAIL: pinned release integrity mismatch" >&2
        return 1
      fi
      chmod 0444 "$CURRENT_ATTEMPT_FILE"
      mv -- "$CURRENT_ATTEMPT_FILE" "$output"
      CURRENT_ATTEMPT_FILE=""
      echo "GoatCounter fetch: pinned release verified"
      return 0
    fi

    rm -f -- "$CURRENT_ATTEMPT_FILE"
    CURRENT_ATTEMPT_FILE=""

    if [[ "$curl_rc" -eq 0 ]]; then
      if ! is_retryable_http_status "$http_code"; then
        echo "GoatCounter fetch: FAIL: non-transient HTTP status $http_code" >&2
        return 1
      fi
      if [[ "$attempt" -eq "$GOATCOUNTER_FETCH_MAX_ATTEMPTS" ]]; then
        echo "GoatCounter fetch: FAIL: transient HTTP status $http_code exhausted after $attempt attempts" >&2
        return 1
      fi
      echo "GoatCounter fetch: transient HTTP status $http_code; retrying ($attempt/$GOATCOUNTER_FETCH_MAX_ATTEMPTS)" >&2
    else
      if ! is_retryable_curl_code "$curl_rc"; then
        echo "GoatCounter fetch: FAIL: non-transient curl error $curl_rc" >&2
        return 1
      fi
      if [[ "$attempt" -eq "$GOATCOUNTER_FETCH_MAX_ATTEMPTS" ]]; then
        echo "GoatCounter fetch: FAIL: transient curl error $curl_rc exhausted after $attempt attempts" >&2
        return 1
      fi
      echo "GoatCounter fetch: transient curl error $curl_rc; retrying ($attempt/$GOATCOUNTER_FETCH_MAX_ATTEMPTS)" >&2
    fi

    delay=$((attempt * 2))
    sleep "$delay"
  done

  echo "GoatCounter fetch: FAIL: attempt ceiling reached" >&2
  return 1
}

main() {
  [[ "$#" -eq 1 ]] || {
    echo "usage: $0 OUTPUT" >&2
    return 2
  }

  trap 'if [[ -n "${CURRENT_ATTEMPT_FILE:-}" ]]; then rm -f -- "$CURRENT_ATTEMPT_FILE"; fi' EXIT

  fetch_verified_release \
    "$GOATCOUNTER_URL" \
    "$1" \
    "$GOATCOUNTER_EXPECTED_BYTES" \
    "$GOATCOUNTER_EXPECTED_SHA256"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -Eeuo pipefail
  main "$@"
fi
