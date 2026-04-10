# Hybrid Memory for ChatAgent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic conversation compaction to `ChatAgent` so it can handle arbitrarily long conversations without exceeding the model's context window.

**Architecture:** Inline in `ChatAgent`. Before each API call, count tokens via `client.messages.count_tokens()`. When usage exceeds 50% of max context, split history into old + recent (last 20 messages), summarize old via a separate Claude call, and replace history with `[summary_pair] + recent`.

**Tech Stack:** Python, `anthropic` SDK (`AnthropicBedrock`), pytest

---

### Task 1: Add new constructor parameters and update existing tests

**Files:**
- Modify: `claude_agents/chat/agent.py:9-21`
- Modify: `claude_agents/tests/unit/test_chat_agent.py:49-87`

- [ ] **Step 1: Add new parameters to `__init__`**

In `claude_agents/chat/agent.py`, update the constructor:

```python
class ChatAgent:
    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        aws_region: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_context_tokens: int = 200_000,
        summary_threshold: float = 0.5,
        recent_messages_to_keep: int = 20,
        client: AnthropicBedrock | None = None,
    ):
        self.model_id = model_id
        self.aws_region = aws_region or os.environ.get("AWS_REGION", "us-west-2")
        self.max_tokens = max_tokens
        self.max_context_tokens = max_context_tokens
        self.summary_threshold = summary_threshold
        self.recent_messages_to_keep = recent_messages_to_keep
        self.history: list[dict] = []
        self._client = client or AnthropicBedrock(aws_region=self.aws_region)
```

- [ ] **Step 2: Run existing tests to ensure nothing breaks**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_chat_agent.py -v`
Expected: All 12 existing tests PASS (no behavior changed, only new optional parameters added).

- [ ] **Step 3: Write test for new constructor parameters**

Add to `claude_agents/tests/unit/test_chat_agent.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify new tests pass**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_chat_agent.py -v`
Expected: All 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
sl add claude_agents/chat/agent.py claude_agents/tests/unit/test_chat_agent.py
sl commit -m "feat(chat): add memory config parameters to ChatAgent"
```

---

### Task 2: Implement `_count_history_tokens` method (TDD)

**Files:**
- Modify: `claude_agents/chat/agent.py`
- Modify: `claude_agents/tests/unit/test_chat_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `claude_agents/tests/unit/test_chat_agent.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_chat_agent.py::test_count_history_tokens -v`
Expected: FAIL with `AttributeError: 'ChatAgent' object has no attribute '_count_history_tokens'`

- [ ] **Step 3: Write minimal implementation**

Add to `ChatAgent` in `claude_agents/chat/agent.py`:

```python
def _count_history_tokens(self) -> int:
    """Count tokens in current history via the API."""
    result = self._client.messages.count_tokens(
        model=self.model_id,
        messages=self.history,
    )
    return result.input_tokens
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_chat_agent.py::test_count_history_tokens -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
sl add claude_agents/chat/agent.py claude_agents/tests/unit/test_chat_agent.py
sl commit -m "feat(chat): add _count_history_tokens method"
```

---

### Task 3: Implement `_summarize_messages` method (TDD)

**Files:**
- Modify: `claude_agents/chat/agent.py`
- Modify: `claude_agents/tests/unit/test_chat_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `claude_agents/tests/unit/test_chat_agent.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_chat_agent.py::test_summarize_messages -v`
Expected: FAIL with `AttributeError: 'ChatAgent' object has no attribute '_summarize_messages'`

- [ ] **Step 3: Write minimal implementation**

Add constant at module level in `claude_agents/chat/agent.py`:

```python
SUMMARY_SYSTEM_PROMPT = (
    "Summarize the following conversation concisely, preserving key facts, "
    "decisions, user preferences, and important context. Be thorough but brief."
)
```

Add method to `ChatAgent`:

```python
def _summarize_messages(self, messages: list[dict]) -> str:
    """Summarize a list of messages into a concise text."""
    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )
    response = self._client.messages.create(
        model=self.model_id,
        max_tokens=1024,
        system=SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": conversation_text}],
    )
    return response.content[0].text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_chat_agent.py::test_summarize_messages -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
sl add claude_agents/chat/agent.py claude_agents/tests/unit/test_chat_agent.py
sl commit -m "feat(chat): add _summarize_messages method"
```

---

### Task 4: Implement `_maybe_compact_history` method (TDD)

**Files:**
- Modify: `claude_agents/chat/agent.py`
- Modify: `claude_agents/tests/unit/test_chat_agent.py`

