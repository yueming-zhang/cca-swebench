# pyre-strict
"""Unit tests for ReadOnlyExceptTmpPolicy.

All tests use mocks - no LLM calls required.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from my_agents.file_search.policy import ReadOnlyExceptTmpPolicy


@pytest.fixture
def policy() -> ReadOnlyExceptTmpPolicy:
    return ReadOnlyExceptTmpPolicy()


@pytest.fixture
def custom_policy() -> ReadOnlyExceptTmpPolicy:
    return ReadOnlyExceptTmpPolicy(writable_root="/tmp/my_agent_workspace")


# --- Read Access Tests ---


@pytest.mark.asyncio
async def test_read_file_allowed_anywhere(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Reading should be allowed from any path."""
    paths = [
        Path("/home/user/documents/report.txt"),
        Path("/etc/config.yaml"),
        Path("/var/log/syslog"),
        Path("/tmp/output.txt"),
        Path("/usr/local/bin/script.sh"),
    ]
    for path in paths:
        result = await policy.check_read(path)
        assert result.allowed, f"Read should be allowed for {path}"


@pytest.mark.asyncio
async def test_read_directory_allowed(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Reading directories should be allowed."""
    result = await policy.check_read(Path("/home/user"), is_directory=True)
    assert result.allowed


@pytest.mark.asyncio
async def test_read_root_allowed(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Reading root path should be allowed."""
    result = await policy.check_read(Path("/"))
    assert result.allowed


# --- Create Access Tests ---


@pytest.mark.asyncio
async def test_create_in_tmp_allowed(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Creating files under /tmp should be allowed."""
    paths = [
        Path("/tmp/results.txt"),
        Path("/tmp/search_output/matches.log"),
        Path("/tmp/deep/nested/dir/file.txt"),
    ]
    for path in paths:
        result = await policy.check_create(path)
        assert result.allowed, f"Create should be allowed for {path}"


@pytest.mark.asyncio
async def test_create_outside_tmp_denied(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Creating files outside /tmp should be denied."""
    paths = [
        Path("/home/user/newfile.txt"),
        Path("/etc/new_config.yaml"),
        Path("/var/data/output.csv"),
        Path("/opt/app/data.json"),
    ]
    for path in paths:
        result = await policy.check_create(path)
        assert not result.allowed, f"Create should be denied for {path}"
        assert "/tmp" in result.message


@pytest.mark.asyncio
async def test_create_tmp_itself_allowed(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Creating at /tmp root itself should be allowed."""
    result = await policy.check_create(Path("/tmp"))
    assert result.allowed


# --- Update Access Tests ---


@pytest.mark.asyncio
async def test_update_in_tmp_allowed(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Updating files under /tmp should be allowed."""
    result = await policy.check_update(Path("/tmp/existing_file.txt"))
    assert result.allowed


@pytest.mark.asyncio
async def test_update_outside_tmp_denied(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Updating files outside /tmp should be denied."""
    result = await policy.check_update(Path("/home/user/important.py"))
    assert not result.allowed
    assert "write operations" in result.message.lower()


# --- Delete Access Tests ---


@pytest.mark.asyncio
async def test_delete_in_tmp_allowed(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Deleting files under /tmp should be allowed."""
    result = await policy.check_delete(Path("/tmp/old_results.txt"))
    assert result.allowed


@pytest.mark.asyncio
async def test_delete_outside_tmp_denied(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Deleting files outside /tmp should be denied."""
    result = await policy.check_delete(Path("/home/user/data.csv"))
    assert not result.allowed
    assert "/tmp" in result.message


# --- Path Traversal Security Tests ---


@pytest.mark.asyncio
async def test_path_traversal_blocked(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Path traversal attempts should not bypass the /tmp restriction."""
    # Paths that try to escape /tmp via ..
    malicious_paths = [
        Path("/tmp/../etc/passwd"),
        Path("/tmp/../../home/user/secret.txt"),
        Path("/tmp/subdir/../../etc/shadow"),
    ]
    for path in malicious_paths:
        result = await policy.check_create(path)
        # After resolve(), these should point outside /tmp
        assert not result.allowed, f"Path traversal should be blocked for {path}"


# --- Custom Writable Root Tests ---


@pytest.mark.asyncio
async def test_custom_writable_root(custom_policy: ReadOnlyExceptTmpPolicy) -> None:
    """Custom writable root should restrict writes to that directory."""
    # Allowed: within custom root
    result = await custom_policy.check_create(
        Path("/tmp/my_agent_workspace/output.txt")
    )
    assert result.allowed

    # Denied: /tmp but outside custom root
    result = await custom_policy.check_create(Path("/tmp/other_dir/file.txt"))
    assert not result.allowed


# --- Error Message Tests ---


@pytest.mark.asyncio
async def test_error_messages_informative(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Error messages should clearly explain the restriction."""
    result = await policy.check_create(Path("/home/user/file.txt"))
    assert not result.allowed
    assert "Cannot create" in result.message
    assert "/home/user/file.txt" in result.message
    assert "/tmp" in result.message

    result = await policy.check_update(Path("/etc/config"))
    assert not result.allowed
    assert "Cannot update" in result.message

    result = await policy.check_delete(Path("/var/log/old.log"))
    assert not result.allowed
    assert "Cannot delete" in result.message
