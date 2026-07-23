import difflib
import os


class PatchEngine:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root

    def _get_abs_path(self, relative_path: str) -> str:
        return os.path.abspath(os.path.join(self.workspace_root, relative_path))

    def apply_patch(self, file_path: str, new_content: str) -> str:
        """
        Applies a patch (or full replacement) and returns the diff hunk.
        """
        abs_path = self._get_abs_path(file_path)
        old_content = ""

        if os.path.exists(abs_path):
            with open(abs_path, encoding="utf-8") as f:
                old_content = f.read()

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)

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
        if original_content == "":
            if os.path.exists(abs_path):
                os.remove(abs_path)
        else:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(original_content)
