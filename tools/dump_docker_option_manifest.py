#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict


DEFAULT_TARGET_PATH = "spec/current-target.json"
DEFAULT_OUTPUT_PATH = "spec/docker-option-manifest.json"
DEFAULT_DICTIONARY_PATH = "spec/option-dictionary"

PLATFORM_ONLY_REASONS = {
    "linux_only": ("linux",),
    "macos_only": ("darwin", "macos"),
    "windows_only": ("windows",),
}

OPTION_RE = re.compile(
    r"^\s{2,}(?:(-[A-Za-z]),\s+)?"
    r"(--[A-Za-z0-9][A-Za-z0-9-]*)"
    r"(?:\s+([A-Za-z0-9][A-Za-z0-9_-]*))?"
    r"\s{2,}(.*)$"
)


def load_target(path):
    with open(path) as target_file:
        return json.load(target_file)


def load_dictionary_entries(path):
    entries = []
    for filename in sorted(os.listdir(path)):
        if not filename.endswith(".json"):
            continue
        with open(os.path.join(path, filename)) as dictionary_file:
            entries.append(json.load(dictionary_file))
    return entries


def _compact_help(parts):
    return " ".join(part.strip() for part in parts if part.strip())


def parse_docker_options(help_text):
    """Parse Docker command help into canonical long-option entries."""
    options = []
    current = None
    in_options = False

    for raw_line in help_text.splitlines():
        line = raw_line.rstrip()
        if line.strip() == "Options:":
            in_options = True
            continue
        if not in_options:
            continue
        if not line.strip():
            continue

        match = OPTION_RE.match(line)
        if match:
            if current is not None:
                options.append(current)

            short_flag, canonical_flag, value_type, help_text = match.groups()
            current = {
                "canonical_flag": canonical_flag,
                "short_flag": short_flag,
                "value_type": value_type,
                "_help_parts": [help_text],
            }
            continue

        if current is not None:
            current["_help_parts"].append(line.strip())

    if current is not None:
        options.append(current)

    return [
        {
            "canonical_flag": option["canonical_flag"],
            "short_flag": option["short_flag"],
            "value_type": option["value_type"],
            "help": _compact_help(option["_help_parts"]),
        }
        for option in options
    ]


def _command_family(commands):
    if commands == set(["run", "create"]):
        return "both"
    if commands == set(["run"]):
        return "run"
    if commands == set(["create"]):
        return "create"
    raise ValueError("Unsupported command family: %r" % sorted(commands))


def _merge_options(run_options, create_options):
    merged = {}
    for command, options in (("run", run_options), ("create", create_options)):
        for option in options:
            canonical_flag = option["canonical_flag"]
            if canonical_flag not in merged:
                merged[canonical_flag] = {
                    "canonical_flag": canonical_flag,
                    "short_flag": option["short_flag"],
                    "value_type": option["value_type"],
                    "help": option["help"],
                    "_commands": set(),
                    "_command_help": {},
                }

            entry = merged[canonical_flag]
            if entry["short_flag"] != option["short_flag"]:
                raise ValueError(
                    "Conflicting short flag for %s: %r != %r" % (
                        canonical_flag, entry["short_flag"], option["short_flag"]))
            if entry["value_type"] != option["value_type"]:
                raise ValueError(
                    "Conflicting value type for %s: %r != %r" % (
                        canonical_flag, entry["value_type"], option["value_type"]))

            entry["_commands"].add(command)
            entry["_command_help"][command] = option["help"]

    result = []
    for canonical_flag in sorted(merged):
        entry = merged[canonical_flag]
        manifest_entry = {
            "canonical_flag": entry["canonical_flag"],
            "short_flag": entry["short_flag"],
            "value_type": entry["value_type"],
            "help": entry["help"],
            "command_family": _command_family(entry["_commands"]),
        }
        help_values = set(entry["_command_help"].values())
        if len(help_values) > 1:
            manifest_entry["command_help"] = {
                command: entry["_command_help"][command]
                for command in sorted(entry["_command_help"])
            }
        result.append(manifest_entry)
    return result


def build_manifest(target, run_help, create_help):
    return {
        "generated_by": "tools/dump_docker_option_manifest.py",
        "target": target,
        "options": _merge_options(
            parse_docker_options(run_help),
            parse_docker_options(create_help)),
    }


def build_manifest_source_ledger(manifest, run_help, create_help):
    source_commands_by_flag = defaultdict(set)
    for command, help_text in (("run", run_help), ("create", create_help)):
        for option in parse_docker_options(help_text):
            source_commands_by_flag[option["canonical_flag"]].add(command)

    manifest_rows_by_flag = defaultdict(list)
    for option in manifest.get("options", []):
        manifest_rows_by_flag[option["canonical_flag"]].append(option)

    flags = sorted(set(source_commands_by_flag) | set(manifest_rows_by_flag))
    ledger = []
    for flag in flags:
        source_commands = sorted(source_commands_by_flag.get(flag, set()))
        manifest_rows = manifest_rows_by_flag.get(flag, [])
        actual_command_families = [
            row.get("command_family")
            for row in manifest_rows
        ]
        expected_command_family = (
            _command_family(set(source_commands))
            if source_commands
            else None
        )

        if not source_commands:
            status = "extra"
        elif not manifest_rows:
            status = "missing"
        elif len(manifest_rows) > 1:
            status = "duplicate"
        elif actual_command_families[0] != expected_command_family:
            status = "command_family_mismatch"
        else:
            status = "covered"

        ledger.append({
            "actual_command_families": actual_command_families,
            "expected_command_family": expected_command_family,
            "manifest_flag": flag,
            "manifest_row_count": len(manifest_rows),
            "source_commands": source_commands,
            "status": status,
        })
    return ledger


