try:
    from pipes import quote
except ImportError:
    from shlex import quote

try:
    from .option_warnings import load_dictionary_entries
except ValueError:
    from option_warnings import load_dictionary_entries


RENDER_ORDER = [
    "name",
    "hostname",
    "domainname",
    "user",
    "group-add",
    "mac-address",
    "env",
    "volume",
    "volume-driver",
    "volumes-from",
    "cap-add",
    "cap-drop",
    "security-opt",
    "dns",
    "dns-option",
    "dns-search",
    "network",
    "ip",
    "ip6",
    "link-local-ip",
    "privileged",
    "rm",
    "publish-all",
    "attach",
    "interactive",
    "entrypoint",
    "workdir",
    "expose",
    "health-cmd",
    "health-interval",
    "health-retries",
    "health-start-interval",
    "health-start-period",
    "health-timeout",
    "no-healthcheck",
    "publish",
    "link",
    "restart",
    "device",
    "mount",
    "tmpfs",
    "label",
    "log-driver",
    "log-opt",
    "add-host",
    "runtime",
    "init",
    "read-only",
    "annotation",
    "blkio-weight",
    "cgroup-parent",
    "cgroupns",
    "cpu-period",
    "cpu-quota",
    "cpu-shares",
    "cpus",
    "cpuset-cpus",
    "cpuset-mems",
    "memory",
    "memory-reservation",
    "memory-swap",
    "memory-swappiness",
    "kernel-memory",
    "oom-kill-disable",
    "oom-score-adj",
    "pid",
    "ipc",
    "pids-limit",
    "shm-size",
    "stop-signal",
    "stop-timeout",
    "sysctl",
    "ulimit",
    "userns",
    "uts",
    "detach",
    "tty",
]

SPACE_SEPARATED_FLAGS = set([
    "--add-host",
    "--attach",
    "--device",
    "--link",
    "--log-opt",
    "--mount",
])


class DictionaryRenderer(object):

    def __init__(self, dictionary_entries=None):
        self.dictionary_entries = (
            dictionary_entries
            if dictionary_entries is not None
            else load_dictionary_entries())
        self.entries_by_id = {
            entry["id"]: entry
            for entry in self.dictionary_entries
        }

    def render(self, model, pretty=False):
        parameters = ["run"]
        for token in self.option_tokens(model):
            parameters.append(token)
        parameters.append(model.image)
        command = self._render_command(model.command)
        if command:
            parameters.append(command)

        joiner = " "
        if pretty:
            joiner += "\\\n\t"
        return "docker %s" % joiner.join(parameters)

    def option_tokens(self, model):
        tokens = []
        for option_id in RENDER_ORDER:
            entry = self.entries_by_id.get(option_id)
            if entry is None or not self._entry_is_renderable(entry):
                continue
            value = model.value_for(option_id)
            if self._empty_value(value):
                continue
            tokens.extend(self._render_option(entry, value))
        return tokens

    def _entry_is_renderable(self, entry):
        if entry.get("priority") not in ("P0", "P1"):
            return False
        if entry.get("scope", {}).get("classification") != "in_scope":
            return False
        return entry.get("render_profile", {}).get("command_family") in (
            "both",
            "run",
        )

    def _empty_value(self, value):
        if value == [] or value == {}:
            return True
        if isinstance(value, (list, dict, set)):
            return False
        if value in (None, "", False):
            return True
        return False

    def _render_option(self, entry, value):
        flag = entry.get("render_profile", {}).get("flag")
        value_type = entry.get("render_profile", {}).get("value_type")
        if value_type is None:
            return [flag]
        if isinstance(value, list):
            return [
                self._render_flag_value(flag, item)
                for item in value
            ]
        return [self._render_flag_value(flag, value)]

    def _render_flag_value(self, flag, value):
        value = quote(str(value))
        if flag in SPACE_SEPARATED_FLAGS:
            return "%s %s" % (flag, value)
        return "%s=%s" % (flag, value)

    def _render_command(self, command):
        if not command:
            return ""
        quoted = [
            quote(str(part)).replace("'\"'\"'", r"\'")
            for part in command
        ]
        return " ".join(quoted)
