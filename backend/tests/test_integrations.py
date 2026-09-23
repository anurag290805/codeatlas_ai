from pathlib import Path

from app.integrations.dependencies import extract_dependencies
from app.api.routes_intelligence import _status, _version_tuple


def test_extracts_supported_javascript_and_python_manifests(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"dependencies":{"axios":"^1.7.4"}}', encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n# comment\n", encoding="utf-8")

    dependencies = extract_dependencies(tmp_path)

    assert {(item.ecosystem, item.name) for item in dependencies} == {("npm", "axios"), ("PyPI", "requests")}
    assert next(item for item in dependencies if item.name == "requests").installed_version == "2.31.0"


def test_lockfile_version_wins_over_requested_manifest(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"dependencies":{"axios":"^1.7.4"}}', encoding="utf-8")
    (tmp_path / "package-lock.json").write_text('{"packages":{"":{"name":"demo"},"node_modules/axios":{"version":"1.8.2"}}}', encoding="utf-8")

    axios = next(item for item in extract_dependencies(tmp_path) if item.name == "axios")
    assert axios.installed_version == "1.8.2"


def test_version_status_is_honest_for_invalid_versions() -> None:
    assert _version_tuple("not-a-version") is None
    assert _status("1.0.0", "1.1.0", []) == "outdated"
    assert _status("1.0.0", "1.1.0", [{"id": "OSV-1"}]) == "vulnerable"
