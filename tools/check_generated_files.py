#!/usr/bin/env python3

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module(script_path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, str(script_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json_dump(payload):
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def build_checks(root=ROOT):
    root = Path(root)
    ledger_module = _load_module(
        root / "tools" / "build_probe_work_ledger.py",
        "build_probe_work_ledger")
    matrix_module = _load_module(
        root / "tools" / "build_support_matrix.py",
        "build_support_matrix")

    dictionary_entries = ledger_module.load_dictionary_entries(
        root / "spec" / "option-dictionary")
    probes = ledger_module.load_probe_definitions([
        root / "tests" / "probes",
    ])
    ledger = ledger_module.build_probe_work_ledger(
        dictionary_entries,
        probes)

    matrix_dictionary_entries = matrix_module.load_dictionary_entries(
        root / "spec" / "option-dictionary")
    matrix_probes = matrix_module.load_probe_definitions([
        root / "tests" / "probes",
    ])
    matrix = matrix_module.build_support_matrix(
        matrix_dictionary_entries,
        matrix_probes,
        matrix_module.load_probe_results(root / "generated" / "probe-results.json"),
        target=matrix_module.load_target(root / "spec" / "current-target.json"))

    return [
        {
            "expected": _json_dump(ledger),
            "path": root / "generated" / "probe-work-ledger.json",
        },
        {
            "expected": _json_dump(matrix),
            "path": root / "generated" / "support-matrix.json",
        },
        {
            "expected": matrix_module.render_support_matrix_markdown(matrix),
            "path": root / "generated" / "support-matrix.md",
        },
    ]


def find_stale_files(checks):
    stale = []
    for check in checks:
        path = Path(check["path"])
        if not path.exists() or path.read_text() != check["expected"]:
            stale.append(str(path))
    return stale


def main(argv=None):
    stale = find_stale_files(build_checks(ROOT))
    if stale:
        print("Generated files are stale:", file=sys.stderr)
        for path in stale:
            print("  %s" % path, file=sys.stderr)
        print(
            "Run `make generate-support-artifacts` after updating generated inputs.",
            file=sys.stderr)
        return 1
    print("Generated files are current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
