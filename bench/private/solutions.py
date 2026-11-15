"""Deterministic infrastructure demo plans; never copy these into agent workspaces."""

import ast
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "fixture"

SOLUTIONS: dict[str, dict[str, dict[str, str]]] = {
    "clamp-boundary": {"forgebench.py": {"clamp": """def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))"""}},
    "port-validation": {"forgebench.py": {"parse_port": """def parse_port(value: str) -> int:
    if not value.isdecimal() or not 1 <= int(value) <= 65535:
        raise ValueError("Invalid TCP port")
    return int(value)"""}},
    "slug-normalization": {"forgebench.py": {"slug": """def slug(value: str) -> str:
    return "-".join(value.lower().split())"""}},
    "divide-zero": {"forgebench.py": {"safe_divide": """def safe_divide(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else numerator / denominator"""}},
    "state-transition": {"forgebench.py": {"transition": """def transition(current: str, event: str) -> str:
    if current == "pending" and event == "start":
        return "running"
    if current == "running" and event == "finish":
        return "done"
    return current"""}},
    "row-parsing": {"forgebench.py": {"parse_rows": """def parse_rows(text: str) -> list[list[str]]:
    return [[cell.strip() for cell in line.split(",")] for line in text.splitlines() if line.strip()]"""}},
    "stable-dedupe": {"forgebench.py": {"dedupe": """def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))"""}},
    "retry-cap": {"forgebench.py": {"retry_delay": """def retry_delay(attempt: int) -> int:
    if attempt < 0:
        raise ValueError("Negative attempt")
    return min(2 ** attempt, 8)"""}},
    "runtime-selection": {"forgebench.py": {"choose_runtime": """def choose_runtime(filename: str) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "py":
        return "python"
    if suffix in {"js", "ts"}:
        return "node"
    raise ValueError("Unsupported runtime")"""}},
    "output-limit": {"forgebench.py": {"limit_output": """def limit_output(data: bytes, limit: int) -> bytes:
    if limit < 0:
        raise ValueError("Negative limit")
    return data[:limit]"""}},
    "api-port-contract": {
        "forgebench.py": {"parse_port": """def parse_port(value: str) -> int:
    if not value.isdecimal() or not 1 <= int(value) <= 65535:
        raise ValueError("Invalid TCP port")
    return int(value)"""},
        "api.py": {"build_server_config": """def build_server_config(port_text: str) -> dict:
    return {"port": parse_port(port_text) if port_text else 8000, "host": "127.0.0.1"}"""},
    },
    "worker-retry-contract": {
        "forgebench.py": {"retry_delay": """def retry_delay(attempt: int) -> int:
    if attempt < 0:
        raise ValueError("Negative attempt")
    return min(2 ** attempt, 8)"""},
        "worker.py": {"retry_schedule": """def retry_schedule(attempts: int) -> list[int]:
    if not 0 <= attempts <= 5:
        raise ValueError("Invalid retry count")
    return [retry_delay(index) for index in range(attempts)]"""},
    },
}


def deterministic_edits(task_id: str, variant: str = "correct") -> list[tuple[str, str]]:
    if task_id not in SOLUTIONS:
        raise ValueError("Unknown benchmark task")
    if variant not in {"correct", "incorrect", "regression", "timeout"}:
        raise ValueError("Unknown deterministic demo variant")
    if variant != "correct" and task_id != "clamp-boundary":
        raise ValueError("Demo variants are supported only for clamp-boundary")
    if variant == "timeout":
        return []
    edits = {file: dict(functions) for file, functions in SOLUTIONS[task_id].items()}
    if variant == "incorrect":
        edits["forgebench.py"]["clamp"] = "def clamp(value: int, low: int, high: int) -> int:\n    return value"
    if variant == "regression":
        edits["forgebench.py"]["clamp"] = (
            "def clamp(value: int, low: int, high: int) -> int:\n"
            "    return 0 if value == 5 else max(low, min(value, high))"
        )
    result = []
    for file, functions in edits.items():
        source = (FIXTURE / file).read_text()
        lines = source.splitlines(keepends=True)
        nodes = {node.name: node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}
        for name, replacement in sorted(functions.items(), key=lambda item: nodes[item[0]].lineno, reverse=True):
            node = nodes[name]
            lines[node.lineno - 1:node.end_lineno] = [replacement + "\n"]
        result.append((file, "".join(lines)))
    return result
