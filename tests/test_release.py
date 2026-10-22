import json

import pytest

from scripts import release


@pytest.mark.parametrize("tag", ["2.9.1", "v2.9.1;echo bad", "v2.9.1\nbad", "v2.9.1/other", "v2.9.1+local", "v2.9.1-rc1"])
def test_release_rejects_unsafe_or_noncanonical_tags(tag):
    with pytest.raises(ValueError):
        release.version_from_tag(tag)


def test_version_staging_updates_metadata_and_app_together(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    (tmp_path / "qpypack").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "2.9.1"\n', encoding="utf-8")
    (tmp_path / "qpypack/main.py").write_text('__version__ = "2.9.1"\n', encoding="utf-8")
    release.stage("2.9.2rc1")
    assert 'version = "2.9.2rc1"' in (tmp_path / "pyproject.toml").read_text()
    assert '__version__ = "2.9.2rc1"' in (tmp_path / "qpypack/main.py").read_text()


def test_release_refuses_incomplete_or_tampered_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ASSETS", tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    with pytest.raises(AssertionError):
        release.verify_assets("2.9.2rc1")
    for kind in ("python", "linux", "windows", "macos"):
        artifact = tmp_path / f"{kind}.zip"
        artifact.write_bytes(b"validated build")
        data = {"commit": "a" * 40, "version": "2.9.2rc1", "kind": kind,
                "assets": {artifact.name: {"sha256": release.digest(artifact), "size": artifact.stat().st_size}}}
        (tmp_path / f"manifest-{kind}.json").write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "linux.zip").write_bytes(b"changed after validation")
    with pytest.raises(AssertionError):
        release.verify_assets("2.9.2rc1")
    assert not (tmp_path / "SHA256SUMS").exists()
