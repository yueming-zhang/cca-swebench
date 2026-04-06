# pyre-strict
"""Integration tests for file search commands.

These tests verify commands actually work on the real file system - no mocks.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from my_agents.file_search.commands import get_allowed_commands


@pytest.fixture
def test_dir() -> Path:
    """Create a temporary directory with test files for searching."""
    tmpdir = Path(tempfile.mkdtemp(dir="/tmp", prefix="file_search_cmd_test_"))

    # Create test file structure
    (tmpdir / "hello.py").write_text("def main():\n    print('hello world')\n")
    (tmpdir / "config.yaml").write_text("database:\n  host: localhost\n  port: 5432\n")
    (tmpdir / "readme.md").write_text("# Test Project\nThis is a test.\n")

    subdir = tmpdir / "subdir"
    subdir.mkdir()
    (subdir / "utils.py").write_text("def helper():\n    return 42\n")
    (subdir / "data.csv").write_text("name,age\nalice,30\nbob,25\n")

    yield tmpdir

    # Cleanup
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)


def _run_cmd(cmd: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the result."""
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=10
    )


class TestFindCommand:
    """Test the 'find' command for file name searches."""

    def test_find_by_extension(self, test_dir: Path) -> None:
        """Find all Python files by extension."""
        commands = get_allowed_commands()
        assert "find" in commands

        result = _run_cmd(f"find {test_dir} -name '*.py'")
        assert result.returncode == 0
        assert "hello.py" in result.stdout
        assert "utils.py" in result.stdout

    def test_find_by_name(self, test_dir: Path) -> None:
        """Find files by exact name."""
        result = _run_cmd(f"find {test_dir} -name 'config.yaml'")
        assert result.returncode == 0
        assert "config.yaml" in result.stdout

    def test_find_by_type(self, test_dir: Path) -> None:
        """Find only directories."""
        result = _run_cmd(f"find {test_dir} -type d")
        assert result.returncode == 0
        assert "subdir" in result.stdout

    def test_find_no_results(self, test_dir: Path) -> None:
        """Find with no matching files returns empty."""
        result = _run_cmd(f"find {test_dir} -name '*.nonexistent'")
        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestGrepCommand:
    """Test the 'grep' command for content searches."""

    def test_grep_simple_pattern(self, test_dir: Path) -> None:
        """Grep for a simple text pattern."""
        commands = get_allowed_commands()
        assert "grep" in commands

        result = _run_cmd(f"grep -r 'def main' {test_dir}")
        assert result.returncode == 0
        assert "hello.py" in result.stdout

    def test_grep_recursive(self, test_dir: Path) -> None:
        """Grep recursively through subdirectories."""
        result = _run_cmd(f"grep -r 'def ' {test_dir}")
        assert result.returncode == 0
        assert "hello.py" in result.stdout
        assert "utils.py" in result.stdout

    def test_grep_with_line_numbers(self, test_dir: Path) -> None:
        """Grep with line numbers for context."""
        result = _run_cmd(f"grep -rn 'localhost' {test_dir}")
        assert result.returncode == 0
        assert "config.yaml" in result.stdout

    def test_grep_case_insensitive(self, test_dir: Path) -> None:
        """Grep with case-insensitive matching."""
        result = _run_cmd(f"grep -ri 'test project' {test_dir}")
        assert result.returncode == 0
        assert "readme.md" in result.stdout

    def test_grep_no_match(self, test_dir: Path) -> None:
        """Grep for a pattern that doesn't exist."""
        result = _run_cmd(f"grep -r 'zzz_nonexistent_pattern_zzz' {test_dir}")
        assert result.returncode == 1  # grep returns 1 for no match


class TestFileReadingCommands:
    """Test file reading commands."""

    def test_cat_file(self, test_dir: Path) -> None:
        """Cat should display file contents."""
        result = _run_cmd(f"cat {test_dir}/hello.py")
        assert result.returncode == 0
        assert "def main" in result.stdout

    def test_head_file(self, test_dir: Path) -> None:
        """Head should show first lines."""
        result = _run_cmd(f"head -n 1 {test_dir}/hello.py")
        assert result.returncode == 0
        assert "def main" in result.stdout

    def test_wc_file(self, test_dir: Path) -> None:
        """Wc should count lines/words."""
        result = _run_cmd(f"wc -l {test_dir}/subdir/data.csv")
        assert result.returncode == 0
        # data.csv has 3 lines
        assert "3" in result.stdout

    def test_ls_directory(self, test_dir: Path) -> None:
        """Ls should list directory contents."""
        result = _run_cmd(f"ls {test_dir}")
        assert result.returncode == 0
        assert "hello.py" in result.stdout
        assert "subdir" in result.stdout


class TestTextProcessingPipelines:
    """Test combining search with text processing commands."""

    def test_find_and_sort(self, test_dir: Path) -> None:
        """Find files and sort the results."""
        result = _run_cmd(f"find {test_dir} -name '*.py' | sort")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert len(lines) == 2
        # Sorted order: hello.py should come before utils.py
        assert "hello.py" in lines[0]
        assert "utils.py" in lines[1]

    def test_grep_and_count(self, test_dir: Path) -> None:
        """Grep for pattern and count matches."""
        result = _run_cmd(f"grep -rc 'def ' {test_dir} | grep -v ':0'")
        assert result.returncode == 0
        assert "hello.py" in result.stdout

    def test_find_and_xargs_grep(self, test_dir: Path) -> None:
        """Find files then search their content."""
        result = _run_cmd(
            f"find {test_dir} -name '*.py' | xargs grep -l 'return'"
        )
        assert result.returncode == 0
        assert "utils.py" in result.stdout


class TestWriteToTmpOnly:
    """Test that write operations work in /tmp."""

    def test_save_search_results_to_tmp(self, test_dir: Path) -> None:
        """Simulate saving search results to /tmp."""
        output_file = Path(tempfile.mktemp(dir="/tmp", prefix="search_out_"))
        try:
            result = _run_cmd(
                f"find {test_dir} -name '*.py' > {output_file}"
            )
            assert result.returncode == 0
            assert output_file.exists()
            content = output_file.read_text()
            assert "hello.py" in content
            assert "utils.py" in content
        finally:
            if output_file.exists():
                output_file.unlink()

    def test_mkdir_in_tmp(self, test_dir: Path) -> None:
        """Should be able to create directories in /tmp."""
        new_dir = Path(tempfile.mktemp(dir="/tmp", prefix="search_dir_"))
        try:
            result = _run_cmd(f"mkdir -p {new_dir}/results")
            assert result.returncode == 0
            assert (new_dir / "results").is_dir()
        finally:
            import shutil

            shutil.rmtree(new_dir, ignore_errors=True)
