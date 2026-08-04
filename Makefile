.PHONY: test secret-scan validate

test:
	./tests/test-shell-syntax.sh
	./tests/test-safe-inventory.sh

secret-scan:
	./scripts/check-no-secrets.sh

validate: test secret-scan
