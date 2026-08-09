.PHONY: test secret-scan public-safety validate

test:
	./tests/test-shell-syntax.sh
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
	bash ./tests/test-maintenance-updater-space-policy.sh
	bash ./tests/test-maintenance-updater-origin-policy.sh
	bash ./tests/test-maintenance-updater-http-health.sh
	bash ./tests/test-maintenance-updater-provenance.sh
	python3 ./tests/test-maintenance-updater-source-validator.py
	bash ./tests/test-adguard-memory-attribution.sh
	bash ./tests/test-controlled-deploy.sh
	bash ./tests/test-cloudflare-tunnel-ownership.sh
	bash ./tests/test-hermes-tech-web-runtime.sh
	bash ./tests/test-hermes-tech-http-policy.sh
	bash ./tests/test-hermes-tech-http-policy-activation.sh
	bash ./tests/test-hermes-tech-v20-retry.sh
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
	python3 -m py_compile scripts/*.py

secret-scan:
	./scripts/check-no-secrets.sh

public-safety:
	bash ./scripts/check-public-safety.sh

validate: test secret-scan public-safety
