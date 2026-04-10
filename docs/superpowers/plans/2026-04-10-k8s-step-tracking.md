# K8s Agent Step Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add step tracking to `run_agent()` so every LLM call, tool use, and result is captured in a structured list for model evaluation.

**Architecture:** `run_agent()` builds a `steps: list[dict]` internally, appending a step dict at each event (LLM request, tool use, tool result/error, final response). Returns `tuple[str, list[dict]]` instead of `str`. A helper `_estimate_tokens(messages)` computes context size.

**Tech Stack:** Python, Anthropic Bedrock SDK, `datetime` stdlib module.

---

## File Structure

- **Modify:** `claude_agents/k8s/agent.py` — add step tracking to `run_agent()`, add `_estimate_tokens()` helper, update `main()` to unpack tuple
- **Modify:** `claude_agents/tests/unit/test_k8s_agent.py` — update existing tests, add new step tracking tests
- **Modify:** `claude_agents/tests/integration/test_k8s_agent_integration.py` — update existing tests, add step verification

---

### Task 1: Add `_estimate_tokens` helper and step tracking to `run_agent()`

**Files:**
- Modify: `claude_agents/k8s/agent.py:1-168`
- Test: `claude_agents/tests/unit/test_k8s_agent.py`

- [ ] **Step 1: Write failing test for `_estimate_tokens`**

In `claude_agents/tests/unit/test_k8s_agent.py`, add:

```python
from claude_agents.k8s.agent import _estimate_tokens


class TestEstimateTokens:
    def test_empty_messages(self):
        assert _estimate_tokens([]) == 0

    def test_simple_messages(self):
        messages = [
            {"role": "user", "content": "hello world"},  # 11 chars -> 2 tokens
        ]
        assert _estimate_tokens(messages) == 11 // 4

    def test_multiple_messages(self):
        messages = [
            {"role": "user", "content": "a" * 100},
            {"role": "assistant", "content": "b" * 200},
        ]
        assert _estimate_tokens(messages) == 300 // 4
```

Also update the import at the top of the file to include `_estimate_tokens`:

```python
from claude_agents.k8s.agent import (
    BLOCKED_SUBCOMMANDS,
    DANGEROUS_PATTERN,
    TOOLS,
    _estimate_tokens,
    execute_tool,
    run_agent,
    validate_input,
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_k8s_agent.py::TestEstimateTokens -v`
Expected: FAIL with `ImportError` — `_estimate_tokens` does not exist yet.

- [ ] **Step 3: Implement `_estimate_tokens`**

In `claude_agents/k8s/agent.py`, add after the `import sys` line:

```python
from datetime import datetime, timezone
```

Then add after the `execute_tool` function (before `create_client`):

```python
def _estimate_tokens(messages: list[dict]) -> int:
    """Estimate token count using ~4 chars per token heuristic."""
    total_chars = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_chars += len(str(block))
                else:
                    total_chars += len(str(block))
    return total_chars // 4
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_k8s_agent.py::TestEstimateTokens -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
sl add claude_agents/k8s/agent.py claude_agents/tests/unit/test_k8s_agent.py
sl commit -m "feat(k8s): add _estimate_tokens helper"
```

---

### Task 2: Add step tracking to `run_agent()` return type

**Files:**
- Modify: `claude_agents/k8s/agent.py:99-143`
- Test: `claude_agents/tests/unit/test_k8s_agent.py`

- [ ] **Step 1: Write failing test for step tracking on simple text response**

In `claude_agents/tests/unit/test_k8s_agent.py`, add to `TestRunAgent`:

```python
    def test_simple_response_returns_steps(self):
        """run_agent returns (text, steps) tuple with llm_request and llm_response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [self._make_text_block("No pods found.")]
        mock_client.messages.create.return_value = mock_response

        text, steps = run_agent("list pods", client=mock_client)
        assert text == "No pods found."
        assert len(steps) == 2
        assert steps[0]["type"] == "llm_request"
        assert steps[0]["message_count"] == 1
        assert "estimated_tokens" in steps[0]
        assert "timestamp" in steps[0]
        assert steps[1]["type"] == "llm_response"
        assert steps[1]["text"] == "No pods found."
        assert "timestamp" in steps[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_k8s_agent.py::TestRunAgent::test_simple_response_returns_steps -v`
Expected: FAIL — `run_agent` returns `str`, not a tuple.

- [ ] **Step 3: Implement step tracking in `run_agent()`**

Replace the entire `run_agent` function in `claude_agents/k8s/agent.py` with:

