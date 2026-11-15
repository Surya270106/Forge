from pathlib import Path

import pytest

from services.execution.patch_engine import PatchEngine


def test_patch_engine_blocks_workspace_escape(tmp_path: Path):
    engine = PatchEngine(str(tmp_path))
    with pytest.raises(PermissionError):
        engine.apply_patch("../escaped.py", "bad")
    with pytest.raises(PermissionError):
        engine.apply_patch(".git/config", "bad")


def test_patch_engine_writes_inside_workspace(tmp_path: Path):
    engine = PatchEngine(str(tmp_path))
    diff = engine.apply_patch("src/hello.py", "print('hello')\n")
    assert (tmp_path / "src" / "hello.py").read_text() == "print('hello')\n"
    assert "+print('hello')" in diff
