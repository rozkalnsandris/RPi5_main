.PHONY: test secret-scan validate

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
	bash ./tests/test-adguard-memory-attribution.sh
	bash ./tests/test-controlled-deploy.sh
	bash ./tests/test-cloudflare-tunnel-ownership.sh
	bash ./tests/test-hermes-tech-web-runtime.sh
	bash ./tests/test-hermes-tech-http-policy.sh
	bash ./tests/test-hermes-tech-http-policy-activation.sh
	bash ./tests/test-hermes-tech-http-policy-v20-retry.sh
	bash ./tests/test-hermes-tech-legacy-runtime-retirement.sh
	bash ./tests/test-hermes-tech-reboot-survival.sh
	bash ./tests/test-hermes-tech-rollback-container-retirement.sh
	bash ./tests/test-cloudflare-lan-origin-audit.sh
	python3 ./tests/test-controlled-deploy-rollback.py
	python3 ./tests/test-vscode-deploy-tasks.py
	python3 ./tests/test-v12-maintenance-conflicts.py
	python3 ./tests/test-deals-route-cutover.py
	python3 -m py_compile scripts/*.py

secret-scan:
	./scripts/check-no-secrets.sh

validate: test secret-scan
