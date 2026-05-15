from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_readme_points_to_generated_support_matrix():
    readme = (ROOT / "README.md").read_text()

    assert "generated/support-matrix.md" in readme
    assert "generated/support-matrix.json" in readme


def test_readme_does_not_maintain_static_support_tables():
    readme = (ROOT / "README.md").read_text()

    assert "## Supported Run Options" not in readme
    assert "## Not Yet Supported Run Options" not in readme
