from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FileCategory(str, Enum):
    """Enumeration of all possible file categories."""

    SOURCE = "source"
    CONFIGURATION = "configuration"
    DOCUMENTATION = "documentation"
    TEST = "test"
    BUILD = "build"
    DEPENDENCY = "dependency"
    ASSET = "asset"
    GENERATED = "generated"
    UNKNOWN = "unknown"


class FileEntry(BaseModel):
    """Represents a file or directory in the repository."""

    relative_path: str
    absolute_path: str
    file_name: str
    extension: str
    size_bytes: int
    is_directory: bool
    is_symlink: bool
    is_hidden: bool


class LanguageInfo(BaseModel):
    """Information about a detected language."""

    language: str
    file_count: int
    byte_count: int
    percentage: float
    confidence: float
    detection_method: str


class LanguageSummary(BaseModel):
    """Summary of all languages detected in the repository."""

    primary_language: str | None
    languages: list[LanguageInfo]
    total_source_files: int
    total_source_bytes: int


class FrameworkInfo(BaseModel):
    """Information about a detected framework."""

    name: str
    version: str | None
    confidence: float
    detection_source: str


class RepositoryStatistics(BaseModel):
    """Statistical information about the repository."""

    total_files: int
    source_files: int
    test_files: int
    doc_files: int
    config_files: int
    total_size_bytes: int
    avg_file_size: float
    largest_files: list[FileEntry]
    language_distribution: dict[str, float]


class RepositoryManifest(BaseModel):
    """Complete manifest of a scanned repository."""

    version: str = "1.0.0"
    scanned_at: datetime = Field(default_factory=datetime.utcnow)
    repository_owner: str | None = None
    repository_name: str | None = None
    commit_sha: str | None = None
    default_branch: str | None = None
    languages: LanguageSummary
    frameworks: list[FrameworkInfo]
    directory_tree: list[str]
    configuration_files: list[FileEntry]
    entry_points: list[FileEntry]
    test_locations: list[str]
    dependency_files: list[FileEntry]
    documentation_files: list[FileEntry]
    statistics: RepositoryStatistics

    def to_dict(self) -> dict:
        """Convert to JSON-compatible dictionary."""
        return self.model_dump(mode="json")
