import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_ledger_module():
    script = ROOT / "tools" / "build_probe_work_ledger.py"
    assert script.exists(), "expected tools/build_probe_work_ledger.py to exist"
    spec = importlib.util.spec_from_file_location(
        "build_probe_work_ledger", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dictionary_entry(entry_id, priority="P0", scope="in_scope"):
    path_coverage = {
        "container_name": "detectable",
        "stdin": "detectable",
    }
    if scope == "out_of_scope":
        path_coverage = {
            "container_name": "client_side_only",
            "stdin": "client_side_only",
        }

    return {
        "id": entry_id,
        "path_coverage": path_coverage,
        "priority": priority,
        "scope": {
            "classification": scope,
            "reason": "client_side_only" if scope == "out_of_scope" else None,
        },
        "warning_behavior": {
            "warn_when_detected_unsupported": scope == "in_scope",
        },
    }


def test_probe_work_ledger_records_status_comparison_and_remaining_work():
    module = load_ledger_module()
    entries = [
        dictionary_entry("env"),
        dictionary_entry("help", priority="not_applicable", scope="out_of_scope"),
        dictionary_entry("label"),
    ]
    probes = [
        {
            "id": "p0-env",
            "option_id": "env",
            "paths": ["container_name", "stdin"],
        },
    ]
    probe_results = {
        "results": [
            {
                "probe_id": "p0-env",
                "passed": False,
                "paths": {
                    "container_name": {
                        "compare": {"passed": True},
                        "passed": True,
                        "status": "passed",
                    },
                    "stdin": {
                        "compare": {"passed": False},
                        "passed": False,
                        "status": "failed",
                    },
                },
            },
        ],
    }

    ledger = module.build_probe_work_ledger(entries, probes, probe_results)

    assert ledger["summary"] == {
        "defined_unrun": 0,
        "failed": 1,
        "missing_probe": 1,
        "not_applicable": 1,
        "passed": 0,
        "runner_blocked": 0,
    }
    assert ledger["entries"] == [
        {
            "comparison_results": {
                "container_name": "passed",
                "stdin": "failed",
            },
            "option_id": "env",
            "path_coverage": {
                "container_name": "detectable",
                "stdin": "detectable",
            },
            "priority": "P0",
            "probe_ids": ["p0-env"],
            "probe_status": "failed",
            "remaining_work": ["Fix failing probe paths: stdin."],
            "scope": {
                "classification": "in_scope",
                "reason": None,
            },
            "support_status": "partial",
            "warning_expectation": True,
        },
        {
            "comparison_results": {},
            "option_id": "help",
            "path_coverage": {
                "container_name": "client_side_only",
                "stdin": "client_side_only",
            },
            "priority": "not_applicable",
            "probe_ids": [],
            "probe_status": "not_applicable",
            "remaining_work": [],
            "scope": {
                "classification": "out_of_scope",
                "reason": "client_side_only",
            },
            "support_status": "out_of_scope",
            "warning_expectation": False,
        },
        {
            "comparison_results": {},
            "option_id": "label",
            "path_coverage": {
                "container_name": "detectable",
                "stdin": "detectable",
            },
            "priority": "P0",
            "probe_ids": [],
            "probe_status": "missing_probe",
            "remaining_work": ["Add focused probe definition."],
            "scope": {
                "classification": "in_scope",
                "reason": None,
            },
            "support_status": "unsupported",
            "warning_expectation": True,
        },
    ]


def test_checked_in_phase5_seed_probes_cover_initial_p0_options():
    module = load_ledger_module()
    dictionary_entries = module.load_dictionary_entries(
        ROOT / "spec" / "option-dictionary")
    probes = module.load_probe_definitions([ROOT / "tests" / "probes"])

    ledger = module.build_probe_work_ledger(dictionary_entries, probes)
    entries = {
        entry["option_id"]: entry
        for entry in ledger["entries"]
    }

    p0_in_scope = [
        entry for entry in ledger["entries"]
        if (
            entry["priority"] == "P0"
            and entry["scope"]["classification"] == "in_scope"
        )
    ]
    assert len(p0_in_scope) == 39
    for entry in p0_in_scope:
        assert entry["probe_status"] == "defined_unrun"
        assert entry["probe_ids"] == ["p0-%s" % entry["option_id"]]
    assert len(ledger["entries"]) == len(dictionary_entries)


def test_checked_in_probe_work_ledger_is_current():
    module = load_ledger_module()
    dictionary_entries = module.load_dictionary_entries(
        ROOT / "spec" / "option-dictionary")
    probes = module.load_probe_definitions([ROOT / "tests" / "probes"])
    expected = module.build_probe_work_ledger(dictionary_entries, probes)

    with (ROOT / "generated" / "probe-work-ledger.json").open() as ledger_file:
        checked_in = json.load(ledger_file)

    assert checked_in == expected
