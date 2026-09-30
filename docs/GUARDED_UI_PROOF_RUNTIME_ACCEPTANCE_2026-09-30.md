# Guarded UI proof runtime acceptance — 2026-09-30

Status: ACCEPTED HISTORICAL RUNTIME EVIDENCE  
Issue: #783  
Source repository: `rozkalnsandris/RPi5_main`

## Source identity

Accepted source anchor at the time of proof:

- `RPi5_main/main = ccc5b9b8d74b9cb662895b7a222a212fc0a6be43`
- launcher source: `ops/bin/ui-proof-guarded`
- launcher Git blob: `93511d0879728418d29daa9117e003bef92c9668`

This receipt does not make that commit or blob a standing runtime authorization. Future consequential runtime work still requires fresh source/runtime validation and applicable current authority.

## Host activation evidence

Owner-authorized minimum-sufficient RPi5 checks established that:

- the guarded launcher was installed as the current user's regular executable with the reviewed Git blob identity;
- the lifecycle guard and `ui-proof` renderer were present and executable;
- lifecycle health reported `PASS` with zero active, stale, or ambiguous owned sessions.

The source/runtime boundary remains unchanged: merging source never proves installation by itself. This section records only the dated accepted host observation.

## Clean-baseline reconciliation

A separately owner-authorized cleanup retired historical unrelated browser leftovers and established a clean browser-process baseline of `0`.

The cleanup did not rely on broad process-name cleanup. Its one-shot authorization was consumed and is not reusable.

## Guarded smoke proof

A separately owner-authorized smoke run used the canonical guarded launcher against `https://example.com`.

Accepted result:

- guarded launcher return code: `0`;
- pre-run browser-process count: `0`;
- standard desktop/mobile/DOM/log/manifest evidence was produced;
- post-run browser-process count: `0`;
- post-run lifecycle health: `PASS`;
- active owned sessions after run: `0`;
- stale owned sessions after run: `0`;
- ambiguous owned records after run: `0`.

This proves the intended bounded lifecycle behavior for the accepted test point:

```text
clean browser baseline (0)
-> guarded ui-proof run
-> clean browser baseline (0)
```

No stale cleanup fallback or broad browser cleanup was required after the smoke run.

## Authority boundary

This receipt is evidence, not authority.

It does not grant standing permission for browser execution, process cleanup, stale-session recovery, service/container changes, packages, scheduler/systemd changes, networking, credentials, protected data, or any other LIVE mutation.

`docs/VISUAL_VERIFICATION.md` remains the canonical operational contract. When current runtime state matters, observe it freshly rather than inferring it from this historical acceptance receipt.
