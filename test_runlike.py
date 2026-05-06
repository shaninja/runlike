import unittest
import os
import pipes
from subprocess import check_output
from json import dumps
from click.testing import CliRunner
from unittest.mock import patch
from runlike.option_warnings import (
    UnsupportedOptionWarningEngine,
    rendered_option_ids,
)
from runlike.runlike import cli
from runlike.inspector import Inspector


def minimal_inspect_facts(host_config=None, config=None):
    base_host_config = {
        "Binds": None,
        "VolumesFrom": None,
        "CapAdd": None,
        "CapDrop": None,
        "Dns": None,
        "NetworkMode": "default",
        "Privileged": False,
        "PortBindings": {},
        "Links": None,
        "RestartPolicy": {
            "Name": "",
            "MaximumRetryCount": 0,
        },
        "Devices": None,
        "LogConfig": {
            "Type": "json-file",
            "Config": {},
        },
        "ExtraHosts": None,
        "Runtime": "",
    }
    base_config = {
        "Image": "fixture_image",
        "Hostname": "fixture",
        "User": "",
        "MacAddress": "",
        "Env": [],
        "Volumes": None,
        "WorkingDir": "",
        "Labels": {},
        "AttachStdout": False,
        "Tty": False,
        "Cmd": None,
    }
    if host_config:
        base_host_config.update(host_config)
    if config:
        base_config.update(config)

    return [{
        "Name": "/fixture_container",
        "Config": base_config,
        "HostConfig": base_host_config,
        "NetworkSettings": {
            "MacAddress": "",
            "Ports": {},
        },
    }]


