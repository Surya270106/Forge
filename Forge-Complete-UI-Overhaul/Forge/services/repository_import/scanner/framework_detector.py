import json
import os
from typing import Any

from .models import FileEntry, FrameworkInfo


class FrameworkDetector:
    """Detects frameworks used in a repository by inspecting manifests."""

    def __init__(self):
        self.frameworks: list[FrameworkInfo] = []

    def _parse_json(self, path: str) -> dict[str, Any]:
        """Safely parse a JSON file."""
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _read_text(self, path: str) -> str:
        """Safely read text file content."""
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().lower()
        except Exception:
            return ""

    def _check_package_json(self, path: str):
        """Analyze package.json for Node.js frameworks."""
        data = self._parse_json(path)
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

        framework_map = {
            "next": "Next.js",
            "react": "React",
            "express": "Express",
            "@nestjs/core": "NestJS",
            "@remix-run/react": "Remix",
            "vue": "Vue",
            "@angular/core": "Angular",
            "svelte": "Svelte",
        }

        for pkg, name in framework_map.items():
            if pkg in deps:
                self.frameworks.append(
                    FrameworkInfo(
                        name=name,
                        version=deps[pkg],
                        confidence=1.0,
                        detection_source="package.json",
                    )
                )

    def _check_python_manifests(self, requirements_path: str, pyproject_path: str):
        """Analyze Python manifests for frameworks."""
        content = ""
        source = ""

        if os.path.exists(requirements_path):
            content += self._read_text(requirements_path)
            source = "requirements.txt"
        if os.path.exists(pyproject_path):
            content += self._read_text(pyproject_path)
            source = "pyproject.toml"

        if not content:
            return

        framework_map = {
            "fastapi": "FastAPI",
            "flask": "Flask",
            "django": "Django",
            "celery": "Celery",
            "sqlalchemy": "SQLAlchemy",
        }

        for pkg, name in framework_map.items():
            if pkg in content:
                self.frameworks.append(FrameworkInfo(name=name, version=None, confidence=0.8, detection_source=source))

    def _check_go_mod(self, path: str):
        """Analyze go.mod for Go frameworks."""
        content = self._read_text(path)
        framework_map = {
            "github.com/gin-gonic/gin": "Gin",
            "github.com/labstack/echo": "Echo",
            "github.com/gofiber/fiber": "Fiber",
        }

        for pkg, name in framework_map.items():
            if pkg in content:
                self.frameworks.append(FrameworkInfo(name=name, version=None, confidence=0.9, detection_source="go.mod"))

    def _check_pom_xml(self, path: str):
        """Analyze pom.xml for Java frameworks."""
        content = self._read_text(path)
        if "spring-boot" in content:
            self.frameworks.append(FrameworkInfo(name="Spring Boot", version=None, confidence=0.9, detection_source="pom.xml"))

    def _check_cargo_toml(self, path: str):
        """Analyze Cargo.toml for Rust frameworks."""
        content = self._read_text(path)
        framework_map = {"actix-web": "Actix Web", "axum": "Axum", "rocket": "Rocket"}

        for pkg, name in framework_map.items():
            if pkg in content:
                self.frameworks.append(FrameworkInfo(name=name, version=None, confidence=0.9, detection_source="Cargo.toml"))

    def detect_frameworks(self, workspace_path: str, files: list[FileEntry], manifests: list[str] | None = None) -> list[FrameworkInfo]:
        """
        Detect frameworks used in the repository.

        Args:
            workspace_path: Absolute path to the repository root.
            files: List of file entries.
            manifests: Optional list of specific manifests to check.

        Returns:
            List of detected FrameworkInfo objects.
        """
        self.frameworks = []

        pkg_json = os.path.join(workspace_path, "package.json")
        req_txt = os.path.join(workspace_path, "requirements.txt")
        pyproj = os.path.join(workspace_path, "pyproject.toml")
        go_mod = os.path.join(workspace_path, "go.mod")
        pom_xml = os.path.join(workspace_path, "pom.xml")
        cargo_toml = os.path.join(workspace_path, "Cargo.toml")

        if os.path.exists(pkg_json):
            self._check_package_json(pkg_json)

        self._check_python_manifests(req_txt, pyproj)

        if os.path.exists(go_mod):
            self._check_go_mod(go_mod)

        if os.path.exists(pom_xml):
            self._check_pom_xml(pom_xml)

        if os.path.exists(cargo_toml):
            self._check_cargo_toml(cargo_toml)

        return self.frameworks
