#!/usr/bin/env python3

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shlex
import signal
import subprocess
import sys
from pathlib import Path


DEFAULT_DOCKER_COMMAND = ["docker"]
DEFAULT_RUNLIKE_COMMAND = [
    sys.executable,
    "-m",
    "runlike.runlike",
]
DEFAULT_COMMAND_TIMEOUT_SECONDS = 120
DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1] / "spec" / "docker-option-manifest.json")
DEFAULT_DICTIONARY_PATH = (
    Path(__file__).resolve().parents[1] / "spec" / "option-dictionary")

# Probe rewrite policy: remove run/lifecycle flags when turning runlike output
# into a cloneable docker container create command.
RUN_ONLY_FLAGS = set([
    "-d",
    "--detach",
    "--rm",
])


def _load_canonicalize_module():
    script = Path(__file__).with_name("canonicalize_inspect.py")
    spec = importlib.util.spec_from_file_location(
        "canonicalize_inspect", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


canonicalize_inspect = _load_canonicalize_module()


def load_value_flags_from_manifest(manifest_path=DEFAULT_MANIFEST_PATH):
    with Path(manifest_path).open() as manifest_file:
        manifest = json.load(manifest_file)

    value_flags = set()
    for option in manifest.get("options", []):
        if option.get("value_type") is None:
            continue
        value_flags.add(option["canonical_flag"])
        short_flag = option.get("short_flag")
        if short_flag:
            value_flags.add(short_flag)
    return value_flags


def _json_sha256(payload):
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while True:
            chunk = source.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_probe_results_metadata(probes, root=None):
    if root is None:
        root = Path(__file__).resolve().parents[1]
    root = Path(root)
    tool_paths = [
        Path("tools/canonicalize_inspect.py"),
        Path("tools/run_probes.py"),
    ]
    return {
        "count": len(probes),
        "ids": sorted(
            probe["id"]
            for probe in probes
            if probe.get("id")),
        "sha256": _json_sha256(probes),
        "tool_hashes": dict(
            (str(path), _file_sha256(root / path))
            for path in tool_paths),
    }


VALUE_FLAGS = load_value_flags_from_manifest()


class CommandResult(object):

    def __init__(self, returncode, stdout, stderr, timed_out=False):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out


class ProbeCommandError(Exception):

    def __init__(self, command, result):
        self.command = command
        self.result = result
        message = "Command failed with exit code %s: %s" % (
            result.returncode, " ".join(command))
        super(ProbeCommandError, self).__init__(message)


class ProbeConfigurationError(Exception):
    pass


def _parse_timeout_seconds(timeout_seconds, source):
    try:
        parsed = float(timeout_seconds)
    except (TypeError, ValueError):
        raise ProbeConfigurationError(
            "%s must be a number of seconds; got %r" % (
                source,
                timeout_seconds))
    if not math.isfinite(parsed):
        raise ProbeConfigurationError(
            "%s must be finite; got %r" % (source, timeout_seconds))
    return parsed


class SubprocessCommandRunner(object):

    def __init__(self, timeout_seconds=None):
        timeout_source = "--command-timeout"
        if timeout_seconds is None:
            env_timeout_seconds = os.environ.get("RUNLIKE_PROBE_COMMAND_TIMEOUT")
            if env_timeout_seconds is not None:
                timeout_source = "RUNLIKE_PROBE_COMMAND_TIMEOUT"
                timeout_seconds = env_timeout_seconds
            else:
                timeout_source = "default command timeout"
                timeout_seconds = DEFAULT_COMMAND_TIMEOUT_SECONDS
        timeout_seconds = _parse_timeout_seconds(
            timeout_seconds,
            timeout_source)
        self.timeout_seconds = timeout_seconds if timeout_seconds > 0 else None

    def _popen_kwargs(self):
        if self.timeout_seconds is not None and hasattr(os, "setsid"):
            return {"preexec_fn": os.setsid}
        return {}

    def _kill_timed_out_process(self, process):
        if self.timeout_seconds is not None and hasattr(os, "killpg"):
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                return
            except OSError:
                pass
        process.kill()

    def run(self, command, stdin=None):
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if stdin is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **self._popen_kwargs())
        try:
            stdout, stderr = process.communicate(
                stdin.encode("utf-8") if stdin is not None else None,
                timeout=self.timeout_seconds)
            timed_out = False
        except subprocess.TimeoutExpired:
            self._kill_timed_out_process(process)
            stdout, stderr = process.communicate()
            timeout_message = "Command timed out after %s seconds." % (
                self.timeout_seconds,)
            if stderr:
                stderr += b"\n"
            stderr += timeout_message.encode("utf-8")
            timed_out = True
        return CommandResult(
            process.returncode,
            stdout.decode("utf-8"),
            stderr.decode("utf-8"),
            timed_out=timed_out)


