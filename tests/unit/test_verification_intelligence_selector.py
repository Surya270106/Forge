from types import SimpleNamespace

from services.verification.intelligence import select_verification, verifier_ref


def verifier(identifier: str, target: str, category: str = "test"):
    return SimpleNamespace(identifier=identifier, category=category, enabled=True,
                           command=["pytest", target] if category == "test" else ["ruff", "check", "."], arguments=[])


def test_ranked_base_graph_tests_narrow_only_explicit_configured_targets():
    decision = select_verification(
        [{"path": "src/service.py", "type": "modified"}],
        [{"path": "tests/test_service.py", "source_path": "src/service.py", "depth": 1,
          "confidence": "MEDIUM", "relationship": "TESTS"}],
        {"src/service.py"}, "snapshot-1",
        [verifier("focused", "tests/test_service.py"), verifier("unrelated", "tests/test_other.py"),
         verifier("lint", "", "lint")],
    )
    assert decision["fallback_reasons"] == []
    assert decision["suggested_tests"][0]["path"] == "tests/test_service.py"
    assert decision["suggested_tests"][0]["confidence"] == "MEDIUM"
    assert decision["suggested_tests"][0]["reason_codes"] == ["ATLAS_TEST_ASSOCIATION"]
    assert decision["selected_verifiers"] == ["focused", "lint"]
    assert decision["verifier_targets"]["focused"] == "tests/test_service.py"
    assert decision["selected_verifier_reasons"]["focused"] == "SUGGESTED_TEST"
    assert decision["deferred_verifiers"] == [{"id": "unrelated", "reason": "UNRELATED_EXPLICIT_TEST"}]
    assert decision["coverage_claimed"] is False


def test_changed_test_is_direct_but_missing_graph_or_new_code_forces_broad_run():
    checks = [verifier("focused", "tests/test_service.py"), verifier("other", "tests/test_other.py")]
    direct = select_verification([{"path": "tests/test_service.py", "type": "modified"}], [],
                                 {"tests/test_service.py"}, "snapshot-1", checks)
    assert direct["suggested_tests"][0]["confidence"] == "HIGH"
    assert direct["suggested_tests"][0]["reason_codes"] == ["CHANGED_TEST_FILE"]
    assert direct["selected_verifiers"] == ["focused"]
    for changes, base_paths, snapshot, reason in (
        ([{"path": "src/new.py", "type": "added"}], set(), "snapshot-1", "NEW_OR_DELETED_CODE"),
        ([{"path": "src/service.py", "type": "modified"}], set(), None, "MISSING_BASE_GRAPH"),
        ([{"path": "migrations/versions/new.py", "type": "modified"}], {"migrations/versions/new.py"},
         "snapshot-1", "CROSS_CUTTING_CHANGE"),
        ([{"path": "services/auth/api.py", "type": "modified"}], {"services/auth/api.py"},
         "snapshot-1", "CROSS_CUTTING_CHANGE"),
    ):
        decision = select_verification(changes, [], base_paths, snapshot, checks)
        assert reason in decision["fallback_reasons"]
        assert decision["selected_verifiers"] == ["focused", "other"]


def test_unmapped_test_commands_and_unmapped_candidates_do_not_narrow():
    changes = [{"path": "src/service.py", "type": "modified"}]
    associations = [{"path": "tests/test_service.py", "source_path": "src/service.py", "depth": 1,
                     "confidence": "LOW", "relationship": "IMPORTS"}]
    checks = [SimpleNamespace(identifier="suite", category="test", enabled=True,
                              command=["npm", "test"], arguments=[])]
    decision = select_verification(changes, associations, {"src/service.py"}, "snapshot-1", checks)
    assert "UNMAPPED_VERIFIER_COMMAND" in decision["fallback_reasons"]
    assert decision["selected_verifiers"] == ["suite"]
    assert decision["suggested_tests"][0]["confidence"] == "LOW"
    partial = select_verification(changes + [{"path": "src/other.py", "type": "modified"}], associations,
                                  {"src/service.py", "src/other.py"}, "snapshot-1",
                                  [verifier("focused", "tests/test_service.py"), verifier("other", "tests/test_other.py")])
    assert "PARTIAL_TEST_MAPPING" in partial["fallback_reasons"]
    assert partial["selected_verifiers"] == ["focused", "other"]


def test_truncated_or_ambiguous_graph_does_not_claim_complete_selection():
    decision = select_verification([{"path": "src/service.py", "type": "modified"}], [],
                                   {"src/service.py"}, "snapshot-1",
                                   [verifier("test", "tests/test_service.py")], graph_truncated=True)
    assert "GRAPH_TRUNCATED" in decision["fallback_reasons"]
    assert "NO_TEST_MAPPING" in decision["fallback_reasons"]
    assert decision["selected_verifiers"] == ["test"]
    unresolved = select_verification([{"path": "tests/test_service.py", "type": "modified"}], [],
                                     {"tests/test_service.py"}, "snapshot-1",
                                     [verifier("test", "tests/test_service.py")], graph_uncertain=True)
    assert "UNRESOLVED_RELATIONSHIP" in unresolved["fallback_reasons"]


def test_sensitive_verifier_identifier_is_only_stored_as_a_hash_reference():
    assert verifier_ref("secret=example").startswith("sha256:")
    assert "example" not in verifier_ref("secret=example")


def test_excessive_configured_checks_are_bounded_and_marked_for_blocking():
    checks = [verifier(f"check-{index}", "tests/test_service.py") for index in range(101)]
    decision = select_verification([{"path": "tests/test_service.py", "type": "modified"}], [],
                                   {"tests/test_service.py"}, "snapshot-1", checks)
    assert "VERIFIER_LIMIT_EXCEEDED" in decision["fallback_reasons"]
    assert len(decision["selected_verifiers"]) == 100
