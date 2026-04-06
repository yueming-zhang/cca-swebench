# pyre-strict
"""CLI entry point for my_agents.

Adds custom agent commands alongside the existing Confucius CLI.
"""
from __future__ import annotations

import asyncio
import signal

import click

from my_agents.file_search.entry import FileSearchEntry  # noqa: F401

from confucius.lib.confucius import Confucius
from confucius.lib.entry_repl import run_entry_repl


async def _run_repl(entry_name: str, *, verbose: bool) -> None:
    """Start a REPL that routes user input to the specified entry."""
    cf: Confucius = Confucius(verbose=verbose)

    task: asyncio.Task[None] = asyncio.create_task(
        run_entry_repl(cf, entry_name=entry_name)
    )

    async def on_interrupt(_cf: Confucius, _task: asyncio.Task[None]) -> None:
        if not await _cf.cancel_task():
            _task.cancel()

    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(
            signal.SIGINT, lambda: asyncio.create_task(on_interrupt(cf, task))
        )
    except NotImplementedError:
        pass

    await task


@click.group()
def main() -> None:
    """My Agents CLI - Custom agents built on Confucius"""
    pass


@main.command("file-search")
@click.option("--verbose", is_flag=True, default=False, help="Enable verbose logs")
def file_search_cmd(verbose: bool) -> None:
    """Launch the File Search agent REPL.

    Search local folders by file name or content.
    Read-only access everywhere, writes only to /tmp.
    """
    asyncio.run(_run_repl("FileSearch", verbose=verbose))


if __name__ == "__main__":
    main()



# python -m my_agents.cli file-search