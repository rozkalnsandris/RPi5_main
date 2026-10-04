# WeatherNext private GCS simple canary

Status: **SOURCE ONLY / ONE LIVE CANARY GATE NEXT**  
Issue: `RPi5_main#843`

## Outcome

The previous multi-step GCS prerequisite rollout is retired for the simple private
Weather app.

The canonical Weather source now contains the bounded one-shot command:

```text
python -m rozkalns_weather weathernext-gcs-canary --init <exact-UTC-init>
```

The RPi5 side no longer needs a separate GCS host installer, Weather application
staging step, separate GCS runtime materialization, credential copy, or
GCS-specific auth-binding publication before the canary.

## Runtime shape

A future separately authorized LIVE canary is intentionally small:

```text
exact current Weather image
-> one ephemeral docker run --rm
-> one fixed root-owned host credential file
   /var/lib/rpi5-deploy/weathernext-google.json
   mounted read-only at /run/secrets/weathernext-google.json
-> weathernext-gcs-canary --init <exact-UTC-init>
-> sanitized PASS/FAIL evidence
```

There is no database mount and no production persistence.

The Weather command itself fixes the canary to:

- `station_05480`;
- six forecast hours;
- WeatherNext 3 precomputed statistics GCS/Zarr;
- no automatic retry;
- no alternate dataset fallback;
- no production write.

## Retired prerequisite chain

These old prerequisite operations are no longer part of the canonical GCS path:

- `rpi5.weathernext-private-gcs-backend.install.v1`;
- `rpi5.weathernext-private-application-stage.v1`;
- `rozkalns-weather.weathernext-private-gcs-runtime-materialization.v1`;
- `rpi5.weathernext-private-gcs-auth-binding.v1`.

They are removed from the privileged dispatcher allowlist by this source change.

Historical implementation modules may remain temporarily for provenance and
safe later cleanup, but they are not canonical execution routes.

## Authorization boundary

Source merge performs no RPi5, Docker, credential, Google/GCS or production-data
mutation.

Before the future canary:

1. resolve the exact current merged Weather `main` SHA and successful required CI;
2. resolve the exact immutable Weather image for that source;
3. verify only sanitized metadata for the fixed host credential file
   `/var/lib/rpi5-deploy/weathernext-google.json`: regular file, root:root,
   mode `0600`, one link, no symlink, non-empty and <= 64 KiB;
4. obtain a separate owner LIVE authorization for the exact ephemeral canary.

Credential contents must never be printed or copied into GitHub evidence.

Any error or drift after the authorized container execution begins is fail-closed:
STOP, with no retry, cleanup, credential substitution or alternate path unless
separately authorized.


## Credential file boundary

The host-side source is fixed to
`/var/lib/rpi5-deploy/weathernext-google.json`. The caller cannot substitute a
different source or container target. The file must be root-owned, mode
`0600`, a single-link regular file, not a symlink, non-empty and no larger than
64 KiB.

The canary receives this file only through a read-only bind mount. Provisioning
or replacing the host credential is a separate credential mutation and requires
an exact owner LIVE authorization. The credential payload is never eligible for
agent output, GitHub evidence or logs.
