from json import dumps
from shlex import split

from click.testing import CliRunner

import runlike.dictionary_renderer as dictionary_renderer
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


def test_image_inherited_list_items_are_filtered_per_value():
    facts = minimal_inspect_facts(config={
        "Env": ["BASE=1", "EXTRA=1"],
    })
    image_facts = minimal_inspect_facts(config={
        "Env": ["BASE=1"],
    })

    model = build_normalized_model(facts, image_facts=image_facts)

    assert model.value_for("env") == ["EXTRA=1"]


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


def test_dictionary_renderer_resolves_probeable_p2_values_from_inspect():
    facts = minimal_inspect_facts(host_config={
        "DeviceCgroupRules": ["c 1:3 rwm"],
        "DeviceRequests": [{
            "Capabilities": [["gpu"]],
            "Count": -1,
            "DeviceIDs": None,
            "Driver": "",
            "Options": {},
        }],
    })
    model = build_normalized_model(facts)

    command = DictionaryRenderer().render(model)
    tokens = split(command)

    assert model.value_for("device-cgroup-rule") == ["c 1:3 rwm"]
    assert model.value_for("gpus") == "all"
    assert "--device-cgroup-rule=c 1:3 rwm" in tokens
    assert "--gpus=all" in tokens


def test_dictionary_renderer_does_not_render_p2_without_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(dictionary_renderer, "RENDER_ORDER", ["future-p2"])
    entries = [{
        "canonical_output_form": "--future-p2",
        "id": "future-p2",
        "render_profile": {
            "command_family": "both",
            "flag": "--future-p2",
            "profile": "canonical-docker-flag",
            "value_type": "string",
        },
        "scope": {
            "classification": "in_scope",
            "reason": None,
        },
        "priority": "P2",
    }]

    class Model(object):
        image = "busybox"
        command = []

        def value_for(self, option_id):
            return "enabled"

    command = dictionary_renderer.DictionaryRenderer(entries).render(Model())

    assert "--future-p2=enabled" not in split(command)


def test_gpu_resolver_ignores_non_gpu_device_requests():
    facts = minimal_inspect_facts(host_config={
        "DeviceRequests": [{
            "Capabilities": [["fpga"]],
            "Count": -1,
            "DeviceIDs": None,
            "Driver": "",
            "Options": {},
        }],
    })

    model = build_normalized_model(facts)
    command = DictionaryRenderer().render(model)

    assert model.value_for("gpus") is None
    assert "--gpus=all" not in split(command)


def test_gpu_resolver_declines_constrained_requests_instead_of_broadening():
    facts = minimal_inspect_facts(host_config={
        "DeviceRequests": [{
            "Capabilities": [["gpu", "compute", "utility"]],
            "Count": -1,
            "DeviceIDs": None,
            "Driver": "",
            "Options": {},
        }],
    })

    model = build_normalized_model(facts)
    command = DictionaryRenderer().render(model)

    assert model.value_for("gpus") is None
    assert "--gpus=all" not in split(command)


def test_gpu_resolver_declines_additional_device_requests():
    facts = minimal_inspect_facts(host_config={
        "DeviceRequests": [
            {
                "Capabilities": [["gpu"]],
                "Count": -1,
                "DeviceIDs": None,
                "Driver": "",
                "Options": {},
            },
            {
                "Capabilities": [["fpga"]],
                "Count": -1,
                "DeviceIDs": None,
                "Driver": "",
                "Options": {},
            },
        ],
    })

    model = build_normalized_model(facts)
    command = DictionaryRenderer().render(model)

    assert model.value_for("gpus") is None
    assert "--gpus=all" not in split(command)


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


def test_image_inherited_healthcheck_timing_is_not_rendered():
    healthcheck = {
        "Interval": 5000000000,
        "Retries": 3,
        "StartPeriod": 2000000000,
        "Test": ["CMD-SHELL", "echo ok"],
        "Timeout": 1000000000,
    }
    facts = minimal_inspect_facts(config={
        "Healthcheck": healthcheck,
    })
    image_facts = minimal_inspect_facts(config={
        "Healthcheck": healthcheck,
    })

    model = build_normalized_model(facts, image_facts=image_facts)
    tokens = split(DictionaryRenderer().render(model))

    assert model.value_for("health-interval") is None
    assert model.value_for("health-start-period") is None
    assert model.value_for("health-timeout") is None
    assert "--health-interval=5000000000ns" not in tokens
    assert "--health-start-period=2000000000ns" not in tokens
    assert "--health-timeout=1000000000ns" not in tokens


