# pyre-strict
"""End-to-end integration test for the FileSearch agent.

This test creates a real file in /tmp, invokes the FileSearchEntry with a real
LLM call through Confucius, and verifies the agent finds the file.

Requires valid AWS/Bedrock credentials to run.
"""
from __future__ import annotations

import shutil
import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from confucius.core.entry.base import EntryInput
from confucius.core.entry.entry import Entry
from confucius.core.io.base import IOInterface
from confucius.lib.confucius import Confucius

# Import to trigger @public registration
from my_agents.file_search.entry import FileSearchEntry  # noqa: F401


class CapturingIOInterface(IOInterface):
    """IO interface that captures all output for test assertions."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def print(self, text: str, **kwargs: Any) -> None:
        self.messages.append(text)

    async def _get_input(self, prompt: str, placeholder: str | None = None) -> str:
        return ""

    def get_all_output(self) -> str:
        return "\n".join(self.messages)


@pytest.fixture
def sample_file() -> Generator[Path, None, None]:
    """Create a uniquely-named sample text file in /tmp for the agent to find."""
    test_id = uuid.uuid4().hex[:8]
    tmpdir = Path(tempfile.mkdtemp(dir="/tmp", prefix=f"e2e_search_{test_id}_"))
    filepath = tmpdir / f"secret_notes_{test_id}.txt"
    filepath.write_text(
        "This file contains important information.\n"
        "The password to the vault is 'open-sesame'.\n"
        "Do not share this with anyone.\n"
    )
    yield filepath
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_file_search_e2e(sample_file: Path) -> None:
    """The agent should find a file in /tmp when asked to search for it."""
    capturing_io = CapturingIOInterface()

    cf = Confucius(
        session=f"test-e2e-{uuid.uuid4().hex[:8]}",
        io=capturing_io,
    )

    query = f"Find the file named '{sample_file.name}' under /tmp and show me its contents."

    await cf.invoke_analect(
        Entry(),
        EntryInput(question=query, entry_name="FileSearch"),
    )

    output = capturing_io.get_all_output()

    # The agent should have read the file contents (proves it found and opened the file)
    assert "open-sesame" in output, (
        f"Agent output should include file contents. Got:\n{output[:2000]}"
    )



@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_file_search_ls_result() -> None:
    """The agent should find a file in /tmp when asked to search for it."""
    file_name = "ls_result.txt"
    capturing_io = CapturingIOInterface()

    cf = Confucius(
        session=f"test-e2e-{uuid.uuid4().hex[:8]}",
        io=capturing_io,
    )

    query = f"Find the file named '{file_name}' under /tmp and show me its contents."

    await cf.invoke_analect(
        Entry(),
        EntryInput(question=query, entry_name="FileSearch"),
    )

    output = capturing_io.get_all_output()

    # The agent should have found and referenced the file
    assert file_name in output, (
        f"Agent output should mention the file '{file_name}'. Got:\n{output[:2000]}"
    )
