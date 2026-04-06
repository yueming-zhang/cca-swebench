# pyre-strict
"""Integration tests for ReadOnlyExceptTmpPolicy.

These tests use real file system operations - no mocks.
They verify the policy correctly enforces permissions on actual paths.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from my_agents.file_search.policy import ReadOnlyExceptTmpPolicy


@pytest.fixture
def policy() -> ReadOnlyExceptTmpPolicy:
    return ReadOnlyExceptTmpPolicy()


# --- Real Filesystem Read Tests ---


@pytest.mark.asyncio
async def test_read_existing_file(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Should allow reading a real existing file."""
    # /etc/hostname typically exists on Linux
    test_paths = [Path("/etc/hostname"), Path("/etc/os-release")]
    for path in test_paths:
        if path.exists():
            result = await policy.check_read(path)
            assert result.allowed
            break


@pytest.mark.asyncio
async def test_read_current_directory(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Should allow reading the current working directory."""
    cwd = Path.cwd()
    result = await policy.check_read(cwd, is_directory=True)
    assert result.allowed


@pytest.mark.asyncio
async def test_read_project_files(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Should allow reading files in the project directory."""
    project_root = Path("/workspaces/cca-swebench")
    if project_root.exists():
        result = await policy.check_read(project_root, is_directory=True)
        assert result.allowed

        # Find a real file in the project
        for child in project_root.iterdir():
            if child.is_file():
                result = await policy.check_read(child)
                assert result.allowed
                break


# --- Real Filesystem Write Tests in /tmp ---


@pytest.mark.asyncio
async def test_create_real_file_in_tmp(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Should allow creating a real file in /tmp and verify it works."""
    test_path = Path(tempfile.mktemp(dir="/tmp", prefix="file_search_test_"))

    # Policy should allow it
    result = await policy.check_create(test_path)
    assert result.allowed

    # Actually create the file to verify the path is valid
    test_path.write_text("test content from integration test")
    assert test_path.exists()
    assert test_path.read_text() == "test content from integration test"

    # Policy should allow updating it
    result = await policy.check_update(test_path)
    assert result.allowed

    # Policy should allow deleting it
    result = await policy.check_delete(test_path)
    assert result.allowed

    # Clean up
    test_path.unlink()


@pytest.mark.asyncio
async def test_create_in_tmp_subdirectory(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Should allow creating files in subdirectories of /tmp."""
    subdir = Path(tempfile.mkdtemp(dir="/tmp", prefix="file_search_test_"))
    test_file = subdir / "search_results.txt"

    result = await policy.check_create(test_file)
    assert result.allowed

    # Actually create it
    test_file.write_text("search results here")
    assert test_file.exists()

    # Clean up
    test_file.unlink()
    subdir.rmdir()


# --- Real Filesystem Write Denial Tests ---


@pytest.mark.asyncio
async def test_deny_create_in_home(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Should deny creating files in home directory."""
    home = Path.home()
    test_path = home / "should_not_create.txt"
    result = await policy.check_create(test_path)
    assert not result.allowed
    # Verify the file was NOT created
    assert not test_path.exists()


@pytest.mark.asyncio
async def test_deny_create_in_project(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Should deny creating files in the project directory."""
    project = Path("/workspaces/cca-swebench")
    if project.exists():
        test_path = project / "should_not_create.txt"
        result = await policy.check_create(test_path)
        assert not result.allowed


@pytest.mark.asyncio
async def test_deny_update_system_files(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Should deny updating system files."""
    system_paths = [
        Path("/etc/hostname"),
        Path("/var/log/syslog"),
    ]
    for path in system_paths:
        result = await policy.check_update(path)
        assert not result.allowed, f"Update should be denied for {path}"


# --- Path Traversal Integration Tests ---


@pytest.mark.asyncio
async def test_symlink_traversal(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Symlinks from /tmp pointing outside should be resolved correctly."""
    # Create a symlink in /tmp pointing to /etc
    link_path = Path(tempfile.mktemp(dir="/tmp", prefix="symlink_test_"))
    target = Path("/etc")

    try:
        link_path.symlink_to(target)
        # The resolved path of the symlink is /etc, which is outside /tmp
        # Reading should still be allowed (reads are always allowed)
        result = await policy.check_read(link_path)
        assert result.allowed
    finally:
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()


@pytest.mark.asyncio
async def test_real_path_traversal_attempt(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Path traversal via .. should be caught after resolution."""
    # /tmp/../etc resolves to /etc
    path = Path("/tmp/../etc/passwd")
    result = await policy.check_create(path)
    assert not result.allowed


# --- End-to-End Search Scenario Tests ---


@pytest.mark.asyncio
async def test_search_workflow_permissions(policy: ReadOnlyExceptTmpPolicy) -> None:
    """Simulate a complete search workflow verifying permissions at each step."""
    # Step 1: Read source directory (allowed)
    source_dir = Path("/workspaces/cca-swebench")
    if source_dir.exists():
        result = await policy.check_read(source_dir, is_directory=True)
        assert result.allowed

    # Step 2: Read files during search (allowed)
    for py_file in source_dir.rglob("*.py"):
        result = await policy.check_read(py_file)
        assert result.allowed
        break  # Just test one

    # Step 3: Save results to /tmp (allowed)
    output = Path("/tmp/search_results_integration_test.txt")
    result = await policy.check_create(output)
    assert result.allowed

    # Step 4: Try to modify source files (denied)
    for py_file in source_dir.rglob("*.py"):
        result = await policy.check_update(py_file)
        assert not result.allowed
        break

    # Clean up if file was created
    if output.exists():
        output.unlink()
