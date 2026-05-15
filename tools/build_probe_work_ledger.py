#!/usr/bin/env python3

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


DEFAULT_DICTIONARY_PATH = "spec/option-dictionary"
DEFAULT_PROBE_PATH = "tests/probes"

PROBE_STATUS_KEYS = (
    "defined_unrun",
    "failed",
    "missing_probe",
    "not_applicable",
    "passed",
    "runner_blocked",
)


def load_dictionary_entries(path):
    dictionary_path = Path(path)
    entries = []
    for entry_path in sorted(dictionary_path.glob("*.json")):
        with entry_path.open() as entry_file:
            entries.append(json.load(entry_file))
    return entries


def _expand_probe_paths(paths):
    expanded = []
    for path in paths:
        probe_path = Path(path)
        if not probe_path.exists():
            raise ValueError("Probe path does not exist: %s" % probe_path)
        if probe_path.is_dir():
            expanded.extend(sorted(probe_path.glob("**/*.json")))
        else:
            expanded.append(probe_path)
    return expanded


def load_probe_definitions(paths):
    probes = []
    for probe_path in _expand_probe_paths(paths):
        with Path(probe_path).open() as probe_file:
            probes.append(json.load(probe_file))
    return probes


def load_probe_results(path):
    if not path:
        return None
    with Path(path).open() as results_file:
        return json.load(results_file)


def _probes_by_option_id(probes):
    grouped = defaultdict(list)
    for probe in probes:
        option_id = probe.get("option_id")
        if option_id:
            grouped[option_id].append(probe)
    return grouped


def _results_by_probe_id(probe_results):
    if not probe_results:
        return {}
    return {
        result.get("probe_id"): result
        for result in probe_results.get("results", [])
        if result.get("probe_id")
    }


def _comparison_status(path_result):
    compare = path_result.get("compare")
    if isinstance(compare, dict) and "passed" in compare:
        return "passed" if compare["passed"] else "failed"
    if path_result.get("passed"):
        return "passed"
    return path_result.get("status", "failed")


def _comparison_results(probe_ids, results_by_probe_id):
    comparisons = {}
    for probe_id in probe_ids:
        result = results_by_probe_id.get(probe_id)
        if not result:
            continue
        for path_name, path_result in sorted(result.get("paths", {}).items()):
            key = path_name
            if len(probe_ids) > 1:
                key = "%s:%s" % (probe_id, path_name)
            comparisons[key] = _comparison_status(path_result)
    return comparisons


def _failed_paths(comparison_results):
    return [
        path_name
        for path_name, status in sorted(comparison_results.items())
        if status != "passed"
    ]


def _probe_status(scope_classification, probe_ids, results_by_probe_id):
    if scope_classification == "out_of_scope":
        return "not_applicable"
    if scope_classification == "blocked_by_runner":
        return "runner_blocked"
    if not probe_ids:
        return "missing_probe"

    results = [
        results_by_probe_id[probe_id]
        for probe_id in probe_ids
        if probe_id in results_by_probe_id
    ]
    if not results:
        return "defined_unrun"
    if len(results) != len(probe_ids):
        return "failed"
    if all(result.get("passed") for result in results):
        return "passed"
    return "failed"


def _support_status(
        scope_classification,
        probe_status,
        comparison_results,
        support_level=None):
    if scope_classification == "out_of_scope":
        return "out_of_scope"
    if scope_classification == "blocked_by_runner":
        return "blocked_by_runner"
    if probe_status == "passed":
        if support_level == "partial":
            return "partial"
        return "supported"
    if (
            probe_status == "failed"
            and any(status == "passed" for status in comparison_results.values())):
        return "partial"
    return "unsupported"


def _warning_expectation(dictionary_entry, support_status):
    if support_status in ("out_of_scope", "supported"):
        return False
    return dictionary_entry["warning_behavior"]["warn_when_detected_unsupported"]


def _remaining_work(probe_status, comparison_results, support_status=None):
    if support_status == "partial" and probe_status == "passed":
        return ["See support reason for the known limitation."]
    if probe_status in ("not_applicable", "passed", "runner_blocked"):
        return []
    if probe_status == "missing_probe":
        return ["Add focused probe definition."]
    if probe_status == "defined_unrun":
        return ["Run focused probe definition."]

    failed_paths = _failed_paths(comparison_results)
    if failed_paths:
        return ["Fix failing probe paths: %s." % ", ".join(failed_paths)]
    return ["Inspect failing probe result."]


def _empty_summary():
    return dict((key, 0) for key in PROBE_STATUS_KEYS)


def _summarize(entries):
    summary = _empty_summary()
    for entry in entries:
        summary[entry["probe_status"]] += 1
    return summary


def build_probe_work_ledger(dictionary_entries, probes, probe_results=None):
    probes_by_option_id = _probes_by_option_id(probes)
    results_by_probe_id = _results_by_probe_id(probe_results)
    ledger_entries = []

    for dictionary_entry in sorted(
            dictionary_entries,
            key=lambda entry: entry["id"]):
        option_id = dictionary_entry["id"]
        scope = dictionary_entry["scope"]
        scope_classification = scope["classification"]
        support_level = dictionary_entry.get("support_level")
        option_probes = probes_by_option_id.get(option_id, [])
        probe_ids = sorted(probe["id"] for probe in option_probes)
        comparison_results = _comparison_results(
            probe_ids,
            results_by_probe_id)
        probe_status = _probe_status(
            scope_classification,
            probe_ids,
            results_by_probe_id)

        support_status = _support_status(
            scope_classification,
            probe_status,
            comparison_results,
            support_level=support_level)
        ledger_entry = {
            "comparison_results": comparison_results,
            "option_id": option_id,
            "path_coverage": dictionary_entry["path_coverage"],
            "priority": dictionary_entry["priority"],
            "probe_ids": probe_ids,
            "probe_status": probe_status,
            "remaining_work": _remaining_work(
                probe_status,
                comparison_results,
                support_status=support_status),
            "scope": scope,
            "support_status": support_status,
            "warning_expectation": _warning_expectation(
                dictionary_entry,
                support_status),
        }
        if support_level is not None:
            ledger_entry["support_level"] = support_level
        if dictionary_entry.get("support_notes"):
            ledger_entry["support_notes"] = dictionary_entry["support_notes"]
        if dictionary_entry.get("support_reason"):
            ledger_entry["support_reason"] = dictionary_entry["support_reason"]
        ledger_entries.append(ledger_entry)

    return {
        "entries": ledger_entries,
        "schema_version": 1,
        "summary": _summarize(ledger_entries),
    }


def write_probe_work_ledger(path, ledger):
    output_path = Path(path)
    if output_path.parent:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as output_file:
        json.dump(ledger, output_file, indent=2, sort_keys=True)
        output_file.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the per-option probe work ledger.")
    parser.add_argument(
        "--dictionary",
        default=DEFAULT_DICTIONARY_PATH,
        help="Path to spec/option-dictionary.")
    parser.add_argument(
        "--probes",
        action="append",
        default=[],
        help="Probe JSON file or directory. May be passed multiple times.")
    parser.add_argument(
        "--probe-results",
        help="Optional structured probe results JSON.")
    parser.add_argument(
        "--output",
        help="Optional path to write the ledger JSON.")
    args = parser.parse_args(argv)

    probe_paths = args.probes or [DEFAULT_PROBE_PATH]
    try:
        ledger = build_probe_work_ledger(
            load_dictionary_entries(args.dictionary),
            load_probe_definitions(probe_paths),
            load_probe_results(args.probe_results))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1

    output = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    if args.output:
        write_probe_work_ledger(args.output, ledger)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
