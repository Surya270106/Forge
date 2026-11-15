import pytest

from services.execution.sandbox import _workspace_path


def test_workspace_path_rejects_sibling_and_absolute_paths(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    sibling = tmp_path / "repo-other"
    sibling.mkdir()

    assert _workspace_path(str(root), "src/main.py") == root / "src" / "main.py"
    for path in ("../repo-other/file", str(sibling / "file"), "src/../file"):
        with pytest.raises(PermissionError):
            _workspace_path(str(root), path)


def test_workspace_path_rejects_symlink_escape(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks unavailable")

    with pytest.raises(PermissionError):
        _workspace_path(str(root), "link/file")
