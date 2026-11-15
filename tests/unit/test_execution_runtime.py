import pytest

from services.execution.runtime import select_execution_image


@pytest.mark.parametrize(("language", "command", "expected"), [
    ("python", "python -m pytest", "python:3.12-slim"),
    ("javascript", "npm test", "node:20-slim"),
    ("typescript", "test -f result.txt", "node:20-slim"),
])
def test_selects_approved_runtime(language, command, expected):
    assert select_execution_image(language, [command], ["python:3.12-slim", "node:20-slim"]) == expected


@pytest.mark.parametrize(("language", "commands", "images"), [
    ("go", [], ["python:3.12-slim"]),
    (None, [], ["python:3.12-slim"]),
    ("python", [], ["node:20-slim"]),
    ("python", [], []),
    ("javascript", [], [None]),
    ("python", ["npm test"], ["python:3.12-slim", "node:20-slim"]),
])
def test_rejects_unknown_missing_or_mixed_runtime(language, commands, images):
    with pytest.raises(ValueError):
        select_execution_image(language, commands, images)
