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

.PHONY: test-probes-p0
test-probes-p0:
	poetry run python tools/run_probes.py tests/probes/p0 --output $${PROBE_RESULTS:-/tmp/runlike-p0-probe-results.json}

.PHONY: verify-docker-target
verify-docker-target:
	poetry run python tools/verify_docker_target.py

.PHONY: pypi
pypi:
	poetry build
	poetry publish -u __token__ -p $(POETRY_PYPI_TOKEN_PYPI)

.PHONY: release
release: push pypi
