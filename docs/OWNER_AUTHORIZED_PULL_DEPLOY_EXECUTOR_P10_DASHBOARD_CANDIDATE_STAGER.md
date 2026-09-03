# P10 Dashboard normal candidate stager — repaired source-only contract

Status: **source only / execution disabled / no LIVE authority**.

Issues: original `RPi5_main#341`; trust-boundary repair `RPi5_main#347`.

## Fixed root-owned input

The only accepted input is:

```text
/var/lib/rozkalns-dashboard-candidate-input/066b9a24008dd57439f9e66eae198416c4dfc590/
  source/
  candidate-manifest.json
```

The input base is `root:root 0755`. The candidate root and source directories are `root:root 0555`; files and manifest are `root:root 0444`. The input is deliberately outside `/var/lib/rozkalns-deploy-executor`, which is the unprivileged executor service StateDirectory.

The stager verifies the fixed base metadata before opening the source-specific root, uses descriptor-safe `O_NOFOLLOW` traversal, rejects symlinks and special files, requires exact manifest/tree equality, and re-hashes every candidate byte against the separately authorized exact digest.

## Output and exclusions

The staging output remains fixed at `/var/lib/rozkalns-dashboard-release-candidates/<reviewed-source-sha>`. The stager does not mutate `/opt/dashboard_RPi5`, `current`, releases, or the apply lock; it performs no PLAN/APPLY and executes no candidate JavaScript, shell, Node/package manager, Git, network client, credential API, or generic caller-selected command/path/argv/environment.

`ops/deploy/executor-operations.json` remains globally `execution_enabled=false`.

Source merge grants no staging LIVE authority. After #347 is merged and exact merged-source validation passes, candidate staging still requires a **new separate exact LIVE/root authorization**, and only after repaired handoff materialization plus read-only handoff proof succeeds.
