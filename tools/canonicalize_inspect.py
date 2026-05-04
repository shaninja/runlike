#!/usr/bin/env python3

import argparse
import json
import sys


ORDER_SENSITIVE_LIST_PATHS = set([
    "Config.Cmd",
    "Config.Entrypoint",
    # TODO: Add regression coverage for healthcheck and shell ordering.
    "Config.Healthcheck.Test",
    "Config.Shell",
])

TOP_LEVEL_DYNAMIC_FIELDS = set([
    "AppArmorProfile",
    "Created",
    "ExecIDs",
    "GraphDriver",
    "HostnamePath",
    "HostsPath",
    "Id",
    "LogPath",
    "MountLabel",
    "Path",
    "Platform",
    "ProcessLabel",
    "ResolvConfPath",
    "RestartCount",
    "SizeRootFs",
    "SizeRw",
    "State",
])

NETWORK_DYNAMIC_FIELDS = set([
    "EndpointID",
    "Gateway",
    "GlobalIPv6Address",
    "GlobalIPv6PrefixLen",
    "IPAddress",
    "IPPrefixLen",
    "IPv6Gateway",
    "MacAddress",
    "NetworkID",
])

NETWORK_SETTINGS_DYNAMIC_FIELDS = set([
    "Bridge",
    "EndpointID",
    "Gateway",
    "GlobalIPv6Address",
    "GlobalIPv6PrefixLen",
    "HairpinMode",
    "IPAddress",
    "IPPrefixLen",
    "IPv6Gateway",
    "LinkLocalIPv6Address",
    "LinkLocalIPv6PrefixLen",
    "MacAddress",
    "SandboxID",
    "SandboxKey",
])


def load_inspect(raw_json):
    return json.loads(raw_json)


def normalize_inspect_document(inspect_document):
    if isinstance(inspect_document, list):
        if not inspect_document:
            raise ValueError("docker inspect document is empty")
        if len(inspect_document) != 1:
            raise ValueError("docker inspect document must contain exactly one object")
        return inspect_document[0]
    if isinstance(inspect_document, dict):
        return inspect_document
    raise ValueError("docker inspect document must be an object or single-item list")


def _path_parts(path):
    if isinstance(path, tuple):
        return path
    if not path:
        return ()
    return tuple(path.split("."))


def _path_string(path):
    if isinstance(path, tuple):
        return ".".join(path)
    return path


def _path_join(path, key):
    return _path_parts(path) + (key,)


def _is_dynamic_field(path, key):
    parts = _path_parts(path)
    if not parts and key in TOP_LEVEL_DYNAMIC_FIELDS:
        return True
    if parts == ("NetworkSettings",) and key in NETWORK_SETTINGS_DYNAMIC_FIELDS:
        return True
    if (
            len(parts) == 3
            and parts[:2] == ("NetworkSettings", "Networks")
            and key in NETWORK_DYNAMIC_FIELDS):
        return True
    return False


def _sort_key(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def canonicalize_value(value, path=""):
    if isinstance(value, dict):
        canonical = {}
        for key in sorted(value):
            if _is_dynamic_field(path, key):
                continue
            canonical[key] = canonicalize_value(value[key], _path_join(path, key))
        return canonical

    if isinstance(value, list):
        canonical_list = [
            canonicalize_value(item, path)
            for item in value
        ]
        if _path_string(path) in ORDER_SENSITIVE_LIST_PATHS:
            return canonical_list
        return sorted(canonical_list, key=_sort_key)

    return value


def canonicalize_inspect(inspect_document):
    inspect_object = normalize_inspect_document(inspect_document)
    return canonicalize_value(inspect_object)


def _extract_path(value, parts):
    if not parts:
        return value

    part = parts[0]
    rest = parts[1:]
    if part == "*":
        if isinstance(value, dict):
            return {
                key: _extract_path(value[key], rest)
                for key in sorted(value)
            }
        if isinstance(value, list):
            return [
                _extract_path(item, rest)
                for item in value
            ]
        return None

    if isinstance(value, dict) and part in value:
        return _extract_path(value[part], rest)
    return None


def extract_field(inspect_object, field):
    return _extract_path(inspect_object, field.split("."))


def _normalize_container_name(value):
    if isinstance(value, str):
        return value.lstrip("/")
    return value


def _normalize_restart_policy(value):
    if not isinstance(value, dict):
        return value

    name = value.get("Name") or "no"
    maximum_retry_count = value.get("MaximumRetryCount") or 0
    if name != "on-failure":
        maximum_retry_count = 0

    return {
        "MaximumRetryCount": maximum_retry_count,
        "Name": name,
    }


def _normalize_profile_value(profile_name, field, value):
    if profile_name == "normalized-container-name" and field == "Name":
        return _normalize_container_name(value)
    if profile_name == "restart-policy" and field == "HostConfig.RestartPolicy":
        return _normalize_restart_policy(value)
    return value


def canonicalize_for_compare(inspect_document, compare_profile):
    inspect_object = normalize_inspect_document(inspect_document)
    profile_name = compare_profile.get("profile", "inspect-projection")
    if profile_name == "not-observable":
        return {}

    projection = {}
    for field in sorted(compare_profile.get("fields", [])):
        value = extract_field(inspect_object, field)
        value = _normalize_profile_value(profile_name, field, value)
        projection[field] = canonicalize_value(value, field)
    return projection


def compare_inspects(expected_document, actual_document, compare_profile):
    expected = canonicalize_for_compare(expected_document, compare_profile)
    actual = canonicalize_for_compare(actual_document, compare_profile)

    mismatches = []
    for field in sorted(set(expected) | set(actual)):
        if expected.get(field) != actual.get(field):
            mismatches.append({
                "actual": actual.get(field),
                "expected": expected.get(field),
                "field": field,
            })

    return {
        "actual": actual,
        "expected": expected,
        "mismatches": mismatches,
        "passed": not mismatches,
        "profile": compare_profile.get("profile", "inspect-projection"),
    }


def _read_text(path):
    if not path or path == "-":
        return sys.stdin.read()
    with open(path) as input_file:
        return input_file.read()


def _load_compare_profile(raw_profile):
    if not raw_profile:
        return None
    try:
        return json.loads(raw_profile)
    except ValueError:
        with open(raw_profile) as profile_file:
            return json.load(profile_file)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Canonicalize docker inspect JSON for runlike probes.")
    parser.add_argument(
        "inspect_json",
        nargs="?",
        help="Path to docker inspect JSON. Reads stdin when omitted or '-'.")
    parser.add_argument(
        "--field",
        action="append",
        dest="fields",
        default=[],
        help="Inspect field path to include in the projection.")
    parser.add_argument(
        "--compare-profile",
        help="Compare profile JSON object, or a path to a JSON file.")
    args = parser.parse_args(argv)

    inspect_document = load_inspect(_read_text(args.inspect_json))
    compare_profile = _load_compare_profile(args.compare_profile)
    if compare_profile is None and not args.fields:
        projection = canonicalize_inspect(inspect_document)
    else:
        if compare_profile is None:
            compare_profile = {
                "fields": args.fields,
                "profile": "inspect-projection",
            }
        projection = canonicalize_for_compare(inspect_document, compare_profile)
    json.dump(projection, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
