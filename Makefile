.PHONY: test secret-scan validate

test:
	./tests/test-shell-syntax.sh

secret-scan:
	./scripts/check-no-secrets.sh

validate: test secret-scan
