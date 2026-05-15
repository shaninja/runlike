from pathlib import Path


ROOT = Path(__file__).resolve().parent


def makefile_target_recipe(makefile, target):
    lines = makefile.splitlines()
    target_prefix = "%s:" % target
    start = [
        index
        for index, line in enumerate(lines)
        if line.startswith(target_prefix)
    ][0] + 1
    recipe = []
    for line in lines[start:]:
        if line and not line.startswith("\t") and not line.startswith(" "):
            break
        recipe.append(line)
    return "\n".join(recipe)


def test_makefile_exposes_option_probe_target():
    makefile = (ROOT / "Makefile").read_text()

    assert ".PHONY: test-probes-options" in makefile
    assert "tools/run_probes.py tests/probes/options" in makefile


def test_github_actions_installs_pinned_docker_target():
    workflow = (ROOT / ".github" / "workflows" / "ci.yaml").read_text()

    assert "runs-on: ubuntu-22.04" in workflow
    assert 'DOCKER_API_VERSION: "1.44"' in workflow
    assert "./tools/install_pinned_docker.sh" in workflow


def test_github_actions_uses_node24_action_versions():
    workflow = (ROOT / ".github" / "workflows" / "ci.yaml").read_text()

    assert "actions/checkout@v6" in workflow
    assert "actions/setup-python@v6" in workflow


def test_github_actions_runs_option_probe_target():
    workflow = (ROOT / ".github" / "workflows" / "ci.yaml").read_text()

    assert "make test-probes-options" in workflow


def test_github_actions_runs_phase8_generated_file_checks():
    workflow = (ROOT / ".github" / "workflows" / "ci.yaml").read_text()

    assert "make check-generated" in workflow


def test_makefile_exposes_manifest_source_check_target():
    makefile = (ROOT / "Makefile").read_text()
    recipe = makefile_target_recipe(makefile, "check-manifest-source")

    assert ".PHONY: check-manifest-source" in makefile
    assert "check-manifest-source: verify-docker-target" in makefile
    assert "tools/dump_docker_option_manifest.py --check" in recipe


def test_github_actions_runs_manifest_source_check():
    workflow = (ROOT / ".github" / "workflows" / "ci.yaml").read_text()

    assert "make check-manifest-source" in workflow


def test_github_actions_build_job_does_not_require_dockerhub_credentials():
    workflow = (ROOT / ".github" / "workflows" / "ci.yaml").read_text()

    assert "docker/login-action" not in workflow
    assert "DOCKERHUB_TOKEN" not in workflow


def test_github_actions_does_not_run_legacy_fixture_dump_on_failure():
    workflow = (ROOT / ".github" / "workflows" / "ci.yaml").read_text()

    assert "inspect_fixtures.sh" not in workflow


def test_makefile_exposes_phase8_refresh_support_artifacts_target():
    makefile = (ROOT / "Makefile").read_text()
    generate_probe_results = makefile_target_recipe(
        makefile,
        "generate-probe-results")
    refresh_support_artifacts = makefile_target_recipe(
        makefile,
        "refresh-support-artifacts")

    assert ".PHONY: refresh-support-artifacts" in makefile
    assert "refresh-support-artifacts: verify-docker-target" in makefile
    assert "--allow-failures" not in generate_probe_results
    assert "--allow-failures" in refresh_support_artifacts
    assert "$(MAKE) generate-support-artifacts" in refresh_support_artifacts
