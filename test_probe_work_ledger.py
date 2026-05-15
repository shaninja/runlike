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


def dictionary_entry(
        entry_id,
        priority="P0",
        scope="in_scope",
        support_level=None,
        support_reason=None):
    path_coverage = {
        "container_name": "detectable",
        "stdin": "detectable",
    }
    reason = None
    if scope == "out_of_scope":
        path_coverage = {
            "container_name": "client_side_only",
            "stdin": "client_side_only",
        }
        reason = "client_side_only"
    elif scope == "blocked_by_runner":
        path_coverage = {
            "container_name": "runner_blocked",
            "stdin": "runner_blocked",
        }
        reason = "needs_special_runner"

    entry = {
        "id": entry_id,
        "path_coverage": path_coverage,
        "priority": priority,
        "scope": {
            "classification": scope,
            "reason": reason,
        },
        "warning_behavior": {
            "warn_when_detected_unsupported": scope != "out_of_scope",
        },
    }
    if support_level is not None:
        entry["support_level"] = support_level
    if support_reason is not None:
        entry["support_reason"] = support_reason
    return entry


def test_probe_work_ledger_records_status_comparison_and_remaining_work():
    module = load_ledger_module()
    entries = [
        dictionary_entry("env"),
        dictionary_entry("gpus", priority="P2", scope="blocked_by_runner"),
        dictionary_entry("help", priority="not_applicable", scope="out_of_scope"),
        dictionary_entry("label"),
        dictionary_entry("name"),
    ]
    probes = [
        {
            "id": "option-env",
            "option_id": "env",
            "paths": ["container_name", "stdin"],
        },
        {
            "id": "option-name",
            "option_id": "name",
            "paths": ["container_name", "stdin"],
        },
    ]
    probe_results = {
        "results": [
            {
                "probe_id": "option-env",
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
            {
                "probe_id": "option-name",
                "passed": True,
                "paths": {
                    "container_name": {
                        "compare": {"passed": True},
                        "passed": True,
                        "status": "passed",
                    },
                    "stdin": {
                        "compare": {"passed": True},
                        "passed": True,
                        "status": "passed",
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
        "passed": 1,
        "runner_blocked": 1,
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
            "probe_ids": ["option-env"],
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
            "option_id": "gpus",
            "path_coverage": {
                "container_name": "runner_blocked",
                "stdin": "runner_blocked",
            },
            "priority": "P2",
            "probe_ids": [],
            "probe_status": "runner_blocked",
            "remaining_work": [],
            "scope": {
                "classification": "blocked_by_runner",
                "reason": "needs_special_runner",
            },
            "support_status": "blocked_by_runner",
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
        {
            "comparison_results": {
                "container_name": "passed",
                "stdin": "passed",
            },
            "option_id": "name",
            "path_coverage": {
                "container_name": "detectable",
                "stdin": "detectable",
            },
            "priority": "P0",
            "probe_ids": ["option-name"],
            "probe_status": "passed",
            "remaining_work": [],
            "scope": {
                "classification": "in_scope",
                "reason": None,
            },
            "support_status": "supported",
            "warning_expectation": False,
        },
    ]


def test_probe_work_ledger_can_mark_passing_probe_as_known_partial():
    module = load_ledger_module()
    entries = [
        dictionary_entry(
            "gpus",
            priority="P2",
            support_level="partial",
            support_reason="needs_gpu_runner_for_runtime_execution"),
    ]
    probes = [{"id": "option-gpus", "option_id": "gpus"}]
    probe_results = {
        "results": [
            {
                "probe_id": "option-gpus",
                "passed": True,
                "paths": {
                    "container_name": {
                        "compare": {"passed": True},
                        "passed": True,
                        "status": "passed",
                    },
                    "stdin": {
                        "compare": {"passed": True},
                        "passed": True,
                        "status": "passed",
                    },
                },
            },
        ],
    }

    ledger = module.build_probe_work_ledger(entries, probes, probe_results)
    entry = ledger["entries"][0]

    assert entry["probe_status"] == "passed"
    assert entry["support_status"] == "partial"
    assert entry["support_reason"] == "needs_gpu_runner_for_runtime_execution"
    assert entry["remaining_work"] == [
        "See support reason for the known limitation."
    ]


def test_checked_in_option_probes_cover_initial_p0_options():
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
        assert entry["probe_ids"] == ["option-%s" % entry["option_id"]]
    assert len(ledger["entries"]) == len(dictionary_entries)


def test_checked_in_probe_work_ledger_is_current():
    module = load_ledger_module()
    dictionary_entries = module.load_dictionary_entries(
        ROOT / "spec" / "option-dictionary")
    probes = module.load_probe_definitions([ROOT / "tests" / "probes"])
    probe_results = module.load_probe_results(ROOT / "generated" / "probe-results.json")
    expected = module.build_probe_work_ledger(
        dictionary_entries,
        probes,
        probe_results)

    with (ROOT / "generated" / "probe-work-ledger.json").open() as ledger_file:
        checked_in = json.load(ledger_file)

    assert checked_in == expected