class TestCompatibilityDefaults(unittest.TestCase):

    def test_warning_engine_reports_detected_unsupported_options_in_dictionary_order(self):
        facts = minimal_inspect_facts({
            "CgroupnsMode": "host",
            "Init": True,
        }, config={
            "Env": ["SUPPORTED=1"],
            "Healthcheck": {
                "Test": ["CMD-SHELL", "true"],
            },
        })
        engine = UnsupportedOptionWarningEngine()

        self.assertEqual(
            [
                "runlike: warning: unsupported Docker option-states detected: "
                "--cgroupns, --health-cmd, --init",
            ],
            engine.warning_lines(
                facts,
                "stdin",
                rendered_command=(
                    "docker run --name=fixture_container --hostname=fixture "
                    "--env=SUPPORTED=1 --detach fixture_image")))

    def test_warning_engine_ignores_rendered_options_and_default_values(self):
        facts = minimal_inspect_facts({
            "CgroupnsMode": "private",
            "Init": False,
        }, config={
            "Env": ["SUPPORTED=1"],
        })
        engine = UnsupportedOptionWarningEngine()

        self.assertEqual(
            [],
            engine.warning_lines(
                facts,
                "container_name",
                rendered_command=(
                    "docker run --name=fixture_container --hostname=fixture "
                    "--env=SUPPORTED=1 --detach fixture_image")))

    def test_warning_engine_uses_normalized_defaults_for_runtime_state(self):
        facts = minimal_inspect_facts({
            "ShmSize": 67108864,
        }, config={
            "AttachStdout": True,
            "AttachStderr": True,
        })
        facts[0]["NetworkSettings"]["Networks"] = {
            "bridge": {
                "Aliases": None,
                "IPAddress": "172.17.0.2",
            },
        }
        engine = UnsupportedOptionWarningEngine()

        self.assertEqual(
            [],
            engine.warning_lines(
                facts,
                "container_name",
                rendered_command=(
                    "docker run --name=fixture_container --hostname=fixture "
                    "fixture_image")))

    def test_warning_engine_does_not_treat_rendered_mount_as_volume(self):
        facts = minimal_inspect_facts()
        facts[0]["Mounts"] = [{
                "ReadOnly": True,
                "Source": "/tmp",
                "Target": "/runlike-mount",
                "Type": "bind",
        }]
        engine = UnsupportedOptionWarningEngine()

        self.assertEqual(
            [],
            engine.warning_lines(
                facts,
                "container_name",
                rendered_command=(
                    "docker run --name=fixture_container --hostname=fixture "
                    "--mount type=bind,source=/tmp,target=/runlike-mount,readonly "
                    "--detach "
                    "fixture_image")))

    def test_warning_engine_ignores_memory_swap_derived_from_memory(self):
        facts = minimal_inspect_facts({
            "Memory": 67108864,
            "MemorySwap": 134217728,
        })
        engine = UnsupportedOptionWarningEngine()

        self.assertEqual(
            [],
            engine.warning_lines(
                facts,
                "container_name",
                rendered_command=(
                    "docker run --name=fixture_container --hostname=fixture "
                    "--memory=67108864 --detach fixture_image")))

    def test_warning_engine_ignores_security_opt_side_effects(self):
        facts = minimal_inspect_facts({
            "PidMode": "host",
            "SecurityOpt": ["label=disable"],
        })
        engine = UnsupportedOptionWarningEngine()

        self.assertEqual(
            [],
            engine.warning_lines(
                facts,
                "container_name",
                rendered_command=(
                    "docker run --name=fixture_container --hostname=fixture "
                    "--pid=host --detach fixture_image")))

    def test_rendered_option_ids_are_derived_from_command_aliases(self):
        engine = UnsupportedOptionWarningEngine()

        self.assertEqual(
            set(["env", "interactive", "publish", "tty"]),
            rendered_option_ids(
                "docker run -i -t -p 8080:80 --env=A=1 busybox",
                engine.dictionary_entries))

    def test_rendered_option_ids_stop_at_container_command_boundary(self):
        engine = UnsupportedOptionWarningEngine()

        self.assertEqual(
            set(["env", "name"]),
            rendered_option_ids(
                "docker run --name fixture_container --env A=1 "
                "busybox --init -c --health-cmd",
                engine.dictionary_entries))

    def test_warning_engine_does_not_ignore_unsupported_command_arguments(self):
        facts = minimal_inspect_facts({
            "Init": True,
        })
        engine = UnsupportedOptionWarningEngine()

        self.assertEqual(
            [
                "runlike: warning: unsupported Docker option-states detected: "
                "--init",
            ],
            engine.warning_lines(
                facts,
                "container_name",
                rendered_command=(
                    "docker run --name=fixture_container "
                    "--hostname=fixture "
                    "--detach fixture_image --init")))

    def test_warning_engine_ignores_image_inherited_unsupported_options(self):
        facts = minimal_inspect_facts(config={
            "Healthcheck": {
                "Test": ["CMD-SHELL", "true"],
            },
            "StopSignal": "SIGTERM",
        })
        image_facts = [{
            "Config": {
                "Healthcheck": {
                    "Test": ["CMD-SHELL", "true"],
                },
                "StopSignal": "SIGTERM",
            },
        }]
        engine = UnsupportedOptionWarningEngine()

        self.assertEqual(
            [],
            engine.warning_lines(
                facts,
                "container_name",
                image_facts=image_facts,
                rendered_command=(
                    "docker run --name=fixture_container --hostname=fixture "
                    "--detach fixture_image")))

    def test_cli_writes_unsupported_option_warnings_to_stderr_only(self):
        runner = CliRunner(mix_stderr=False)
        facts = minimal_inspect_facts({
            "Init": True,
        })

        result = runner.invoke(cli, ["--stdin"], input=dumps(facts))

        self.assertEqual(0, result.exit_code)
        self.assertEqual(
            "runlike: warning: unsupported Docker option-states detected: --init\n",
            result.stderr)
        self.assertTrue(result.stdout.startswith("docker run "))
        self.assertNotIn("warning:", result.stdout)

    def test_default_bridge_network_is_not_rendered(self):
        ins = Inspector(no_name=True)
        ins.facts = minimal_inspect_facts({
            "NetworkMode": "bridge",
        })

        self.assertNotIn("--network", ins.format_cli())

    def test_default_no_restart_policy_is_not_rendered(self):
        ins = Inspector(no_name=True)
        ins.facts = minimal_inspect_facts({
            "RestartPolicy": {
                "Name": "no",
                "MaximumRetryCount": 0,
            },
        })

        self.assertNotIn("--restart", ins.format_cli())

    def test_image_inherited_labels_are_not_rendered_when_image_facts_exist(self):
        ins = Inspector()
        ins.facts = minimal_inspect_facts(config={
            "Labels": {
                "com.example.explicit": "1",
                "org.opencontainers.image.version": "24.04",
            },
        })
        ins.image_facts = [{
            "Config": {
                "Labels": {
                    "org.opencontainers.image.version": "24.04",
                },
            },
        }]

        ins.parse_labels()

        self.assertEqual(["--label='com.example.explicit=1'"], ins.options)

    def test_live_inspection_loads_image_facts_by_image_id(self):
        facts = minimal_inspect_facts(config={
            "Image": "runlike_fixture:latest",
        })
        facts[0]["Image"] = "sha256:actual-image-id"
        image_facts = [{
            "Config": {
                "Labels": {
                    "org.opencontainers.image.version": "24.04",
                },
            },
        }]

        with patch("runlike.inspector.check_output") as patched_check_output:
            patched_check_output.side_effect = [
                dumps(facts).encode(),
                dumps(image_facts).encode(),
            ]

            ins = Inspector("fixture")
            ins.inspect()

        self.assertEqual(image_facts, ins.image_facts)
        self.assertEqual(
            ["docker", "image", "inspect", "sha256:actual-image-id"],
            patched_check_output.call_args_list[1][0][0])

    def test_set_facts_resets_image_facts(self):
        ins = Inspector()
        ins.image_facts = [{
            "Config": {
                "Labels": {
                    "org.opencontainers.image.version": "24.04",
                },
            },
        }]

        ins.set_facts(dumps(minimal_inspect_facts()))

        self.assertIsNone(ins.image_facts)

    def test_expose_is_rendered_from_config_exposed_ports(self):
        ins = Inspector(no_name=True)
        ins.facts = minimal_inspect_facts(config={
            "ExposedPorts": {
                "8080/tcp": {},
            },
        })

        self.assertIn("--expose=8080", ins.format_cli())

    def test_p0_host_config_options_are_rendered(self):
        ins = Inspector(no_name=True)
        ins.facts = minimal_inspect_facts({
            "AutoRemove": True,
            "CpusetCpus": "0",
            "CpusetMems": "0",
            "Memory": 67108864,
            "MemoryReservation": 33554432,
            "PidMode": "host",
            "PublishAllPorts": True,
            "ShmSize": 134217728,
        })

        output = ins.format_cli()

        self.assertIn("--rm", output)
        self.assertIn("--cpuset-cpus=0", output)
        self.assertIn("--cpuset-mems=0", output)
        self.assertIn("--memory=67108864", output)
        self.assertIn("--memory-reservation=33554432", output)
        self.assertIn("--pid=host", output)
        self.assertIn("--publish-all", output)
        self.assertIn("--shm-size=134217728", output)

    def test_entrypoint_interactive_and_attach_are_rendered(self):
        ins = Inspector(no_name=True)
        ins.facts = minimal_inspect_facts(config={
            "AttachStdin": True,
            "AttachStdout": False,
            "AttachStderr": False,
            "Entrypoint": ["/bin/sh"],
            "OpenStdin": True,
            "StdinOnce": True,
        })

        output = ins.format_cli()

        self.assertIn("--attach stdin", output)
        self.assertIn("--entrypoint=/bin/sh", output)
        self.assertIn("-i", output)
        self.assertNotIn("--detach=true", output)

    def test_image_inherited_entrypoint_is_not_rendered_when_image_facts_exist(self):
        ins = Inspector(no_name=True)
        ins.facts = minimal_inspect_facts(config={
            "Entrypoint": ["/bin/sh"],
        })
        ins.image_facts = [{
            "Config": {
                "Entrypoint": ["/bin/sh"],
            },
        }]

        self.assertNotIn("--entrypoint", ins.format_cli())

    def test_network_ip_addresses_are_rendered(self):
        ins = Inspector(no_name=True)
        ins.facts = minimal_inspect_facts({
            "NetworkMode": "runlike-net",
        })
        ins.facts[0]["NetworkSettings"]["Networks"] = {
            "runlike-net": {
                "IPAMConfig": {
                    "IPv4Address": "172.28.5.10",
                    "IPv6Address": "fd00:5::10",
                },
            },
        }

        output = ins.format_cli()

        self.assertIn("--network=runlike-net", output)
        self.assertIn("--ip=172.28.5.10", output)
        self.assertIn("--ip6=fd00:5::10", output)

    def test_mounts_are_rendered(self):
        ins = Inspector(no_name=True)
        ins.facts = minimal_inspect_facts({
            "Mounts": [{
                "ReadOnly": True,
                "Source": "/tmp",
                "Target": "/runlike-mount",
                "Type": "bind",
            }],
        })

        output = ins.format_cli()

        self.assertIn(
            "--mount type=bind,source=/tmp,target=/runlike-mount,readonly",
            output)


