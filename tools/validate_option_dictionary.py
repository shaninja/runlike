#!/usr/bin/env python3

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


DEFAULT_MANIFEST_PATH = "spec/docker-option-manifest.json"
DEFAULT_DICTIONARY_PATH = "spec/option-dictionary"

REQUIRED_FIELDS = (
    "id",
    "manifest_flags",
    "canonical_output_form",
    "aliases",
    "observability",
    "inspect_fields",
    "detection_profile",
    "compare_profile",
    "render_profile",
    "path_coverage",
    "scope",
    "priority",
    "warning_behavior",
)

OBSERVABILITY_VALUES = set([
    "observable",
    "partially_observable",
    "not_observable",
])
PATH_COVERAGE_VALUES = set([
    "detectable",
    "not_observable",
    "client_side_only",
    "runner_blocked",
])
SCOPE_CLASSIFICATIONS = set([
    "in_scope",
    "out_of_scope",
    "blocked_by_runner",
])
PRIORITY_VALUES = set([
    "P0",
    "P1",
    "P2",
    "not_applicable",
])


def load_manifest(path):
    with open(path) as manifest_file:
        return json.load(manifest_file)


def load_dictionary_entries(path):
    dictionary_path = Path(path)
    entries = []
    for entry_path in sorted(dictionary_path.glob("*.json")):
        with entry_path.open() as entry_file:
            entries.append(json.load(entry_file))
    return entries


def _is_non_empty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _validate_entry_schema(entry):
    errors = []
    entry_id = entry.get("id", "<missing id>")

    for field in REQUIRED_FIELDS:
        if field not in entry:
            errors.append("Dictionary entry %s is missing required field %s." % (
                entry_id, field))

    manifest_flags = entry.get("manifest_flags")
    if not isinstance(manifest_flags, list) or not manifest_flags:
        errors.append("Dictionary entry %s must list at least one manifest flag." % (
            entry_id,))
    elif not all(_is_non_empty_string(flag) for flag in manifest_flags):
        errors.append("Dictionary entry %s has invalid manifest_flags." % entry_id)

    aliases = entry.get("aliases")
    if not isinstance(aliases, list):
        errors.append("Dictionary entry %s aliases must be a list." % entry_id)

    observability = entry.get("observability")
    if observability not in OBSERVABILITY_VALUES:
        errors.append("Dictionary entry %s has invalid observability %r." % (
            entry_id, observability))

    inspect_fields = entry.get("inspect_fields")
    if not isinstance(inspect_fields, list):
        errors.append("Dictionary entry %s inspect_fields must be a list." % entry_id)
    elif observability in ("observable", "partially_observable") and not inspect_fields:
        errors.append(
            "Dictionary entry %s is observable but has no inspect_fields." % entry_id)

    for profile_name in ("detection_profile", "compare_profile", "render_profile"):
        if not isinstance(entry.get(profile_name), dict):
            errors.append("Dictionary entry %s %s must be an object." % (
                entry_id, profile_name))

    path_coverage = entry.get("path_coverage")
    if not isinstance(path_coverage, dict):
        errors.append("Dictionary entry %s path_coverage must be an object." % entry_id)
    else:
        for path_name in ("container_name", "stdin"):
            value = path_coverage.get(path_name)
            if value not in PATH_COVERAGE_VALUES:
                errors.append(
                    "Dictionary entry %s has invalid %s path coverage %r." % (
                        entry_id, path_name, value))

    scope = entry.get("scope")
    if not isinstance(scope, dict):
        errors.append("Dictionary entry %s scope must be an object." % entry_id)
    else:
        classification = scope.get("classification")
        reason = scope.get("reason")
        if classification not in SCOPE_CLASSIFICATIONS:
            errors.append("Dictionary entry %s has invalid scope classification %r." % (
                entry_id, classification))
        if classification in ("out_of_scope", "blocked_by_runner") and not reason:
            errors.append("Dictionary entry %s is %s but has no reason." % (
                entry_id, classification))

    priority = entry.get("priority")
    if priority not in PRIORITY_VALUES:
        errors.append("Dictionary entry %s has invalid priority %r." % (
            entry_id, priority))

    warning_behavior = entry.get("warning_behavior")
    if not isinstance(warning_behavior, dict):
        errors.append(
            "Dictionary entry %s warning_behavior must be an object." % entry_id)
    elif not isinstance(
            warning_behavior.get("warn_when_detected_unsupported"), bool):
        errors.append(
            "Dictionary entry %s warning_behavior.warn_when_detected_unsupported "
            "must be boolean." % entry_id)

    return errors


