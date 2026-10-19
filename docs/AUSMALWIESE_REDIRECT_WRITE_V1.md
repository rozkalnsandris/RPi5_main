# Ausmalwiese legacy 301 bounded write path (#1114)

**Status: SOURCE ONLY · not installed · no credential access · no Cloudflare request · no LIVE authority.**

This source closes the final operator gap for parent issue #996. It does not
perform the redirect. It defines one future fail-closed write path that can be
installed and invoked only under a separate exact COMPOSITE LIVE authorization
after the earlier Stats and sitemap stages have passed.

## Exact redirect

The only desired rule is:

- zone: `rozkalns.net`;
- phase: `http_request_dynamic_redirect`;
- expression: `http.host eq "coloring.rozkalns.net"`;
- action: `redirect`;
- dynamic target:
  `concat("https://ausmalwiese.de", http.request.uri.path)`;
- status: `301`;
- preserve query string: `true`;
- enabled: `true`;
- ref: `ausmalwiese_legacy_301`.

This follows Cloudflare's documented different-host redirect pattern: dynamic
target expression for the new origin plus the original request path, with
query preservation enabled.

## Reuse of the existing #996 read boundary

`scripts/ausmalwiese_redirect_write_v1.py` imports and reuses:

- `ausmalwiese_redirect_inventory.inspect_redirect_inventory()` for the
  fresh three-GET zone/ruleset/phase inventory;
- the existing anchored-host scope classifier from that inventory module;
- `ausmalwiese_redirect_get_adapter.FixedZoneGetAdapter` for the exact
  GET allowlist and in-memory credential transport.

It does not create a second redirect-scope parser.

`preflight()` emits only a sanitized baseline SHA-256 and one operation
class: `CREATE_RULESET`, `ADD_RULE`, `UPDATE_RULE`, or `NOOP`.
It never returns zone IDs, ruleset IDs, rule IDs, raw rules, or credentials.

## One-write decision

A future authorized invocation must supply the exact expected preflight
baseline SHA-256. The source re-reads the provider state and stops before any
write if that baseline changed.

Only one provider write is possible:

1. phase entrypoint absent:
   `POST /zones/{zone}/rulesets` with the exact zone/phase and one desired
   rule;
2. entrypoint present with no exact legacy-host rule:
   `POST /zones/{zone}/rulesets/{ruleset}/rules` with only the desired rule;
3. exactly one exact legacy-host rule exists but differs:
   `PATCH /zones/{zone}/rulesets/{ruleset}/rules/{rule}` with the complete
   desired rule definition;
4. already exact:
   no provider write.

An active ambiguous expression or more than one exact legacy-host rule is a
pre-write STOP. Unknown write methods, paths or bodies are rejected by the
transport itself. Dynamic ruleset and rule IDs are accepted only when they
match the immediately observed phase entrypoint and exact legacy-host rule
identity from the same transport's pre-write read.

The one-write budget is consumed immediately before network dispatch. Any
timeout, transport exception, unexpected response, or ambiguous provider
outcome after that point is terminal for the invocation. There is no retry,
rollback, cleanup, alternate endpoint, or fallback transport.

## Post-write proof

After the single write, the source runs the existing sanitized inventory again
and requires:

- exactly one active exact legacy-host rule with the full desired redirect
  semantics;
- no active ambiguous redirect rule;
- unrelated rule semantics unchanged;
- existing entrypoint identity unchanged for add/update;
- existing rule identity unchanged for update;
- provider inventory baseline changed after mutation.

A no-op instead requires a stable baseline.

The returned receipt contains only operation, mutation_started, and pre/post
inventory SHA-256 values.

## Protected transport boundary

`FixedZoneRedirectWriteTransport` accepts an exact 32-hex zone ID and an
in-memory credential. It inherits the existing GET-only no-proxy/no-redirect
transport and exposes at most one write matching one of the three exact
method/path/body shapes above.

There is intentionally:

- no CLI;
- no argv/env/stdin credential source;
- no token provisioning;
- no permission change;
- no installed runtime entrypoint;
- no source-side owner authorization issuer.

A later installed caller or equivalent reviewed packaging must bind exact
merged source bytes, exact zone identity, an independently authorized
`Dynamic URL Redirects Write` credential, and the fresh owner-approved
baseline without exposing credential content.

## Parent #996 flow

This source preserves the simplified owner-visible sequence:

`MERGE -> one COMPOSITE LIVE`

Inside that future LIVE envelope the ordered technical stages remain:

`Gate A -> Stats Worker -> sitemap -> legacy 301`

The redirect stage must not run if an earlier stage fails acceptance. This
source grants no authority for any of those stages.

## References

Cloudflare:
- https://developers.cloudflare.com/rules/url-forwarding/examples/redirect-all-different-hostname/
- https://developers.cloudflare.com/rules/url-forwarding/single-redirects/create-api/
- https://developers.cloudflare.com/ruleset-engine/rulesets-api/add-rule/
- https://developers.cloudflare.com/ruleset-engine/rulesets-api/update-rule/
- https://developers.cloudflare.com/ruleset-engine/rulesets-api/create/

Contract:
`ops/contracts/ausmalwiese-redirect-write-v1.json`.

Offline test:
`python3 tests/test-ausmalwiese-redirect-write-v1.py`.
