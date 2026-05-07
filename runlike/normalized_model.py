from collections import OrderedDict

try:
    from .option_warnings import load_dictionary_entries
except ValueError:
    from option_warnings import load_dictionary_entries


DEFAULT_FALSE_VALUES = set([None, "", False])
NANO_CPUS_PER_CPU = 1000000000


def _container_document(facts):
    if isinstance(facts, list):
        if not facts:
            return {}
        return facts[0]
    return facts or {}


def _image_document(image_facts):
    return _container_document(image_facts)


def _path_parts(path):
    if not path:
        return []
    return path.split(".")


def _values_at_path(value, parts):
    if not parts:
        return [value]

    part = parts[0]
    remaining = parts[1:]
    if part == "*":
        values = []
        if isinstance(value, dict):
            iterable = value.values()
        elif isinstance(value, list):
            iterable = value
        else:
            iterable = []
        for item in iterable:
            values.extend(_values_at_path(item, remaining))
        return values

    if not isinstance(value, dict) or part not in value:
        return []
    return _values_at_path(value[part], remaining)


def _first_value(value):
    if isinstance(value, list):
        if not value:
            return None
        return value[0]
    return value


def _is_empty(value):
    if value == [] or value == {}:
        return True
    if isinstance(value, (list, dict, set)):
        return False
    if value in DEFAULT_FALSE_VALUES:
        return True
    return False


def _sorted_strings(values):
    return sorted(str(value) for value in values if not _is_empty(value))


class NormalizedContainerModel(object):

    def __init__(
            self,
            facts,
            image_facts=None,
            no_name=False,
            dictionary_entries=None):
        self.facts = _container_document(facts)
        self.image_facts = _image_document(image_facts)
        self.no_name = no_name
        self.dictionary_entries = (
            dictionary_entries
            if dictionary_entries is not None
            else load_dictionary_entries())
        self.image = self.get("Config.Image")
        self.command = self._command_parts(self.get("Config.Cmd"))
        self.option_values = OrderedDict()

    def get(self, path, default=None):
        values = self.values(path)
        if not values:
            return default
        return values[0]

    def values(self, path):
        return _values_at_path(self.facts, _path_parts(path))

    def image_values(self, path):
        return _values_at_path(self.image_facts, _path_parts(path))

    def image_has_value(self, path, value):
        if not self.image_facts:
            return False
        return value in self.image_values(path)

    def set_option(self, option_id, value):
        if _is_empty(value):
            return
        self.option_values[option_id] = value

    def value_for(self, option_id):
        return self.option_values.get(option_id)

    def _command_parts(self, command):
        if not command:
            return []
        if isinstance(command, str):
            return [command]
        return command


def build_normalized_model(
        facts,
        image_facts=None,
        no_name=False,
        dictionary_entries=None):
    model = NormalizedContainerModel(
        facts,
        image_facts=image_facts,
        no_name=no_name,
        dictionary_entries=dictionary_entries)
    NormalizedModelBuilder(model).build()
    return model


def normalized_model_can_resolve_entry(entry):
    return NormalizedModelBuilder.can_resolve_entry(entry)


