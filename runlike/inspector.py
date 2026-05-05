import sys
import re
from subprocess import (
    check_output,
    STDOUT,
    CalledProcessError
)
from json import loads, dumps
from pipes import quote


def die(message):
    sys.stderr.write(message + "\n")
    sys.exit(1)


class Inspector(object):

    def __init__(self, container=None, no_name=None, pretty=None):
        self.container = container
        self.no_name = no_name
        self.output = ""
        self.pretty = pretty
        self.facts = None
        self.image_facts = None
        self.options = []

    def inspect(self):
        try:
            output = check_output(
                ["docker", "container", "inspect", self.container],
                stderr=STDOUT)
            self.facts = loads(output.decode())
            self.inspect_image()
        except CalledProcessError as e:
            if b"No such container" in e.output:
                die("No such container %s" % self.container)
            else:
                die(str(e))

    def inspect_image(self):
        self.image_facts = None
        image = self.get_fact("Image")
        if not image:
            return
        try:
            output = check_output(
                ["docker", "image", "inspect", image],
                stderr=STDOUT)
            self.image_facts = loads(output.decode())
        except CalledProcessError:
            self.image_facts = None

    def set_facts(self, raw_json):
        self.facts = loads(raw_json)
        self.image_facts = None

    def _get_fact(self, source, path):
        parts = path.split(".")
        if not source:
            return None
        value = source[0]
        for p in parts:
            if p not in value:
                return None
            value = value[p]
        return value

    def get_fact(self, path):
        return self._get_fact(self.facts, path)

    def get_image_fact(self, path):
        return self._get_fact(self.image_facts, path)

    def multi_option(self, path, option):
        values = self.get_fact(path)
        if values:
            for val in values:
                self.options.append('--%s=%s' % (option, quote(val)))

    def parse_hostname(self):
        hostname = self.get_fact("Config.Hostname")
        self.options.append("--hostname=%s" % hostname)

    def parse_user(self):
        user = self.get_fact("Config.User")
        if user != "":
            self.options.append("--user=%s" % user)

    def parse_macaddress(self):
        try:
            mac_address = self.get_fact("Config.MacAddress") or self.get_fact("NetworkSettings.MacAddress") or {}
            if mac_address:
                self.options.append("--mac-address=%s" % mac_address)
        except Exception:
            pass

    def parse_ports(self):
        ports = self.get_fact("NetworkSettings.Ports") or {}
        ports.update(self.get_fact("HostConfig.PortBindings") or {})
        for exposed_port in self.get_fact("Config.ExposedPorts") or {}:
            ports.setdefault(exposed_port, None)

        if ports:
            for container_port_and_protocol, options in ports.items():
                container_port, protocol = container_port_and_protocol.split('/')
                protocol_part = '' if protocol == 'tcp' else '/udp'
                option_part = '-p '
                host_port_part = ''
                hostname_part = ''

                if options is None:
                    # --expose
                    option_part = '--expose='
                else:
                    # -p
                    host_ip = options[0]['HostIp']
                    host_port = options[0]['HostPort']

                    if host_port != '0' and host_port != '':
                        host_port_part = f"{host_port}:"

                    if host_ip not in ['0.0.0.0', '']:
                        hostname_part = f"{host_ip}:"

                self.options.append(f"{option_part}{hostname_part}{host_port_part}{container_port}{protocol_part}")

    def parse_links(self):
        links = self.get_fact("HostConfig.Links")
        link_options = set()
        if links is not None:
            for link in links:
                src, dst = link.split(":")
                dst = dst.split("/")[-1]
                src = src.split("/")[-1]
                if src != dst:
                    link_options.add('--link %s:%s' % (src, dst))
                else:
                    link_options.add('--link %s' % (src))

        self.options += list(link_options)

    def parse_restart(self):
        restart = self.get_fact("HostConfig.RestartPolicy.Name")
        if not restart or restart == 'no':
            return
        elif restart == 'on-failure':
            max_retries = self.get_fact(
                "HostConfig.RestartPolicy.MaximumRetryCount")
            if max_retries > 0:
                restart += ":%d" % max_retries
        self.options.append("--restart=%s" % restart)

    def parse_host_config_value(self, path, option, default=None):
        value = self.get_fact(path)
        if value in (None, "", default):
            return
        self.options.append("--%s=%s" % (option, value))

    def parse_auto_remove(self):
        if self.get_fact("HostConfig.AutoRemove"):
            self.options.append("--rm")

    def parse_publish_all(self):
        if self.get_fact("HostConfig.PublishAllPorts"):
            self.options.append("--publish-all")

    def parse_attach(self):
        attached = []
        if self.get_fact("Config.AttachStdin"):
            attached.append("stdin")
        if self.get_fact("Config.AttachStdout") is False and attached:
            pass
        if self.get_fact("Config.AttachStdout") and attached:
            attached.append("stdout")
        if self.get_fact("Config.AttachStderr") and attached:
            attached.append("stderr")
        for stream in attached:
            self.options.append("--attach %s" % stream)

    def parse_interactive(self):
        if self.get_fact("Config.OpenStdin"):
            self.options.append("-i")

    def parse_entrypoint(self):
        entrypoint = self.get_fact("Config.Entrypoint")
        if not entrypoint:
            return
        if entrypoint == self.get_image_fact("Config.Entrypoint"):
            return
        if isinstance(entrypoint, list):
            entrypoint = " ".join(quote(part) for part in entrypoint)
        self.options.append("--entrypoint=%s" % entrypoint)

    def parse_devices(self):
        devices = self.get_fact("HostConfig.Devices")
        if not devices:
            return
        device_options = set()
        for device_spec in devices:
            host = device_spec['PathOnHost']
            container = device_spec['PathInContainer']
            perms = device_spec['CgroupPermissions']
            spec = '%s:%s' % (host, container)
            if perms != 'rwm':
                spec += ":%s" % perms
            device_options.add('--device %s' % (spec,))

        self.options += list(device_options)

    def parse_labels(self):
        labels = self.get_fact("Config.Labels") or {}
        image_labels = self.get_image_fact("Config.Labels") or {}
        label_options = set()
        if labels is not None:
            for key, value in labels.items():
                if image_labels.get(key) == value:
                    continue
                label_options.add("--label='%s=%s'" % (key, value))
        self.options += list(label_options)

    def parse_log(self):
        log_type = self.get_fact("HostConfig.LogConfig.Type")
        log_opts = self.get_fact("HostConfig.LogConfig.Config") or {}
        log_options = set()
        if log_type != 'json-file':
            log_options.add('--log-driver=%s' % log_type)
        if log_opts:
            for key, value in log_opts.items():
                log_options.add('--log-opt %s=%s' % (key, value))
        self.options += list(log_options)

    def parse_extra_hosts(self):
        hosts = self.get_fact("HostConfig.ExtraHosts") or []
        self.options += ['--add-host %s' % host for host in hosts]

    def parse_workdir(self):
        workdir = self.get_fact("Config.WorkingDir")
        if workdir:
            self.options.append("--workdir=%s" % workdir)

    def parse_runtime(self):
        runtime = self.get_fact("HostConfig.Runtime")
        if runtime:
            self.options.append("--runtime=%s" % runtime)

    def parse_network(self):
        network_mode = self.get_fact("HostConfig.NetworkMode")
        if network_mode not in (None, "", "default", "bridge"):
            self.options.append("--network=" + network_mode)

    def parse_network_ipam(self):
        networks = self.get_fact("NetworkSettings.Networks") or {}
        for network_name in sorted(networks):
            ipam_config = networks[network_name].get("IPAMConfig") or {}
            ipv4_address = ipam_config.get("IPv4Address")
            ipv6_address = ipam_config.get("IPv6Address")
            if ipv4_address:
                self.options.append("--ip=%s" % ipv4_address)
            if ipv6_address:
                self.options.append("--ip6=%s" % ipv6_address)

    def parse_mounts(self):
        mounts = self.get_fact("HostConfig.Mounts") or []
        for mount in mounts:
            mount_type = mount.get("Type")
            source = mount.get("Source")
            target = mount.get("Target")
            if not mount_type or not target:
                continue
            parts = [
                "type=%s" % mount_type,
            ]
            if source:
                parts.append("source=%s" % quote(source))
            parts.append("target=%s" % quote(target))
            if mount.get("ReadOnly"):
                parts.append("readonly")
            self.options.append("--mount %s" % ",".join(parts))

    def format_cli(self):
        self.output = "docker run "

        image = self.get_fact("Config.Image")
        self.options = []

        name = self.get_fact("Name").split("/")[1]
        if not self.no_name:
            self.options.append("--name=%s" % name)
        self.parse_hostname()
        self.parse_user()
        self.parse_macaddress()

        self.multi_option("Config.Env", "env")
        self.multi_option("HostConfig.Binds", "volume")
        self.multi_option("Config.Volumes", "volume")
        self.multi_option("HostConfig.VolumesFrom", "volumes-from")
        self.multi_option("HostConfig.CapAdd", "cap-add")
        self.multi_option("HostConfig.CapDrop", "cap-drop")
        self.multi_option("HostConfig.Dns", "dns")
        self.parse_network()
        self.parse_network_ipam()
        privileged = self.get_fact('HostConfig.Privileged')
        if privileged:
            self.options.append("--privileged")

        self.parse_auto_remove()
        self.parse_publish_all()
        self.parse_attach()
        self.parse_interactive()
        self.parse_entrypoint()
        self.parse_workdir()
        self.parse_ports()
        self.parse_links()
        self.parse_restart()
        self.parse_devices()
        self.parse_mounts()
        self.parse_labels()
        self.parse_log()
        self.parse_extra_hosts()
        self.parse_runtime()
        self.parse_host_config_value("HostConfig.CpusetCpus", "cpuset-cpus")
        self.parse_host_config_value("HostConfig.CpusetMems", "cpuset-mems")
        self.parse_host_config_value("HostConfig.Memory", "memory", 0)
        self.parse_host_config_value(
            "HostConfig.MemoryReservation",
            "memory-reservation",
            0)
        self.parse_host_config_value("HostConfig.PidMode", "pid")
        self.parse_host_config_value(
            "HostConfig.ShmSize",
            "shm-size",
            67108864)

        stdout_attached = self.get_fact("Config.AttachStdout")
        stdin_attached = self.get_fact("Config.AttachStdin")
        if not stdout_attached and not stdin_attached:
            self.options.append("--detach=true")

        if self.get_fact("Config.Tty"):
            self.options.append('-t')

        parameters = ["run"]
        if self.options:
            parameters += self.options
        parameters.append(image)

        cmd_parts = self.get_fact("Config.Cmd")
        if cmd_parts:
            # NOTE: pipes.quote() performs syntactically correct
            # quoting and replace operation below is needed just for
            # aesthetic reasons and visual similarity with old output.
            quoted = [
                quote(p).replace("'\"'\"'", r"\'")
                for p in cmd_parts
            ]
            command = " ".join(quoted)
            parameters.append(command)

        joiner = " "
        if self.pretty:
            joiner += "\\\n\t"
        parameters = joiner.join(parameters)

        return "docker %s" % parameters
