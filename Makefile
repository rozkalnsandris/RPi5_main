.PHONY: test secret-scan public-safety validate

test:
	./tests/test-shell-syntax.sh
	bash ./tests/test-balcony-watering.sh
	bash ./tests/test-balkons-log-mqtt-credential.sh
	./tests/test-safe-inventory.sh
	./tests/test-access-model.sh
	./tests/test-runtime-baseline.sh
	./tests/test-runtime-diff.sh
	bash ./tests/test-runtime-baseline-review.sh
	bash ./tests/test-runtime-baseline-lineage.sh
	bash ./tests/test-memory-pressure-diagnostic.sh
	bash ./tests/test-memory-pressure-series.sh
	bash ./tests/test-backup-ownership.sh
	bash ./tests/test-maintenance-updater-status.sh
	bash ./tests/test-maintenance-updater-locks.sh
	bash ./tests/test-maintenance-updater-reboot.sh
	bash ./tests/test-maintenance-updater-compose-health.sh
	bash ./tests/test-maintenance-updater-compose-policy.sh
	python3 ./tests/test-maintenance-compose-policy-activation.py
	bash ./tests/test-maintenance-updater-space-policy.sh
	bash ./tests/test-maintenance-updater-origin-policy.sh
	bash ./tests/test-maintenance-updater-http-health.sh
	bash ./tests/test-maintenance-updater-apt-policy.sh
	bash ./tests/test-maintenance-updater-provenance.sh
	bash ./tests/test-maintenance-updater-source.sh
	python3 ./tests/test-maintenance-updater-source-validator.py
	python3 ./tests/test-maintenance-updater-telegram.py
	bash ./tests/test-maintenance-health.sh
	bash ./tests/test-maintenance-health-entrypoints.sh
	python3 ./tests/test-maintenance-telegram-credentials.py
	bash ./tests/test-maintenance-systemd-units.sh
	python3 ./tests/test-maintenance-systemd-cutover.py
	bash ./tests/test-maintenance-systemd-notify.sh
	bash ./tests/test-maintenance-cleanup-policy.sh
	python3 ./tests/test-maintenance-cleanup-source.py
	bash ./tests/test-maintenance-shared-lock.sh
	python3 ./tests/test-maintenance-shared-lock-source.py
	python3 ./tests/test-maintenance-lock-cutover.py
	bash ./tests/test-adguard-memory-attribution.sh
	bash ./tests/test-controlled-deploy.sh
	bash ./tests/test-cloudflare-tunnel-ownership.sh
	bash ./tests/test-hermes-tech-web-runtime.sh
	bash ./tests/test-hermes-tech-http-policy.sh
	bash ./tests/test-hermes-tech-http-policy-activation.sh
	bash ./tests/test-hermes-tech-http-policy-v20-retry.sh
	bash ./tests/test-hermes-tech-v20-git-index-owner.sh
	bash ./tests/test-rpi5-main-git-index-owner-bootstrap.sh
	bash ./tests/test-v20-operator-executable-mode.sh
	bash ./tests/test-hermes-tech-legacy-runtime-retirement.sh
	bash ./tests/test-hermes-tech-reboot-survival.sh
	bash ./tests/test-hermes-tech-rollback-container-retirement.sh
	bash ./tests/test-cloudflare-lan-origin-audit.sh
	bash ./tests/test-public-safety.sh
	python3 ./tests/test-controlled-deploy-rollback.py
	python3 ./tests/test-vscode-deploy-tasks.py
	python3 ./tests/test-v12-maintenance-conflicts.py
	python3 ./tests/test-deals-route-cutover.py
	python3 ./tests/test-github-app-readonly.py
	python3 ./tests/test-github-app-read-token.py
	python3 ./tests/test-cv-github-app-auth-boundary.py
	python3 ./tests/test-cv-deploy-readiness.py
	python3 ./tests/test-cv-pull-deploy-controller.py
	python3 ./tests/test-cv-controller-activation.py
	python3 ./tests/test-cv-classifier-host-alignment.py
	python3 ./tests/test-cv-pull-deploy-canary.py
	python3 -m py_compile scripts/*.py ops/lib/rpi5-update-telegram.py ops/lib/rpi5-maintenance-telegram.py

secret-scan:
	./scripts/check-no-secrets.sh

public-safety:
	bash ./scripts/check-public-safety.sh

validate: test secret-scan public-safety