def build_coverage_ledger(manifest, entries):
    """Return one accounting row for every canonical flag in the manifest."""
    owners_by_flag = defaultdict(list)
    for entry in entries:
        entry_id = entry.get("id", "<missing id>")
        for flag in entry.get("manifest_flags", []):
            owners_by_flag[flag].append(entry_id)

    ledger = []
    for option in sorted(
            manifest.get("options", []),
            key=lambda option: option["canonical_flag"]):
        flag = option["canonical_flag"]
        owners = sorted(owners_by_flag.get(flag, []))
        if not owners:
            status = "missing"
        elif len(owners) > 1:
            status = "duplicate"
        else:
            status = "covered"

        ledger.append({
            "manifest_flag": flag,
            "owners": owners,
            "owner_count": len(owners),
            "status": status,
        })

    return ledger


def summarize_coverage_ledger(ledger):
    summary = {
        "covered": 0,
        "duplicate": 0,
        "missing": 0,
    }
    for row in ledger:
        summary[row["status"]] += 1
    return summary


def write_coverage_ledger(path, ledger):
    payload = {
        "summary": summarize_coverage_ledger(ledger),
        "manifest_option_count": len(ledger),
        "ledger": ledger,
    }
    with open(path, "w") as ledger_file:
        json.dump(payload, ledger_file, indent=2, sort_keys=True)
        ledger_file.write("\n")


def validate_dictionary(manifest, entries):
    errors = []
    manifest_flags = set(
        option["canonical_flag"]
        for option in manifest.get("options", [])
    )
    entry_ids = set()

    for entry in entries:
        entry_id = entry.get("id")
        if not _is_non_empty_string(entry_id):
            errors.append("Dictionary entry has missing or invalid id.")
            entry_id = "<missing id>"
        elif entry_id in entry_ids:
            errors.append("Dictionary entry id %s is duplicated." % entry_id)
        else:
            entry_ids.add(entry_id)

        errors.extend(_validate_entry_schema(entry))

        for flag in entry.get("manifest_flags", []):
            if flag not in manifest_flags:
                errors.append(
                    "Dictionary entry %s references unknown manifest option %s." % (
                        entry_id, flag))

    for row in build_coverage_ledger(manifest, entries):
        flag = row["manifest_flag"]
        if row["status"] == "missing":
            errors.append("Manifest option %s has no dictionary entry." % flag)
        elif row["status"] == "duplicate":
            errors.append(
                "Manifest option %s is covered by multiple dictionary entries: %s." % (
                    flag, ", ".join(row["owners"])))

    return sorted(errors)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate runlike option dictionary coverage and schema.")
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST_PATH,
        help="Path to spec/docker-option-manifest.json.")
    parser.add_argument(
        "--dictionary",
        default=DEFAULT_DICTIONARY_PATH,
        help="Path to spec/option-dictionary.")
    parser.add_argument(
        "--coverage-ledger",
        help="Optional path to write one accounting row per manifest option.")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    entries = load_dictionary_entries(args.dictionary)
    ledger = build_coverage_ledger(manifest, entries)
    if args.coverage_ledger:
        write_coverage_ledger(args.coverage_ledger, ledger)

    errors = validate_dictionary(
        manifest,
        entries)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("Option dictionary validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
