.PHONY: test secret-scan validate

test:
	./tests/test-shell-syntax.sh
	./tests/test-safe-inventory.sh
	./tests/test-access-model.sh
	./tests/test-runtime-baseline.sh

secret-scan:
	./scripts/check-no-secrets.sh

validate: test secret-scan
