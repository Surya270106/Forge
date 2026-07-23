import os
from datetime import datetime

from .classifier import FileClassifier
from .framework_detector import FrameworkDetector
from .ignore_engine import IgnoreEngine
from .language_detector import LanguageDetector
from .models import FileCategory, FileEntry, RepositoryManifest
from .statistics import StatisticsCollector
from .walker import RepositoryWalker


class ManifestBuilder:
    """Builds the final repository manifest."""

    def __init__(
        self,
        workspace_path: str,
        repo_owner: str = None,
        repo_name: str = None,
        commit_sha: str = None,
        default_branch: str = None,
    ):
        """
        Initialize the manifest builder.

        Args:
            workspace_path: Absolute path to the repository root.
            repo_owner: Optional repository owner name.
            repo_name: Optional repository name.
            commit_sha: Optional commit hash.
            default_branch: Optional default branch name.
        """
        self.workspace_path = workspace_path
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.commit_sha = commit_sha
        self.default_branch = default_branch

        self.classifier = FileClassifier()
        self.lang_detector = LanguageDetector()
        self.fw_detector = FrameworkDetector()
        self.stats_collector = StatisticsCollector()
        self.walker = RepositoryWalker()
        self.ignore_engine = IgnoreEngine(workspace_path)

    def _extract_top_directories(self, files: list[FileEntry]) -> list[str]:
        """Extract unique top-level directories from file paths."""
        dirs: set[str] = set()
        for f in files:
            parts = f.relative_path.split("/")
            if len(parts) > 1:
                dirs.add(parts[0])
        return sorted(list(dirs))

    def _extract_test_locations(self, test_files: list[FileEntry]) -> list[str]:
        """Extract unique directories containing test files."""
        dirs: set[str] = set()
        for f in test_files:
            dirname = os.path.dirname(f.relative_path)
            if dirname:
                dirs.add(dirname.replace("\\", "/"))
        return sorted(list(dirs))

    def _find_entry_points(self, files: list[FileEntry]) -> list[FileEntry]:
        """Heuristically find potential entry points."""
        entry_points = []
        entry_names = {
            "main.py",
            "app.py",
            "index.js",
            "index.ts",
            "main.go",
            "main.rs",
            "manage.py",
        }

        for f in files:
            # Check for standard entry point names in root or common src dirs
            if f.file_name.lower() in entry_names:
                parts = f.relative_path.split("/")
                if len(parts) == 1 or (len(parts) == 2 and parts[0] in {"src", "app", "cmd", "bin"}):
                    entry_points.append(f)

        return entry_points

    def build(self) -> RepositoryManifest:
        """
        Scan the repository and build the full manifest.

        Returns:
            RepositoryManifest containing all scanned data.
        """
        # 1. Walk repository
        all_files = self.walker.walk(self.workspace_path)

        # 2. Filter ignored files
        valid_files = [f for f in all_files if not self.ignore_engine.is_ignored(f.relative_path)]

        # 3. Classify files
        categorized_files: dict[FileCategory, list[FileEntry]] = {cat: [] for cat in FileCategory}
        for f in valid_files:
            cat = self.classifier.classify(f)
            categorized_files[cat].append(f)

        # 4. Detect languages
        lang_summary = self.lang_detector.detect_languages(categorized_files[FileCategory.SOURCE])

        # 5. Detect frameworks
        frameworks = self.fw_detector.detect_frameworks(self.workspace_path, valid_files)

        # 6. Collect statistics
        stats = self.stats_collector.collect(valid_files, categorized_files, lang_summary)

        # 7. Build final manifest
        return RepositoryManifest(
            version="1.0.0",
            scanned_at=datetime.utcnow(),
            repository_owner=self.repo_owner,
            repository_name=self.repo_name,
            commit_sha=self.commit_sha,
            default_branch=self.default_branch,
            languages=lang_summary,
            frameworks=frameworks,
            directory_tree=self._extract_top_directories(valid_files),
            configuration_files=categorized_files[FileCategory.CONFIGURATION],
            entry_points=self._find_entry_points(valid_files),
            test_locations=self._extract_test_locations(categorized_files[FileCategory.TEST]),
            dependency_files=categorized_files[FileCategory.DEPENDENCY],
            documentation_files=categorized_files[FileCategory.DOCUMENTATION],
            statistics=stats,
        )