def _checked_run(command_runner, command, stdin=None):
    result = command_runner.run(command, stdin=stdin)
    if result.returncode != 0:
        raise ProbeCommandError(command, result)
    return result


def _normalize_stream(value):
    return value.rstrip("\n")


def _stream_lines(value):
    normalized = _normalize_stream(value)
    if not normalized:
        return []
    return normalized.splitlines()


def _safe_name(value):
    return re.sub(r"[^a-zA-Z0-9_.-]", "-", value)


def _format_template_command(command, context):
    return [
        part.format(**context)
        for part in command
    ]


def _option_name(token):
    if token.startswith("--") and "=" in token:
        return token.split("=", 1)[0]
    return token


def _skip_name_option(tokens, index):
    token = tokens[index]
    if token == "--name":
        return index + 2
    if token.startswith("--name="):
        return index + 1
    return None


def _skip_run_only_option(tokens, index):
    token = tokens[index]
    option = _option_name(token)
    if option in RUN_ONLY_FLAGS:
        return index + 1
    return None


def _is_short_option_token(token):
    return token.startswith("-") and not token.startswith("--") and token != "-"


def _copy_short_option(tokens, index, output):
    token = tokens[index]
    if not _is_short_option_token(token):
        return None

    short_name = token[:2]
    attached_value = token[2:]
    if short_name in VALUE_FLAGS:
        output.append(short_name)
        if attached_value:
            output.append(attached_value)
            return index + 1
        if index + 1 < len(tokens):
            output.append(tokens[index + 1])
            return index + 2
        return index + 1

    short_flags = token[1:]
    if len(short_flags) > 1:
        for offset, flag in enumerate(short_flags):
            option = "-" + flag
            remaining = short_flags[offset + 1:]
            if option in VALUE_FLAGS:
                output.append(option)
                if remaining:
                    output.append(remaining)
                    return index + 1
                if index + 1 < len(tokens):
                    output.append(tokens[index + 1])
                    return index + 2
                return index + 1
            if option not in RUN_ONLY_FLAGS:
                output.append(option)
        return index + 1

    return None


def _copy_option(tokens, index, output):
    token = tokens[index]
    option = _option_name(token)
    if token.startswith("--") and "=" in token:
        output.append(token)
        return index + 1
    next_index = _copy_short_option(tokens, index, output)
    if next_index is not None:
        return next_index
    output.append(token)
    if option in VALUE_FLAGS and index + 1 < len(tokens):
        output.append(tokens[index + 1])
        return index + 2
    return index + 1


def _docker_run_payload(tokens):
    if len(tokens) >= 2 and tokens[0] == "docker" and tokens[1] == "run":
        return tokens[2:]
    if (
            len(tokens) >= 3
            and tokens[0] == "docker"
            and tokens[1] == "container"
            and tokens[2] == "run"):
        return tokens[3:]
    raise ValueError("probe clone command must start with docker run")


def prepare_clone_create_payload(rendered_command, clone_name):
    tokens = shlex.split(rendered_command.strip())
    payload = _docker_run_payload(tokens)
    rewritten = []
    image_seen = False
    index = 0

    while index < len(payload):
        token = payload[index]
        if image_seen:
            rewritten.append(token)
            index += 1
            continue

        if not image_seen and token == "--":
            index += 1
            continue

        next_index = _skip_name_option(payload, index)
        if next_index is not None:
            index = next_index
            continue

        next_index = _skip_run_only_option(payload, index)
        if next_index is not None:
            index = next_index
            continue

        if token.startswith("-"):
            index = _copy_option(payload, index, rewritten)
            continue

        rewritten.append(token)
        image_seen = True
        index += 1

    return [
        "--name",
        clone_name,
    ] + rewritten