class NormalizedModelBuilder(object):

    def __init__(self, model):
        self.model = model

    def build(self):
        for entry in self.model.dictionary_entries:
            value = self._resolve_entry(entry)
            self.model.set_option(entry["id"], value)
        return self.model

    @classmethod
    def can_resolve_entry(cls, entry):
        if getattr(cls, cls._resolver_name(entry), None) is not None:
            return True
        profile = entry.get("render_profile", {}).get("profile")
        return profile == "canonical-docker-flag"

    @staticmethod
    def _resolver_name(entry):
        return "_resolve_" + entry["id"].replace("-", "_")

    def _resolve_entry(self, entry):
        resolver = getattr(
            self,
            self._resolver_name(entry),
            None)
        if resolver is not None:
            return resolver(entry)

        profile = entry.get("render_profile", {}).get("profile")
        if profile == "canonical-docker-flag":
            return self._resolve_canonical_docker_flag(entry)
        return None

    def _resolve_canonical_docker_flag(self, entry):
        value_type = entry.get("render_profile", {}).get("value_type")
        values = self._field_values(entry)
        if value_type in ("list", "map"):
            return self._resolve_list_or_map_values(entry, values)
        if value_type is None:
            return self._resolve_boolean_value(entry, values)
        return self._resolve_scalar_value(entry, values)

    def _field_values(self, entry):
        values = []
        for path in entry.get("inspect_fields", []):
            for value in self.model.values(path):
                if self.model.image_has_value(path, value):
                    continue
                values.append(value)
        return values

    def _resolve_boolean_value(self, entry, values):
        option_id = entry["id"]
        if option_id == "detach":
            stdout_attached = self.model.get("Config.AttachStdout")
            stderr_attached = self.model.get("Config.AttachStderr")
            stdin_attached = self.model.get("Config.AttachStdin")
            return (
                not stdout_attached
                and not stderr_attached
                and not stdin_attached)
        for value in values:
            if value is True:
                return True
        return None

    def _resolve_scalar_value(self, entry, values):
        option_id = entry["id"]
        for value in values:
            if self._scalar_is_default(option_id, value):
                continue
            return value
        return None

    def _resolve_list_or_map_values(self, entry, values):
        option_id = entry["id"]
        collected = []
        for value in values:
            if _is_empty(value):
                continue
            if isinstance(value, dict):
                for key in sorted(value):
                    item = value[key]
                    if item in ({}, None):
                        collected.append(str(key))
                    else:
                        collected.append("%s=%s" % (key, item))
            elif isinstance(value, list):
                collected.extend(value)
            else:
                collected.append(value)
        collected = [
            value
            for value in collected
            if not self._scalar_is_default(option_id, value)
        ]
        return _sorted_strings(collected)

    def _scalar_is_default(self, option_id, value):
        if option_id == "hostname":
            return value in (None, "")
        if option_id == "log-driver":
            return value in (None, "", "json-file")
        if option_id == "cgroupns":
            return value in (None, "", "private")
        if option_id == "ipc":
            return value in (None, "", "private")
        if option_id == "memory" or option_id == "memory-reservation":
            return value in (None, "", 0)
        if option_id == "memory-swappiness":
            return value in (None, "", -1)
        if option_id == "network":
            return value in (None, "", "default", "bridge")
        if option_id == "pids-limit":
            return value in (None, "", 0)
        if option_id == "restart":
            return not value or value == "no"
        if option_id == "shm-size":
            return value in (None, "", 0, 67108864)
        return _is_empty(value) or value == 0

    def _format_duration_ns(self, value):
        if value in (None, "", 0):
            return None
        return "%dns" % int(value)

    def _resolve_annotation(self, entry):
        annotations = []
        for value in self._field_values(entry):
            if not isinstance(value, dict):
                continue
            for key in sorted(value):
                annotations.append("%s=%s" % (key, value[key]))
        return sorted(set(annotations))

    def _resolve_name(self, entry):
        if self.model.no_name:
            return None
        name = self.model.get("Name")
        if isinstance(name, str):
            return name.lstrip("/")
        return name

    def _resolve_hostname(self, entry):
        if self.model.get("HostConfig.UTSMode") == "host":
            return None
        return self._resolve_canonical_docker_flag(entry)

    def _resolve_attach(self, entry):
        stdin = self.model.get("Config.AttachStdin")
        stdout = self.model.get("Config.AttachStdout")
        stderr = self.model.get("Config.AttachStderr")
        default_stdout_stderr = (
            not stdin
            and stdout is True
            and stderr is True)
        streams = []
        if stdin:
            streams.append("stdin")
        if stdout and not default_stdout_stderr:
            streams.append("stdout")
        if stderr and not default_stdout_stderr:
            streams.append("stderr")
        return streams

    def _resolve_entrypoint(self, entry):
        entrypoint = self.model.get("Config.Entrypoint")
        if _is_empty(entrypoint):
            return None
        if self.model.image_has_value("Config.Entrypoint", entrypoint):
            return None
        if isinstance(entrypoint, list):
            return " ".join(str(part) for part in entrypoint)
        return entrypoint

    def _resolve_expose(self, entry):
        ports = self.model.get("Config.ExposedPorts") or {}
        if self.model.image_has_value("Config.ExposedPorts", ports):
            return None
        exposed = []
        for container_port_and_protocol in sorted(ports):
            exposed.append(self._format_container_port(container_port_and_protocol))
        return exposed

    def _resolve_health_cmd(self, entry):
        test = self.model.get("Config.Healthcheck.Test")
        if _is_empty(test) or self.model.image_has_value(
                "Config.Healthcheck.Test",
                test):
            return None
        if isinstance(test, list) and test and test[0] == "NONE":
            return None
        if isinstance(test, list):
            if test and test[0] in ("CMD", "CMD-SHELL"):
                return " ".join(str(part) for part in test[1:])
            return " ".join(str(part) for part in test)
        return test

    def _resolve_health_interval(self, entry):
        return self._format_duration_ns(
            self.model.get("Config.Healthcheck.Interval"))

    def _resolve_health_start_interval(self, entry):
        return self._format_duration_ns(
            self.model.get("Config.Healthcheck.StartInterval"))

    def _resolve_health_start_period(self, entry):
        return self._format_duration_ns(
            self.model.get("Config.Healthcheck.StartPeriod"))

    def _resolve_health_timeout(self, entry):
        return self._format_duration_ns(
            self.model.get("Config.Healthcheck.Timeout"))

    def _resolve_no_healthcheck(self, entry):
        test = self.model.get("Config.Healthcheck.Test")
        if _is_empty(test) or self.model.image_has_value(
                "Config.Healthcheck.Test",
                test):
            return None
        if isinstance(test, list) and test and test[0] == "NONE":
            return True
        if test == "NONE":
            return True
        return None

    def _resolve_label(self, entry):
        labels = self.model.get("Config.Labels") or {}
        image_labels = self.model.image_values("Config.Labels")
        image_labels = _first_value(image_labels) or {}
        values = []
        for key in sorted(labels):
            value = labels[key]
            if image_labels.get(key) == value:
                continue
            values.append("%s=%s" % (key, value))
        return values

    def _resolve_link(self, entry):
        links = self.model.get("HostConfig.Links") or []
        link_options = set()
        for link in links:
            source, destination = link.split(":")
            destination = destination.split("/")[-1]
            source = source.split("/")[-1]
            if source != destination:
                link_options.add("%s:%s" % (source, destination))
            else:
                link_options.add(source)
        return sorted(link_options)

    def _resolve_log_opt(self, entry):
        log_opts = self.model.get("HostConfig.LogConfig.Config") or {}
        return [
            "%s=%s" % (key, log_opts[key])
            for key in sorted(log_opts)
        ]

    def _resolve_mount(self, entry):
        mounts = self.model.get("HostConfig.Mounts") or self.model.get("Mounts") or []
        rendered = []
        for mount in mounts:
            mount_type = mount.get("Type")
            target = mount.get("Target")
            if not mount_type or not target:
                continue
            parts = ["type=%s" % mount_type]
            source = mount.get("Source")
            if source:
                parts.append("source=%s" % source)
            parts.append("target=%s" % target)
            if mount.get("ReadOnly"):
                parts.append("readonly")
            rendered.append(",".join(parts))
        return sorted(rendered)

    def _resolve_network(self, entry):
        return self._resolve_scalar_value(
            entry,
            [self.model.get("HostConfig.NetworkMode")])

    def _resolve_ip(self, entry):
        return _sorted_strings(
            self.model.values("NetworkSettings.Networks.*.IPAMConfig.IPv4Address"))

    def _resolve_ip6(self, entry):
        return _sorted_strings(
            self.model.values("NetworkSettings.Networks.*.IPAMConfig.IPv6Address"))

    def _resolve_link_local_ip(self, entry):
        networks = self.model.get("NetworkSettings.Networks") or {}
        addresses = []
        for network in networks.values():
            ipam_config = network.get("IPAMConfig") or {}
            link_local_ips = ipam_config.get("LinkLocalIPs") or []
            addresses.extend(link_local_ips)
            link_local_ipv6 = network.get("LinkLocalIPv6Address")
            if link_local_ipv6:
                addresses.append(link_local_ipv6)
        return _sorted_strings(addresses)

    def _resolve_memory_swap(self, entry):
        memory_swap = self.model.get("HostConfig.MemorySwap")
        if memory_swap in (None, "", 0):
            return None
        memory = self.model.get("HostConfig.Memory") or 0
        if memory and memory_swap == memory * 2:
            return None
        return memory_swap

    def _resolve_cpus(self, entry):
        nano_cpus = self.model.get("HostConfig.NanoCpus")
        if nano_cpus in (None, "", 0):
            return None
        nano_cpus = int(nano_cpus)
        whole = nano_cpus // NANO_CPUS_PER_CPU
        remainder = nano_cpus % NANO_CPUS_PER_CPU
        if not remainder:
            return str(whole)
        return ("%d.%09d" % (whole, remainder)).rstrip("0")

    def _resolve_publish(self, entry):
        ports = self.model.get("NetworkSettings.Ports") or {}
        port_bindings = self.model.get("HostConfig.PortBindings") or {}
        merged_ports = {}
        merged_ports.update(ports)
        merged_ports.update(port_bindings)

        published = []
        for container_port_and_protocol in sorted(merged_ports):
            bindings = merged_ports[container_port_and_protocol]
            if not bindings:
                continue
            for binding in bindings:
                published.append(
                    self._format_published_port(
                        container_port_and_protocol,
                        binding))
        return sorted(published)

    def _resolve_restart(self, entry):
        restart_policy = self.model.get("HostConfig.RestartPolicy") or {}
        name = restart_policy.get("Name")
        if not name or name == "no":
            return None
        if name == "on-failure":
            max_retries = restart_policy.get("MaximumRetryCount")
            if max_retries and max_retries > 0:
                return "%s:%d" % (name, max_retries)
        return name

    def _resolve_security_opt(self, entry):
        values = self.model.get("HostConfig.SecurityOpt") or []
        if (
                values == ["label=disable"]
                and (
                    self.model.get("HostConfig.Privileged")
                    or self.model.get("HostConfig.PidMode") == "host")):
            return None
        return _sorted_strings(values)

    def _resolve_volume(self, entry):
        volumes = []
        for value in self.model.values("HostConfig.Binds"):
            if isinstance(value, list):
                volumes.extend(value)
        config_volumes = self.model.get("Config.Volumes") or {}
        for target in sorted(config_volumes):
            volumes.append(target)
        return _sorted_strings(volumes)

    def _resolve_tmpfs(self, entry):
        tmpfs = self.model.get("HostConfig.Tmpfs") or {}
        if isinstance(tmpfs, list):
            return _sorted_strings(tmpfs)
        rendered = []
        for target in sorted(tmpfs):
            options = tmpfs[target]
            if options:
                rendered.append("%s:%s" % (target, options))
            else:
                rendered.append(target)
        return rendered

    def _resolve_ulimit(self, entry):
        ulimits = self.model.get("HostConfig.Ulimits") or []
        rendered = []
        for ulimit in ulimits:
            name = ulimit.get("Name")
            if not name:
                continue
            soft = ulimit.get("Soft")
            hard = ulimit.get("Hard")
            if hard is None or hard == soft:
                rendered.append("%s=%s" % (name, soft))
            else:
                rendered.append("%s=%s:%s" % (name, soft, hard))
        return sorted(rendered)

    def _resolve_device(self, entry):
        devices = self.model.get("HostConfig.Devices") or []
        rendered = []
        for device_spec in devices:
            host = device_spec["PathOnHost"]
            container = device_spec["PathInContainer"]
            permissions = device_spec["CgroupPermissions"]
            value = "%s:%s" % (host, container)
            if permissions != "rwm":
                value += ":%s" % permissions
            rendered.append(value)
        return sorted(rendered)

    def _format_container_port(self, container_port_and_protocol):
        container_port, protocol = container_port_and_protocol.split("/")
        if protocol == "tcp":
            return container_port
        return "%s/%s" % (container_port, protocol)

    def _format_published_port(self, container_port_and_protocol, binding):
        container_port = self._format_container_port(container_port_and_protocol)
        host_ip = binding.get("HostIp", "")
        host_port = binding.get("HostPort", "")

        prefix = ""
        if host_ip not in ("", "0.0.0.0"):
            prefix += host_ip + ":"
        if host_port not in ("", "0"):
            prefix += host_port + ":"
        return prefix + container_port
