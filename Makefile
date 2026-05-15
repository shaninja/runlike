CUR_VER = $(shell ./current_version.py)
SHELL := bash
DOCKER_API_VERSION ?= 1.44
export DOCKER_API_VERSION

.PHONY: build
build:
	docker build -t assaflavie/runlike .
	docker tag assaflavie/runlike assaflavie/runlike:$(CUR_VER)

.PHONY: rebuild
rebuild:
	docker build -t assaflavie/runlike --no-cache=true .
	docker tag assaflavie/runlike assaflavie/runlike:$(CUR_VER)

.PHONY: push
push: rebuild
	docker push assaflavie/runlike
	docker push assaflavie/runlike:$(CUR_VER)

.PHONY: test
test:
	poetry run pytest

.PHONY: test-probes-options
test-probes-options:
	poetry run python tools/run_probes.py tests/probes/options --output $${PROBE_RESULTS:-/tmp/runlike-option-probe-results.json}

.PHONY: generate-probe-results
generate-probe-results:
	poetry run python tools/run_probes.py tests/probes --output generated/probe-results.json

.PHONY: generate-support-artifacts
generate-support-artifacts:
	poetry run python tools/build_probe_work_ledger.py --probe-results generated/probe-results.json --output generated/probe-work-ledger.json
	poetry run python tools/build_support_matrix.py

.PHONY: refresh-support-artifacts
refresh-support-artifacts: verify-docker-target
	poetry run python tools/run_probes.py tests/probes --output generated/probe-results.json --allow-failures
	$(MAKE) generate-support-artifacts
	$(MAKE) check-generated

.PHONY: check-generated
check-generated:
	poetry run python tools/check_generated_files.py

.PHONY: check-manifest-source
check-manifest-source: verify-docker-target
	poetry run python tools/dump_docker_option_manifest.py --check

.PHONY: verify-docker-target
verify-docker-target:
	poetry run python tools/verify_docker_target.py

.PHONY: pypi
pypi:
	poetry build
	poetry publish -u __token__ -p $(POETRY_PYPI_TOKEN_PYPI)

.PHONY: release
release: push pypi
