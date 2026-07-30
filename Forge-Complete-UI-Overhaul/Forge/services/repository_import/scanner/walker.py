import os

from .models import FileEntry


class RepositoryWalker:
    """Walks a directory deterministically and yields file entries."""

    def __init__(self, max_depth: int | None = None):
        """
        Initialize the repository walker.

        Args:
            max_depth: Maximum directory depth to traverse. None means unlimited.
        """
        self.max_depth = max_depth

    def _is_hidden(self, file_name: str) -> bool:
        """Check if a file or directory is hidden."""
        return file_name.startswith(".") and file_name != "." and file_name != ".."

    def _get_extension(self, file_name: str) -> str:
        """Get the file extension in lowercase, including the dot."""
        _, ext = os.path.splitext(file_name)
        return ext.lower()

    def walk(self, root_path: str) -> list[FileEntry]:
        """
        Walk the directory deterministically and return all entries.

        Args:
            root_path: Absolute path to the root directory to scan.

        Returns:
            List of FileEntry objects sorted by relative path.
        """
        entries = []
        root_path = os.path.abspath(root_path)

        for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
            # Sort inplace to ensure deterministic ordering
            dirnames.sort()
            filenames.sort()

            rel_dir = os.path.relpath(dirpath, root_path)
            if rel_dir == ".":
                rel_dir = ""

            # Check depth
            if self.max_depth is not None:
                depth = len(rel_dir.split(os.sep)) if rel_dir else 0
                if depth >= self.max_depth:
                    dirnames.clear()
                    continue

            # Process files
            for file_name in filenames:
                abs_path = os.path.join(dirpath, file_name)
                rel_path = os.path.join(rel_dir, file_name) if rel_dir else file_name
                # Ensure cross-platform relative path formatting (use forward slashes for internal logic usually, but keep os.path for now)
                rel_path = rel_path.replace("\\", "/")

                is_symlink = os.path.islink(abs_path)

                # Skip symlinks for safety
                if is_symlink:
                    continue

                try:
                    stat_info = os.stat(abs_path)
                    size_bytes = stat_info.st_size
                except OSError:
                    size_bytes = 0

                entries.append(
                    FileEntry(
                        relative_path=rel_path,
                        absolute_path=abs_path,
                        file_name=file_name,
                        extension=self._get_extension(file_name),
                        size_bytes=size_bytes,
                        is_directory=False,
                        is_symlink=False,
                        is_hidden=self._is_hidden(file_name) or self._is_hidden(rel_path.split("/")[0]),  # naive hidden check
                    )
                )

        # Sort the final list to guarantee deterministic output
        entries.sort(key=lambda e: e.relative_path)
        return entries
