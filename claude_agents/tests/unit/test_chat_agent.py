"""Unit tests for ChatAgent.

All tests use mocks - no LLM or AWS calls required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from claude_agents.chat.agent import ChatAgent, DEFAULT_MODEL_ID, DEFAULT_MAX_TOKENS


class FakeTextStream:
    """Simulates the streaming text iterator."""

    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    def __iter__(self):
        return iter(self._chunks)


class FakeStreamContext:
    """Simulates the context manager returned by messages.stream()."""

    def __init__(self, chunks: list[str]):
        self.text_stream = FakeTextStream(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _make_agent_with_mock(chunks: list[str] = None) -> tuple[ChatAgent, MagicMock]:
    """Create a ChatAgent with a mocked client that streams given chunks."""
    if chunks is None:
        chunks = ["Hello", " there", "!"]

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = FakeStreamContext(chunks)

    agent = ChatAgent(client=mock_client)
    return agent, mock_client


def test_default_config():
    """ChatAgent should use sensible defaults."""
    with patch("claude_agents.chat.agent.AnthropicBedrock"):
        agent = ChatAgent()
    assert agent.model_id == DEFAULT_MODEL_ID
    assert agent.max_tokens == DEFAULT_MAX_TOKENS
    assert agent.history == []


def test_aws_region_from_env():
    """ChatAgent should read AWS_REGION from environment."""
    with patch("claude_agents.chat.agent.AnthropicBedrock") as mock_cls:
        with patch.dict("os.environ", {"AWS_REGION": "eu-west-1"}):
            agent = ChatAgent()
    assert agent.aws_region == "eu-west-1"
    mock_cls.assert_called_once_with(aws_region="eu-west-1")


def test_aws_region_default():
    """ChatAgent should default to us-west-2 when AWS_REGION is not set."""
    with patch("claude_agents.chat.agent.AnthropicBedrock"):
        with patch.dict("os.environ", {}, clear=True):
            agent = ChatAgent()
    assert agent.aws_region == "us-west-2"


def test_custom_config():
    """ChatAgent should accept custom model_id and max_tokens."""
    mock_client = MagicMock()
    agent = ChatAgent(
        model_id="us.anthropic.claude-haiku-4-5-20251001",
        aws_region="ap-northeast-1",
        max_tokens=1024,
        client=mock_client,
    )
    assert agent.model_id == "us.anthropic.claude-haiku-4-5-20251001"
    assert agent.aws_region == "ap-northeast-1"
    assert agent.max_tokens == 1024


def test_chat_returns_full_text(capsys):
    """chat() should return the concatenated streamed text."""
    agent, _ = _make_agent_with_mock(["Hello", " world"])
    result = agent.chat("Hi")
    assert result == "Hello world"


def test_chat_streams_to_stdout(capsys):
    """chat() should print streamed tokens to stdout."""
    agent, _ = _make_agent_with_mock(["one", "two", "three"])
    agent.chat("test")
    captured = capsys.readouterr()
    assert "onetwothree" in captured.out


def test_chat_builds_history():
    """chat() should append user and assistant messages to history."""
    agent, _ = _make_agent_with_mock(["response"])
    agent.chat("hello")

    assert len(agent.history) == 2
    assert agent.history[0] == {"role": "user", "content": "hello"}
    assert agent.history[1] == {"role": "assistant", "content": "response"}


def test_chat_accumulates_history():
    """Multiple chat() calls should accumulate in history."""
    agent, mock_client = _make_agent_with_mock(["first reply"])
    agent.chat("first message")

    mock_client.messages.stream.return_value = FakeStreamContext(["second reply"])
    agent.chat("second message")

    assert len(agent.history) == 4
    assert agent.history[0]["content"] == "first message"
    assert agent.history[1]["content"] == "first reply"
    assert agent.history[2]["content"] == "second message"
    assert agent.history[3]["content"] == "second reply"


def test_chat_passes_history_to_api():
    """chat() should send the full conversation history to the API."""
    agent, mock_client = _make_agent_with_mock(["reply1"])
    agent.chat("msg1")

    mock_client.messages.stream.return_value = FakeStreamContext(["reply2"])
    agent.chat("msg2")

    # Second call should include all 3 messages (user1, assistant1, user2)
    second_call = mock_client.messages.stream.call_args_list[1]
    messages = second_call.kwargs["messages"]
    assert len(messages) == 3
    assert messages[0] == {"role": "user", "content": "msg1"}
    assert messages[1] == {"role": "assistant", "content": "reply1"}
    assert messages[2] == {"role": "user", "content": "msg2"}


def test_chat_passes_model_params():
    """chat() should pass model_id and max_tokens to the API."""
    agent, mock_client = _make_agent_with_mock(["ok"])
    agent.chat("test")

    mock_client.messages.stream.assert_called_once_with(
        model=DEFAULT_MODEL_ID,
        max_tokens=DEFAULT_MAX_TOKENS,
        messages=[{"role": "user", "content": "test"}],
    )


def test_three_turn_conversation_saves_memory():
    """Three chat() calls should save all 6 messages and pass full history to API."""
    agent, mock_client = _make_agent_with_mock(["reply1"])

    agent.chat("turn1")

    mock_client.messages.stream.return_value = FakeStreamContext(["reply2"])
    agent.chat("turn2")

    mock_client.messages.stream.return_value = FakeStreamContext(["reply3"])
    agent.chat("turn3")

    # All 6 messages (3 user + 3 assistant) are saved in order
    assert len(agent.history) == 6
    assert agent.history[0] == {"role": "user", "content": "turn1"}
    assert agent.history[1] == {"role": "assistant", "content": "reply1"}
    assert agent.history[2] == {"role": "user", "content": "turn2"}
    assert agent.history[3] == {"role": "assistant", "content": "reply2"}
    assert agent.history[4] == {"role": "user", "content": "turn3"}
    assert agent.history[5] == {"role": "assistant", "content": "reply3"}

    # Third API call received the full 5-message history (turn1, reply1, turn2, reply2, turn3)
    third_call = mock_client.messages.stream.call_args_list[2]
    messages = third_call.kwargs["messages"]
    assert len(messages) == 5
    assert messages[0] == {"role": "user", "content": "turn1"}
    assert messages[1] == {"role": "assistant", "content": "reply1"}
    assert messages[2] == {"role": "user", "content": "turn2"}
    assert messages[3] == {"role": "assistant", "content": "reply2"}
    assert messages[4] == {"role": "user", "content": "turn3"}


def test_reset_clears_history():
    """reset() should clear conversation history."""
    agent, _ = _make_agent_with_mock(["reply"])
    agent.chat("hello")
    assert len(agent.history) == 2

    agent.reset()
    assert agent.history == []


def test_default_memory_config():
    """ChatAgent should use sensible defaults for memory parameters."""
    with patch("claude_agents.chat.agent.AnthropicBedrock"):
        agent = ChatAgent()
    assert agent.max_context_tokens == 200_000
    assert agent.summary_threshold == 0.5
    assert agent.recent_messages_to_keep == 20


def test_custom_memory_config():
    """ChatAgent should accept custom memory parameters."""
    mock_client = MagicMock()
    agent = ChatAgent(
        max_context_tokens=100_000,
        summary_threshold=0.8,
        recent_messages_to_keep=10,
        client=mock_client,
    )
    assert agent.max_context_tokens == 100_000
    assert agent.summary_threshold == 0.8
    assert agent.recent_messages_to_keep == 10


def test_count_history_tokens():
    """_count_history_tokens should call client.messages.count_tokens and return the count."""
    agent, mock_client = _make_agent_with_mock()
    mock_client.messages.count_tokens.return_value = MagicMock(input_tokens=500)

    agent.history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    result = agent._count_history_tokens()

    assert result == 500
    mock_client.messages.count_tokens.assert_called_once_with(
        model=DEFAULT_MODEL_ID,
        messages=agent.history,
    )


def test_summarize_messages():
    """_summarize_messages should call Claude to produce a summary string."""
    agent, mock_client = _make_agent_with_mock()

    mock_response = MagicMock()
    mock_text_block = MagicMock()
    mock_text_block.text = "User discussed Python testing. Agent provided examples."
    mock_response.content = [mock_text_block]
    mock_client.messages.create.return_value = mock_response

    messages = [
        {"role": "user", "content": "Tell me about Python testing"},
        {"role": "assistant", "content": "Here are some examples of pytest..."},
    ]
    result = agent._summarize_messages(messages)

    assert result == "User discussed Python testing. Agent provided examples."
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == DEFAULT_MODEL_ID
    assert call_kwargs["max_tokens"] == 1024
    assert any("summarize" in s.lower() for s in [call_kwargs["system"]])
    assert call_kwargs["messages"][0]["role"] == "user"


def test_compact_history_triggers_when_over_threshold():
    """_maybe_compact_history should summarize old messages when over token threshold."""
    mock_client = MagicMock()
    mock_client.messages.stream.return_value = FakeStreamContext(["r"])
    agent = ChatAgent(
        max_context_tokens=1000,
        summary_threshold=0.5,
        recent_messages_to_keep=4,
        client=mock_client,
    )

    # Build history with 6 messages (3 turns) — more than recent_messages_to_keep (4)
    agent.history = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "msg2"},
        {"role": "assistant", "content": "reply2"},
        {"role": "user", "content": "msg3"},
        {"role": "assistant", "content": "reply3"},
    ]

    # Token count above 50% of 1000
    mock_client.messages.count_tokens.return_value = MagicMock(input_tokens=600)

    # Summarization returns a summary
    mock_response = MagicMock()
    mock_text_block = MagicMock()
    mock_text_block.text = "Summary of earlier conversation."
    mock_response.content = [mock_text_block]
    mock_client.messages.create.return_value = mock_response

    agent._maybe_compact_history()

    # History should now be: summary_user, summary_assistant, msg2, reply2, msg3, reply3
    # Old messages (msg1, reply1) were summarized; last 4 messages kept verbatim
    assert len(agent.history) == 6
    assert "[Conversation summary]" in agent.history[0]["content"]
    assert "Summary of earlier conversation." in agent.history[0]["content"]
    assert agent.history[0]["role"] == "user"
    assert agent.history[1]["role"] == "assistant"
    assert agent.history[1]["content"] == "Understood, I'll keep this context in mind."
    # Last 4 messages preserved
    assert agent.history[2] == {"role": "user", "content": "msg2"}
    assert agent.history[3] == {"role": "assistant", "content": "reply2"}
    assert agent.history[4] == {"role": "user", "content": "msg3"}
    assert agent.history[5] == {"role": "assistant", "content": "reply3"}


def test_compact_history_skips_when_under_threshold():
    """_maybe_compact_history should not compact when tokens are below threshold."""
    mock_client = MagicMock()
    mock_client.messages.stream.return_value = FakeStreamContext(["r"])
    agent = ChatAgent(
        max_context_tokens=1000,
        summary_threshold=0.5,
        recent_messages_to_keep=4,
        client=mock_client,
    )

    agent.history = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "msg2"},
        {"role": "assistant", "content": "reply2"},
        {"role": "user", "content": "msg3"},
        {"role": "assistant", "content": "reply3"},
    ]

    # Token count below 50% of 1000
    mock_client.messages.count_tokens.return_value = MagicMock(input_tokens=400)

    agent._maybe_compact_history()

    # History unchanged
    assert len(agent.history) == 6
    assert agent.history[0] == {"role": "user", "content": "msg1"}
    mock_client.messages.create.assert_not_called()


def test_chat_calls_compact_before_api_call():
    """chat() should call _maybe_compact_history before streaming."""
    agent, mock_client = _make_agent_with_mock(["response"])

    call_order = []
    original_compact = agent._maybe_compact_history

    def tracking_compact():
        call_order.append("compact")
        original_compact()

    def tracking_stream(**kwargs):
        call_order.append("stream")
        return FakeStreamContext(["response"])

    agent._maybe_compact_history = tracking_compact
    mock_client.messages.stream.side_effect = tracking_stream
    mock_client.messages.count_tokens.return_value = MagicMock(input_tokens=100)

    agent.chat("hello")

    assert call_order == ["compact", "stream"]


def test_compact_history_skips_when_too_few_messages():
    """_maybe_compact_history should not compact when history <= recent_messages_to_keep."""
    mock_client = MagicMock()
    mock_client.messages.stream.return_value = FakeStreamContext(["r"])
    agent = ChatAgent(
        max_context_tokens=1000,
        summary_threshold=0.5,
        recent_messages_to_keep=20,
        client=mock_client,
    )

    # Only 4 messages — well under the 20 threshold
    agent.history = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "msg2"},
        {"role": "assistant", "content": "reply2"},
    ]

    # Even with high token count, should not compact
    mock_client.messages.count_tokens.return_value = MagicMock(input_tokens=600)

    agent._maybe_compact_history()

    # History unchanged — no compaction when <= recent_messages_to_keep
    assert len(agent.history) == 4
    mock_client.messages.create.assert_not_called()