```python
def run_agent(user_message: str, client: AnthropicBedrock | None = None) -> tuple[str, list[dict]]:
    """Run the K8s agent with a single user message.

    Returns a tuple of (final_text, steps) where steps is a list of dicts
    tracking each event in the agent loop for evaluation.
    """
    if client is None:
        client = create_client()

    messages = [{"role": "user", "content": user_message}]
    steps: list[dict] = []

    steps.append({
        "type": "llm_request",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_count": len(messages),
        "estimated_tokens": _estimate_tokens(messages),
    })

    response = client.messages.create(
        model=MODEL_ID,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
    )

    while response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                subcommand = block.input.get("subcommand", "")
                args = block.input.get("args", [])

                steps.append({
                    "type": "tool_use",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "subcommand": subcommand,
                    "args": args,
                })

                try:
                    result = execute_tool(block.name, block.input)
                    steps.append({
                        "type": "tool_result",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "subcommand": subcommand,
                        "args": args,
                        "output": result,
                    })
                except (ValueError, subprocess.TimeoutExpired) as e:
                    result = f"Error: {e}"
                    steps.append({
                        "type": "tool_error",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "subcommand": subcommand,
                        "args": args,
                        "error": str(e),
                    })

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        steps.append({
            "type": "llm_request",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_count": len(messages),
            "estimated_tokens": _estimate_tokens(messages),
        })

        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

    final_text = "\n".join(
        block.text for block in response.content if hasattr(block, "text")
    )

    steps.append({
        "type": "llm_response",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": final_text,
    })

    return final_text, steps
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_k8s_agent.py::TestRunAgent::test_simple_response_returns_steps -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
sl commit -m "feat(k8s): add step tracking to run_agent return type"
```

---

### Task 3: Update existing unit tests to unpack new return type

**Files:**
- Modify: `claude_agents/tests/unit/test_k8s_agent.py:197-327`

- [ ] **Step 1: Update `test_simple_text_response`**

Change:
```python
        result = run_agent("list pods", client=mock_client)
        assert result == "No pods found."
```
To:
```python
        result, _steps = run_agent("list pods", client=mock_client)
        assert result == "No pods found."
```

- [ ] **Step 2: Update `test_tool_use_loop`**

Change:
```python
        result = run_agent("list pods", client=mock_client)
        assert result == "Found 1 pod: pod1"
```
To:
```python
        result, _steps = run_agent("list pods", client=mock_client)
        assert result == "Found 1 pod: pod1"
```

- [ ] **Step 3: Update `test_tool_error_fed_back`**

Change:
```python
        result = run_agent("get bad;input", client=mock_client)
        assert "couldn't" in result
```
To:
```python
        result, _steps = run_agent("get bad;input", client=mock_client)
        assert "couldn't" in result
```

- [ ] **Step 4: Update `test_multiple_tool_calls_in_one_response`**

Change:
```python
        result = run_agent("show everything", client=mock_client)
        assert result == "Found pods and services."
```
To:
```python
        result, _steps = run_agent("show everything", client=mock_client)
        assert result == "Found pods and services."
```

- [ ] **Step 5: Update `test_messages_include_system_prompt_and_tools`**

No change needed — this test doesn't use the return value of `run_agent`.

