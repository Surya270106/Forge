from typing import TYPE_CHECKING, cast
from uuid import uuid4

from services.verification.registry import VerifierDefinition
from services.verification.service import VerificationDispatcher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def test_passing_verifier_output_is_not_an_error():
    dispatcher = VerificationDispatcher(cast("AsyncSession", None), uuid4())
    verifier = VerifierDefinition(identifier="lint", display_name="Lint", category="lint", command=["ruff"])
    assert dispatcher._parse_diagnostics(verifier, 0, "All checks passed!", "") == []


def test_failing_verifier_reports_real_location_and_message():
    dispatcher = VerificationDispatcher(cast("AsyncSession", None), uuid4())
    verifier = VerifierDefinition(identifier="lint", display_name="Lint", category="lint", command=["ruff"])
    diagnostics = dispatcher._parse_diagnostics(verifier, 1, "src/app.py:12:4: Undefined name 'value'", "")
    assert diagnostics[0]["file"] == "src/app.py"
    assert diagnostics[0]["line"] == 12
    assert diagnostics[0]["column"] == 4
    assert diagnostics[0]["message"] == "Undefined name 'value'"
