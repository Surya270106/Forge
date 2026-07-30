from .models import FileCategory, FileEntry


class FileClassifier:
    """Classifies files into categories based on name and path."""

    SOURCE_EXTS: set[str] = {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".cs",
        ".cpp",
        ".c",
        ".h",
        ".rb",
        ".php",
        ".swift",
    }

    CONFIG_EXTS: set[str] = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}

    DOC_EXTS: set[str] = {".md", ".rst", ".txt", ".adoc"}

    ASSET_EXTS: set[str] = {".css", ".scss", ".less", ".html"}

    def classify(self, entry: FileEntry) -> FileCategory:
        """
        Determine the category of a file.

        Args:
            entry: FileEntry object representing the file.

        Returns:
            FileCategory enum value.
        """
        name = entry.file_name.lower()
        path = entry.relative_path.lower()
        ext = entry.extension.lower()

        # Build files
        if (
            name in {"makefile", "gruntfile.js", "gulpfile.js", "turbo.json", "nx.json"}
            or name.startswith("webpack.")
            or name.startswith("rollup.")
            or name.startswith("vite.")
        ):
            return FileCategory.BUILD

        # Dependency files
        if name in {
            "package.json",
            "requirements.txt",
            "pipfile",
            "pyproject.toml",
            "go.mod",
            "cargo.toml",
            "pom.xml",
            "build.gradle",
            "gemfile",
            "composer.json",
        }:
            return FileCategory.DEPENDENCY

        # Configuration files
        if (
            ext in self.CONFIG_EXTS
            or name in {"dockerfile", "procfile", ".env"}
            or name.startswith("docker-compose.")
            or name.startswith(".env.")
            or name == "makefile"
        ):
            return FileCategory.CONFIGURATION

        # Documentation files
        if (
            ext in self.DOC_EXTS
            or name.startswith("license")
            or name.startswith("readme")
            or name.startswith("changelog")
            or name.startswith("contributing")
        ):
            return FileCategory.DOCUMENTATION

        # Test files
        if (
            "test_" in name
            or "_test" in name
            or ".test." in name
            or ".spec." in name
            or "/test/" in f"/{path}"
            or "/tests/" in f"/{path}"
            or "/__tests__/" in f"/{path}"
            or "/spec/" in f"/{path}"
        ):
            return FileCategory.TEST

        # Generated files
        if (
            name.endswith(".min.js")
            or name.endswith(".min.css")
            or ext == ".map"
            or (ext == ".ts" and name.endswith(".d.ts") and "/dist/" in f"/{path}")
            or name.endswith(".lock")
        ):
            return FileCategory.GENERATED

        # Source files
        if ext in self.SOURCE_EXTS:
            return FileCategory.SOURCE

        # Asset files
        if ext in self.ASSET_EXTS:
            return FileCategory.ASSET

        return FileCategory.UNKNOWN