- [ ] **Step 6: Run all existing tests to verify they still pass**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_k8s_agent.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
sl commit -m "test(k8s): update existing unit tests for new run_agent return type"
```

---

### Task 4: Add new step tracking unit tests

**Files:**
- Modify: `claude_agents/tests/unit/test_k8s_agent.py`

- [ ] **Step 1: Write test for tool-use loop step sequence**

Add to `TestRunAgent`:

```python
    @patch("claude_agents.k8s.agent.execute_tool")
    def test_tool_use_loop_step_sequence(self, mock_execute_tool):
        """Steps follow correct sequence: llm_request, tool_use, tool_result, llm_request, llm_response."""
        mock_execute_tool.return_value = "NAME  READY\npod1  1/1\n"

        mock_client = MagicMock()

        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.content = [
            self._make_tool_use_block(
                "kubectl",
                {"subcommand": "get", "args": ["pods"]},
            )
        ]

        final_response = MagicMock()
        final_response.stop_reason = "end_turn"
        final_response.content = [self._make_text_block("Found pod1")]

        mock_client.messages.create.side_effect = [tool_response, final_response]

        _text, steps = run_agent("list pods", client=mock_client)

        step_types = [s["type"] for s in steps]
        assert step_types == [
            "llm_request",
            "tool_use",
            "tool_result",
            "llm_request",
            "llm_response",
        ]
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_k8s_agent.py::TestRunAgent::test_tool_use_loop_step_sequence -v`
Expected: PASS

- [ ] **Step 3: Write test for context growth across LLM requests**

Add to `TestRunAgent`:

```python
    @patch("claude_agents.k8s.agent.execute_tool")
    def test_llm_request_context_grows(self, mock_execute_tool):
        """message_count and estimated_tokens grow between successive llm_request steps."""
        mock_execute_tool.return_value = "pod1"

        mock_client = MagicMock()

        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.content = [
            self._make_tool_use_block(
                "kubectl",
                {"subcommand": "get", "args": ["pods"]},
            )
        ]

        final_response = MagicMock()
        final_response.stop_reason = "end_turn"
        final_response.content = [self._make_text_block("done")]

        mock_client.messages.create.side_effect = [tool_response, final_response]

        _text, steps = run_agent("list pods", client=mock_client)

        llm_requests = [s for s in steps if s["type"] == "llm_request"]
        assert len(llm_requests) == 2
        assert llm_requests[1]["message_count"] > llm_requests[0]["message_count"]
        assert llm_requests[1]["estimated_tokens"] >= llm_requests[0]["estimated_tokens"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_k8s_agent.py::TestRunAgent::test_llm_request_context_grows -v`
Expected: PASS

- [ ] **Step 5: Write test for tool_error step**

Add to `TestRunAgent`:

```python
    @patch("claude_agents.k8s.agent.execute_tool")
    def test_tool_error_step_recorded(self, mock_execute_tool):
        """tool_error step is recorded when execute_tool raises."""
        mock_execute_tool.side_effect = ValueError("Blocked subcommand: 'delete' is not allowed")

        mock_client = MagicMock()

        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.content = [
            self._make_tool_use_block(
                "kubectl",
                {"subcommand": "delete", "args": ["pod", "x"]},
            )
        ]

        final_response = MagicMock()
        final_response.stop_reason = "end_turn"
        final_response.content = [self._make_text_block("Cannot delete.")]

        mock_client.messages.create.side_effect = [tool_response, final_response]

        _text, steps = run_agent("delete pod x", client=mock_client)

        error_steps = [s for s in steps if s["type"] == "tool_error"]
        assert len(error_steps) == 1
        assert error_steps[0]["subcommand"] == "delete"
        assert error_steps[0]["args"] == ["pod", "x"]
        assert "Blocked subcommand" in error_steps[0]["error"]
```

- [ ] **Step 6: Run all tests**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_k8s_agent.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
sl commit -m "test(k8s): add step tracking unit tests"
```

---

### Task 5: Update `main()` REPL and integration tests

**Files:**
- Modify: `claude_agents/k8s/agent.py:146-168` (the `main()` function)
- Modify: `claude_agents/tests/integration/test_k8s_agent_integration.py`

- [ ] **Step 1: Update `main()` to unpack the new return type**

In `claude_agents/k8s/agent.py`, change in the `main()` function:

```python
            response = run_agent(user_input, client=client)
            print(f"\nAssistant: {response}")
```

To:

```python
            response, _steps = run_agent(user_input, client=client)
            print(f"\nAssistant: {response}")
```

- [ ] **Step 2: Update integration test `test_agent_calls_kubectl_get_for_pod_question`**

In `claude_agents/tests/integration/test_k8s_agent_integration.py`, change:

```python
        result = run_agent(
            "List all pods in the default namespace", client=client
        )
        # Final response should be non-empty text
        assert len(result) > 0
```

To:

```python
        result, steps = run_agent(
            "List all pods in the default namespace", client=client
        )
        assert len(result) > 0
        assert len(steps) >= 2  # at least llm_request + llm_response
        assert steps[0]["type"] == "llm_request"
        assert steps[-1]["type"] == "llm_response"
```

- [ ] **Step 3: Update integration test `test_agent_describes_node`**

Change:

```python
        result = run_agent(
            "Describe any one node in the cluster", client=client
        )
        assert len(result) > 0
```

To:

```python
        result, steps = run_agent(
            "Describe any one node in the cluster", client=client
        )
        assert len(result) > 0
        assert any(s["type"] == "tool_use" for s in steps)
        assert any(s["type"] == "tool_result" for s in steps)
```

- [ ] **Step 4: Run unit tests to verify main() change doesn't break anything**

Run: `.venv/bin/python -m pytest claude_agents/tests/unit/test_k8s_agent.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
sl commit -m "feat(k8s): update main() and integration tests for step tracking"
```
