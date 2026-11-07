.PHONY: test validate validate-group api-contract targeted-legacy secret-scan public-safety

VALIDATE_GROUPS := syntax-policy weather ausmalwiese-coloring hermes-cv deploy-control cloudflare-ingress balcony host-a host-b misc

# Historical v3/v4 tests are immutable evidence; keep their legacy registration
# strings discoverable while the executable source of truth is ci/validate-groups.json.
# python3 ./tests/test-deploy-executor-weather-public-operator-upgrade-v3.py
# python3 ./tests/test-deploy-executor-weather-public-operator-upgrade-v4.py

test:
	@set -e; for group in $(VALIDATE_GROUPS); do \
		python3 ./scripts/run-validation-group.py "$$group"; \
	done

validate-group:
	@test -n "$(GROUP)" || { echo "GROUP is required" >&2; exit 2; }
	python3 ./scripts/run-validation-group.py "$(GROUP)"

api-contract:
	python3 ./tests/test-github-api-access-rollout.py

targeted-legacy:
	python3 ./scripts/targeted_legacy_regressions.py

secret-scan:
	./scripts/check-no-secrets.sh

public-safety:
	bash ./scripts/check-public-safety.sh

validate: test api-contract targeted-legacy secret-scan public-safety
