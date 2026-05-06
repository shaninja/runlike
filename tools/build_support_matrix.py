#!/usr/bin/env python3

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


DEFAULT_DICTIONARY_PATH = "spec/option-dictionary"
DEFAULT_PROBE_PATH = "tests/probes"
DEFAULT_PROBE_RESULTS_PATH = "generated/probe-results.json"
DEFAULT_TARGET_PATH = "spec/current-target.json"
DEFAULT_JSON_OUTPUT_PATH = "generated/support-matrix.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = "generated/support-matrix.md"

INPUT_PATHS = ("container_name", "stdin")
SUPPORT_STATUSES = (
    "blocked_by_runner",
    "out_of_scope",
    "partial",
    "supported",
    "unsupported",
)
MARKDOWN_STATUS_LABELS = {
    "blocked_by_runner": "needs special runner",
}


def load_json(path):
    with Path(path).open() as json_file:
        return json.load(json_file)


def load_target(path=DEFAULT_TARGET_PATH):
    return load_json(path)


def load_probe_results(path=DEFAULT_PROBE_RESULTS_PATH):
    return load_json(path)


def load_dictionary_entries(path=DEFAULT_DICTIONARY_PATH):
    dictionary_path = Path(path)
    entries = []
    for entry_path in sorted(dictionary_path.glob("*.json")):
        entries.append(load_json(entry_path))
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
        probes.append(load_json(probe_path))
    return probes


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
    if not path_result:
        return "defined_unrun"
    compare = path_result.get("compare")
    if isinstance(compare, dict) and "passed" in compare:
        return "passed" if compare["passed"] else "failed"
    status = path_result.get("status")
    if status in ("partial", "passed"):
        return status
    if path_result.get("passed"):
        return "passed"
    return "failed"


def _path_probe_statuses(path_name, probe_ids, results_by_probe_id):
    statuses = []
    for probe_id in probe_ids:
        result = results_by_probe_id.get(probe_id)
        if not result:
            statuses.append("defined_unrun")
            continue
        statuses.append(
            _comparison_status(result.get("paths", {}).get(path_name)))
    return statuses


def _collapse_path_statuses(statuses):
    if not statuses:
        return "missing_probe"
    if all(status == "passed" for status in statuses):
        return "passed"
    if any(status == "passed" for status in statuses):
        return "partial"
    if any(status == "partial" for status in statuses):
        return "partial"
    if all(status == "defined_unrun" for status in statuses):
        return "defined_unrun"
    return "failed"


def _support_status(scope_classification, path_coverage, probe_status):
    if scope_classification == "out_of_scope":
        return "out_of_scope"
    if scope_classification == "blocked_by_runner":
        return "blocked_by_runner"
    if path_coverage in ("client_side_only", "not_observable"):
        return "out_of_scope"
    if path_coverage == "runner_blocked":
        return "blocked_by_runner"
    if probe_status == "passed":
        return "supported"
    if probe_status == "partial":
        return "partial"
    return "unsupported"


def _probe_status(scope_classification, path_coverage, collapsed_status):
    if scope_classification == "out_of_scope":
        return "not_applicable"
    if scope_classification == "blocked_by_runner":
        return "runner_blocked"
    if path_coverage in ("client_side_only", "not_observable"):
        return "not_applicable"
    if path_coverage == "runner_blocked":
        return "runner_blocked"
    return collapsed_status


def _comparison_summary(path_coverage, probe_status):
    if probe_status in ("not_applicable", "runner_blocked"):
        return path_coverage
    return probe_status


def _remaining_work(status, probe_status):
    if status in ("blocked_by_runner", "out_of_scope", "supported"):
        return []
    if probe_status == "missing_probe":
        return ["Add focused probe definition."]
    if probe_status == "defined_unrun":
        return ["Run focused probe definition."]
    if status == "partial":
        return ["Complete failing or unrun probe paths."]
    return ["Fix failing probe path."]


def _matrix_summary(rows):
    by_status = dict((status, 0) for status in SUPPORT_STATUSES)
    by_path = {}
    by_option = defaultdict(dict)

    for row in rows:
        by_status[row["status"]] += 1
        by_path.setdefault(
            row["path"],
            dict((status, 0) for status in SUPPORT_STATUSES))
        by_path[row["path"]][row["status"]] += 1
        by_option[row["option_id"]][row["path"]] = row

    return {
        "by_path": by_path,
        "by_option_status": _option_summary(by_option),
        "by_status": by_status,
        "total_rows": len(rows),
    }


