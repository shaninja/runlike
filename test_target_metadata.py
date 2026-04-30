import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_verify_module():
    script = ROOT / "tools" / "verify_docker_target.py"
    assert script.exists(), "expected tools/verify_docker_target.py to exist"
    spec = importlib.util.spec_from_file_location("verify_docker_target", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_target_metadata_pins_first_maintained_docker_target():
    target_path = ROOT / "spec" / "current-target.json"

    assert target_path.exists()
    target = json.loads(target_path.read_text())

    assert target["platform"] == "linux"
    assert target["docker"]["engine_version"] == "25.0.5"
    assert target["docker"]["cli_version"] == "25.0.5"
    assert target["docker"]["api_version"] == "1.44"
    assert target["environment"]["DOCKER_API_VERSION"] == "1.44"


def test_travis_sets_api_version_installs_pinned_docker_and_verifies_target():
    travis = (ROOT / ".travis.yml").read_text()

    assert "DOCKER_API_VERSION=1.44" in travis
    assert "./tools/install_pinned_docker.sh" in travis
    assert "poetry run python tools/verify_docker_target.py" in travis


def test_makefile_exports_pinned_docker_api_version_for_local_verification():
    makefile = (ROOT / "Makefile").read_text()

    assert "DOCKER_API_VERSION ?= 1.44" in makefile
    assert "export DOCKER_API_VERSION" in makefile
    assert "poetry run python tools/verify_docker_target.py" in makefile


def test_pinned_docker_installer_uses_python3_before_poetry_is_installed():
    installer = (ROOT / "tools" / "install_pinned_docker.sh").read_text()

    assert "python3 -" in installer


def test_pinned_docker_installer_handles_preinstalled_newer_docker_packages():
    installer = (ROOT / "tools" / "install_pinned_docker.sh").read_text()
    cleanup_block = installer.split("cleanup_packages=(", 1)[1]
    cleanup_block = cleanup_block.split(")", 1)[0]
    cleanup_packages = {
        line.strip()
        for line in cleanup_block.splitlines()
        if line.strip()
    }

    assert "sudo_cmd apt-get install -y --allow-downgrades" in installer
    assert "dpkg-query -W" in installer
    for package in (
        "docker-ce",
        "docker-ce-cli",
        "docker-ce-rootless-extras",
        "containerd.io",
        "docker-buildx-plugin",
        "docker-compose-plugin",
    ):
        assert package in cleanup_packages


def test_verify_docker_target_accepts_matching_docker_version_payload():
    module = load_verify_module()
    target = {
        "docker": {
            "engine_version": "25.0.5",
            "cli_version": "25.0.5",
            "api_version": "1.44",
        },
        "environment": {
            "DOCKER_API_VERSION": "1.44",
        },
    }
    version_payload = {
        "Client": {"Version": "25.0.5", "APIVersion": "1.44"},
        "Server": {"Version": "25.0.5", "APIVersion": "1.44"},
    }

    assert module.validate_docker_version_payload(
        version_payload, target, {"DOCKER_API_VERSION": "1.44"}) == []


def test_verify_docker_target_reports_version_and_environment_mismatches():
    module = load_verify_module()
    target = {
        "docker": {
            "engine_version": "25.0.5",
            "cli_version": "25.0.5",
            "api_version": "1.44",
        },
        "environment": {
            "DOCKER_API_VERSION": "1.44",
        },
    }
    version_payload = {
        "Client": {"Version": "25.0.4", "APIVersion": "1.43"},
        "Server": {"Version": "25.0.6", "APIVersion": "1.45"},
    }

    errors = module.validate_docker_version_payload(
        version_payload, target, {"DOCKER_API_VERSION": "1.43"})

    assert "Docker client version: expected 25.0.5, got 25.0.4" in errors
    assert "Docker engine version: expected 25.0.5, got 25.0.6" in errors
    assert "Docker client API version: expected 1.44, got 1.43" in errors
    assert "Docker server API version: expected 1.44, got 1.45" in errors
    assert "DOCKER_API_VERSION: expected 1.44, got 1.43" in errors
