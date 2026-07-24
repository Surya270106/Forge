import os
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field


class VerifierDefinition(BaseModel):
    identifier: str
    display_name: str
    category: str
    command: List[str]
    arguments: List[str] = Field(default_factory=list)
    working_directory: str = "."
    timeout: int = 300
    blocking: bool = True
    enabled: bool = True
    supported_languages: List[str] = Field(default_factory=list)
    diagnostic_parser: str = "default"


class ForgeYamlVerification(BaseModel):
    format: Optional[List[VerifierDefinition]] = None
    lint: Optional[List[VerifierDefinition]] = None
    typecheck: Optional[List[VerifierDefinition]] = None
    test: Optional[List[VerifierDefinition]] = None
    build: Optional[List[VerifierDefinition]] = None
    security: Optional[List[VerifierDefinition]] = None


class ForgeYamlConfig(BaseModel):
    version: int = 1
    languages: List[str] = Field(default_factory=list)
    verification: Optional[ForgeYamlVerification] = None


class VerificationRegistry:
    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.config = self._load_forge_yaml()

    def _load_forge_yaml(self) -> Optional[ForgeYamlConfig]:
        yaml_path = os.path.join(self.workspace_dir, "forge.yaml")
        if not os.path.exists(yaml_path):
            return None
        try:
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
                return ForgeYamlConfig(**data)
        except Exception:
            return None

    def get_verifiers(self) -> List[VerifierDefinition]:
        if not self.config or not self.config.verification:
            # Return some defaults if no forge.yaml is present
            return [
                VerifierDefinition(
                    identifier="default-lint", display_name="Default Linter", category="lint", command=["npm", "run", "lint"], timeout=300
                ),
                VerifierDefinition(identifier="default-test", display_name="Default Tests", category="test", command=["npm", "test"], timeout=600),
            ]

        v = self.config.verification
        verifiers = []
        for category_list in [v.format, v.lint, v.typecheck, v.test, v.build, v.security]:
            if category_list:
                verifiers.extend(category_list)
        return verifiers
