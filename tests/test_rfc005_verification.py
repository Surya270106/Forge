from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.database.models.execution import ExecutionJobModel, ExecutionStatus
from packages.database.models.verification import (
    RepairAttemptModel,
    VerificationJobModel,
    VerificationResultModel,
    VerificationStatus,
)
from packages.shared.identifiers import generate_id
from services.execution.sandbox import SandboxResult
from services.verification.registry import VerifierDefinition
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
    session.verification_jobs = {}

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
            return session.verification_jobs.setdefault(
                id,
                VerificationJobModel(
                    id=id,
                    organization_id=org_id,
                    repository_id=generate_id(),
                    execution_job_id=exec_id,
                    status=VerificationStatus.PENDING,
                ),
            )
        return None

    session.get.side_effect = mock_get
    return session


@pytest.mark.asyncio
async def test_trigger_verification(mock_session, org_id, exec_id):
    dispatcher = VerificationDispatcher(mock_session, org_id)
    mock_session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)

    job = await dispatcher.trigger_verification(exec_id)

    assert job.status == VerificationStatus.PENDING
    assert job.execution_job_id == exec_id
    assert any(call.args[0] is job for call in mock_session.add.call_args_list)
    mock_session.commit.assert_called()


@pytest.mark.asyncio
@patch("services.verification.service.VerificationRegistry")
@patch("services.verification.service.DockerSandbox")
async def test_run_verification_failure_triggers_repair(mock_sandbox_class, mock_registry_class, mock_session, org_id):
    dispatcher = VerificationDispatcher(mock_session, org_id)
    dispatcher.publisher = AsyncMock()
    mock_registry_class.return_value.config = None
    mock_registry_class.return_value.get_verifiers.return_value = [
        VerifierDefinition(identifier="lint", display_name="Lint", category="lint", command=["lint"]),
        VerifierDefinition(identifier="test", display_name="Test", category="test", command=["test"]),
    ]
    job_id = generate_id()
    job = await mock_session.get(VerificationJobModel, job_id)
    mock_session.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: job),
        SimpleNamespace(scalar_one=lambda: job),
        SimpleNamespace(scalar_one_or_none=lambda: None),
        SimpleNamespace(scalar_one_or_none=lambda: None),
        SimpleNamespace(scalar_one_or_none=lambda: None),
    ]

    # Mock sandbox to fail test
    mock_sandbox = AsyncMock()
    mock_sandbox.run_command.side_effect = [
        SandboxResult(exit_code=0, stdout="Lint OK", stderr=""),  # lint passes
        SandboxResult(exit_code=1, stdout="", stderr="Test failed"),  # test fails
    ]
    mock_sandbox_class.return_value = mock_sandbox

    await dispatcher.run_verification(job_id)

    # Verification should fail
    # We should have stored VerificationResultModel twice and RepairAttemptModel once
    add_calls = mock_session.add.call_args_list
    assert len(add_calls) == 3

    results = [call[0][0] for call in add_calls]
    assert isinstance(results[0], VerificationResultModel)
    assert results[0].status == VerificationStatus.PASSED

    assert isinstance(results[1], VerificationResultModel)
    assert results[1].status == VerificationStatus.FAILED

    repair = results[2]
    assert isinstance(repair, RepairAttemptModel)
    assert repair.verification_job_id == job_id
    assert mock_session.verification_jobs[job_id].status == VerificationStatus.FAILED

    mock_session.commit.assert_called()
    assert dispatcher.publisher.publish.call_count == 3  # started, completed, repair_attempted


@pytest.mark.asyncio
@patch("services.verification.service.VerificationRegistry")
@patch("services.verification.service.DockerSandbox")
async def test_no_configured_verifiers_is_not_reported_as_passed(mock_sandbox_class, mock_registry_class, mock_session, org_id):
    dispatcher = VerificationDispatcher(mock_session, org_id)
    dispatcher.publisher = AsyncMock()
    mock_registry_class.return_value.config = None
    mock_registry_class.return_value.get_verifiers.return_value = []
    mock_sandbox_class.return_value = AsyncMock()
    job_id = generate_id()
    job = await mock_session.get(VerificationJobModel, job_id)
    mock_session.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: job),
        SimpleNamespace(scalar_one_or_none=lambda: None),
    ]

    await dispatcher.run_verification(job_id)

    assert mock_session.verification_jobs[job_id].status == VerificationStatus.NOT_CONFIGURED
    mock_sandbox_class.return_value._ensure_container.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_verification_event_does_not_start_sandbox(mock_session, org_id):
    dispatcher = VerificationDispatcher(mock_session, org_id)
    job_id = generate_id()
    job = await mock_session.get(VerificationJobModel, job_id)
    job.status = VerificationStatus.RUNNING
    mock_session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: job)

    await dispatcher.run_verification(job_id)

    mock_session.commit.assert_not_awaited()