def build_support_matrix(
        dictionary_entries,
        probes,
        probe_results=None,
        target=None):
    probes_by_option_id = _probes_by_option_id(probes)
    results_by_probe_id = _results_by_probe_id(probe_results)
    rows = []

    for dictionary_entry in sorted(
            dictionary_entries,
            key=lambda entry: entry["id"]):
        option_id = dictionary_entry["id"]
        scope = dictionary_entry["scope"]
        scope_classification = scope["classification"]
        option_probes = probes_by_option_id.get(option_id, [])
        probe_ids = sorted(probe["id"] for probe in option_probes)

        for path_name in INPUT_PATHS:
            path_coverage = dictionary_entry["path_coverage"].get(path_name)
            path_statuses = _path_probe_statuses(
                path_name,
                probe_ids,
                results_by_probe_id)
            collapsed_status = _collapse_path_statuses(path_statuses)
            probe_status = _probe_status(
                scope_classification,
                path_coverage,
                collapsed_status)
            status = _support_status(
                scope_classification,
                path_coverage,
                probe_status)

            rows.append({
                "aliases": dictionary_entry.get("aliases", []),
                "canonical_output_form": dictionary_entry[
                    "canonical_output_form"],
                "comparison_status": _comparison_summary(
                    path_coverage,
                    probe_status),
                "manifest_flags": dictionary_entry["manifest_flags"],
                "option_id": option_id,
                "path": path_name,
                "path_coverage": path_coverage,
                "probe_ids": probe_ids,
                "probe_status": probe_status,
                "reason": scope.get("reason"),
                "remaining_work": _remaining_work(status, probe_status),
                "scope": scope_classification,
                "status": status,
                "warning_when_detected_unsupported": dictionary_entry[
                    "warning_behavior"]["warn_when_detected_unsupported"],
            })

    return {
        "entries": rows,
        "generated_by": "tools/build_support_matrix.py",
        "input_paths": list(INPUT_PATHS),
        "probe_results_summary": (
            probe_results or {}).get("summary", {}),
        "schema_version": 1,
        "summary": _matrix_summary(rows),
        "target": target or {},
    }


def _rows_by_option(matrix):
    grouped = defaultdict(dict)
    for row in matrix["entries"]:
        grouped[row["option_id"]][row["path"]] = row
    return grouped


def _option_status(path_rows):
    statuses = set(
        row["status"]
        for row in path_rows.values()
        if row.get("status"))
    if len(statuses) == 1:
        return statuses.pop()
    return "partial"


def _option_summary(matrix):
    summary = dict((status, 0) for status in SUPPORT_STATUSES)
    if isinstance(matrix, dict) and "entries" in matrix:
        option_rows = _rows_by_option(matrix)
    else:
        option_rows = matrix
    for path_rows in option_rows.values():
        summary[_option_status(path_rows)] += 1
    return summary


def _format_cell(value):
    if value is None:
        return ""
    return str(value)


def _format_status(value):
    return MARKDOWN_STATUS_LABELS.get(value, value)


def render_support_matrix_markdown(matrix):
    lines = [
        "# Runlike support matrix",
        "",
        "Generated from `generated/probe-results.json`, "
        "`spec/option-dictionary/`, and `tests/probes/`.",
        "",
    ]

    target = matrix.get("target", {})
    if target.get("id"):
        lines.extend([
            "Target: `%s`." % target["id"],
            "",
        ])

    summary = _option_summary(matrix)
    lines.extend([
        "Summary: %s supported, %s partial, %s unsupported, "
        "%s out of scope, %s needs special runner." % (
            summary["supported"],
            summary["partial"],
            summary["unsupported"],
            summary["out_of_scope"],
            summary["blocked_by_runner"]),
        "",
        "| Option | Flag | Container name | Stdin | Scope | Reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ])

    for option_id, paths in sorted(_rows_by_option(matrix).items()):
        first_row = paths.get("container_name") or paths.get("stdin")
        container_status = _format_status(
            paths.get("container_name", {}).get("status", ""))
        stdin_status = _format_status(
            paths.get("stdin", {}).get("status", ""))
        lines.append("| %s | `%s` | %s | %s | %s | %s |" % (
            option_id,
            first_row["canonical_output_form"],
            container_status,
            stdin_status,
            _format_status(first_row["scope"]),
            _format_cell(first_row.get("reason"))))

    lines.append("")
    return "\n".join(lines)


def _json_dump(payload):
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def write_json(path, payload):
    output_path = Path(path)
    if output_path.parent:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_json_dump(payload))


def write_text(path, payload):
    output_path = Path(path)
    if output_path.parent:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build generated runlike support matrix artifacts.")
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
        default=DEFAULT_PROBE_RESULTS_PATH,
        help="Structured probe results JSON.")
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET_PATH,
        help="Target metadata JSON.")
    parser.add_argument(
        "--json-output",
        default=DEFAULT_JSON_OUTPUT_PATH,
        help="Path to generated support-matrix.json.")
    parser.add_argument(
        "--markdown-output",
        default=DEFAULT_MARKDOWN_OUTPUT_PATH,
        help="Path to generated support-matrix.md.")
    args = parser.parse_args(argv)

    probe_paths = args.probes or [DEFAULT_PROBE_PATH]
    try:
        matrix = build_support_matrix(
            load_dictionary_entries(args.dictionary),
            load_probe_definitions(probe_paths),
            load_probe_results(args.probe_results),
            target=load_target(args.target))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1

    write_json(args.json_output, matrix)
    write_text(args.markdown_output, render_support_matrix_markdown(matrix))
    return 0


if __name__ == "__main__":
    sys.exit(main())
