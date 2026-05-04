import importlib.util
import json
from pathlib import Path


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
