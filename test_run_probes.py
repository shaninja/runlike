import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent


def load_probe_module():
    script = ROOT / "tools" / "run_probes.py"
    assert script.exists(), "expected tools/run_probes.py to exist"
    spec = importlib.util.spec_from_file_location("run_probes", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_canonicalize_module():
    script = ROOT / "tools" / "canonicalize_inspect.py"
    assert script.exists(), "expected tools/canonicalize_inspect.py to exist"
    spec = importlib.util.spec_from_file_location(
        "canonicalize_inspect", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_document(name, env=None):
    if env is None:
        env = ["A=1"]
    return [{
        "Name": "/" + name,
        "Config": {
            "Env": env,
            "Image": "busybox",
        },
        "HostConfig": {},
        "NetworkSettings": {},
    }]


class FakeCommandRunner(object):

    def __init__(self, run_probes, responses):
        self.run_probes = run_probes
        self.responses = list(responses)
        self.calls = []

    def run(self, command, stdin=None):
        self.calls.append({
            "command": command,
            "stdin": stdin,
        })
        if not self.responses:
            return self.run_probes.CommandResult(0, "", "")
        return self.responses.pop(0)


def test_prepare_clone_create_command_rewrites_run_command_for_probe_clone():
    module = load_probe_module()

    command = module.prepare_clone_create_command(
        "docker run --name=original -d --rm --env A=1 busybox sh -c 'sleep 600'",
        "clone")

    assert command == [
        "docker",
        "container",
        "create",
        "--name",
        "clone",
        "--env",
        "A=1",
        "busybox",
        "sh",
        "-c",
        "sleep 600",
    ]


def test_prepare_clone_run_command_rewrites_name_and_preserves_lifecycle_flags():
    module = load_probe_module()

    command = module.prepare_clone_run_command(
        "docker run --rm --name=original -d --env A=1 busybox sh -c 'sleep 600'",
        "clone")

    assert command == [
        "docker",
        "container",
        "run",
        "--name",
        "clone",
        "--rm",
        "-d",
        "--env",
        "A=1",
        "busybox",
        "sh",
        "-c",
        "sleep 600",
    ]


def test_prepare_clone_create_command_omits_option_delimiter_before_image():
    module = load_probe_module()

    command = module.prepare_clone_create_command(
        "docker run --name original -- busybox sh",
        "clone")

    assert command == [
        "docker",
        "container",
        "create",
        "--name",
        "clone",
        "busybox",
        "sh",
    ]


def test_prepare_clone_create_command_expands_short_flags_and_drops_detach():
    module = load_probe_module()

    command = module.prepare_clone_create_command(
        "docker run -itd --name original -eA=1 busybox sh",
        "clone")

    assert command == [
        "docker",
        "container",
        "create",
        "--name",
        "clone",
        "-i",
        "-t",
        "-e",
        "A=1",
        "busybox",
        "sh",
    ]


def test_value_flags_are_derived_from_docker_option_manifest():
    module = load_probe_module()

    value_flags = module.load_value_flags_from_manifest()

    assert "--env" in value_flags
    assert "-e" in value_flags
    assert "--name" in value_flags
    assert "--detach-keys" in value_flags
    assert "--interactive" not in value_flags
    assert "-i" not in value_flags
    assert "--tty" not in value_flags
    assert "-t" not in value_flags


def test_expand_probe_paths_recurses_into_probe_layout(tmp_path):
    module = load_probe_module()
    probe_root = tmp_path / "probes"
    p0_root = probe_root / "p0"
    p1_root = probe_root / "p1"
    p0_root.mkdir(parents=True)
    p1_root.mkdir(parents=True)
    (p0_root / "env.json").write_text("{}")
    (p1_root / "health.json").write_text("{}")
    (probe_root / "README.md").write_text("not a probe")

    paths = module._expand_probe_paths([str(probe_root)])

    assert paths == [
        str(p0_root / "env.json"),
        str(p1_root / "health.json"),
    ]


def test_resolve_probe_defaults_from_option_dictionary():
    module = load_probe_module()

    probe = module.resolve_probe_definition({
        "id": "env-smoke",
        "option_id": "env",
        "image": "busybox",
        "docker_run_args": ["--env", "A=1"],
        "command": ["sh", "-c", "sleep 600"],
    })

    assert probe["compare_profile"] == {
        "fields": ["Config.Env"],
        "profile": "inspect-projection",
    }
    assert probe["paths"] == ["container_name", "stdin"]


def test_probe_runner_formats_probe_args_and_can_run_original_container():
    run_probes = load_probe_module()
    original = json.dumps(inspect_document("original", ["A=1"]))
    clone = json.dumps(inspect_document("clone", ["A=1"]))
    responses = [
        run_probes.CommandResult(0, "helper\n", ""),
        run_probes.CommandResult(0, "original-id\n", ""),
        run_probes.CommandResult(0, original, ""),
        run_probes.CommandResult(
            0,
            "docker run --name=original --rm -d --env A=1 busybox sh -c 'sleep 600'\n",
            ""),
        run_probes.CommandResult(0, "clone-id\n", ""),
        run_probes.CommandResult(0, clone, ""),
        run_probes.CommandResult(0, "removed\n", ""),
    ]
    fake = FakeCommandRunner(run_probes, responses)
    probe = {
        "id": "rm-smoke",
        "option_id": "env",
        "image": "busybox",
        "original_lifecycle": "run",
        "clone_lifecycle": "run",
        "docker_run_args": ["--env", "{probe_id}=1", "--rm", "-d"],
        "command": ["sh", "-c", "sleep 600"],
        "setup": [
            {"command": ["docker", "network", "create", "{probe_id}"]},
        ],
        "compare_profile": {
            "profile": "inspect-projection",
            "fields": ["Config.Env"],
        },
        "paths": ["container_name"],
    }

    result = run_probes.run_probe(
        probe,
        command_runner=fake,
        runlike_command=["runlike"])

    assert result["passed"] is True
    assert fake.calls[0]["command"] == [
        "docker",
        "network",
        "create",
        "rm-smoke",
    ]
    assert fake.calls[1]["command"] == [
        "docker",
        "container",
        "run",
        "--name",
        "runlike-probe-rm-smoke-original",
        "--env",
        "rm-smoke=1",
        "--rm",
        "-d",
        "busybox",
        "sh",
        "-c",
        "sleep 600",
    ]
    assert fake.calls[4]["command"][:5] == [
        "docker",
        "container",
        "run",
        "--name",
        "runlike-probe-rm-smoke-container-name-clone",
    ]


def test_probe_runner_supports_stdout_contains_assertions():
    run_probes = load_probe_module()
    original = json.dumps(inspect_document("original", ["A=1"]))
    clone = json.dumps(inspect_document("clone", ["A=1"]))
    responses = [
        run_probes.CommandResult(0, "original-id\n", ""),
        run_probes.CommandResult(0, original, ""),
        run_probes.CommandResult(
            0,
            "docker run --name=runlike-probe-name-smoke-original busybox\n",
            ""),
        run_probes.CommandResult(0, "clone-id\n", ""),
        run_probes.CommandResult(0, clone, ""),
        run_probes.CommandResult(0, "removed\n", ""),
    ]
    fake = FakeCommandRunner(run_probes, responses)
    probe = {
        "id": "name-smoke",
        "option_id": "name",
        "image": "busybox",
        "compare_profile": {
            "profile": "not-observable",
            "fields": [],
        },
        "paths": ["container_name"],
        "stdout_contains": ["--name={original_name}"],
    }

    result = run_probes.run_probe(
        probe,
        command_runner=fake,
        runlike_command=["runlike"])

    assert result["passed"] is True
    assert result["paths"]["container_name"]["stdout_assertions"] == [
        {
            "expected": "--name=runlike-probe-name-smoke-original",
            "passed": True,
            "type": "contains",
        },
    ]


def test_probe_runner_supports_stderr_contains_assertions():
    run_probes = load_probe_module()
    original = json.dumps(inspect_document("original", ["A=1"]))
    clone = json.dumps(inspect_document("clone", ["A=1"]))
    responses = [
        run_probes.CommandResult(0, "original-id\n", ""),
        run_probes.CommandResult(0, original, ""),
        run_probes.CommandResult(
            0,
            "docker run --name=original --env A=1 busybox sh -c 'sleep 600'\n",
            "runlike: warning: unsupported Docker option-states detected: --init\n"),
        run_probes.CommandResult(0, "clone-id\n", ""),
        run_probes.CommandResult(0, clone, ""),
        run_probes.CommandResult(0, "removed\n", ""),
    ]
    fake = FakeCommandRunner(run_probes, responses)
    probe = {
        "id": "init-warning-smoke",
        "option_id": "init",
        "image": "busybox",
        "compare_profile": {
            "profile": "not-observable",
            "fields": [],
        },
        "paths": ["container_name"],
        "stderr_contains": [
            "unsupported Docker option-states detected: --init",
        ],
    }

    result = run_probes.run_probe(
        probe,
        command_runner=fake,
        runlike_command=["runlike"])

    assert result["passed"] is True
    assert result["paths"]["container_name"]["stderr_assertions"] == [
        {
            "expected": "unsupported Docker option-states detected: --init",
            "passed": True,
            "type": "contains",
        },
    ]


def test_probe_runner_cleans_up_only_created_containers_for_selected_paths():
    run_probes = load_probe_module()
    original = json.dumps(inspect_document("original", ["A=1"]))
    clone = json.dumps(inspect_document("clone", ["A=1"]))
    responses = [
        run_probes.CommandResult(0, "original-id\n", ""),
        run_probes.CommandResult(0, original, ""),
        run_probes.CommandResult(
            0,
            "docker run --name=original --env A=1 busybox sh -c 'sleep 600'\n",
            ""),
        run_probes.CommandResult(0, "clone-id\n", ""),
        run_probes.CommandResult(0, clone, ""),
        run_probes.CommandResult(0, "removed\n", ""),
    ]
    fake = FakeCommandRunner(run_probes, responses)
    probe = {
        "id": "env-smoke",
        "option_id": "env",
        "image": "busybox",
        "docker_run_args": ["--env", "A=1"],
        "command": ["sh", "-c", "sleep 600"],
        "compare_profile": {
            "profile": "inspect-projection",
            "fields": ["Config.Env"],
        },
        "paths": ["container_name"],
    }

    result = run_probes.run_probe(
        probe,
        command_runner=fake,
        runlike_command=["runlike"])

    assert result["passed"] is True
    assert fake.calls[-1]["command"] == [
        "docker",
        "container",
        "rm",
        "-f",
        "runlike-probe-env-smoke-original",
        "runlike-probe-env-smoke-container-name-clone",
    ]


def test_probe_runner_preserves_first_cleanup_error():
    run_probes = load_probe_module()
    responses = [
        run_probes.CommandResult(0, "", ""),
        run_probes.CommandResult(0, "original-id\n", ""),
        run_probes.CommandResult(1, "", "inspect failed"),
        run_probes.CommandResult(1, "", "rm failed"),
        run_probes.CommandResult(1, "", "helper cleanup failed"),
    ]
    fake = FakeCommandRunner(run_probes, responses)
    probe = {
        "id": "env-smoke",
        "option_id": "env",
        "image": "busybox",
        "compare_profile": {
            "profile": "inspect-projection",
            "fields": ["Config.Env"],
        },
        "paths": ["container_name"],
        "setup": [
            {"command": ["docker", "network", "create", "{probe_id}"]},
        ],
        "cleanup": [
            {"command": ["docker", "network", "rm", "{probe_id}"]},
        ],
    }

    result = run_probes.run_probe(
        probe,
        command_runner=fake,
        runlike_command=["runlike"])

    assert result["passed"] is False
    assert result["cleanup_error"]["stderr"] == "rm failed"
    assert [error["stderr"] for error in result["cleanup_errors"]] == [
        "rm failed",
        "helper cleanup failed",
    ]


def test_probe_runner_reports_non_command_path_errors_structurally():
    run_probes = load_probe_module()
    original = json.dumps(inspect_document("original", ["A=1"]))
    responses = [
        run_probes.CommandResult(0, "original-id\n", ""),
        run_probes.CommandResult(0, original, ""),
        run_probes.CommandResult(0, "not a docker run command\n", ""),
        run_probes.CommandResult(0, "removed\n", ""),
    ]
    fake = FakeCommandRunner(run_probes, responses)
    probe = {
        "id": "env-smoke",
        "option_id": "env",
        "image": "busybox",
        "compare_profile": {
            "profile": "inspect-projection",
            "fields": ["Config.Env"],
        },
        "paths": ["container_name"],
    }

    result = run_probes.run_probe(
        probe,
        command_runner=fake,
        runlike_command=["runlike"])

    assert result["passed"] is False
    assert result["paths"]["container_name"]["passed"] is False
    assert result["paths"]["container_name"]["status"] == "error"
    assert result["paths"]["container_name"]["error"] == (
        "probe clone command must start with docker run")


def test_probe_runner_reports_timed_out_path_commands_structurally():
    run_probes = load_probe_module()
    original = json.dumps(inspect_document("original", ["A=1"]))
    responses = [
        run_probes.CommandResult(0, "original-id\n", ""),
        run_probes.CommandResult(0, original, ""),
        run_probes.CommandResult(
            124,
            "",
            "Command timed out after 1 seconds.",
            timed_out=True),
        run_probes.CommandResult(0, "removed\n", ""),
    ]
    fake = FakeCommandRunner(run_probes, responses)
    probe = {
        "id": "env-smoke",
        "option_id": "env",
        "image": "busybox",
        "compare_profile": {
            "profile": "inspect-projection",
            "fields": ["Config.Env"],
        },
        "paths": ["container_name"],
    }

    result = run_probes.run_probe(
        probe,
        command_runner=fake,
        runlike_command=["runlike"])

    assert result["passed"] is False
    assert result["paths"]["container_name"]["passed"] is False
    assert result["paths"]["container_name"]["status"] == "timeout"
    assert result["paths"]["container_name"]["timed_out"] is True
    assert result["paths"]["container_name"]["stderr"] == (
        "Command timed out after 1 seconds.")


def test_subprocess_command_runner_times_out_hung_commands():
    run_probes = load_probe_module()
    runner = run_probes.SubprocessCommandRunner(timeout_seconds=0.1)

    result = runner.run([
        sys.executable,
        "-c",
        "import time; time.sleep(10)",
    ])

    assert result.timed_out is True
    assert result.returncode != 0
    assert "timed out" in result.stderr


def test_subprocess_command_runner_times_out_descendants_holding_pipes():
    run_probes = load_probe_module()
    runner = run_probes.SubprocessCommandRunner(timeout_seconds=0.1)

    started = time.time()
    result = runner.run([
        sys.executable,
        "-c",
        (
            "import subprocess, sys, time; "
            "subprocess.Popen([sys.executable, '-c', "
            "'import time; time.sleep(2)']); "
            "time.sleep(10)"
        ),
    ])
    elapsed = time.time() - started

    assert result.timed_out is True
    assert elapsed < 1


def test_probe_runner_reports_invalid_timeout_env_without_traceback(
        monkeypatch,
        capsys,
        tmp_path):
    run_probes = load_probe_module()
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(json.dumps({}))
    monkeypatch.setenv("RUNLIKE_PROBE_COMMAND_TIMEOUT", "")

    with pytest.raises(SystemExit) as exit_error:
        run_probes.main([str(probe_path)])

    captured = capsys.readouterr()
    assert exit_error.value.code == 2
    assert "RUNLIKE_PROBE_COMMAND_TIMEOUT must be a number" in captured.err
    assert "Traceback" not in captured.err


def test_probe_runner_reports_non_finite_timeout_env_without_traceback(
        monkeypatch,
        capsys,
        tmp_path):
    run_probes = load_probe_module()
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(json.dumps({}))
    monkeypatch.setenv("RUNLIKE_PROBE_COMMAND_TIMEOUT", "nan")

    with pytest.raises(SystemExit) as exit_error:
        run_probes.main([str(probe_path)])

    captured = capsys.readouterr()
    assert exit_error.value.code == 2
    assert "RUNLIKE_PROBE_COMMAND_TIMEOUT must be finite" in captured.err
    assert "Traceback" not in captured.err


def test_subprocess_command_runner_uses_default_timeout(monkeypatch):
    run_probes = load_probe_module()
    monkeypatch.delenv("RUNLIKE_PROBE_COMMAND_TIMEOUT", raising=False)

    runner = run_probes.SubprocessCommandRunner()

    assert runner.timeout_seconds == 120


def test_probe_runner_executes_both_input_paths_and_captures_results():
    run_probes = load_probe_module()
    original = json.dumps(inspect_document("original", ["A=1"]))
    clone = json.dumps(inspect_document("clone", ["A=1"]))
    responses = [
        run_probes.CommandResult(0, "", ""),  # setup helper
        run_probes.CommandResult(0, "original-id\n", ""),  # create original
        run_probes.CommandResult(0, original, ""),  # inspect original
        run_probes.CommandResult(
            0,
            "docker run --name=original --env A=1 busybox sh -c 'sleep 600'\n",
            "warning: unsupported fixture\n"),
        run_probes.CommandResult(0, "clone-id\n", ""),  # create clone
        run_probes.CommandResult(0, clone, ""),  # inspect clone
        run_probes.CommandResult(
            0,
            "docker run --name=original --env A=1 busybox sh -c 'sleep 600'\n",
            "warning: stdin fixture\n"),
        run_probes.CommandResult(0, "stdin-clone-id\n", ""),  # create clone
        run_probes.CommandResult(0, clone, ""),  # inspect stdin clone
    ]
    fake = FakeCommandRunner(run_probes, responses)
    probe = {
        "id": "env-smoke",
        "option_id": "env",
        "image": "busybox",
        "docker_run_args": ["--env", "A=1"],
        "command": ["sh", "-c", "sleep 600"],
        "compare_profile": {
            "profile": "inspect-projection",
            "fields": ["Config.Env"],
        },
        "paths": ["container_name", "stdin"],
        "setup": [
            {"command": ["docker", "network", "create", "{probe_id}"]},
        ],
        "cleanup": [
            {"command": ["docker", "network", "rm", "{probe_id}"]},
        ],
    }

    result = run_probes.run_probe(
        probe,
        command_runner=fake,
        runlike_command=["runlike"])

    assert result["passed"] is True
    assert result["paths"]["container_name"]["passed"] is True
    assert result["paths"]["container_name"]["stderr_lines"] == [
        "warning: unsupported fixture",
    ]
    assert result["paths"]["stdin"]["passed"] is True
    assert result["paths"]["stdin"]["stderr_lines"] == [
        "warning: stdin fixture",
    ]
    assert fake.calls[0]["command"] == [
        "docker",
        "network",
        "create",
        "env-smoke",
    ]
    assert fake.calls[3]["command"] == ["runlike", "runlike-probe-env-smoke-original"]
    assert json.loads(fake.calls[6]["stdin"]) == inspect_document("original", ["A=1"])
    assert fake.calls[-1]["command"] == [
        "docker",
        "network",
        "rm",
        "env-smoke",
    ]
