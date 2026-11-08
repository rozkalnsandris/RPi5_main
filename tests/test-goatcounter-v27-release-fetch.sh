#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../scripts/fetch-pinned-goatcounter-v27.sh
source "$ROOT/scripts/fetch-pinned-goatcounter-v27.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ "$GOATCOUNTER_URL" == "https://github.com/arp242/goatcounter/releases/download/v2.7.0/goatcounter-v2.7.0-linux-amd64.gz" ]] || fail "pinned URL drift"
[[ "$GOATCOUNTER_EXPECTED_BYTES" == "13935060" ]] || fail "pinned byte count drift"
[[ "$GOATCOUNTER_EXPECTED_SHA256" == "98d221cb9c8ef2bf76d8daa9cca647839f8d8b0bb5bc7400ff9337c5da834511" ]] || fail "pinned SHA-256 drift"
[[ "$GOATCOUNTER_FETCH_MAX_ATTEMPTS" == "3" ]] || fail "attempt ceiling drift"
[[ "$GOATCOUNTER_FETCH_CONNECT_TIMEOUT_SECONDS" == "15" ]] || fail "connect timeout drift"
[[ "$GOATCOUNTER_FETCH_ATTEMPT_MAX_SECONDS" == "45" ]] || fail "attempt timeout drift"

for status in 408 429 500 502 503 504 599; do
  is_retryable_http_status "$status" || fail "expected retryable HTTP status $status"
done
for status in 200 301 400 401 403 404; do
  if is_retryable_http_status "$status"; then
    fail "unexpected retryable HTTP status $status"
  fi
done
for code in 7 18 28 52 56; do
  is_retryable_curl_code "$code" || fail "expected retryable curl code $code"
done
for code in 1 2 3 22 23 60; do
  if is_retryable_curl_code "$code"; then
    fail "unexpected retryable curl code $code"
  fi
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
MOCK_FIXTURE="$TMP/fixture.bin"
printf 'goatcounter-pinned-fixture\n' > "$MOCK_FIXTURE"
FIXTURE_BYTES="$(wc -c < "$MOCK_FIXTURE")"
FIXTURE_SHA256="$(sha256sum "$MOCK_FIXTURE" | awk '{print $1}')"
MOCK_COUNT_FILE="$TMP/count"
MOCK_PATH_LOG="$TMP/paths"
MOCK_SEQUENCE=()
MOCK_PAYLOAD="good"

sleep() {
  :
}

curl() {
  local output="" url="" count entry rc http payload arg
  while (($#)); do
    arg="$1"
    case "$arg" in
      --output)
        output="$2"
        shift 2
        ;;
      --write-out|--connect-timeout|--max-time|--proto|--proto-redir|--max-redirs)
        shift 2
        ;;
      --disable|--silent|--show-error|--location|--tlsv1.2)
        shift
        ;;
      *)
        url="$arg"
        shift
        ;;
    esac
  done

  [[ -n "$output" ]] || return 90
  [[ "$url" == "https://example.invalid/pinned" ]] || return 91

  count="$(cat "$MOCK_COUNT_FILE")"
  count=$((count + 1))
  printf '%s\n' "$count" > "$MOCK_COUNT_FILE"
  printf '%s\n' "$output" >> "$MOCK_PATH_LOG"

  entry="${MOCK_SEQUENCE[$((count - 1))]:-}"
  [[ -n "$entry" ]] || return 92
  IFS=',' read -r rc http payload <<< "$entry"

  if [[ "$rc" == "0" ]]; then
    if [[ "$http" == "200" && "$payload" == "good" ]]; then
      cp "$MOCK_FIXTURE" "$output"
    else
      printf 'bad-or-error-payload\n' > "$output"
    fi
  else
    : > "$output"
  fi

  printf '%s' "$http"
  return "$rc"
}

reset_mock() {
  : > "$MOCK_PATH_LOG"
  printf '0\n' > "$MOCK_COUNT_FILE"
  MOCK_SEQUENCE=("$@")
}

out="$TMP/out-success"
reset_mock "0,504,error" "0,200,good"
fetch_verified_release "https://example.invalid/pinned" "$out" "$FIXTURE_BYTES" "$FIXTURE_SHA256" >/dev/null
[[ "$(cat "$MOCK_COUNT_FILE")" == "2" ]] || fail "504 did not retry exactly once"
cmp -s "$MOCK_FIXTURE" "$out" || fail "verified output mismatch"
[[ "$(stat -c '%a' "$out")" == "444" ]] || fail "verified output mode mismatch"
[[ "$(sort -u "$MOCK_PATH_LOG" | wc -l)" == "2" ]] || fail "retry reused an attempt path"

out="$TMP/out-404"
reset_mock "0,404,error" "0,200,good"
if fetch_verified_release "https://example.invalid/pinned" "$out" "$FIXTURE_BYTES" "$FIXTURE_SHA256" >/dev/null 2>&1; then
  fail "404 unexpectedly succeeded"
fi
[[ "$(cat "$MOCK_COUNT_FILE")" == "1" ]] || fail "404 was retried"
[[ ! -e "$out" ]] || fail "404 left a final output"

out="$TMP/out-exhausted"
reset_mock "0,504,error" "0,504,error" "0,504,error"
if fetch_verified_release "https://example.invalid/pinned" "$out" "$FIXTURE_BYTES" "$FIXTURE_SHA256" >/dev/null 2>&1; then
  fail "exhausted 504 unexpectedly succeeded"
fi
[[ "$(cat "$MOCK_COUNT_FILE")" == "3" ]] || fail "transient retry ceiling changed"
[[ ! -e "$out" ]] || fail "exhausted retry left a final output"

out="$TMP/out-timeout"
reset_mock "28,000,error" "0,200,good"
fetch_verified_release "https://example.invalid/pinned" "$out" "$FIXTURE_BYTES" "$FIXTURE_SHA256" >/dev/null 2>&1
[[ "$(cat "$MOCK_COUNT_FILE")" == "2" ]] || fail "timeout did not retry"
cmp -s "$MOCK_FIXTURE" "$out" || fail "timeout retry output mismatch"

out="$TMP/out-integrity"
reset_mock "0,200,bad" "0,200,good"
if fetch_verified_release "https://example.invalid/pinned" "$out" "$FIXTURE_BYTES" "$FIXTURE_SHA256" >/dev/null 2>&1; then
  fail "integrity mismatch unexpectedly succeeded"
fi
[[ "$(cat "$MOCK_COUNT_FILE")" == "1" ]] || fail "integrity mismatch was retried"
[[ ! -e "$out" ]] || fail "integrity mismatch left a final output"

echo "GoatCounter pinned release fetch tests: PASS"
