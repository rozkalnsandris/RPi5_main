# V08 memory-pressure diagnostic findings

V08 adds the repository tooling for the first read-only diagnosis pass of issue #5. No real host bundle is collected or interpreted in this implementation PR.

## Implemented safety

- non-root execution only;
- output restricted to ignored repository evidence/export trees;
- no symlink, hard-link, special-file or world-writable artifacts;
- bounded per-command time and per-section bytes;
- exact fixed command arguments;
- no process arguments, environments, Docker inspect, DNS queries or raw application configuration;
- redaction of secret-like assignments, authorization values, URLs with credentials, IP/MAC values and long hexadecimal runtime identifiers;
- deterministic report recomputation and full checksum coverage.

## Synthetic validation

The fixture models low MemAvailable, retained swap and a small swap-out/major-fault delta. It proves deterministic `attention` classification, process-name RSS aggregation, safe container-memory parsing, kernel identifier redaction, missing-Docker handling and strict tamper rejection.

Additional negative tests cover root execution, output escape, symlink output, report modification, secret-like content, raw long identifiers and FIFO artifacts.

## Remaining work

After merge, run the collector on RPi5 in the normal unprivileged context and verify the bundle. The first real evidence determines whether repeated idle/busy sampling is needed and whether issue #5 can conclude “retained swap without active pressure” or needs a separately reviewed service-specific investigation.
