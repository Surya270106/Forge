import difflib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from services.safety.policy import _protected_path

from .sandbox import _workspace_path


class PatchEngine:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root

    def _get_abs_path(self, relative_path: str) -> str:
        if _protected_path(relative_path):
            raise PermissionError("Protected repository path cannot be modified by a patch")
        candidate = Path(self.workspace_root)
        for part in Path(relative_path).parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise PermissionError("Symlink paths cannot be modified by a patch")
        return str(_workspace_path(self.workspace_root, relative_path))

    @contextmanager
    def _parent_directory(self, file_path: str) -> Iterator[tuple[int, str]]:
        parts = Path(file_path).parts
        if not parts or not hasattr(os, "O_NOFOLLOW"):
            raise PermissionError("Race-safe patch paths require a POSIX worker")
        descriptor = os.open(Path(self.workspace_root).resolve(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                try:
                    os.mkdir(part, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            yield descriptor, parts[-1]
        finally:
            os.close(descriptor)

    def apply_patch(self, file_path: str, new_content: str) -> str:
        """
        Applies a patch (or full replacement) and returns the diff hunk.
        """
        abs_path = self._get_abs_path(file_path)
        if os.name == "posix":
            with self._parent_directory(file_path) as (parent, name):
                descriptor = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644, dir_fd=parent)
                with os.fdopen(descriptor, "r+", encoding="utf-8") as file:
                    old_content = file.read()
                    file.seek(0)
                    file.truncate()
                    file.write(new_content)
        else:
            old_content = Path(abs_path).read_text(encoding="utf-8") if os.path.exists(abs_path) else ""
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            Path(abs_path).write_text(new_content, encoding="utf-8")

        diff = difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=file_path,
            tofile=file_path,
        )
        return "".join(diff)

    def revert_patch(self, file_path: str, original_content: str) -> None:
        """
        Reverts a file to its original content.
        """
        abs_path = self._get_abs_path(file_path)
        if os.name == "posix":
            with self._parent_directory(file_path) as (parent, name):
                if original_content == "":
                    try:
                        os.unlink(name, dir_fd=parent)
                    except FileNotFoundError:
                        pass
                else:
                    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644, dir_fd=parent)
                    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                        file.write(original_content)
        elif original_content == "":
            if os.path.exists(abs_path):
                os.remove(abs_path)
        else:
            Path(abs_path).write_text(original_content, encoding="utf-8")
