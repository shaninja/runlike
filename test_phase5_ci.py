from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_makefile_exposes_phase5_p0_probe_target():
    makefile = (ROOT / "Makefile").read_text()

    assert ".PHONY: test-probes-p0" in makefile
    assert "tools/run_probes.py tests/probes/p0" in makefile


def test_travis_runs_phase5_p0_probe_target():
    travis = (ROOT / ".travis.yml").read_text()

    assert "make test-probes-p0" in travis


def test_travis_runs_phase8_generated_file_checks():
    travis = (ROOT / ".travis.yml").read_text()

    assert "make check-generated" in travis


def test_makefile_exposes_phase8_refresh_support_artifacts_target():
    makefile = (ROOT / "Makefile").read_text()

    assert ".PHONY: refresh-support-artifacts" in makefile
    assert "refresh-support-artifacts: verify-docker-target" in makefile
    assert "--allow-failures" in makefile
    assert "generate-support-artifacts" in makefile
