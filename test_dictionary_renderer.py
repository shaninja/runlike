from json import dumps
from shlex import split

from click.testing import CliRunner

from runlike.dictionary_renderer import DictionaryRenderer
from runlike.normalized_model import build_normalized_model
from runlike.runlike import cli


def minimal_inspect_facts(host_config=None, config=None, name="/fixture"):
    base_host_config = {
        "AutoRemove": False,
        "Binds": None,
        "CapAdd": None,
        "CapDrop": None,
        "Devices": None,
        "Dns": None,
        "ExtraHosts": None,
        "LogConfig": {
            "Config": {},
            "Type": "json-file",
        },
        "Mounts": None,
        "NetworkMode": "default",
        "PortBindings": {},
        "Privileged": False,
        "PublishAllPorts": False,
        "RestartPolicy": {
            "MaximumRetryCount": 0,
            "Name": "",
        },
        "Runtime": "",
        "VolumesFrom": None,
    }
    base_config = {
        "AttachStderr": False,
        "AttachStdin": False,
        "AttachStdout": False,
        "Cmd": None,
        "Entrypoint": None,
        "Env": [],
        "ExposedPorts": {},
        "Hostname": "fixture-host",
        "Image": "busybox",
        "Labels": {},
        "MacAddress": "",
        "OpenStdin": False,
        "Tty": False,
        "User": "",
        "Volumes": None,
        "WorkingDir": "",
    }
    if host_config:
        base_host_config.update(host_config)
    if config:
        base_config.update(config)
    return [{
        "Config": base_config,
        "HostConfig": base_host_config,
        "Name": name,
        "NetworkSettings": {
            "MacAddress": "",
            "Networks": {},
            "Ports": {},
        },
    }]


def test_normalized_model_resolves_p0_values_from_inspect():
    facts = minimal_inspect_facts(
        host_config={
            "CapAdd": ["NET_ADMIN"],
            "Memory": 67108864,
            "NetworkMode": "runlike-net",
            "PortBindings": {
                "8080/tcp": [{
                    "HostIp": "127.0.0.1",
                    "HostPort": "18080",
                }],
            },
        },
        config={
            "Cmd": ["sh", "-c", "echo ok"],
            "Env": ["A=1"],
            "Labels": {
                "com.example": "yes",
            },
            "OpenStdin": True,
            "Tty": True,
            "WorkingDir": "/work",
        })

    model = build_normalized_model(facts)

    assert model.image == "busybox"
    assert model.command == ["sh", "-c", "echo ok"]
    assert model.value_for("name") == "fixture"
    assert model.value_for("env") == ["A=1"]
    assert model.value_for("label") == ["com.example=yes"]
    assert model.value_for("cap-add") == ["NET_ADMIN"]
    assert model.value_for("memory") == 67108864
    assert model.value_for("network") == "runlike-net"
    assert model.value_for("publish") == ["127.0.0.1:18080:8080"]
    assert model.value_for("interactive") is True
    assert model.value_for("tty") is True
    assert model.value_for("workdir") == "/work"


def test_dictionary_renderer_uses_model_values_and_canonical_dictionary_flags():
    facts = minimal_inspect_facts(
        host_config={
            "CapAdd": ["NET_ADMIN"],
            "Memory": 67108864,
            "PortBindings": {
                "8080/tcp": [{
                    "HostIp": "",
                    "HostPort": "18080",
                }],
            },
        },
        config={
            "Cmd": ["sh", "-c", "echo ok"],
            "Env": ["B=2", "A=1"],
            "OpenStdin": True,
            "Tty": True,
            "WorkingDir": "/work",
        })
    model = build_normalized_model(facts)

    command = DictionaryRenderer().render(model)

    assert command == (
        "docker run --name=fixture --hostname=fixture-host "
        "--env=A=1 --env=B=2 --cap-add=NET_ADMIN --interactive "
        "--workdir=/work --publish=18080:8080 --memory=67108864 "
        "--detach --tty busybox sh -c 'echo ok'")


def test_cli_stdin_uses_dictionary_pipeline_for_rendering():
    runner = CliRunner(mix_stderr=False)
    facts = minimal_inspect_facts(
        host_config={
            "CapAdd": ["NET_ADMIN"],
        },
        config={
            "Env": ["A=1"],
        })

    result = runner.invoke(cli, ["--stdin"], input=dumps(facts))

    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.stdout == (
        "docker run --name=fixture --hostname=fixture-host "
        "--env=A=1 --cap-add=NET_ADMIN --detach busybox\n")


def test_mount_renderer_quotes_full_mount_value_once():
    facts = minimal_inspect_facts(host_config={
        "Mounts": [{
            "ReadOnly": True,
            "Source": "/tmp/run like source",
            "Target": "/run like target",
            "Type": "bind",
        }],
    })
    model = build_normalized_model(facts)

    tokens = split(DictionaryRenderer().render(model))
    mount_index = tokens.index("--mount")

    assert tokens[mount_index + 1] == (
        "type=bind,source=/tmp/run like source,"
        "target=/run like target,readonly")
