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
	python3 -m py_compile scripts/*.py

secret-scan:
	./scripts/check-no-secrets.sh

validate: test secret-scan
