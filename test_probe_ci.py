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


def test_travis_runs_option_probe_target():
    travis = (ROOT / ".travis.yml").read_text()

    assert "make test-probes-options" in travis


def test_travis_runs_phase8_generated_file_checks():
    travis = (ROOT / ".travis.yml").read_text()

    assert "make check-generated" in travis


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
