# pyre-strict
"""Unit tests for FileSearchEntry.

All tests use mocks - no LLM calls required.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from my_agents.file_search.entry import FileSearchEntry
from my_agents.file_search.policy import ReadOnlyExceptTmpPolicy


def test_display_name() -> None:
    """Entry should have correct display name."""
    assert FileSearchEntry.display_name() == "FileSearch"


def test_description() -> None:
    """Entry should have a meaningful description."""
    desc = FileSearchEntry.description()
    assert "search" in desc.lower() or "Search" in desc
    assert len(desc) > 10


def test_input_examples() -> None:
    """Entry should provide input examples."""
    examples = FileSearchEntry.input_examples()
    assert len(examples) > 0
    for ex in examples:
        assert ex.question
        assert len(ex.question) > 0


@pytest.mark.asyncio
async def test_impl_creates_correct_extensions() -> None:
    """impl() should configure extensions with the right policy."""
    entry = FileSearchEntry()

    mock_context = MagicMock()
    mock_context.invoke_analect = AsyncMock()

    mock_input = MagicMock()
    mock_input.question = "find all .py files"
    mock_input.attachments = []

    await entry.impl(mock_input, mock_context)

    # Verify invoke_analect was called
    mock_context.invoke_analect.assert_called_once()

    # Get the orchestrator that was passed
    call_args = mock_context.invoke_analect.call_args
    orchestrator = call_args[0][0]

    # Verify orchestrator has extensions configured
    assert len(orchestrator.extensions) > 0

    # Verify FileEditExtension uses ReadOnlyExceptTmpPolicy
    from confucius.orchestrator.extensions.file.edit import FileEditExtension

    file_ext = None
    for ext in orchestrator.extensions:
        if isinstance(ext, FileEditExtension):
            file_ext = ext
            break

    assert file_ext is not None, "FileEditExtension should be present"
    assert isinstance(
        file_ext.access_policy, ReadOnlyExceptTmpPolicy
    ), "Should use ReadOnlyExceptTmpPolicy"


@pytest.mark.asyncio
async def test_impl_passes_question_to_orchestrator() -> None:
    """impl() should forward the user's question to the orchestrator."""
    entry = FileSearchEntry()

    mock_context = MagicMock()
    mock_context.invoke_analect = AsyncMock()

    mock_input = MagicMock()
    mock_input.question = "search for config files"
    mock_input.attachments = []

    await entry.impl(mock_input, mock_context)

    call_args = mock_context.invoke_analect.call_args
    orchestrator_input = call_args[0][1]

    # Verify the user's question is in the messages
    assert len(orchestrator_input.messages) == 1
    assert orchestrator_input.messages[0].content == "search for config files"


@pytest.mark.asyncio
async def test_impl_includes_task_definition() -> None:
    """impl() should include a task definition with the system prompt."""
    entry = FileSearchEntry()

    mock_context = MagicMock()
    mock_context.invoke_analect = AsyncMock()

    mock_input = MagicMock()
    mock_input.question = "test"
    mock_input.attachments = []

    await entry.impl(mock_input, mock_context)

    call_args = mock_context.invoke_analect.call_args
    orchestrator_input = call_args[0][1]

    assert "File Search Agent" in orchestrator_input.task
    assert "READ-ONLY" in orchestrator_input.task
