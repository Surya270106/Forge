from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.database.models.execution import ExecutionJobModel, ExecutionStatus
from packages.database.models.verification import (
    DiagnosticType,
    VerificationJobModel,
    VerificationStatus,
)
from packages.shared.identifiers import generate_id
from services.execution.sandbox import SandboxResult
from services.verification.service import VerificationDispatcher


@pytest.fixture
def org_id():
    return generate_id()


@pytest.fixture
def exec_id():
    return generate_id()


@pytest.fixture
def mock_session(org_id, exec_id):
    session = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()

    # Mock Execution Job fetching
    exec_job = ExecutionJobModel(
        id=exec_id,
        organization_id=org_id,
        repository_id=generate_id(),
        plan_id=generate_id(),
        status=ExecutionStatus.COMPLETED,
    )

    def mock_get(model, id):
        if model == ExecutionJobModel:
            return exec_job
        elif model == VerificationJobModel:
            return VerificationJobModel(
                id=id,
                organization_id=org_id,
                repository_id=generate_id(),
                execution_job_id=exec_id,
                status=VerificationStatus.PENDING,
            )
        return None

    session.get.side_effect = mock_get
    return session


@pytest.mark.asyncio
async def test_trigger_verification(mock_session, org_id, exec_id):
    dispatcher = VerificationDispatcher(mock_session, org_id)

    job = await dispatcher.trigger_verification(exec_id)

    assert job.status == VerificationStatus.PENDING
    assert job.execution_job_id == exec_id
    mock_session.add.assert_called_with(job)
    mock_session.commit.assert_called()


@pytest.mark.asyncio
@patch("services.verification.service.LocalProcessSandbox")
async def test_run_verification_failure_triggers_repair(mock_sandbox_class, mock_session, org_id):
    dispatcher = VerificationDispatcher(mock_session, org_id)
    dispatcher.publisher = AsyncMock()

    # Mock sandbox to fail test
    mock_sandbox = AsyncMock()
    mock_sandbox.run_command.side_effect = [
        SandboxResult(exit_code=0, stdout="Lint OK", stderr=""),  # lint passes
        SandboxResult(exit_code=1, stdout="", stderr="Test failed"),  # test fails
    ]
    mock_sandbox_class.return_value = mock_sandbox

    job_id = generate_id()
    await dispatcher.run_verification(job_id)

    # Verification should fail
    # We should have stored VerificationResultModel twice and RepairAttemptModel once
    add_calls = mock_session.add.call_args_list
    assert len(add_calls) == 3

    results = [call[0][0] for call in add_calls]
    assert results[0].diagnostic_type == DiagnosticType.LINT
    assert results[0].is_passed

    assert results[1].diagnostic_type == DiagnosticType.UNIT_TEST
    assert not results[1].is_passed

    repair = results[2]
    assert repair.__class__.__name__ == "RepairAttemptModel"
    assert repair.verification_job_id == job_id

    mock_session.commit.assert_called()
    assert dispatcher.publisher.publish.call_count == 3  # started, completed, repair_attempted
