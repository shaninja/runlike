import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_matrix_module():
    script = ROOT / "tools" / "build_support_matrix.py"
    assert script.exists(), "expected tools/build_support_matrix.py to exist"
    spec = importlib.util.spec_from_file_location(
        "build_support_matrix", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dictionary_entry(
        entry_id,
        priority="P0",
        scope="in_scope",
        support_level=None,
        support_notes=None,
        support_reason=None):
    path_coverage = {
        "container_name": "detectable",
        "stdin": "detectable",
    }
    reason = None
    warning = scope == "in_scope"
    if scope == "out_of_scope":
        path_coverage = {
            "container_name": "client_side_only",
            "stdin": "client_side_only",
        }
        reason = "client_side_only"
        warning = False
    elif scope == "blocked_by_runner":
        path_coverage = {
            "container_name": "runner_blocked",
            "stdin": "runner_blocked",
        }
        reason = "needs_gpu_runner"

    entry = {
        "aliases": [],
        "canonical_output_form": "--%s" % entry_id,
        "id": entry_id,
        "manifest_flags": ["--%s" % entry_id],
        "path_coverage": path_coverage,
        "priority": priority,
        "scope": {
            "classification": scope,
            "reason": reason,
        },
        "warning_behavior": {
            "warn_when_detected_unsupported": warning,
        },
    }
    if support_level is not None:
        entry["support_level"] = support_level
    if support_notes is not None:
        entry["support_notes"] = support_notes
    if support_reason is not None:
        entry["support_reason"] = support_reason
    return entry


def test_support_matrix_records_one_status_row_per_option_path():
    module = load_matrix_module()
    entries = [
        dictionary_entry("env"),
        dictionary_entry("help", priority="not_applicable", scope="out_of_scope"),
        dictionary_entry("gpus", priority="P2", scope="blocked_by_runner"),
    ]
    probes = [
        {
            "id": "option-env",
            "option_id": "env",
            "paths": ["container_name", "stdin"],
        },
    ]
    probe_results = {
        "summary": {
            "failed": 1,
            "passed": 0,
            "total": 1,
        },
        "results": [
            {
                "probe_id": "option-env",
                "passed": False,
                "paths": {
                    "container_name": {
                        "compare": {"passed": True},
                        "passed": True,
                        "status": "passed",
                    },
                    "stdin": {
                        "compare": {"passed": False},
                        "passed": False,
                        "status": "failed",
                    },
                },
            },
        ],
    }

    matrix = module.build_support_matrix(
        entries,
        probes,
        probe_results,
        target={"id": "linux-docker-25.0.5-api-1.44"})

    assert matrix["target"]["id"] == "linux-docker-25.0.5-api-1.44"
    assert matrix["summary"]["by_status"] == {
        "blocked_by_runner": 2,
        "out_of_scope": 2,
        "partial": 0,
        "supported": 1,
        "unsupported": 1,
    }
    assert matrix["summary"]["by_option_status"] == {
        "blocked_by_runner": 1,
        "out_of_scope": 1,
        "partial": 1,
        "supported": 0,
        "unsupported": 0,
    }
    assert "by_priority" not in matrix["summary"]
    assert all("priority" not in row for row in matrix["entries"])
    rows = [
        (
            row["option_id"],
            row["path"],
            row["status"],
            row["probe_status"],
            row["comparison_status"],
            row["reason"],
        )
        for row in matrix["entries"]
    ]

    assert rows == [
        ("env", "container_name", "supported", "passed", "passed", None),
        ("env", "stdin", "unsupported", "failed", "failed", None),
        (
            "gpus",
            "container_name",
            "blocked_by_runner",
            "runner_blocked",
            "runner_blocked",
            "needs_gpu_runner",
        ),
        (
            "gpus",
            "stdin",
            "blocked_by_runner",
            "runner_blocked",
            "runner_blocked",
            "needs_gpu_runner",
        ),
        (
            "help",
            "container_name",
            "out_of_scope",
            "not_applicable",
            "client_side_only",
            "client_side_only",
        ),
        (
            "help",
            "stdin",
            "out_of_scope",
            "not_applicable",
            "client_side_only",
            "client_side_only",
        ),
    ]


def test_support_matrix_marks_mixed_probe_results_as_partial_for_a_path():
    module = load_matrix_module()
    entries = [dictionary_entry("env")]
    probes = [
        {"id": "env-one", "option_id": "env"},
        {"id": "env-two", "option_id": "env"},
    ]
    probe_results = {
        "results": [
            {
                "probe_id": "env-one",
                "passed": True,
                "paths": {
                    "container_name": {
                        "compare": {"passed": True},
                        "passed": True,
                        "status": "passed",
                    },
                },
            },
            {
                "probe_id": "env-two",
                "passed": False,
                "paths": {
                    "container_name": {
                        "compare": {"passed": False},
                        "passed": False,
                        "status": "failed",
                    },
                },
            },
        ],
    }

    matrix = module.build_support_matrix(entries, probes, probe_results)
    container_row = [
        row for row in matrix["entries"]
        if row["path"] == "container_name"
    ][0]

    assert container_row["status"] == "partial"
    assert container_row["probe_status"] == "partial"
    assert container_row["comparison_status"] == "partial"


def test_support_matrix_uses_only_probes_declared_for_each_path():
    module = load_matrix_module()
    entries = [dictionary_entry("env")]
    probes = [
        {
            "id": "env-container",
            "option_id": "env",
            "paths": ["container_name"],
        },
        {
            "id": "env-stdin",
            "option_id": "env",
            "paths": ["stdin"],
        },
    ]
    probe_results = {
        "results": [
            {
                "probe_id": "env-container",
                "paths": {
                    "container_name": {
                        "compare": {"passed": True},
                        "passed": True,
                        "status": "passed",
                    },
                },
            },
            {
                "probe_id": "env-stdin",
                "paths": {
                    "stdin": {
                        "compare": {"passed": True},
                        "passed": True,
                        "status": "passed",
                    },
                },
            },
        ],
    }

    matrix = module.build_support_matrix(entries, probes, probe_results)
    rows = dict((row["path"], row) for row in matrix["entries"])

    assert rows["container_name"]["status"] == "supported"
    assert rows["stdin"]["status"] == "supported"


def test_support_matrix_can_mark_probe_passing_option_as_known_partial():
    module = load_matrix_module()
    entries = [
        dictionary_entry(
            "gpus",
            priority="P2",
            support_level="partial",
            support_reason="needs_gpu_runner_for_runtime_execution",
            support_notes=[
                "Create/inspect round-trip is covered on the pinned runner.",
                "Starting a GPU container requires a GPU runner.",
            ]),
    ]
    probes = [{"id": "option-gpus", "option_id": "gpus"}]
    probe_results = {
        "results": [
            {
                "probe_id": "option-gpus",
                "paths": {
                    "container_name": {
                        "compare": {"passed": True},
                        "passed": True,
                        "status": "passed",
                    },
                    "stdin": {
                        "compare": {"passed": True},
                        "passed": True,
                        "status": "passed",
                    },
                },
                "passed": True,
            },
        ],
    }

    matrix = module.build_support_matrix(entries, probes, probe_results)
    rows = dict((row["path"], row) for row in matrix["entries"])

    assert rows["container_name"]["status"] == "partial"
    assert rows["container_name"]["probe_status"] == "passed"
    assert rows["container_name"]["reason"] == (
        "needs_gpu_runner_for_runtime_execution")
    assert rows["container_name"]["support_notes"] == [
        "Create/inspect round-trip is covered on the pinned runner.",
        "Starting a GPU container requires a GPU runner.",
    ]
    assert rows["container_name"]["remaining_work"] == [
        "See support notes for the known limitation."
    ]
    assert rows["stdin"]["status"] == "partial"


def test_render_support_matrix_markdown_uses_matrix_rows_not_manual_tables():
    module = load_matrix_module()
    matrix = module.build_support_matrix(
        [
            dictionary_entry("env"),
            dictionary_entry("gpus", priority="P2", scope="blocked_by_runner"),
        ],
        [{"id": "option-env", "option_id": "env"}],
        {
            "results": [
                {
                    "probe_id": "option-env",
                    "paths": {
                        "container_name": {
                            "compare": {"passed": True},
                            "passed": True,
                            "status": "passed",
                        },
                        "stdin": {
                            "compare": {"passed": False},
                            "passed": False,
                            "status": "failed",
                        },
                    },
                },
            ],
        })

    markdown = module.render_support_matrix_markdown(matrix)

    assert markdown.startswith("# Runlike support matrix\n")
    assert (
        "Summary: 0 supported, 1 partial, 0 unsupported, "
        "0 out of scope, 1 needs_special_runner."
    ) in markdown
    assert "| Option | Flag | Container name | Stdin | Scope | Reason | Notes |" in markdown
    assert "| Priority |" not in markdown
    assert "| env | `--env` | supported | unsupported | in_scope |  |  |" in markdown
    assert (
        "| gpus | `--gpus` | needs_special_runner | needs_special_runner | "
        "needs_special_runner | needs_gpu_runner |  |"
    ) in markdown
    assert "needs special runner" not in markdown
    assert "blocked_by_runner" not in markdown
    assert "Generated from `generated/probe-results.json`" in markdown


def test_render_support_matrix_markdown_escapes_note_cells():
    module = load_matrix_module()
    matrix = module.build_support_matrix(
        [
            dictionary_entry(
                "env",
                support_notes=["Uses A|B notation"]),
        ],
        [{"id": "option-env", "option_id": "env"}],
        {
            "results": [
                {
                    "probe_id": "option-env",
                    "paths": {
                        "container_name": {
                            "compare": {"passed": True},
                            "passed": True,
                            "status": "passed",
                        },
                        "stdin": {
                            "compare": {"passed": True},
                            "passed": True,
                            "status": "passed",
                        },
                    },
                },
            ],
        })

    markdown = module.render_support_matrix_markdown(matrix)

    assert "Uses A\\|B notation" in markdown


def test_checked_in_support_matrix_is_current():
    module = load_matrix_module()
    expected = module.build_support_matrix(
        module.load_dictionary_entries(ROOT / "spec" / "option-dictionary"),
        module.load_probe_definitions([ROOT / "tests" / "probes"]),
        module.load_probe_results(ROOT / "generated" / "probe-results.json"),
        target=module.load_target(ROOT / "spec" / "current-target.json"))

    with (ROOT / "generated" / "support-matrix.json").open() as matrix_file:
        checked_in = json.load(matrix_file)

    assert checked_in == expected


def test_checked_in_support_matrix_markdown_is_current():
    module = load_matrix_module()
    with (ROOT / "generated" / "support-matrix.json").open() as matrix_file:
        matrix = json.load(matrix_file)

    expected = module.render_support_matrix_markdown(matrix)
    checked_in = (ROOT / "generated" / "support-matrix.md").read_text()

    assert checked_in == expected
