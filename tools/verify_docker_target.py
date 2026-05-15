#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys


DEFAULT_METADATA_PATH = "spec/current-target.json"


def load_target(path):
    with open(path) as target_file:
        return json.load(target_file)


def _first_value(mapping, names):
    for name in names:
        if name in mapping and mapping[name] not in (None, ""):
            return str(mapping[name])
    return None


def _display(value):
    if value in (None, ""):
        return "<unset>"
    return str(value)


def _check(errors, label, expected, actual):
    if str(expected) != _display(actual):
        errors.append(
            "%s: expected %s, got %s" % (label, expected, _display(actual)))


def validate_docker_version_payload(version_payload, target, environment=None):
    """Return validation errors for a Docker `version --format '{{json .}}'` payload."""
    if environment is None:
        environment = os.environ

    docker_target = target["docker"]
    expected_engine = docker_target["engine_version"]
    expected_cli = docker_target["cli_version"]
    expected_api = docker_target["api_version"]
    expected_env_api = target["environment"]["DOCKER_API_VERSION"]

    client = version_payload.get("Client") or {}
    server = version_payload.get("Server") or {}

    client_version = _first_value(client, ("Version", "version"))
    engine_version = _first_value(server, ("Version", "version"))
    client_api = _first_value(
        client, ("APIVersion", "ApiVersion", "API version", "Api version"))
    server_api = _first_value(
        server, ("APIVersion", "ApiVersion", "API version", "Api version"))
    docker_api_version = environment.get("DOCKER_API_VERSION")

    errors = []
    _check(errors, "Docker client version", expected_cli, client_version)
    _check(errors, "Docker engine version", expected_engine, engine_version)
    _check(errors, "Docker client API version", expected_api, client_api)
    _check(errors, "Docker server API version", expected_api, server_api)
    _check(errors, "DOCKER_API_VERSION", expected_env_api, docker_api_version)
    return errors


def read_docker_version_payload():
    output = subprocess.check_output(
        ["docker", "version", "--format", "{{json .}}"],
        universal_newlines=True)
    return json.loads(output)


def summarize_target(target):
    docker_target = target["docker"]
    return (
        "target=%s platform=%s engine=%s cli=%s api=%s" % (
            target["id"],
            target["platform"],
            docker_target["engine_version"],
            docker_target["cli_version"],
            docker_target["api_version"],
        )
    )


def summarize_payload(version_payload):
    client = version_payload.get("Client") or {}
    server = version_payload.get("Server") or {}
    return (
        "observed client=%s client_api=%s engine=%s server_api=%s" % (
            _display(_first_value(client, ("Version", "version"))),
            _display(_first_value(
                client, ("APIVersion", "ApiVersion", "API version", "Api version"))),
            _display(_first_value(server, ("Version", "version"))),
            _display(_first_value(
                server, ("APIVersion", "ApiVersion", "API version", "Api version"))),
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate the active Docker installation against the runlike target.")
    parser.add_argument(
        "--metadata",
        default=DEFAULT_METADATA_PATH,
        help="Path to the checked-in Docker target metadata.")
    args = parser.parse_args(argv)

    target = load_target(args.metadata)
    print(summarize_target(target), flush=True)

    try:
        version_payload = read_docker_version_payload()
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        sys.stderr.write("Unable to read Docker version JSON: %s\n" % exc)
        return 1

    print(summarize_payload(version_payload), flush=True)
    errors = validate_docker_version_payload(version_payload, target)
    if errors:
        sys.stderr.write("Docker target validation failed:\n")
        for error in errors:
            sys.stderr.write("- %s\n" % error)
        return 1

    print("Docker target validation passed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