def test_no_healthcheck_suppresses_other_health_flags():
    facts = minimal_inspect_facts(config={
        "Healthcheck": {
            "Interval": 5000000000,
            "Retries": 3,
            "Test": ["NONE"],
            "Timeout": 1000000000,
        },
    })
    model = build_normalized_model(facts)

    tokens = split(DictionaryRenderer().render(model))

    assert "--no-healthcheck" in tokens
    assert "--health-interval=5000000000ns" not in tokens
    assert "--health-retries=3" not in tokens
    assert "--health-timeout=1000000000ns" not in tokens


def test_exec_form_healthcheck_is_not_rendered_as_shell_form():
    facts = minimal_inspect_facts(config={
        "Healthcheck": {
            "Test": ["CMD", "test", "-f", "/tmp/has space"],
        },
    })
    model = build_normalized_model(facts)

    tokens = split(DictionaryRenderer().render(model))

    assert model.value_for("health-cmd") is None
    assert "--health-cmd=test -f /tmp/has space" not in tokens


def test_entrypoint_list_uses_only_executable_value():
    facts = minimal_inspect_facts(config={
        "Entrypoint": ["/entrypoint.sh", "--debug"],
    })
    model = build_normalized_model(facts)

    tokens = split(DictionaryRenderer().render(model))

    assert model.value_for("entrypoint") == "/entrypoint.sh"
    assert "--entrypoint=/entrypoint.sh" in tokens
    assert "--entrypoint=/entrypoint.sh --debug" not in tokens


def test_hostname_is_not_rendered_with_host_uts_mode():
    facts = minimal_inspect_facts(host_config={
        "UTSMode": "host",
    })
    model = build_normalized_model(facts)

    tokens = split(DictionaryRenderer().render(model))

    assert "--uts=host" in tokens
    assert "--hostname=fixture-host" not in tokens


def test_image_inherited_exposed_ports_are_filtered_per_port():
    facts = minimal_inspect_facts(config={
        "ExposedPorts": {
            "80/tcp": {},
            "443/tcp": {},
        },
    })
    image_facts = minimal_inspect_facts(config={
        "ExposedPorts": {
            "80/tcp": {},
        },
    })

    model = build_normalized_model(facts, image_facts=image_facts)

    assert model.value_for("expose") == ["443"]


def test_published_ports_are_not_rendered_as_expose():
    facts = minimal_inspect_facts(
        host_config={
            "PortBindings": {
                "80/tcp": [{
                    "HostIp": "",
                    "HostPort": "8080",
                }],
            },
        },
        config={
            "ExposedPorts": {
                "80/tcp": {},
            },
        })

    model = build_normalized_model(facts)
    tokens = split(DictionaryRenderer().render(model))

    assert model.value_for("expose") is None
    assert model.value_for("publish") == ["8080:80"]
    assert "--expose=80" not in tokens
    assert "--publish=8080:80" in tokens


def test_ipv6_publish_bindings_use_docker_run_host_syntax():
    facts = minimal_inspect_facts(host_config={
        "PortBindings": {
            "80/tcp": [
                {
                    "HostIp": "::",
                    "HostPort": "8080",
                },
                {
                    "HostIp": "fd00::1",
                    "HostPort": "8081",
                },
            ],
        },
    })

    model = build_normalized_model(facts)

    assert model.value_for("publish") == [
        "8080:80",
        "[fd00::1]:8081:80",
    ]


def test_publish_merges_unique_network_and_host_config_bindings():
    facts = minimal_inspect_facts(host_config={
        "PortBindings": {
            "80/tcp": [{
                "HostIp": "127.0.0.1",
                "HostPort": "8080",
            }],
        },
    })
    facts[0]["NetworkSettings"]["Ports"] = {
        "80/tcp": [{
            "HostIp": "127.0.0.2",
            "HostPort": "8081",
        }],
    }

    model = build_normalized_model(facts)

    assert model.value_for("publish") == [
        "127.0.0.1:8080:80",
        "127.0.0.2:8081:80",
    ]


def test_named_volume_id_is_hidden_without_use_volume_id():
    facts = minimal_inspect_facts(
        host_config={
            "Binds": ["runlike-volume-id:/data"],
        },
        config={
            "Volumes": {
                "/data": {},
            },
        })
    model = build_normalized_model(facts)
    tokens = split(DictionaryRenderer().render(model))

    assert model.value_for("volume") == ["/data"]
    assert "--volume=/data" in tokens
    assert "runlike-volume-id" not in tokens
