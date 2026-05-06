import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_check_module():
    script = ROOT / "tools" / "check_generated_files.py"
    assert script.exists(), "expected tools/check_generated_files.py to exist"
    spec = importlib.util.spec_from_file_location(
        "check_generated_files", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_generated_files_reports_stale_json_and_markdown(tmp_path):
    module = load_check_module()
    expected_json = {
        "entries": [],
        "schema_version": 1,
    }
    current_json = tmp_path / "current.json"
    current_md = tmp_path / "current.md"
    current_json.write_text(json.dumps({"schema_version": 1}) + "\n")
    current_md.write_text("old\n")

    checks = [
        {
            "path": current_json,
            "expected": json.dumps(expected_json, indent=2, sort_keys=True) + "\n",
        },
        {
            "path": current_md,
            "expected": "new\n",
        },
    ]

    stale = module.find_stale_files(checks)

    assert stale == [str(current_json), str(current_md)]


def test_check_generated_files_accepts_current_files(tmp_path):
    module = load_check_module()
    current = tmp_path / "current.json"
    expected = json.dumps({"schema_version": 1}, indent=2, sort_keys=True) + "\n"
    current.write_text(expected)

    stale = module.find_stale_files([
        {
            "path": current,
            "expected": expected,
        },
    ])

    assert stale == []


def test_phase8_generated_artifacts_are_registered_for_checks():
    module = load_check_module()
    paths = [
        str(check["path"].relative_to(ROOT))
        for check in module.build_checks(ROOT)
    ]

    assert "generated/probe-work-ledger.json" in paths
    assert "generated/support-matrix.json" in paths
    assert "generated/support-matrix.md" in paths
