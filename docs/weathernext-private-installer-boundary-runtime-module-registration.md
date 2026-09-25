# WeatherNext verified runtime module registration

Issue: `RPi5_main#731`

The installer-boundary refresh adapter executes already-verified runtime source bytes under the fixed synthetic module name:

`deploy_executor.weather_private_installer_boundary_refresh_runtime_bootstrap`

Python import semantics require a module object to be present in `sys.modules` before module code executes. This matters for the verified runtime because it defines `@dataclass` classes whose `__module__` identity is resolved during decoration.

The #731 source path therefore:

1. keeps the existing fixed trusted dependency-root and verified runtime-byte checks;
2. creates an initialized module object with `importlib.util.module_from_spec()` for the fixed synthetic name;
3. temporarily binds only that fixed name in `sys.modules` while executing the already-verified bytes;
4. restores any prior entry or removes the temporary entry in `finally`;
5. restores `sys.path` in `finally` as before;
6. converts verified-runtime setup/load failures, before the instrumented runtime entry exists, to the fixed sanitized `runtime_setup / PRECONSUME_RUNTIME_SETUP_FAILED` telemetry pair;
7. does not change the #700 mutation budget, authorization consume point, retry/cleanup/rollback semantics, runtime target, paths, repository, argv or environment authority.

Queue `ops-workflows#107` and authorization `deploy-authorizations#46` remain non-reusable. Source merge grants no LIVE authority. A fresh read-only host/runtime reconciliation is required before any future exact-source Queue/LIVE authorization is constructed.
