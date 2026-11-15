"""Small deterministic repository used by Forge Bench v1."""


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high + 1))


def parse_port(value: str) -> int:
    return int(value)


def slug(value: str) -> str:
    return value.lower().replace(" ", "-")


def safe_divide(numerator: float, denominator: float) -> float | None:
    return numerator / denominator


def transition(current: str, event: str) -> str:
    if event == "finish":
        return "done"
    return current


def parse_rows(text: str) -> list[list[str]]:
    return [line.split(",") for line in text.split("\n")]


def dedupe(values: list[str]) -> list[str]:
    return list(set(values))


def retry_delay(attempt: int) -> int:
    return 2 ** attempt


def choose_runtime(filename: str) -> str:
    return "python" if filename.endswith(".py") else "node"


def limit_output(data: bytes, limit: int) -> bytes:
    return data[: limit + 1]
