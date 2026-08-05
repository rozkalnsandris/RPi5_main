# V06 dynamic runtime semantics findings

V06 introduces `rpi5.runtime-diff.v2` and preserves backward compatibility with the archived v1 report created by V05.

## Synthetic validation

The dynamic fixture contains:

- four rotating high-numbered socket identities with unchanged protocol/scope bucket counts;
- two rotating `veth` names with an unchanged profile multiset;
- one fixed low-port socket addition.

The v2 result preserves all raw dynamic identities but reports:

- one material change for the fixed low-port addition;
- one informational high-port churn group;
- one informational `veth` churn group.

A second fixture proves that a high-port bucket disappearance and a `veth` profile/count change escalate to `attention`.

## V05 replay interpretation

Applying the v2 policy to the V05 transition retains its exact raw observations while reducing the semantic interpretation of dynamic churn:

- the fixed UDP port `5353` addition remains material;
- the systemd state transition remains material;
- high-numbered socket rotation is grouped;
- pure `veth` name replacement is grouped;
- timer timestamp movement and limitation changes remain informational.

This does not rewrite the archived V05 v1 report or its accepted decision. Historical evidence, checksums, and review semantics remain immutable.

## Safety

V06 is an offline code and test change only. It does not collect host data, invoke Docker or systemd, alter access, deploy, remediate, or modify the current runtime baseline.