@unittest.skip("Legacy live fixture suite replaced by Phase 5 focused probes.")
class TestInspection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        check_output("./fixtures.sh")
        cls.outputs = {}
        for i in range(5):

            ins = Inspector("runlike_fixture%d" % (i + 1), True, True)
            ins.inspect()
            cls.outputs[i + 1] = ins.format_cli()

    def expect_substr(self, substr, fixture_index=1):
        hay = TestInspection.outputs[fixture_index]
        if substr not in hay:
            print("Expecting to find:{substr}\nInside:\n{hay}\n".
                  format(substr=substr, hay=hay))
            self.fail()

    def dont_expect_substr(self, substr, fixture_index=1):
        self.assertNotIn(substr, TestInspection.outputs[fixture_index])

    def test_tcp_port(self):
        self.expect_substr("-p 300 \\")

    def test_tcp_port_with_host_port(self):
        self.expect_substr("-p 400:400 \\")

    def test_expose(self):
        self.expect_substr("--expose=1000 \\")

    def test_udp(self):
        self.expect_substr("-p 301/udp \\")

    def test_dns(self):
        self.expect_substr("--dns=8.8.8.8 \\")
        self.expect_substr("--dns=8.8.4.4 \\")

    def test_udp_with_host_port(self):
        self.expect_substr("-p 503:502/udp \\")

    def test_udp_with_host_port_and_ip(self):
        self.expect_substr("-p 127.0.0.1:601:600/udp \\")

    def test_host_volumes(self):
        cur_dir = os.path.dirname(os.path.realpath(__file__))
        self.expect_substr("--volume=%s:/workdir" % pipes.quote(cur_dir))

    def test_no_host_volume(self):
        self.expect_substr('--volume=/random_volume')

    def test_tty(self):
        self.expect_substr('-t \\')
        self.dont_expect_substr('-t \\', 2)

    def test_restart_always(self):
        self.expect_substr('--restart=always \\')

    def test_restart_on_failure(self):
        self.expect_substr('--restart=on-failure \\', 2)

    def test_restart_with_max(self):
        self.expect_substr('--restart=on-failure:3 \\', 3)

    def test_restart_not_present(self):
        self.dont_expect_substr('--restart', 4)

    def test_hostname(self):
        self.expect_substr('--hostname=Essos \\')

    def test_hostname_not_present(self):
        self.dont_expect_substr('--hostname \\', 2)

    def test_network_mode(self):
        self.dont_expect_substr('--network', 1)
        self.expect_substr('--network=host', 2)
        self.expect_substr('--network=runlike_fixture_bridge', 3)

    def test_privileged_mode(self):
        self.expect_substr('--privileged \\')

    def test_privileged_not_present(self):
        self.dont_expect_substr('--privileged \\', 2)

    def test_multi_labels(self):
        self.expect_substr("--label='com.example.environment=test' \\", 1)
        self.expect_substr(
            "--label='com.example.notescaped=$KEEP_DOLLAR' \\", 1)

    def test_one_label(self):
        self.expect_substr("--label='com.example.version=1' \\", 2)

    def test_labels_not_present(self):
        self.dont_expect_substr('--label', 3)

    def test_extra_hosts(self):
        self.expect_substr('--add-host hostname2:127.0.0.2 \\', 1)
        self.expect_substr('--add-host hostname3:127.0.0.3 \\', 1)

    def test_extra_hosts_not_present(self):
        self.dont_expect_substr('--add-host', 2)

    def test_log_driver_default_no_opts(self):
        self.dont_expect_substr('--log-driver', 2)
        self.dont_expect_substr('--log-opt', 2)

    def test_log_driver_default_with_opts(self):
        self.dont_expect_substr('--log-driver', 3)
        self.expect_substr('--log-opt mode=non-blocking \\', 3)
        self.expect_substr('--log-opt max-buffer-size=4m \\', 3)

    def test_log_driver_present(self):
        self.expect_substr('--log-driver=fluentd \\')

    def test_log_driver_options_present(self):
        self.expect_substr('--log-opt fluentd-async-connect=true \\')
        self.expect_substr('--log-opt tag=docker.runlike \\')

    def test_links(self):
        self.expect_substr('--link runlike_fixture4:alias_of4 \\', 5)
        self.expect_substr('--link runlike_fixture1 \\', 5)

    def test_command(self):
        self.dont_expect_substr('/bin/bash', 1)
        self.expect_substr('/bin/bash sleep.sh', 2)
        self.expect_substr("bash -c 'bash sleep.sh'", 3)
        self.expect_substr(r"bash -c 'bash \'sleep.sh\'", 4)

    def test_user(self):
        self.expect_substr('--user=daemon')
        self.dont_expect_substr('--user', 2)

    def test_mac_address(self):
        self.expect_substr('--mac-address=6a:00:01:ad:d9:e0', 4)
        self.dont_expect_substr('--mac-address', 2)

    def test_env(self):
        val = '''FOO=thing="quoted value with 'spaces' and 'single quotes'"'''
        self.expect_substr("""--env=%s""" % pipes.quote(val))
        self.expect_substr("--env=SET_WITHOUT_VALUE")

    def test_cap_add(self):
        self.expect_substr("--cap-add=CHOWN")

    def test_devices(self):
        self.expect_substr("--device /dev/null:/dev/null:r")
        self.expect_substr("--device /dev/null:/dev/null", 2)

    def test_workdir(self):
        self.expect_substr("--workdir=/workdir")
        self.dont_expect_substr('--workdir', 2)

    def test_runtime(self):
        self.expect_substr('--runtime=runc')
