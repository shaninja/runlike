import sys
from shlex import split
from json import load
from pathlib import Path


DEFAULT_DICTIONARY_PATH = (
    Path(__file__).resolve().parents[1] / "spec" / "option-dictionary")

DEFAULT_VALUES_BY_OPTION_ID = {
    "cgroupns": set(["", "private"]),
    "ipc": set(["", "private"]),
    "log-driver": set(["", "json-file"]),
    "memory-swappiness": set([None, -1]),
    "network": set(["", "default", "bridge"]),
}


def load_dictionary_entries(path=DEFAULT_DICTIONARY_PATH):
    entries = []
    dictionary_path = Path(path)
    if not dictionary_path.exists():
        return entries
    for entry_path in sorted(dictionary_path.glob("*.json")):
        with entry_path.open() as entry_file:
            entries.append(load(entry_file))
    return entries


def _container_document(facts):
    if isinstance(facts, list):
        if not facts:
            return {}
        return facts[0]
    return facts or {}


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


def _fact_values(facts, path):
    return _values_at_path(_container_document(facts), path.split("."))


def _is_default_value(option_id, value):
    if option_id == "network" and isinstance(value, dict):
        return not [
            network_name
            for network_name in value
            if network_name not in ("default", "bridge")
        ]
    if option_id == "restart" and isinstance(value, dict):
        return value.get("Name") in (None, "", "no")

    defaults = DEFAULT_VALUES_BY_OPTION_ID.get(option_id)
    if defaults is not None:
        return value in defaults

    if value is None or value is False:
        return True
    if value == "" or value == [] or value == {}:
        return True
    if isinstance(value, (int, float)) and value == 0:
        return True
    return False


def _is_detected_value(option_id, value):
    if option_id == "health-cmd":
        return isinstance(value, list) and value and value[0] != "NONE"
    return not _is_default_value(option_id, value)


def _flag_from_token(token):
    if token.startswith("--") and "=" in token:
        return token.split("=", 1)[0]
    if token.startswith("-") and token != "-":
        return token
    return None


def _entry_spellings(entry):
    return (
        [entry["canonical_output_form"]]
        + entry.get("manifest_flags", [])
        + entry.get("aliases", []))


def _flag_owner_by_spelling(dictionary_entries):
    owners = {}
    for entry in dictionary_entries:
        for spelling in _entry_spellings(entry):
            owners[spelling] = entry["id"]
    return owners


def _flag_takes_value_by_spelling(dictionary_entries):
    takes_value = {}
    for entry in dictionary_entries:
        value_type = entry.get("render_profile", {}).get("value_type")
        for spelling in _entry_spellings(entry):
            takes_value[spelling] = value_type is not None
    return takes_value


def _rendered_command_tokens(rendered_command):
    if not rendered_command:
        return []
    try:
        return split(rendered_command.replace("\\\n", " "))
    except ValueError:
        return []


def _docker_run_option_tokens(tokens, flag_takes_value):
    index = 0
    if index < len(tokens) and tokens[index] == "docker":
        index += 1
    if index < len(tokens) and tokens[index] == "run":
        index += 1

    option_tokens = []
    skip_value = False
    for token in tokens[index:]:
        if skip_value:
            skip_value = False
            continue
        if token == "--":
            break

        flag = _flag_from_token(token)
        if not flag:
            break

        option_tokens.append(token)
        if "=" not in token and flag_takes_value.get(flag):
            skip_value = True

    return option_tokens


def rendered_option_ids(rendered_command, dictionary_entries):
    owners = _flag_owner_by_spelling(dictionary_entries)
    flag_takes_value = _flag_takes_value_by_spelling(dictionary_entries)
    option_ids = set()
    tokens = _docker_run_option_tokens(
        _rendered_command_tokens(rendered_command),
        flag_takes_value)
    for token in tokens:
        flag = _flag_from_token(token)
        if flag in owners:
            option_ids.add(owners[flag])
    return option_ids


class UnsupportedOptionWarningEngine(object):

    def __init__(self, dictionary_entries=None):
        self.dictionary_entries = (
            dictionary_entries
            if dictionary_entries is not None
            else load_dictionary_entries())

    def detected_unsupported_options(
            self,
            facts,
            input_path,
            image_facts=None,
            rendered_command=None):
        rendered_ids = rendered_option_ids(
            rendered_command,
            self.dictionary_entries)
        detected_option_ids = self._detected_option_ids_from_model(
            facts,
            image_facts=image_facts)
        detected = []
        for entry in self.dictionary_entries:
            if not self._should_warn_for_entry(entry, input_path, rendered_ids):
                continue
            if entry["id"] in detected_option_ids:
                detected.append(entry)
        return sorted(
            detected,
            key=lambda entry: entry["canonical_output_form"])

    def warning_lines(
            self,
            facts,
            input_path,
            image_facts=None,
            rendered_command=None):
        options = self.detected_unsupported_options(
            facts,
            input_path,
            image_facts=image_facts,
            rendered_command=rendered_command)
        if not options:
            return []
        flags = [
            entry["canonical_output_form"]
            for entry in options
        ]
        return [
            "runlike: warning: unsupported Docker option-states detected: %s"
            % ", ".join(flags)
        ]

    def emit_warnings(
            self,
            facts,
            input_path,
            stream=None,
            image_facts=None,
            rendered_command=None):
        stream = stream or sys.stderr
        for line in self.warning_lines(
                facts,
                input_path,
                image_facts=image_facts,
                rendered_command=rendered_command):
            stream.write(line + "\n")

    def _should_warn_for_entry(self, entry, input_path, rendered_ids):
        if entry["id"] in rendered_ids:
            return False
        if entry.get("path_coverage", {}).get(input_path) != "detectable":
            return False
        if entry.get("scope", {}).get("classification") != "in_scope":
            return False
        return entry.get(
            "warning_behavior",
            {}).get("warn_when_detected_unsupported") is True

    def _detected_option_ids_from_model(self, facts, image_facts=None):
        try:
            from .normalized_model import build_normalized_model
        except ValueError:
            from normalized_model import build_normalized_model
        model = build_normalized_model(
            facts,
            image_facts=image_facts,
            dictionary_entries=self.dictionary_entries)
        return set(model.option_values)

    def _entry_is_detected(self, entry, facts, image_facts=None):
        profile = entry.get("detection_profile", {}).get("profile")
        if profile == "not-observable":
            return False
        if profile == "healthcheck-none-sentinel":
            return self._healthcheck_none_is_detected(
                entry,
                facts,
                image_facts=image_facts)
        return self._inspect_fields_are_detected(
            entry,
            facts,
            image_facts=image_facts)

    def _healthcheck_none_is_detected(self, entry, facts, image_facts=None):
        for path in entry.get("inspect_fields", []):
            for value in _fact_values(facts, path):
                if self._is_image_inherited(path, value, image_facts):
                    continue
                if isinstance(value, list) and value and value[0] == "NONE":
                    return True
                if value == "NONE":
                    return True
        return False

    def _inspect_fields_are_detected(self, entry, facts, image_facts=None):
        option_id = entry["id"]
        for path in entry.get("inspect_fields", []):
            for value in _fact_values(facts, path):
                if self._is_image_inherited(path, value, image_facts):
                    continue
                if _is_detected_value(option_id, value):
                    return True
        return False

    def _is_image_inherited(self, path, value, image_facts):
        if not image_facts:
            return False
        return value in _fact_values(image_facts, path)
