"""Integration tests for ChatAgent.

These tests make real API calls to AWS Bedrock. Requires:
- Valid AWS credentials (~/.aws/credentials or env vars)
- AWS_REGION set (defaults to us-west-2)
- Access to the Claude model on Bedrock
"""
from __future__ import annotations

import pytest

from claude_agents.chat.agent import ChatAgent


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_chat_returns_nonempty_response(capsys):
    """A simple chat message should return a non-empty response."""
    agent = ChatAgent()
    response = agent.chat("Say exactly: hello")

    assert len(response) > 0
    assert isinstance(response, str)


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_chat_history_after_one_exchange(capsys):
    """After one exchange, history should have a user and assistant message."""
    agent = ChatAgent()
    agent.chat("Say exactly: hi")

    assert len(agent.history) == 2
    assert agent.history[0]["role"] == "user"
    assert agent.history[1]["role"] == "assistant"
    assert len(agent.history[1]["content"]) > 0


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_multi_turn_conversation(capsys):
    """Agent should maintain context across turns."""
    agent = ChatAgent()
    agent.chat("My favorite color is blue. Just say OK.")
    response = agent.chat("What is my favorite color? Reply with just the color.")

    assert "blue" in response.lower()
    assert len(agent.history) == 4