def prepare_clone_create_command(rendered_command, clone_name):
    return [
        "docker",
        "container",
        "create",
    ] + prepare_clone_create_payload(rendered_command, clone_name)


def prepare_clone_run_payload(rendered_command, clone_name):
    tokens = shlex.split(rendered_command.strip())
    payload = _docker_run_payload(tokens)
    rewritten = []
    image_seen = False
    index = 0

    while index < len(payload):
        token = payload[index]
        if image_seen:
            rewritten.append(token)
            index += 1
            continue

        if not image_seen and token == "--":
            index += 1
            continue

        next_index = _skip_name_option(payload, index)
        if next_index is not None:
            index = next_index
            continue

        if token.startswith("-"):
            index = _copy_option(payload, index, rewritten)
            continue

        rewritten.append(token)
        image_seen = True
        index += 1

    return [
        "--name",
        clone_name,
    ] + rewritten


def prepare_clone_run_command(rendered_command, clone_name):
    return [
        "docker",
        "container",
        "run",
    ] + prepare_clone_run_payload(rendered_command, clone_name)


def _container_names(probe):
    safe_id = _safe_name(probe["id"])
    prefix = "runlike-probe-" + safe_id
    return {
        "container_name_clone": prefix + "-container-name-clone",
        "original": prefix + "-original",
        "stdin_clone": prefix + "-stdin-clone",
    }


def _context(probe, names):
    return {
        "container_name_clone": names["container_name_clone"],
        "original_name": names["original"],
        "probe_id": probe["id"],
        "stdin_clone": names["stdin_clone"],
    }


def _load_dictionary_entry(option_id, dictionary_path=DEFAULT_DICTIONARY_PATH):
    entry_path = Path(dictionary_path) / (option_id + ".json")
    if not entry_path.exists():
        raise ValueError("No option dictionary entry for %s." % option_id)
    with entry_path.open() as entry_file:
        return json.load(entry_file)


def _detectable_paths(dictionary_entry):
    path_coverage = dictionary_entry.get("path_coverage", {})
    return [
        path_name
        for path_name in ("container_name", "stdin")
        if path_coverage.get(path_name) == "detectable"
    ]


def resolve_probe_definition(probe, dictionary_path=DEFAULT_DICTIONARY_PATH):
    resolved = dict(probe)
    option_id = resolved.get("option_id")
    dictionary_entry = None

    def dictionary_defaults():
        if not option_id:
            raise ValueError(
                "Probe %s needs compare_profile or option_id." % resolved.get("id"))
        return _load_dictionary_entry(option_id, dictionary_path)

    if "compare_profile" not in resolved:
        dictionary_entry = dictionary_defaults()
        resolved["compare_profile"] = dictionary_entry["compare_profile"]

    if "paths" not in resolved:
        if option_id:
            if dictionary_entry is None:
                dictionary_entry = dictionary_defaults()
            resolved["paths"] = _detectable_paths(dictionary_entry)
        else:
            resolved["paths"] = ["container_name", "stdin"]

    if not resolved.get("paths"):
        raise ValueError(
            "Probe %s has no input paths to run." % resolved.get("id"))

    return resolved


def _run_helper_commands(command_runner, helper_commands, context):
    for helper in helper_commands:
        command = helper.get("command", helper)
        _checked_run(
            command_runner,
            _format_template_command(command, context))


def _probe_command_parts(probe, context):
    return (
        _format_template_command(probe.get("docker_run_args", []), context)
        + [probe["image"]]
        + _format_template_command(probe.get("command", []), context))


def _create_original(
        probe,
        names,
        command_runner,
        docker_command,
        created_names=None):
    lifecycle = probe.get("original_lifecycle", "create")
    if lifecycle not in ("create", "run"):
        raise ValueError("unknown original lifecycle %s" % lifecycle)
    command = (
        docker_command
        + ["container", lifecycle, "--name", names["original"]]
        + _probe_command_parts(probe, _context(probe, names)))
    _checked_run(command_runner, command)
    if created_names is not None:
        created_names.append(names["original"])


