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
