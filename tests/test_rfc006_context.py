from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch as mock_patch

import jinja2
import pytest
from litellm import ModelResponse

from packages.database.models.context import AgentInteractionModel, ModelProvider, PromptTemplateModel
from packages.database.models.memory import SymbolModel
from packages.shared.errors import ConflictError
from packages.shared.identifiers import generate_id
from services.context_engine.service import AgentOrchestrator, PromptManager


@pytest.fixture
def org_id():
    return generate_id()


@pytest.fixture
def repo_id():
    return generate_id()


@pytest.fixture
def mock_session(org_id, repo_id):
    session = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    # Mock template
    template = PromptTemplateModel(
        name="test_template",
        template_text="Fix the bug based on symbols: {% for s in symbols %}{{ s.name }} ({{ s.kind }}) {% endfor %}",
        default_provider=ModelProvider.LOCAL,
        default_model="test-model",
    )

    # Mock symbol
    symbol = SymbolModel(
        id=generate_id(),
        organization_id=org_id,
        repository_id=repo_id,
        source_file_id=generate_id(),
        memory_version_id=generate_id(),
        name="MyClass",
        qualname="src.index.MyClass",
        symbol_type="class",
        line_start=1,
        line_end=10,
        snippet="class MyClass {}",
    )

    # Mock execute/scalars
    mock_result = MagicMock()
    mock_scalars = MagicMock()

    # We call execute twice: first for template, second for symbols
    mock_scalars.first.return_value = template
    mock_scalars.all.return_value = [symbol]

    mock_result.scalars.return_value = mock_scalars
    session.execute = AsyncMock(return_value=mock_result)

    return session


def test_prompt_manager_jinja2_render():
    template = "Hello {{ query }}. Available context: {{ symbols | length }} symbols."
    context = {"query": "fix this", "symbols": [{"name": "A"}, {"name": "B"}]}
    rendered = PromptManager.render(template, context)
    assert rendered == "Hello fix this. Available context: 2 symbols."


def test_prompt_manager_jinja2_secure():
    # Attempting to access unsafe methods should fail in sandbox
    template = "{{ query.__class__.__bases__[0].__subclasses__() }}"
    context = {"query": "test"}
    with pytest.raises(jinja2.exceptions.SecurityError):
        PromptManager.render(template, context)


@pytest.mark.asyncio
async def test_agent_orchestrator_invocation(mock_session, org_id, repo_id):
    orchestrator = AgentOrchestrator(mock_session, org_id)
    orchestrator.publisher = AsyncMock()

    orchestrator.assembler.assemble_context = AsyncMock(
        return_value={
            "query": "help me",
            "symbols": [{"name": "MyClass", "kind": "class"}],
            "files": [],
        }
    )
    mock_session.get = AsyncMock(
        return_value=SimpleNamespace(
            provider_config={
                "provider": "local",
                "model": "test-model",
                "api_key": "encrypted",
            }
        )
    )
    response = ModelResponse(choices=[{"message": {"content": "Here is the plan to achieve your intent..."}}])
    with (
        mock_patch("packages.shared.crypto.CryptoService.decrypt", return_value="test-key"),
        mock_patch("litellm.acompletion", new=AsyncMock(return_value=response)),
    ):
        interaction = await orchestrator.invoke_agent(repository_id=repo_id, query="help me", template_name="test_template")

    assert interaction.provider == ModelProvider.LOCAL
    assert interaction.response_text == "Here is the plan to achieve your intent..."

    # Verify the snapshot contains the correctly rendered Jinja2 template
    add_calls = mock_session.add.call_args_list
    snapshot = add_calls[0][0][0]

    assert "Fix the bug based on symbols: MyClass (class)" in snapshot.assembled_prompt

    assert mock_session.flush.call_count == 2
    assert orchestrator.publisher.publish.call_count == 2


def test_prompt_manager_jinja2_unsafe_attribute():
    template = "{{ query.__class__.__name__ }}"
    context = {"query": "test"}
    with pytest.raises(jinja2.exceptions.SecurityError):
        PromptManager.render(template, context)


@pytest.mark.asyncio
async def test_missing_provider_key_does_not_return_fake_interaction(mock_session, org_id, repo_id):
    orchestrator = AgentOrchestrator(mock_session, org_id)
    orchestrator.assembler.assemble_context = AsyncMock(return_value={"query": "help", "symbols": [], "files": []})
    mock_session.get = AsyncMock(return_value=SimpleNamespace(provider_config={}))
    with (
        mock_patch("packages.shared.crypto.CryptoService.decrypt", return_value=""),
        pytest.raises(ConflictError, match="Configure a model provider"),
    ):
        await orchestrator.invoke_agent(repo_id, "help", "test_template")


@pytest.mark.asyncio
async def test_invalid_provider_response_does_not_create_interaction(mock_session, org_id, repo_id):
    orchestrator = AgentOrchestrator(mock_session, org_id)
    orchestrator.assembler.assemble_context = AsyncMock(return_value={"query": "help", "symbols": [], "files": []})
    mock_session.get = AsyncMock(return_value=SimpleNamespace(provider_config={"provider": "openai", "model": "test-model", "api_key": "encrypted"}))
    with (
        mock_patch("packages.shared.crypto.CryptoService.decrypt", return_value="test-key"),
        mock_patch("litellm.acompletion", new=AsyncMock(return_value=SimpleNamespace())),
        pytest.raises(ConflictError, match="Model provider returned an invalid response"),
    ):
        await orchestrator.invoke_agent(repo_id, "help", "test_template")
    assert not any(isinstance(call.args[0], AgentInteractionModel) for call in mock_session.add.call_args_list)
    mock_session.commit.assert_not_awaited()


def test_prompt_manager_jinja2_missing_variable():
    template = "Hello {{ missing_var }}"
    context = {}
    with pytest.raises(jinja2.exceptions.UndefinedError):
        PromptManager.render(template, context)


def test_prompt_manager_jinja2_oversized_context():
    # In practice, limit lengths by configuration or slicing.
    # Testing that large payloads do not crash the renderer.
    template = "Symbols: {{ symbols | length }}"
    context = {"symbols": [{"name": f"Sym{i}"} for i in range(10000)]}
    rendered = PromptManager.render(template, context)
    assert rendered == "Symbols: 10000"
