import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_dictionary_module():
    script = ROOT / "tools" / "validate_option_dictionary.py"
    assert script.exists(), "expected tools/validate_option_dictionary.py to exist"
    spec = importlib.util.spec_from_file_location(
        "validate_option_dictionary", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def minimal_entry(entry_id, manifest_flags):
    return {
        "id": entry_id,
        "manifest_flags": manifest_flags,
        "canonical_output_form": manifest_flags[0],
        "aliases": [],
        "observability": "observable",
        "inspect_fields": ["Config.Labels"],
        "detection_profile": {"profile": "inspect-field"},
        "compare_profile": {"profile": "exact"},
        "render_profile": {"profile": "flag-value"},
        "path_coverage": {
            "container_name": "detectable",
            "stdin": "detectable",
        },
        "scope": {
            "classification": "in_scope",
            "reason": None,
        },
        "priority": "P0",
        "warning_behavior": {
            "warn_when_detected_unsupported": True,
        },
    }


def test_validate_dictionary_rejects_missing_duplicate_and_unknown_flags():
    module = load_dictionary_module()
    manifest = {
        "options": [
            {"canonical_flag": "--env"},
            {"canonical_flag": "--name"},
        ],
    }
    entries = [
        minimal_entry("env", ["--env"]),
        minimal_entry("duplicate-env", ["--env"]),
        minimal_entry("unknown", ["--unknown"]),
    ]

    errors = module.validate_dictionary(manifest, entries)

    assert "Manifest option --name has no dictionary entry." in errors
    assert "Manifest option --env is covered by multiple dictionary entries: duplicate-env, env." in errors
    assert "Dictionary entry unknown references unknown manifest option --unknown." in errors


def test_validate_dictionary_requires_phase_three_metadata():
    module = load_dictionary_module()
    entry = minimal_entry("name", ["--name"])
    entry["inspect_fields"] = []
    entry["scope"] = {"classification": "out_of_scope", "reason": None}
    manifest = {"options": [{"canonical_flag": "--name"}]}

    errors = module.validate_dictionary(manifest, [entry])

    assert "Dictionary entry name is observable but has no inspect_fields." in errors
    assert "Dictionary entry name is out_of_scope but has no reason." in errors


def test_validate_dictionary_handles_malformed_manifest_flags():
    module = load_dictionary_module()
    manifest = {"options": [{"canonical_flag": "--name"}]}
    entry = minimal_entry("name", ["--name"])
    entry["manifest_flags"] = None

    errors = module.validate_dictionary(manifest, [entry])
    ledger = module.build_coverage_ledger(manifest, [entry])

    assert "Dictionary entry name must list at least one manifest flag." in errors
    assert "Manifest option --name has no dictionary entry." in errors
    assert ledger == [
        {
            "manifest_flag": "--name",
            "owners": [],
            "owner_count": 0,
            "status": "missing",
        },
    ]


def test_build_coverage_ledger_accounts_for_each_manifest_option():
    module = load_dictionary_module()
    manifest = {
        "options": [
            {"canonical_flag": "--env"},
            {"canonical_flag": "--name"},
            {"canonical_flag": "--tty"},
        ],
    }
    entries = [
        minimal_entry("env", ["--env"]),
        minimal_entry("duplicate-env", ["--env"]),
        minimal_entry("tty", ["--tty"]),
    ]

    ledger = module.build_coverage_ledger(manifest, entries)

    assert ledger == [
        {
            "manifest_flag": "--env",
            "owners": ["duplicate-env", "env"],
            "owner_count": 2,
            "status": "duplicate",
        },
        {
            "manifest_flag": "--name",
            "owners": [],
            "owner_count": 0,
            "status": "missing",
        },
        {
            "manifest_flag": "--tty",
            "owners": ["tty"],
            "owner_count": 1,
            "status": "covered",
        },
    ]


def test_checked_in_option_dictionary_covers_the_full_manifest():
    module = load_dictionary_module()
    manifest = module.load_manifest(ROOT / "spec" / "docker-option-manifest.json")
    entries = module.load_dictionary_entries(ROOT / "spec" / "option-dictionary")

    errors = module.validate_dictionary(manifest, entries)

    assert errors == []
    manifest_flags = {option["canonical_flag"] for option in manifest["options"]}
    dictionary_flags = {
        flag
        for entry in entries
        for flag in entry["manifest_flags"]
    }
    assert dictionary_flags == manifest_flags
    assert len(dictionary_flags) == 103


def test_checked_in_coverage_ledger_has_no_missing_or_duplicate_options():
    module = load_dictionary_module()
    manifest = module.load_manifest(ROOT / "spec" / "docker-option-manifest.json")
    entries = module.load_dictionary_entries(ROOT / "spec" / "option-dictionary")

    ledger = module.build_coverage_ledger(manifest, entries)
    summary = module.summarize_coverage_ledger(ledger)

    assert len(ledger) == 103
    assert summary == {
        "covered": 103,
        "duplicate": 0,
        "missing": 0,
    }


def test_checked_in_option_dictionary_records_key_classifications():
    module = load_dictionary_module()
    entries = {
        entry["id"]: entry
        for entry in module.load_dictionary_entries(ROOT / "spec" / "option-dictionary")
    }

    name = entries["name"]
    assert name["manifest_flags"] == ["--name"]
    assert name["canonical_output_form"] == "--name"
    assert name["observability"] == "observable"
    assert name["inspect_fields"] == ["Name"]
    assert name["scope"]["classification"] == "in_scope"
    assert name["priority"] == "P0"
    assert name["path_coverage"] == {
        "container_name": "detectable",
        "stdin": "detectable",
    }

    disable_content_trust = entries["disable-content-trust"]
    assert disable_content_trust["observability"] == "not_observable"
    assert disable_content_trust["scope"] == {
        "classification": "out_of_scope",
        "reason": "client_side_only",
    }
    assert disable_content_trust["warning_behavior"]["warn_when_detected_unsupported"] is False

    gpus = entries["gpus"]
    assert gpus["scope"] == {
        "classification": "in_scope",
        "reason": None,
    }
    assert gpus["path_coverage"] == {
        "container_name": "detectable",
        "stdin": "detectable",
    }
    assert gpus["support_level"] == "partial"
    assert gpus["support_reason"] == "needs_gpu_runner_for_runtime_execution"

    device_cgroup_rule = entries["device-cgroup-rule"]
    assert device_cgroup_rule["scope"] == {
        "classification": "in_scope",
        "reason": None,
    }
    assert device_cgroup_rule["path_coverage"] == {
        "container_name": "detectable",
        "stdin": "detectable",
    }


def test_checked_in_option_dictionary_records_reviewed_profiles():
    module = load_dictionary_module()
    entries = {
        entry["id"]: entry
        for entry in module.load_dictionary_entries(ROOT / "spec" / "option-dictionary")
    }

    profile_expectations = [
        ("attach", ("render_profile", "profile"), "attach-streams"),
        ("name", ("render_profile", "profile"), "normalized-container-name"),
        ("restart", ("render_profile", "value_type"), "restart-policy"),
        ("no-healthcheck", ("detection_profile", "profile"), "healthcheck-none-sentinel"),
        ("log-opt", ("render_profile", "value_type"), "map"),
        ("storage-opt", ("render_profile", "value_type"), "map"),
        ("entrypoint", ("detection_profile", "profile"), "image-default-aware"),
    ]
    for entry_id, path, expected in profile_expectations:
        value = entries[entry_id]
        for key in path:
            value = value[key]
        assert value == expected

    assert entries["publish-all"]["inspect_fields"] == [
        "HostConfig.PublishAllPorts",
    ]
    assert entries["mac-address"]["inspect_fields"] == [
        "Config.MacAddress",
        "NetworkSettings.MacAddress",
        "NetworkSettings.Networks.*.MacAddress",
    ]

    assert entries["entrypoint"]["observability"] == "partially_observable"
    assert entries["expose"]["observability"] == "partially_observable"
    assert entries["expose"]["inspect_fields"] == ["Config.ExposedPorts"]
    assert entries["ip"]["inspect_fields"] == [
        "NetworkSettings.Networks.*.IPAMConfig.IPv4Address",
    ]
    assert entries["ip6"]["inspect_fields"] == [
        "NetworkSettings.Networks.*.IPAMConfig.IPv6Address",
    ]
    assert entries["network-alias"]["observability"] == "not_observable"
    assert entries["network-alias"]["inspect_fields"] == []
    assert entries["network-alias"]["scope"] == {
        "classification": "out_of_scope",
        "reason": "docker_inspect_aliases_include_implicit_container_aliases",
    }
