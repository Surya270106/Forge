from .models import FileEntry, LanguageInfo, LanguageSummary


class LanguageDetector:
    """Detects languages used in a repository."""

    EXT_TO_LANG: dict[str, str] = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".kt": "Kotlin",
        ".cs": "CSharp",
        ".rb": "Ruby",
        ".php": "PHP",
        ".swift": "Swift",
        ".cpp": "CPP",
        ".cc": "CPP",
        ".cxx": "CPP",
        ".c": "C",
        ".h": "C",
    }

    def _detect_file_language(self, entry: FileEntry) -> str:
        """Detect language for a single file based on extension or shebang."""
        ext = entry.extension.lower()
        if ext in self.EXT_TO_LANG:
            return self.EXT_TO_LANG[ext]

        if not ext:
            try:
                with open(entry.absolute_path, "rb") as f:
                    header = f.read(64)
                    if header.startswith(b"#!"):
                        header_str = header.decode("utf-8", errors="ignore")
                        if "python" in header_str:
                            return "Python"
                        if "node" in header_str:
                            return "JavaScript"
                        if "ruby" in header_str:
                            return "Ruby"
            except Exception:
                pass

        return "Unknown"

    def detect_languages(self, files: list[FileEntry]) -> LanguageSummary:
        """
        Analyze files to determine repository language statistics.

        Args:
            files: List of files to analyze.

        Returns:
            LanguageSummary object.
        """
        lang_counts: dict[str, int] = {}
        lang_bytes: dict[str, int] = {}
        total_source_files = 0
        total_source_bytes = 0

        for entry in files:
            lang = self._detect_file_language(entry)
            if lang != "Unknown":
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
                lang_bytes[lang] = lang_bytes.get(lang, 0) + entry.size_bytes
                total_source_files += 1
                total_source_bytes += entry.size_bytes

        languages: list[LanguageInfo] = []
        for lang, count in lang_counts.items():
            bytes_count = lang_bytes[lang]
            percentage = (bytes_count / total_source_bytes * 100) if total_source_bytes > 0 else 0.0

            languages.append(
                LanguageInfo(
                    language=lang,
                    file_count=count,
                    byte_count=bytes_count,
                    percentage=round(percentage, 2),
                    confidence=1.0,
                    detection_method="extension",
                )
            )

        languages.sort(key=lambda x: x.byte_count, reverse=True)
        primary_lang = languages[0].language if languages else None

        return LanguageSummary(
            primary_language=primary_lang,
            languages=languages,
            total_source_files=total_source_files,
            total_source_bytes=total_source_bytes,
        )