- [ ] **Step 1: Write the failing test — compaction triggers**

Add to `claude_agents/tests/unit/test_chat_agent.py`:

```python
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
```

- [ ] **Step 2: Write the failing test — skips when under threshold**

```python
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
```

- [ ] **Step 3: Write the failing test — skips when too few messages**

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_chat_agent.py -k "compact" -v`
Expected: FAIL — 3 failures with `AttributeError: 'ChatAgent' object has no attribute '_maybe_compact_history'`

- [ ] **Step 5: Write the implementation**

Add to `ChatAgent` in `claude_agents/chat/agent.py`:

```python
def _maybe_compact_history(self) -> None:
    """Compact history if token count exceeds the threshold."""
    if len(self.history) <= self.recent_messages_to_keep:
        return

    token_count = self._count_history_tokens()
    if token_count <= self.max_context_tokens * self.summary_threshold:
        return

    # Split: old messages to summarize, recent to keep verbatim
    old_messages = self.history[: -self.recent_messages_to_keep]
    recent_messages = self.history[-self.recent_messages_to_keep :]

    summary = self._summarize_messages(old_messages)

    self.history = [
        {"role": "user", "content": f"[Conversation summary]: {summary}"},
        {"role": "assistant", "content": "Understood, I'll keep this context in mind."},
    ] + recent_messages
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_chat_agent.py -k "compact" -v`
Expected: All 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
sl add claude_agents/chat/agent.py claude_agents/tests/unit/test_chat_agent.py
sl commit -m "feat(chat): add _maybe_compact_history method"
```

---

### Task 5: Integrate compaction into `chat()` method (TDD)

**Files:**
- Modify: `claude_agents/chat/agent.py`
- Modify: `claude_agents/tests/unit/test_chat_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `claude_agents/tests/unit/test_chat_agent.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_chat_agent.py::test_chat_calls_compact_before_api_call -v`
Expected: FAIL — `_maybe_compact_history` is not called by `chat()` yet.

- [ ] **Step 3: Update `chat()` to call `_maybe_compact_history`**

Update `chat()` in `claude_agents/chat/agent.py`:

```python
def chat(self, user_message: str) -> str:
    self.history.append({"role": "user", "content": user_message})

    self._maybe_compact_history()

    full_text = ""
    with self._client.messages.stream(
        model=self.model_id,
        max_tokens=self.max_tokens,
        messages=list(self.history),
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            full_text += text
    print()

    self.history.append({"role": "assistant", "content": full_text})
    return full_text
```

- [ ] **Step 4: Run all tests to verify everything passes**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_chat_agent.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
sl add claude_agents/chat/agent.py claude_agents/tests/unit/test_chat_agent.py
sl commit -m "feat(chat): integrate compaction into chat() method"
```

---

### Task 6: Add integration tests

**Files:**
- Modify: `claude_agents/tests/integration/test_chat_agent_integration.py`

- [ ] **Step 1: Write integration test for compaction**

Add to `claude_agents/tests/integration/test_chat_agent_integration.py`:

```python
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_compaction_preserves_context(capsys):
    """After compaction, the agent should still recall facts from summarized messages."""
    agent = ChatAgent(
        max_context_tokens=8000,
        summary_threshold=0.5,
        recent_messages_to_keep=4,
    )

    # Plant a fact early in the conversation
    agent.chat("My favorite programming language is Rust. Just say OK.")

    # Generate enough conversation to trigger compaction with low thresholds
    for i in range(5):
        agent.chat(f"Tell me a one-sentence fun fact about the number {i}.")

    # Check if the early fact survived through compaction
    response = agent.chat(
        "What is my favorite programming language? Reply with just the language name."
    )

    assert "rust" in response.lower()
```

- [ ] **Step 2: Run the integration test**

Run: `.venv/bin/python -m pytest claude_agents/tests/integration/test_chat_agent_integration.py::test_compaction_preserves_context -v --timeout=180`
Expected: PASS — the agent recalls "Rust" even after compaction.

- [ ] **Step 3: Commit**

```bash
sl add claude_agents/tests/integration/test_chat_agent_integration.py
sl commit -m "test(chat): add integration test for hybrid memory compaction"
```

---

### Task 7: Run full test suite and final verification

**Files:** None (verification only)

- [ ] **Step 1: Run all unit tests**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_chat_agent.py -v`
Expected: All tests PASS.

- [ ] **Step 2: Run all unit tests for the project**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/ -v`
Expected: All tests PASS (including k8s agent tests — no regressions).
