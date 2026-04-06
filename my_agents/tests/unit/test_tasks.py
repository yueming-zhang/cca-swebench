# pyre-strict
"""Unit tests for task definition / system prompt.

All tests use mocks - no LLM calls required.
"""
from __future__ import annotations

from my_agents.file_search.tasks import get_task_definition


def test_task_definition_contains_time() -> None:
    """Task definition should include the current time."""
    result = get_task_definition(current_time="2025-01-01T00:00:00")
    assert "2025-01-01T00:00:00" in result


def test_task_definition_describes_readonly() -> None:
    """Task definition should clearly state read-only access."""
    result = get_task_definition(current_time="now")
    assert "READ-ONLY" in result or "read-only" in result.lower()


def test_task_definition_mentions_tmp() -> None:
    """Task definition should mention /tmp as the writable directory."""
    result = get_task_definition(current_time="now")
    assert "/tmp" in result


def test_task_definition_describes_capabilities() -> None:
    """Task definition should describe search capabilities."""
    result = get_task_definition(current_time="now")
    assert "file name" in result.lower() or "name" in result.lower()
    assert "content" in result.lower()


def test_task_definition_mentions_search_tools() -> None:
    """Task definition should mention key search tools."""
    result = get_task_definition(current_time="now")
    assert "find" in result.lower()
    assert "grep" in result.lower()