def _inspect_container(command_runner, docker_command, container_name):
    result = _checked_run(
        command_runner,
        docker_command + ["container", "inspect", container_name])
    return result.stdout


def _run_runlike(command_runner, runlike_command, args, stdin=None):
    return _checked_run(command_runner, runlike_command + args, stdin=stdin)


def _stream_contains_assertions(probe, stream_name, stream_value, context):
    assertions = []
    for expected in probe.get("%s_contains" % stream_name, []):
        expected_text = expected.format(**context)
        assertions.append({
            "expected": expected_text,
            "passed": expected_text in stream_value,
            "type": "contains",
        })
    return assertions


def _stdout_assertions(probe, rendered_command, context):
    return _stream_contains_assertions(
        probe,
        "stdout",
        rendered_command,
        context)


def _stderr_assertions(probe, stderr, context):
    return _stream_contains_assertions(
        probe,
        "stderr",
        stderr,
        context)


def _run_path(
        probe,
        path_name,
        original_inspect_text,
        names,
        command_runner,
        runlike_command,
        docker_command,
        created_names=None):
    if path_name == "container_name":
        runlike_result = _run_runlike(
            command_runner,
            runlike_command,
            [names["original"]])
        clone_name = names["container_name_clone"]
    elif path_name == "stdin":
        runlike_result = _run_runlike(
            command_runner,
            runlike_command,
            ["--stdin"],
            stdin=original_inspect_text)
        clone_name = names["stdin_clone"]
    else:
        raise ValueError("unknown probe input path %s" % path_name)

    rendered_command = _normalize_stream(runlike_result.stdout)
    stderr = _normalize_stream(runlike_result.stderr)
    context = _context(probe, names)
    stdout_assertions = _stdout_assertions(probe, rendered_command, context)
    stderr_assertions = _stderr_assertions(probe, stderr, context)
    clone_lifecycle = probe.get("clone_lifecycle", "create")
    if clone_lifecycle == "create":
        clone_payload = prepare_clone_create_payload(
            rendered_command,
            clone_name)
        clone_command = docker_command + ["container", "create"] + clone_payload
    elif clone_lifecycle == "run":
        clone_payload = prepare_clone_run_payload(
            rendered_command,
            clone_name)
        clone_command = docker_command + ["container", "run"] + clone_payload
    else:
        raise ValueError("unknown clone lifecycle %s" % clone_lifecycle)

    _checked_run(command_runner, clone_command)
    if created_names is not None:
        created_names.append(clone_name)
    clone_inspect_text = _inspect_container(
        command_runner,
        docker_command,
        clone_name)

    compare_result = canonicalize_inspect.compare_inspects(
        canonicalize_inspect.load_inspect(original_inspect_text),
        canonicalize_inspect.load_inspect(clone_inspect_text),
        probe["compare_profile"])
    assertions_passed = all(
        assertion["passed"]
        for assertion in stdout_assertions + stderr_assertions)
    passed = compare_result["passed"] and assertions_passed

    return {
        "clone_create_command": clone_command,
        "compare": compare_result,
        "passed": passed,
        "rendered_command": rendered_command,
        "status": "passed" if passed else "failed",
        "stderr": stderr,
        "stderr_assertions": stderr_assertions,
        "stderr_lines": _stream_lines(runlike_result.stderr),
        "stdout": rendered_command,
        "stdout_assertions": stdout_assertions,
    }


def _record_cleanup_error(result, error):
    cleanup_error = _error_path_result(error)
    result.setdefault("cleanup_errors", []).append(cleanup_error)
    if "cleanup_error" not in result:
        result["cleanup_error"] = cleanup_error


def _error_path_result(error):
    if isinstance(error, ProbeCommandError):
        return {
            "command": error.command,
            "passed": False,
            "returncode": error.result.returncode,
            "status": "timeout" if error.result.timed_out else "error",
            "stderr": _normalize_stream(error.result.stderr),
            "stderr_lines": _stream_lines(error.result.stderr),
            "stdout": _normalize_stream(error.result.stdout),
            "timed_out": error.result.timed_out,
        }
    return {
        "error": str(error),
        "passed": False,
        "status": "error",
    }


