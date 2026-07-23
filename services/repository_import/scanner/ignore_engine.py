import fnmatch
import os


class IgnoreEngine:
    """Engine to determine if files should be ignored based on rules."""

    SYSTEM_IGNORED_DIRS: set[str] = {
        ".git",
        "node_modules",
        ".next",
        "build",
        "dist",
        "out",
        "target",
        "coverage",
        ".venv",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".eggs",
    }

    SYSTEM_IGNORED_EXTS: set[str] = {
        ".pyc",
        ".pyo",
        ".class",
        ".o",
        ".obj",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".jar",
        ".war",
        ".ear",
        ".zip",
        ".tar",
        ".gz",
        ".rar",
        ".7z",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".svg",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
    }

    def __init__(self, root_path: str):
        """
        Initialize the ignore engine.

        Args:
            root_path: Absolute path to the repository root to parse .gitignore.
        """
        self.root_path = root_path
        self.gitignore_patterns: list[str] = []
        self._load_gitignore()

    def _load_gitignore(self) -> None:
        """Parse .gitignore file if it exists."""
        gitignore_path = os.path.join(self.root_path, ".gitignore")
        if not os.path.exists(gitignore_path):
            return

        try:
            with open(gitignore_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self.gitignore_patterns.append(line)
        except OSError:
            pass

    def _matches_gitignore(self, relative_path: str) -> bool:
        """Check if path matches any gitignore pattern using basic fnmatch."""
        for pattern in self.gitignore_patterns:
            # Handle directory only patterns
            if pattern.endswith("/"):
                pattern = pattern[:-1]
                # If pattern is just a name, match against any part of path
                if "/" not in pattern:
                    parts = relative_path.split("/")
                    if any(fnmatch.fnmatch(part, pattern) for part in parts):
                        return True

            # Match exact paths or full paths
            if fnmatch.fnmatch(relative_path, pattern):
                return True

            # Match basename
            basename = os.path.basename(relative_path)
            if fnmatch.fnmatch(basename, pattern):
                return True

        return False

    def is_ignored(self, relative_path: str) -> bool:
        """
        Determine if a file should be ignored based on configured rules.

        Args:
            relative_path: Path relative to the repository root.

        Returns:
            True if ignored, False otherwise.
        """
        parts = relative_path.split("/")

        # Check system ignored directories (fast set lookup)
        if any(part in self.SYSTEM_IGNORED_DIRS for part in parts):
            return True

        # Check system ignored extensions
        _, ext = os.path.splitext(relative_path)
        if ext.lower() in self.SYSTEM_IGNORED_EXTS:
            return True

        # Special case for egg-info
        if relative_path.endswith(".egg-info") or any(p.endswith(".egg-info") for p in parts):
            return True

        # Check gitignore
        if self._matches_gitignore(relative_path):
            return True

        return False
