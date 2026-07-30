from .models import FileCategory, FileEntry, LanguageSummary, RepositoryStatistics


class StatisticsCollector:
    """Collects statistics about the scanned repository."""

    def collect(
        self,
        files: list[FileEntry],
        categorized_files: dict[FileCategory, list[FileEntry]],
        language_summary: LanguageSummary,
    ) -> RepositoryStatistics:
        """
        Calculate statistics from scanned files.

        Args:
            files: All files found in the repository.
            categorized_files: Dictionary mapping FileCategory to list of files.
            language_summary: Summary of languages in the repository.

        Returns:
            RepositoryStatistics model.
        """
        total_files = len(files)
        total_size_bytes = sum(f.size_bytes for f in files)

        source_files = len(categorized_files.get(FileCategory.SOURCE, []))
        test_files = len(categorized_files.get(FileCategory.TEST, []))
        doc_files = len(categorized_files.get(FileCategory.DOCUMENTATION, []))
        config_files = len(categorized_files.get(FileCategory.CONFIGURATION, []))

        avg_file_size = (total_size_bytes / total_files) if total_files > 0 else 0.0

        # Find largest files (top 10)
        sorted_files = sorted(files, key=lambda f: f.size_bytes, reverse=True)
        largest_files = sorted_files[:10]

        # Map language distribution
        lang_distribution = {lang.language: lang.percentage for lang in language_summary.languages}

        return RepositoryStatistics(
            total_files=total_files,
            source_files=source_files,
            test_files=test_files,
            doc_files=doc_files,
            config_files=config_files,
            total_size_bytes=total_size_bytes,
            avg_file_size=avg_file_size,
            largest_files=largest_files,
            language_distribution=lang_distribution,
        )
