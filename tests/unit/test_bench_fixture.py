from pathlib import Path

import pytest

from services.bench.dataset import load_suite
from services.bench.fixture import materialize_fixture


def test_fixture_commit_is_pinned_and_existing_work_is_not_replaced(tmp_path: Path):
    target = tmp_path / "trial"
    expected = load_suite().tasks[0].base_commit
    assert materialize_fixture(target, expected) == expected
    assert materialize_fixture(target, expected) == expected
    (target / "forgebench.py").write_text("local edit")
    with pytest.raises(ValueError, match="changed"):
        materialize_fixture(target, expected)
