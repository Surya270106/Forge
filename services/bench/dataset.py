"""Versioned public instructions and private grading specifications."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

DATASET = Path(__file__).resolve().parents[2] / "bench" / "core-v1.json"
PRIVATE_TESTS = Path(__file__).resolve().parents[2] / "bench" / "private" / "test_cases.py"
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{2,63}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class BenchmarkTask:
    id: str
    version: int
    title: str
    category: str
    difficulty: str
    instruction: str
    base_commit: str
    budget_seconds: int
    checks: tuple[dict, ...]

    def public(self) -> dict:
        return {key: getattr(self, key) for key in (
            "id", "version", "title", "category", "difficulty", "instruction", "base_commit", "budget_seconds"
        )}


@dataclass(frozen=True)
class BenchmarkSuite:
    id: str
    version: int
    name: str
    digest: str
    tasks: tuple[BenchmarkTask, ...]


def load_suite(path: Path = DATASET) -> BenchmarkSuite:
    raw = path.read_bytes()
    data = json.loads(raw)
    if not IDENTIFIER.fullmatch(data["id"]) or data["version"] < 1:
        raise ValueError("Invalid benchmark suite")
    tasks = tuple(BenchmarkTask(**{**item, "base_commit": item.get("base_commit", data["base_commit"]),
                                   "checks": tuple(item["checks"])}) for item in data["tasks"])
    if not 1 <= len(tasks) <= 15 or len({task.id for task in tasks}) != len(tasks):
        raise ValueError("Invalid benchmark task inventory")
    for task in tasks:
        if (not IDENTIFIER.fullmatch(task.id) or task.version < 1 or not task.instruction.strip()
            or not SHA.fullmatch(task.base_commit) or not 1 <= task.budget_seconds <= 600
            or task.category not in {"bug_fix", "feature", "multi_file", "regression", "understanding", "reliability"}
            or task.difficulty not in {"easy", "medium", "hard"} or not task.checks):
            raise ValueError(f"Invalid benchmark task: {task.id}")
        for check in task.checks:
            if (not IDENTIFIER.fullmatch(check["id"]) or check["category"] not in
                {"correctness", "regression", "quality", "reliability", "safety"}
                or check["type"] not in {"unittest", "scope"}):
                raise ValueError(f"Invalid benchmark check: {task.id}")
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + PRIVATE_TESTS.read_bytes()
    return BenchmarkSuite(data["id"], data["version"], data["name"], hashlib.sha256(canonical).hexdigest(), tasks)
