# pyre-strict
from __future__ import annotations

from datetime import datetime

from confucius.core import types as cf
from confucius.core.analect import Analect, AnalectRunContext
from confucius.core.entry.base import EntryInput, EntryOutput
from confucius.core.entry.decorators import public
from confucius.core.entry.mixin import EntryAnalectMixin
from confucius.core.memory import CfMessage
from confucius.orchestrator.anthropic import AnthropicLLMOrchestrator
from confucius.orchestrator.extensions import Extension
from confucius.orchestrator.extensions.caching.anthropic import AnthropicPromptCaching
from confucius.orchestrator.extensions.command_line.base import CommandLineExtension
from confucius.orchestrator.extensions.file.edit import FileEditExtension
from confucius.orchestrator.extensions.plain_text import PlainTextExtension
from confucius.orchestrator.types import OrchestratorInput

from .commands import get_allowed_commands
from .llm_params import CLAUDE_SONNET_SEARCH
from .policy import ReadOnlyExceptTmpPolicy
from .tasks import get_task_definition


@public
class FileSearchEntry(Analect[EntryInput, EntryOutput], EntryAnalectMixin):
    """File Search Agent

    This analect provides an LLM-powered file search agent that can search
    local folders by file name or content. It has read-only access to all
    directories and can only write to /tmp.
    """

    @classmethod
    def display_name(cls) -> str:
        return "FileSearch"

    @classmethod
    def description(cls) -> str:
        return "Search local folders by file name or content (read-only, writes only to /tmp)"

    @classmethod
    def input_examples(cls) -> list[EntryInput]:
        return [
            EntryInput(question="Find all Python files containing 'def main'"),
            EntryInput(question="Search for files named 'config.yaml' in /home"),
            EntryInput(question="Find all .log files larger than 1MB"),
        ]

    async def impl(self, inp: EntryInput, context: AnalectRunContext) -> EntryOutput:
        # Build task/system prompt
        task_def: str = get_task_definition(
            current_time=datetime.now().isoformat(timespec="seconds")
        )

        # File access policy: read everywhere, write only to /tmp
        access_policy = ReadOnlyExceptTmpPolicy()

        # Prepare extensions
        extensions: list[Extension] = [
            FileEditExtension(
                max_output_lines=500,
                enable_tool_use=True,
                access_policy=access_policy,
            ),
            CommandLineExtension(
                allowed_commands=get_allowed_commands(),
                max_output_lines=500,
                allow_bash_script=True,
                enable_tool_use=True,
            ),
            PlainTextExtension(),
            AnthropicPromptCaching(),
        ]

        orchestrator = AnthropicLLMOrchestrator(
            llm_params=[CLAUDE_SONNET_SEARCH],
            extensions=extensions,
            raw_output_parser=None,
        )

        # Execute the orchestrator
        await context.invoke_analect(
            orchestrator,
            OrchestratorInput(
                messages=[
                    CfMessage(
                        type=cf.MessageType.HUMAN,
                        content=inp.question,
                        attachments=inp.attachments,
                    )
                ],
                task=task_def,
            ),
        )

        return EntryOutput()
