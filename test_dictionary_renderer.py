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


def test_string_command_is_rendered_as_one_command_argument():
    facts = minimal_inspect_facts(config={
        "Cmd": "echo ok",
    })
    model = build_normalized_model(facts)

    command = DictionaryRenderer().render(model)

    assert model.command == ["echo ok"]
    assert command == (
        "docker run --name=fixture --hostname=fixture-host "
        "--detach busybox 'echo ok'")


def test_attach_streams_render_without_requiring_stdin():
    facts = minimal_inspect_facts(config={
        "AttachStderr": True,
        "AttachStdin": False,
        "AttachStdout": False,
    })
    model = build_normalized_model(facts)

    command = DictionaryRenderer().render(model)

    assert model.value_for("attach") == ["stderr"]
    assert "--attach stderr" in command
    assert "--detach" not in command


def test_attach_streams_preserve_explicit_stdin_stdout_stderr_set():
    facts = minimal_inspect_facts(config={
        "AttachStderr": True,
        "AttachStdin": True,
        "AttachStdout": True,
    })
    model = build_normalized_model(facts)

    command = DictionaryRenderer().render(model)

    assert model.value_for("attach") == ["stdin", "stdout", "stderr"]
    assert "--attach stdin" in command
    assert "--attach stdout" in command
    assert "--attach stderr" in command


def test_normalized_model_resolves_p1_values_from_inspect():
    facts = minimal_inspect_facts(
        host_config={
            "CpuPeriod": 100000,
            "CpuQuota": 50000,
            "GroupAdd": ["1001"],
            "Healthcheck": None,
            "Init": True,
            "MemorySwap": 134217728,
            "MemorySwappiness": 10,
            "NanoCpus": 1500000000,
            "ReadonlyRootfs": True,
            "Tmpfs": {
                "/run": "rw,size=64k",
            },
            "Ulimits": [{
                "Hard": 2048,
                "Name": "nofile",
                "Soft": 1024,
            }],
        },
        config={
            "Domainname": "example.test",
            "Healthcheck": {
                "Interval": 5000000000,
                "Retries": 3,
                "StartPeriod": 2000000000,
                "Test": ["CMD-SHELL", "echo ok"],
                "Timeout": 1000000000,
            },
        })

    model = build_normalized_model(facts)

    assert model.value_for("cpu-period") == 100000
    assert model.value_for("cpu-quota") == 50000
    assert model.value_for("cpus") == "1.5"
    assert model.value_for("domainname") == "example.test"
    assert model.value_for("group-add") == ["1001"]
    assert model.value_for("health-cmd") == "echo ok"
    assert model.value_for("health-interval") == "5000000000ns"
    assert model.value_for("health-retries") == 3
    assert model.value_for("health-start-period") == "2000000000ns"
    assert model.value_for("health-timeout") == "1000000000ns"
    assert model.value_for("init") is True
    assert model.value_for("memory-swap") == 134217728
    assert model.value_for("memory-swappiness") == 10
    assert model.value_for("read-only") is True
    assert model.value_for("tmpfs") == ["/run:rw,size=64k"]
    assert model.value_for("ulimit") == ["nofile=1024:2048"]


def test_dictionary_renderer_includes_supported_p1_options():
    facts = minimal_inspect_facts(
        host_config={
            "CpuPeriod": 100000,
            "CpuQuota": 50000,
            "GroupAdd": ["1001"],
            "Init": True,
            "MemorySwap": 134217728,
            "MemorySwappiness": 10,
            "NanoCpus": 1500000000,
            "ReadonlyRootfs": True,
            "Tmpfs": {
                "/run": "rw,size=64k",
            },
            "Ulimits": [{
                "Hard": 2048,
                "Name": "nofile",
                "Soft": 1024,
            }],
        },
        config={
            "Domainname": "example.test",
            "Healthcheck": {
                "Interval": 5000000000,
                "Retries": 3,
                "StartPeriod": 2000000000,
                "Test": ["CMD-SHELL", "echo ok"],
                "Timeout": 1000000000,
            },
        })
    model = build_normalized_model(facts)

    tokens = split(DictionaryRenderer().render(model))

    assert "--domainname=example.test" in tokens
    assert "--group-add=1001" in tokens
    assert "--init" in tokens
    assert "--read-only" in tokens
    assert "--health-cmd=echo ok" in tokens
    assert "--health-interval=5000000000ns" in tokens
    assert "--health-retries=3" in tokens
    assert "--health-start-period=2000000000ns" in tokens
    assert "--health-timeout=1000000000ns" in tokens
    assert "--cpu-period=100000" in tokens
    assert "--cpu-quota=50000" in tokens
    assert "--cpus=1.5" in tokens
    assert "--memory-swap=134217728" in tokens
    assert "--memory-swappiness=10" not in tokens
    assert "--tmpfs=/run:rw,size=64k" in tokens
    assert "--ulimit=nofile=1024:2048" in tokens


def test_hostname_is_not_rendered_with_host_uts_mode():
    facts = minimal_inspect_facts(host_config={
        "UTSMode": "host",
    })
    model = build_normalized_model(facts)

    tokens = split(DictionaryRenderer().render(model))

    assert "--uts=host" in tokens
    assert "--hostname=fixture-host" not in tokens
