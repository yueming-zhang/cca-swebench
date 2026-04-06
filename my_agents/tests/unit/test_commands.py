# pyre-strict
"""Unit tests for file search agent commands configuration.

All tests use mocks - no LLM calls required.
"""
from __future__ import annotations

from my_agents.file_search.commands import get_allowed_commands


def test_get_allowed_commands_returns_dict() -> None:
    """Commands should return a non-empty dict."""
    commands = get_allowed_commands()
    assert isinstance(commands, dict)
    assert len(commands) > 0


def test_search_commands_present() -> None:
    """Core search commands must be available."""
    commands = get_allowed_commands()
    assert "find" in commands
    assert "grep" in commands


def test_file_reading_commands_present() -> None:
    """File reading commands must be available."""
    commands = get_allowed_commands()
    for cmd in ["cat", "head", "tail", "ls"]:
        assert cmd in commands, f"Missing read command: {cmd}"


def test_no_destructive_commands() -> None:
    """Dangerous system-level commands should not be present."""
    commands = get_allowed_commands()
    dangerous = ["rm", "rmdir", "dd", "mkfs", "fdisk", "shutdown", "reboot"]
    for cmd in dangerous:
        assert cmd not in commands, f"Dangerous command should not be allowed: {cmd}"


def test_commands_have_descriptions() -> None:
    """Every command should have a non-empty description string."""
    commands = get_allowed_commands()
    for cmd, desc in commands.items():
        assert isinstance(desc, str), f"Description for {cmd} should be a string"
        assert len(desc) > 0, f"Description for {cmd} should not be empty"


def test_text_processing_commands_present() -> None:
    """Text processing commands for filtering results should be available."""
    commands = get_allowed_commands()
    for cmd in ["sort", "uniq", "cut", "awk"]:
        assert cmd in commands, f"Missing text processing command: {cmd}"