def summarize_manifest_source_ledger(ledger):
    summary = {
        "command_family_mismatch": 0,
        "covered": 0,
        "duplicate": 0,
        "extra": 0,
        "missing": 0,
    }
    for row in ledger:
        summary[row["status"]] += 1
    return summary


def write_manifest_source_ledger(path, ledger):
    payload = {
        "summary": summarize_manifest_source_ledger(ledger),
        "source_option_count": sum(
            1 for row in ledger if row["source_commands"]),
        "manifest_option_count": sum(
            row["manifest_row_count"] for row in ledger),
        "ledger": ledger,
    }
    with open(path, "w") as ledger_file:
        json.dump(payload, ledger_file, indent=2, sort_keys=True)
        ledger_file.write("\n")


def _entries_by_manifest_flag(dictionary_entries):
    grouped = defaultdict(list)
    for entry in dictionary_entries or []:
        for flag in entry.get("manifest_flags") or []:
            grouped[flag].append(entry)
    return grouped


def _target_platform(target):
    if not isinstance(target, dict):
        return None
    return target.get("platform")


def _is_other_platform_only_extra(row, target, entries_by_flag):
    platform = _target_platform(target)
    if not isinstance(platform, str) or not platform:
        return False

    target_platform = platform.lower()
    entries = entries_by_flag.get(row["manifest_flag"], [])
    if not entries:
        return False

    for entry in entries:
        scope = entry.get("scope") or {}
        if scope.get("classification") != "out_of_scope":
            return False
        scoped_platforms = PLATFORM_ONLY_REASONS.get(scope.get("reason"))
        if not scoped_platforms or target_platform in scoped_platforms:
            return False
    return True


def validate_manifest_source_ledger(
        ledger,
        target=None,
        dictionary_entries=None):
    errors = []
    entries_by_flag = _entries_by_manifest_flag(dictionary_entries)
    for row in ledger:
        status = row["status"]
        if status == "covered":
            continue
        if status == "missing":
            errors.append("Docker help option %s has no manifest entry." % (
                row["manifest_flag"],))
        elif status == "duplicate":
            errors.append("Docker help option %s has %d manifest entries." % (
                row["manifest_flag"], row["manifest_row_count"]))
        elif status == "extra":
            if _is_other_platform_only_extra(row, target, entries_by_flag):
                continue
            errors.append("Manifest option %s is not present in Docker help." % (
                row["manifest_flag"],))
        elif status == "command_family_mismatch":
            errors.append(
                "Manifest option %s command_family mismatch: expected %s, got %s." % (
                    row["manifest_flag"],
                    row["expected_command_family"],
                    ", ".join(row["actual_command_families"])))
        else:
            errors.append("Manifest option %s has unknown ledger status %s." % (
                row["manifest_flag"], status))
    return errors


def read_docker_client():
    output = subprocess.check_output(
        ["docker", "version", "--format", "{{json .Client}}"],
        universal_newlines=True)
    return json.loads(output)


def validate_docker_client(target, client):
    docker_target = target.get("docker") if isinstance(target, dict) else None
    if not isinstance(docker_target, dict):
        raise ValueError(
            "Target metadata must include Docker client version and API version.")

    expected_version = docker_target.get("cli_version")
    expected_api_version = docker_target.get("api_version")

    if expected_version is None or expected_api_version is None:
        raise ValueError(
            "Target metadata must include Docker client version and API version.")

    actual_version = client.get("Version")
    actual_api_version = client.get("ApiVersion")
    if actual_version != expected_version or actual_api_version != expected_api_version:
        raise ValueError(
            "Docker client does not match pinned target: "
            "expected version %s/API %s, got version %s/API %s" % (
                expected_version,
                expected_api_version,
                actual_version,
                actual_api_version))


def read_docker_help(command):
    return subprocess.check_output(
        ["docker", "container", command, "--help"],
        universal_newlines=True)


def write_manifest(path, manifest):
    with open(path, "w") as output_file:
        json.dump(manifest, output_file, indent=2, sort_keys=True)
        output_file.write("\n")


def load_manifest(path):
    with open(path) as manifest_file:
        return json.load(manifest_file)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate the Docker option manifest for the pinned runlike target.")
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET_PATH,
        help="Path to spec/current-target.json.")
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help="Path for the generated Docker option manifest.")
    parser.add_argument(
        "--dictionary",
        default=DEFAULT_DICTIONARY_PATH,
        help="Path to the runlike option dictionary directory.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the existing manifest against live Docker help instead of writing it.")
    parser.add_argument(
        "--coverage-ledger",
        help="Optional path to write one accounting row per Docker help option.")
    args = parser.parse_args(argv)

    target = load_target(args.target)
    validate_docker_client(target, read_docker_client())
    run_help = read_docker_help("run")
    create_help = read_docker_help("create")

    if args.check:
        manifest = load_manifest(args.output)
        dictionary_entries = load_dictionary_entries(args.dictionary)
        ledger = build_manifest_source_ledger(manifest, run_help, create_help)
        if args.coverage_ledger:
            write_manifest_source_ledger(args.coverage_ledger, ledger)
        errors = validate_manifest_source_ledger(
            ledger,
            target=target,
            dictionary_entries=dictionary_entries)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        print("Docker option manifest source validation passed.")
        return 0

    manifest = build_manifest(
        target,
        run_help,
        create_help)
    ledger = build_manifest_source_ledger(manifest, run_help, create_help)
    if args.coverage_ledger:
        write_manifest_source_ledger(args.coverage_ledger, ledger)
    write_manifest(args.output, manifest)
    print(
        "Wrote %s with %d Docker options." % (
            args.output, len(manifest["options"])),
        flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
