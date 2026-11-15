"""Deterministic policy decisions. Agent text never supplies identity or policy state."""

import os
import shlex
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import UUID

CAPABILITIES = frozenset({"repository:write", "command:execute", "patch:publish"})
ACTION_CAPABILITY = {"edit_file": "repository:write", "command": "command:execute",
                     "patch_publish": "patch:publish"}
RISK = {"edit_file": "MODERATE", "command": "MODERATE", "patch_publish": "CRITICAL"}
COMMANDS = frozenset({"python", "python3", "pytest", "ruff", "pyright", "node", "npm",
                      "git", "sleep", "true", "echo", "ls", "cat", "test"})
SHELL_OPERATORS = frozenset({";", "&", "&&", "|", "||", ">", ">>", "<", "<<", "(", ")", "$", "`"})


@dataclass(frozen=True)
class PolicyState:
    version: int
    denied: frozenset[str] = frozenset()
    repository_denies: dict[str, frozenset[str]] = field(default_factory=dict)
    stopped: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.version, int) or self.version < 0 or not isinstance(self.stopped, bool) or not self.denied <= CAPABILITIES or any(
            not values <= CAPABILITIES or not _is_uuid(key) for key, values in self.repository_denies.items()
        ):
            raise ValueError("Invalid safety policy")


@dataclass(frozen=True)
class SafetyDecision:
    effect: str
    reason: str
    capability: str | None
    risk: str | None
    policy_version: int
    decided_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def _protected_path(value: str) -> bool:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not value or ".." in path.parts or ":" in value:
        return True
    return any(part in {".git", ".ssh", ".aws", ".config", "credentials"}
               or part == ".env" or part.startswith(".env.")
               or part.endswith((".pem", ".key", ".p12", ".pfx"))
               for part in (piece.casefold() for piece in path.parts))


def workspace_has_sensitive_files(workspace: Path) -> bool:
    # shortcut: recognized credential paths only; scan file content before permitting arbitrary secrets in workspaces.
    for directory, folders, files in os.walk(workspace, followlinks=False):
        folders[:] = [name for name in folders if name != ".git"]
        for name in files:
            relative = (Path(directory) / name).relative_to(workspace).as_posix()
            if relative != ".git" and _protected_path(relative):
                return True
    return False


def parse_command(command: str) -> list[str]:
    if not isinstance(command, str) or len(command) > 4096 or "\x00" in command or "\n" in command:
        raise ValueError("Unsupported command")
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>`$()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError as error:
        raise ValueError("Malformed command") from error
    if not tokens or any(any(char in SHELL_OPERATORS for char in token) for token in tokens if token[0] in ";&|<>`$()"):
        raise ValueError("Shell operators are not supported")
    executable = tokens[0]
    if executable not in COMMANDS or any("=" in part for part in tokens[:1]):
        raise ValueError("Executable is not permitted")
    if executable == "git" and (len(tokens) < 2 or tokens[1] not in {"status", "diff", "log", "show"}):
        raise ValueError("Git command is not permitted")
    if executable == "npm" and (len(tokens) < 2 or tokens[1] not in {"test", "run"}):
        raise ValueError("Package operation is not permitted")
    if executable == "npm" and tokens[1] == "run" and (len(tokens) < 3 or tokens[2] not in {"lint", "build", "test", "typecheck"}):
        raise ValueError("Package script is not permitted")
    return tokens


def decide(action: str, target: str, snapshot: PolicyState, current: PolicyState,
           *, repository_id: UUID | None = None) -> SafetyDecision:
    capability = ACTION_CAPABILITY.get(action)
    version = current.version
    if capability is None:
        return SafetyDecision("DENY", "UNKNOWN_ACTION", None, None, version)
    if current.stopped:
        return SafetyDecision("DENY", "EMERGENCY_STOP", capability, RISK[action], version)
    if action == "edit_file" and _protected_path(target):
        return SafetyDecision("DENY", "PROTECTED_PATH", capability, RISK[action], version)
    if action == "command":
        try:
            parse_command(target)
        except ValueError:
            return SafetyDecision("DENY", "UNSUPPORTED_COMMAND", capability, RISK[action], version)
    for state in (snapshot, current):
        if capability in state.denied or (repository_id and capability in state.repository_denies.get(str(repository_id), frozenset())):
            return SafetyDecision("DENY", "CAPABILITY_REVOKED", capability, RISK[action], version)
    if action == "patch_publish":
        return SafetyDecision("REQUIRES_APPROVAL", "HUMAN_REVIEW", capability, RISK[action], version)
    return SafetyDecision("ALLOW", "CAPABILITY_ALLOWED", capability, RISK[action], version)
