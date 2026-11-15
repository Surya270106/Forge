import json
from pathlib import Path

from services.execution.run_capsules import CAPTURE_EVENTS, FINAL_EVENTS


def test_synthetic_capsule_fixture_states_are_stable():
    path = Path(__file__).resolve().parents[2] / "bench" / "run-capsule-cases-v1.json"
    cases = json.loads(path.read_text())["cases"]
    assert len(cases) == 7
    assert {case["id"] for case in cases} == {"running-attempt", "lease-expired", "execution-awaits-verification",
                                                  "failed-execution", "cancelled-execution", "verification-finalized",
                                                  "verification-cancelled"}
    for case in cases:
        assert case["event"] in CAPTURE_EVENTS
        assert ("FINAL" if case["event"] in FINAL_EVENTS else "PARTIAL") == case["expected_state"]