def run_probe(
        probe,
        command_runner=None,
        runlike_command=None,
        docker_command=None):
    probe = resolve_probe_definition(probe)
    command_runner = command_runner or SubprocessCommandRunner()
    runlike_command = runlike_command or DEFAULT_RUNLIKE_COMMAND
    docker_command = docker_command or DEFAULT_DOCKER_COMMAND
    names = _container_names(probe)
    context = _context(probe, names)
    paths = probe.get("paths", ["container_name", "stdin"])
    result = {
        "option_id": probe.get("option_id"),
        "passed": False,
        "paths": {},
        "probe_id": probe["id"],
    }

    created_names = []
    try:
        _run_helper_commands(command_runner, probe.get("setup", []), context)
        _create_original(
            probe,
            names,
            command_runner,
            docker_command,
            created_names=created_names)
        original_inspect_text = _inspect_container(
            command_runner,
            docker_command,
            names["original"])

        for path_name in paths:
            try:
                result["paths"][path_name] = _run_path(
                    probe,
                    path_name,
                    original_inspect_text,
                    names,
                    command_runner,
                    runlike_command,
                    docker_command,
                    created_names=created_names)
            except Exception as error:
                result["paths"][path_name] = _error_path_result(error)
    except Exception as error:
        result["setup_error"] = _error_path_result(error)
    finally:
        if created_names:
            try:
                _checked_run(
                    command_runner,
                    docker_command + ["container", "rm", "-f"] + created_names)
            except Exception as error:
                _record_cleanup_error(result, error)
        try:
            _run_helper_commands(command_runner, probe.get("cleanup", []), context)
        except Exception as error:
            _record_cleanup_error(result, error)

    result["passed"] = (
        bool(result["paths"])
        and all(path_result["passed"] for path_result in result["paths"].values())
        and "setup_error" not in result
        and "cleanup_error" not in result)
    return result


def load_probe(path):
    with open(path) as probe_file:
        return json.load(probe_file)


def _expand_probe_paths(paths):
    expanded = []
    for path in paths:
        probe_path = Path(path)
        if probe_path.is_dir():
            expanded.extend(
                sorted(str(item) for item in probe_path.glob("**/*.json")))
        else:
            expanded.append(path)
    return expanded


def run_probe_suite(
        probes,
        command_runner=None,
        runlike_command=None,
        docker_command=None):
    results = [
        run_probe(
            probe,
            command_runner=command_runner,
            runlike_command=runlike_command,
            docker_command=docker_command)
        for probe in probes
    ]
    failed = [
        result
        for result in results
        if not result["passed"]
    ]
    return {
        "probe_definitions": build_probe_results_metadata(probes),
        "results": results,
        "schema_version": 1,
        "summary": {
            "failed": len(failed),
            "passed": len(results) - len(failed),
            "total": len(results),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run runlike round-trip probe definitions.")
    parser.add_argument(
        "probes",
        nargs="+",
        help="Probe JSON files or directories containing probe JSON files.")
    parser.add_argument(
        "--runlike-command",
        default=" ".join(DEFAULT_RUNLIKE_COMMAND),
        help="Command used to invoke runlike.")
    parser.add_argument(
        "--docker-command",
        default=" ".join(DEFAULT_DOCKER_COMMAND),
        help="Docker command prefix.")
    parser.add_argument(
        "--command-timeout",
        default=None,
        type=float,
        help=(
            "Per-command timeout in seconds. Use 0 to disable. "
            "Defaults to RUNLIKE_PROBE_COMMAND_TIMEOUT, or 120 seconds "
            "when the environment variable is unset."))
    parser.add_argument(
        "--output",
        help="Optional path for structured JSON probe results.")
    args = parser.parse_args(argv)

    probe_paths = _expand_probe_paths(args.probes)
    probes = [
        load_probe(path)
        for path in probe_paths
    ]
    try:
        command_runner = SubprocessCommandRunner(
            timeout_seconds=args.command_timeout)
    except ProbeConfigurationError as error:
        parser.error(str(error))

    payload = run_probe_suite(
        probes,
        command_runner=command_runner,
        runlike_command=shlex.split(args.runlike_command),
        docker_command=shlex.split(args.docker_command))

    output = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        with open(args.output, "w") as output_file:
            output_file.write(output)
    else:
        sys.stdout.write(output)
    return 0 if payload["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
