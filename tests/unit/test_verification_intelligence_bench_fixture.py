"""Deterministic selection semantics on Forge Bench's separate evidence fixtures."""

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.patch.service import PatchService
from services.verification.intelligence import select_verification

FIXTURE = json.loads((Path(__file__).resolve().parents[2] / "bench" /
                      "verification-intelligence-cases-v1.json").read_text())


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["id"])
def test_bench_selection_evidence_cases(case):
    verifiers = [SimpleNamespace(identifier=item["id"], category="test", enabled=True,
                                 command=["pytest", item["target"]], arguments=[])
                 for item in FIXTURE["verifiers"]]
    result = select_verification(case["changes"], case["associations"], set(case["base_paths"]),
                                 case["snapshot"], verifiers)
    assert result["selected_verifiers"] == case["expected_selected"]
    assert result["fallback_reasons"] == case["expected_reasons"]
    assert (result["suggested_tests"][0]["path"] if result["suggested_tests"] else None) == case["expected_test"]
    assert not result["coverage_claimed"]
    if "captured_digest" in case:
        mutation = SimpleNamespace(id=uuid4(), file_path="tests/test_a.py",
                                   diff_hunk="--- tests/test_a.py\n+++ tests/test_a.py\n@@ -1 +1 @@\n-old\n+new\n")
        assert PatchService._review_digest("a" * 40, [mutation]) != case["captured_digest"]
