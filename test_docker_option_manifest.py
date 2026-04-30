import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_manifest_module():
    script = ROOT / "tools" / "dump_docker_option_manifest.py"
    assert script.exists(), "expected tools/dump_docker_option_manifest.py to exist"
    spec = importlib.util.spec_from_file_location(
        "dump_docker_option_manifest", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUN_HELP = """
Usage:  docker container run [OPTIONS] IMAGE [COMMAND] [ARG...]

Create and run a new container from an image

Options:
      --add-host list                    Add a custom host-to-IP mapping
                                         (host:ip)
  -a, --attach list                      Attach to STDIN, STDOUT or STDERR
      --detach-keys string               Override the key sequence for
                                         detaching a container
      --rm                               Automatically remove the
                                         container when it exits
"""


CREATE_HELP = """
Usage:  docker container create [OPTIONS] IMAGE [COMMAND] [ARG...]

Create a new container

Options:
      --add-host list                    Add a custom host-to-IP mapping
                                         (host:ip)
  -a, --attach list                      Attach to STDIN, STDOUT or STDERR
      --cidfile string                   Write the container ID to the file
"""


def test_parse_docker_help_extracts_options_and_multiline_help():
    module = load_manifest_module()

    options = module.parse_docker_options(RUN_HELP)

    assert options == [
        {
            "canonical_flag": "--add-host",
            "short_flag": None,
            "value_type": "list",
            "help": "Add a custom host-to-IP mapping (host:ip)",
        },
        {
            "canonical_flag": "--attach",
            "short_flag": "-a",
            "value_type": "list",
            "help": "Attach to STDIN, STDOUT or STDERR",
        },
        {
            "canonical_flag": "--detach-keys",
            "short_flag": None,
            "value_type": "string",
            "help": "Override the key sequence for detaching a container",
        },
        {
            "canonical_flag": "--rm",
            "short_flag": None,
            "value_type": None,
            "help": "Automatically remove the container when it exits",
        },
    ]


def test_build_manifest_deduplicates_flags_and_records_command_family():
    module = load_manifest_module()
    target = {
        "id": "linux-docker-25.0.5-api-1.44",
        "platform": "linux",
        "docker": {
            "engine_version": "25.0.5",
            "cli_version": "25.0.5",
            "api_version": "1.44",
        },
    }

    manifest = module.build_manifest(target, RUN_HELP, CREATE_HELP)

    assert manifest["target"] == target
    assert manifest["options"] == [
        {
            "canonical_flag": "--add-host",
            "short_flag": None,
            "value_type": "list",
            "help": "Add a custom host-to-IP mapping (host:ip)",
            "command_family": "both",
        },
        {
            "canonical_flag": "--attach",
            "short_flag": "-a",
            "value_type": "list",
            "help": "Attach to STDIN, STDOUT or STDERR",
            "command_family": "both",
        },
        {
            "canonical_flag": "--cidfile",
            "short_flag": None,
            "value_type": "string",
            "help": "Write the container ID to the file",
            "command_family": "create",
        },
        {
            "canonical_flag": "--detach-keys",
            "short_flag": None,
            "value_type": "string",
            "help": "Override the key sequence for detaching a container",
            "command_family": "run",
        },
        {
            "canonical_flag": "--rm",
            "short_flag": None,
            "value_type": None,
            "help": "Automatically remove the container when it exits",
            "command_family": "run",
        },
    ]


def test_build_manifest_source_ledger_accounts_for_each_help_option():
    module = load_manifest_module()
    manifest = {
        "options": [
            {
                "canonical_flag": "--add-host",
                "command_family": "both",
            },
            {
                "canonical_flag": "--attach",
                "command_family": "run",
            },
            {
                "canonical_flag": "--cidfile",
                "command_family": "create",
            },
            {
                "canonical_flag": "--cidfile",
                "command_family": "create",
            },
            {
                "canonical_flag": "--extra",
                "command_family": "both",
            },
        ],
    }

    ledger = module.build_manifest_source_ledger(
        manifest, RUN_HELP, CREATE_HELP)

    assert ledger == [
        {
            "actual_command_families": ["both"],
            "expected_command_family": "both",
            "manifest_flag": "--add-host",
            "manifest_row_count": 1,
            "source_commands": ["create", "run"],
            "status": "covered",
        },
        {
            "actual_command_families": ["run"],
            "expected_command_family": "both",
            "manifest_flag": "--attach",
            "manifest_row_count": 1,
            "source_commands": ["create", "run"],
            "status": "command_family_mismatch",
        },
        {
            "actual_command_families": ["create", "create"],
            "expected_command_family": "create",
            "manifest_flag": "--cidfile",
            "manifest_row_count": 2,
            "source_commands": ["create"],
            "status": "duplicate",
        },
        {
            "actual_command_families": [],
            "expected_command_family": "run",
            "manifest_flag": "--detach-keys",
            "manifest_row_count": 0,
            "source_commands": ["run"],
            "status": "missing",
        },
        {
            "actual_command_families": ["both"],
            "expected_command_family": None,
            "manifest_flag": "--extra",
            "manifest_row_count": 1,
            "source_commands": [],
            "status": "extra",
        },
        {
            "actual_command_families": [],
            "expected_command_family": "run",
            "manifest_flag": "--rm",
            "manifest_row_count": 0,
            "source_commands": ["run"],
            "status": "missing",
        },
    ]


def test_build_manifest_source_ledger_accepts_generated_manifest():
    module = load_manifest_module()
    target = {
        "id": "linux-docker-25.0.5-api-1.44",
        "platform": "linux",
        "docker": {
            "engine_version": "25.0.5",
            "cli_version": "25.0.5",
            "api_version": "1.44",
        },
    }
    manifest = module.build_manifest(target, RUN_HELP, CREATE_HELP)

    ledger = module.build_manifest_source_ledger(
        manifest, RUN_HELP, CREATE_HELP)
    summary = module.summarize_manifest_source_ledger(ledger)

    assert summary == {
        "command_family_mismatch": 0,
        "covered": 5,
        "duplicate": 0,
        "extra": 0,
        "missing": 0,
    }


def test_checked_in_manifest_matches_current_target_metadata():
    manifest_path = ROOT / "spec" / "docker-option-manifest.json"
    target_path = ROOT / "spec" / "current-target.json"

    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text())
    target = json.loads(target_path.read_text())

    assert manifest["target"] == target
    assert manifest["options"]
    assert manifest["options"] == sorted(
        manifest["options"], key=lambda option: option["canonical_flag"])

    canonical_flags = [
        option["canonical_flag"]
        for option in manifest["options"]
    ]
    assert len(canonical_flags) == len(set(canonical_flags))

    options_by_flag = {
        option["canonical_flag"]: option
        for option in manifest["options"]
    }
    assert options_by_flag["--attach"]["short_flag"] == "-a"
    assert options_by_flag["--attach"]["command_family"] == "both"
    assert options_by_flag["--detach"]["command_family"] == "run"
    assert options_by_flag["--pull"]["command_family"] == "both"
    assert "command_help" in options_by_flag["--pull"]
