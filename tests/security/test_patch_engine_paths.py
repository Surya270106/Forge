from pathlib import Path

import pytest

from services.execution.patch_engine import PatchEngine


def test_patch_engine_blocks_workspace_escape(tmp_path: Path):
    engine = PatchEngine(str(tmp_path))
    with pytest.raises(PermissionError):
        engine.apply_patch("../escaped.py", "bad")
    with pytest.raises(PermissionError):
        engine.apply_patch(".git/config", "bad")
    for path in (".env", "src/.env.local", "keys/id_rsa.pem", ".ssh/config"):
        with pytest.raises(PermissionError):
            engine.apply_patch(path, "secret")
        assert not (tmp_path / path).exists()


def test_patch_engine_writes_inside_workspace(tmp_path: Path):
    engine = PatchEngine(str(tmp_path))
    diff = engine.apply_patch("src/hello.py", "print('hello')\n")
    assert (tmp_path / "src" / "hello.py").read_text() == "print('hello')\n"
    assert "+print('hello')" in diff


def test_patch_engine_does_not_follow_directory_swapped_after_validation(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    (workspace / "src").mkdir(parents=True)
    outside.mkdir()
    engine = PatchEngine(str(workspace))
    validate = engine._get_abs_path

    def swap(path: str) -> str:
        result = validate(path)
        (workspace / "src").rename(workspace / "old-src")
        (workspace / "src").symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(engine, "_get_abs_path", swap)
    with pytest.raises((PermissionError, OSError)):
        engine.apply_patch("src/data.txt", "not outside")
    assert not (outside / "data.txt").exists()
