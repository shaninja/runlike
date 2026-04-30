#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
import sys


DEFAULT_TARGET_PATH = "spec/current-target.json"
DEFAULT_OUTPUT_PATH = "spec/docker-option-manifest.json"

OPTION_RE = re.compile(
    r"^\s{2,}(?:(-[A-Za-z]),\s+)?"
    r"(--[A-Za-z0-9][A-Za-z0-9-]*)"
    r"(?:\s+([A-Za-z0-9][A-Za-z0-9_-]*))?"
    r"\s{2,}(.*)$"
)


def load_target(path):
    with open(path) as target_file:
        return json.load(target_file)


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
    args = parser.parse_args(argv)

    target = load_target(args.target)
    validate_docker_client(target, read_docker_client())
    manifest = build_manifest(
        target,
        read_docker_help("run"),
        read_docker_help("create"))
    write_manifest(args.output, manifest)
    print(
        "Wrote %s with %d Docker options." % (
            args.output, len(manifest["options"])),
        flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
