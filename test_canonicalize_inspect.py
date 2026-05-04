import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_canonicalize_module():
    script = ROOT / "tools" / "canonicalize_inspect.py"
    assert script.exists(), "expected tools/canonicalize_inspect.py to exist"
    spec = importlib.util.spec_from_file_location(
        "canonicalize_inspect", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_document(name="/fixture", env=None, network=None):
    if env is None:
        env = ["B=2", "A=1"]
    if network is None:
        network = {
            "bridge": {
                "Aliases": None,
                "DriverOpts": None,
                "EndpointID": "dynamic-endpoint",
                "Gateway": "172.17.0.1",
                "GlobalIPv6Address": "",
                "GlobalIPv6PrefixLen": 0,
                "IPAddress": "172.17.0.2",
                "IPPrefixLen": 16,
                "IPv6Gateway": "",
                "MacAddress": "02:42:ac:11:00:02",
                "NetworkID": "dynamic-network",
            },
        }

    return [{
        "Id": "dynamic-container-id",
        "Created": "2026-05-04T10:00:00Z",
        "Name": name,
        "Config": {
            "Env": env,
            "Cmd": ["sh", "-c", "sleep 600"],
        },
        "HostConfig": {
            "RestartPolicy": {
                "Name": "no",
                "MaximumRetryCount": 0,
            },
        },
        "NetworkSettings": {
            "SandboxID": "dynamic-sandbox",
            "Networks": network,
        },
        "State": {
            "Running": True,
            "Pid": 1234,
        },
    }]


def test_canonical_projection_uses_compare_profile_fields():
    module = load_canonicalize_module()

    projection = module.canonicalize_for_compare(
        inspect_document(),
        {
            "profile": "inspect-projection",
            "fields": [
                "Config.Env",
                "NetworkSettings.Networks",
            ],
        })

    assert projection == {
        "Config.Env": ["A=1", "B=2"],
        "NetworkSettings.Networks": {
            "bridge": {
                "Aliases": None,
                "DriverOpts": None,
            },
        },
    }


def test_full_canonicalization_removes_top_level_dynamic_fields():
    module = load_canonicalize_module()

    projection = module.canonicalize_inspect(inspect_document())

    assert "Id" not in projection
    assert "Created" not in projection
    assert "State" not in projection
    assert projection["Config"]["Cmd"] == ["sh", "-c", "sleep 600"]


def test_normalized_container_name_profile_strips_leading_slash():
    module = load_canonicalize_module()
    profile = {
        "profile": "normalized-container-name",
        "fields": ["Name"],
    }

    result = module.compare_inspects(
        inspect_document(name="/fixture"),
        inspect_document(name="fixture"),
        profile)

    assert result["passed"] is True
    assert result["mismatches"] == []


def test_compare_inspects_reports_field_mismatches():
    module = load_canonicalize_module()
    profile = {
        "profile": "inspect-projection",
        "fields": ["Config.Env"],
    }

    result = module.compare_inspects(
        inspect_document(env=["A=1"]),
        inspect_document(env=["A=2"]),
        profile)

    assert result["passed"] is False
    assert result["mismatches"] == [{
        "field": "Config.Env",
        "expected": ["A=1"],
        "actual": ["A=2"],
    }]
