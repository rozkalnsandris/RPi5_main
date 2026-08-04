#!/usr/bin/env bash
# Shared helpers for the V01 collector and verifier.  This file is sourced.

safe_inventory_sanitize_stream() {
  LC_ALL=C awk '
    function redact_assignments(line,    lower,cursor,fragment,start,separator_end,value_start,value_end,quote,result) {
      lower=tolower(line)
      cursor=1
      result=""
      while (match(substr(lower,cursor), /(password|passwd|secret|token|api_key|apikey|credential|cookie|authorization|private_key)[a-z0-9_-]*[ \t]*[:=][ \t]*/)) {
        start=cursor+RSTART-1
        separator_end=cursor+RSTART+RLENGTH-2
        value_start=separator_end+1
        if (substr(line,value_start,10) == "[REDACTED]") {
          result=result substr(line,cursor,value_start-cursor+10)
          cursor=value_start+10
          continue
        }
        quote=substr(line,value_start,1)
        value_end=value_start
        if (quote == "\"" || quote == "\047") {
          value_end++
          while (value_end <= length(line) && substr(line,value_end,1) != quote) value_end++
          if (value_end <= length(line)) value_end++
        } else {
          while (value_end <= length(line) && substr(line,value_end,1) !~ /[ \t;,]/) value_end++
        }
        result=result substr(line,cursor,value_start-cursor) "[REDACTED]"
        cursor=value_end
      }
      return result substr(line,cursor)
    }
    /-----BEGIN [A-Za-z ]*PRIVATE KEY-----/ {
      private_block=1
      print "[REDACTED PRIVATE KEY BLOCK]"
      next
    }
    private_block {
      if ($0 ~ /-----END [A-Za-z ]*PRIVATE KEY-----/) private_block=0
      next
    }
    {
      line=redact_assignments($0)
      gsub(/gh[pousr]_[A-Za-z0-9_]+/, "[REDACTED_TOKEN]", line)
      gsub(/github_pat_[A-Za-z0-9_]+/, "[REDACTED_TOKEN]", line)
      gsub(/AKIA[0-9A-Z]+/, "[REDACTED_TOKEN]", line)
      gsub(/[Bb][Ee][Aa][Rr][Ee][Rr][ \t]+[^ \t]+/, "Bearer [REDACTED]", line)
      gsub(/[Bb][Aa][Ss][Ii][Cc][ \t]+[^ \t]+/, "Basic [REDACTED]", line)
      gsub(/(http|https):\/\/[^\/@ \t]+:[^\/@ \t]+@/, "https://[REDACTED]@", line)
      print line
    }
  '
}

safe_inventory_cap_stream() {
  local maximum_bytes="$1"
  LC_ALL=C awk -v maximum="${maximum_bytes}" '
    BEGIN { used=0 }
    {
      record=$0 ORS
      if (used >= maximum) next
      available=maximum-used
      if (length(record) > available) {
        printf "%s", substr(record,1,available)
        used=maximum
      } else {
        printf "%s", record
        used+=length(record)
      }
    }
  '
}

safe_inventory_file_has_obvious_secret() {
  local file="$1"
  LC_ALL=C awk '
    function has_unredacted_authorization(line,    lower,after) {
      lower=tolower(line)
      if (match(lower, /(bearer|basic)[ \t]+/)) {
        after=substr(line,RSTART+RLENGTH)
        return substr(after,1,10) != "[REDACTED]"
      }
      return 0
    }
    function has_unredacted_assignment(line,    lower,match_text,after) {
      lower=tolower(line)
      if (match(lower, /(password|passwd|secret|token|api_key|apikey|credential|cookie|authorization|private_key)[a-z0-9_-]*[ \t]*[:=][ \t]*/)) {
        after=substr(line,RSTART+RLENGTH)
        return substr(after,1,10) != "[REDACTED]"
      }
      return 0
    }
    /-----BEGIN [A-Za-z ]*PRIVATE KEY-----/ { found=1; exit }
    /gh[pousr]_[A-Za-z0-9_]+/ { found=1; exit }
    /github_pat_[A-Za-z0-9_]+/ { found=1; exit }
    /AKIA[0-9A-Z]+/ { found=1; exit }
    /(http|https):\/\/[^\/@ \t]+:[^\/@ \t]+@/ { found=1; exit }
    { if (has_unredacted_authorization($0) || has_unredacted_assignment($0)) { found=1; exit } }
    END { exit(found ? 0 : 1) }
  ' "${file}"
}

safe_inventory_json_string() {
  local value="$1"
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  value=${value//$'\n'/\\n}
  value=${value//$'\r'/\\r}
  value=${value//$'\t'/\\t}
  printf '"%s"' "${value}"
}
