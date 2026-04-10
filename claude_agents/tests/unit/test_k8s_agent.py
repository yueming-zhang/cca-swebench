"""Unit tests for K8s agent.

All tests use mocks — no LLM calls or real kubectl required.
"""

from unittest.mock import MagicMock, patch

import pytest

from claude_agents.k8s.agent import (
    BLOCKED_SUBCOMMANDS,
    DANGEROUS_PATTERN,
    TOOLS,
    _estimate_tokens,
    execute_tool,
    run_agent,
    validate_input,
)


# ---------------------------------------------------------------------------
# validate_input
# ---------------------------------------------------------------------------


class TestValidateInput:
    def test_clean_inputs_accepted(self):
        for value in ["pods", "my-pod-name", "default", "kube-system", "nginx-7b4f9"]:
            validate_input(value)  # should not raise

    @pytest.mark.parametrize(
        "bad_input",
        [
            "pods; rm -rf /",
            "pods | grep secret",
            "pods && cat /etc/shadow",
            "pods `whoami`",
            "pods $(whoami)",
        ],
    )
    def test_shell_metacharacters_rejected(self, bad_input):
        with pytest.raises(ValueError, match="shell metacharacters"):
            validate_input(bad_input)

    def test_dangerous_pattern_covers_all_required(self):
        """Ensure the regex matches every listed metacharacter."""
        for char_seq in [";", "|", "&&", "`", "$("]:
            assert DANGEROUS_PATTERN.search(char_seq), f"Pattern missed: {char_seq!r}"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


class TestToolDefinitions:
    def test_exactly_one_tool(self):
        assert len(TOOLS) == 1

    def test_tool_name(self):
        assert TOOLS[0]["name"] == "kubectl"

    def test_tool_has_required_fields(self):
        tool = TOOLS[0]
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"

    def test_subcommand_is_required(self):
        assert "subcommand" in TOOLS[0]["input_schema"]["required"]

    def test_args_property_exists(self):
        props = TOOLS[0]["input_schema"]["properties"]
        assert "args" in props
        assert props["args"]["type"] == "array"


# ---------------------------------------------------------------------------
# execute_tool
# ---------------------------------------------------------------------------


class TestExecuteTool:
    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_kubectl_get_pods(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="NAME  READY\npod1  1/1\n", stderr=""
        )
        result = execute_tool("kubectl", {
            "subcommand": "get",
            "args": ["pods", "-n", "default"],
        })
        mock_run.assert_called_once_with(
            ["kubectl", "get", "pods", "-n", "default"],
            capture_output=True, text=True, timeout=30,
        )
        assert "pod1" in result

    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_kubectl_describe(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Name: my-pod\nStatus: Running\n", stderr=""
        )
        result = execute_tool("kubectl", {
            "subcommand": "describe",
            "args": ["pod", "my-pod", "-n", "default"],
        })
        mock_run.assert_called_once_with(
            ["kubectl", "describe", "pod", "my-pod", "-n", "default"],
            capture_output=True, text=True, timeout=30,
        )
        assert "my-pod" in result

    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_kubectl_logs(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="log line 1\nlog line 2\n", stderr=""
        )
        result = execute_tool("kubectl", {
            "subcommand": "logs",
            "args": ["my-pod", "-n", "default", "--tail", "100"],
        })
        mock_run.assert_called_once_with(
            ["kubectl", "logs", "my-pod", "-n", "default", "--tail", "100"],
            capture_output=True, text=True, timeout=30,
        )
        assert "log line" in result

    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_kubectl_top_nodes(self, mock_run):
        """Verify a previously-unsupported subcommand now works."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="NAME   CPU%\nnode1  12%\n", stderr=""
        )
        result = execute_tool("kubectl", {"subcommand": "top", "args": ["nodes"]})
        mock_run.assert_called_once_with(
            ["kubectl", "top", "nodes"],
            capture_output=True, text=True, timeout=30,
        )
        assert "node1" in result

    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_args_defaults_to_empty(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="cluster info", stderr=""
        )
        execute_tool("kubectl", {"subcommand": "cluster-info"})
        mock_run.assert_called_once_with(
            ["kubectl", "cluster-info"],
            capture_output=True, text=True, timeout=30,
        )

    def test_unknown_tool_rejected(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            execute_tool("kubectl_delete", {"subcommand": "get"})

    def test_blocked_subcommand_rejected(self):
        with pytest.raises(ValueError, match="Blocked subcommand"):
            execute_tool("kubectl", {"subcommand": "delete", "args": ["pod", "x"]})

    def test_blocked_subcommands_set(self):
        assert "delete" in BLOCKED_SUBCOMMANDS

    def test_subcommand_shell_injection_rejected(self):
        with pytest.raises(ValueError, match="shell metacharacters"):
            execute_tool("kubectl", {"subcommand": "get; rm -rf /"})

    def test_args_shell_injection_rejected(self):
        with pytest.raises(ValueError, match="shell metacharacters"):
            execute_tool("kubectl", {
                "subcommand": "get",
                "args": ["pods | cat /etc/passwd"],
            })

    def test_args_must_be_strings(self):
        with pytest.raises(ValueError, match="expected string"):
            execute_tool("kubectl", {
                "subcommand": "get",
                "args": ["pods", 123],
            })

    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_nonzero_exit_returns_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error: resource not found"
        )
        result = execute_tool("kubectl", {"subcommand": "get", "args": ["pods"]})
        assert result.startswith("Error:")
        assert "resource not found" in result


# ---------------------------------------------------------------------------
# run_agent (agentic loop)
# ---------------------------------------------------------------------------


class TestRunAgent:
    def _make_text_block(self, text):
        block = MagicMock()
        block.type = "text"
        block.text = text
        return block

    def _make_tool_use_block(self, name, tool_input, tool_id="tool_123"):
        block = MagicMock()
        block.type = "tool_use"
        block.name = name
        block.input = tool_input
        block.id = tool_id
        return block

    def test_simple_text_response(self):
        """Agent returns text when model doesn't use tools."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [self._make_text_block("No pods found.")]
        mock_client.messages.create.return_value = mock_response

        result = run_agent("list pods", client=mock_client)
        assert result == "No pods found."
        mock_client.messages.create.assert_called_once()

    @patch("claude_agents.k8s.agent.execute_tool")
    def test_tool_use_loop(self, mock_execute_tool):
        """Agent processes tool_use, feeds result back, returns final text."""
        mock_execute_tool.return_value = "NAME  READY\npod1  1/1\n"

        mock_client = MagicMock()

        # First response: tool_use
        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.content = [
            self._make_tool_use_block(
                "kubectl",
                {"subcommand": "get", "args": ["pods", "-n", "default"]},
            )
        ]

        # Second response: final text
        final_response = MagicMock()
        final_response.stop_reason = "end_turn"
        final_response.content = [self._make_text_block("Found 1 pod: pod1")]

        mock_client.messages.create.side_effect = [tool_response, final_response]

        result = run_agent("list pods", client=mock_client)
        assert result == "Found 1 pod: pod1"
        assert mock_client.messages.create.call_count == 2
        mock_execute_tool.assert_called_once_with(
            "kubectl",
            {"subcommand": "get", "args": ["pods", "-n", "default"]},
        )

    @patch("claude_agents.k8s.agent.execute_tool")
    def test_tool_error_fed_back(self, mock_execute_tool):
        """When execute_tool raises, error is sent back as tool_result."""
        mock_execute_tool.side_effect = ValueError("Invalid input: contains shell metacharacters: 'bad;input'")

        mock_client = MagicMock()

        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.content = [
            self._make_tool_use_block(
                "kubectl",
                {"subcommand": "get", "args": ["bad;input"]},
            )
        ]

        final_response = MagicMock()
        final_response.stop_reason = "end_turn"
        final_response.content = [self._make_text_block("I couldn't run that command.")]

        mock_client.messages.create.side_effect = [tool_response, final_response]

        result = run_agent("get bad;input", client=mock_client)
        assert "couldn't" in result
        assert mock_client.messages.create.call_count == 2

    @patch("claude_agents.k8s.agent.execute_tool")
    def test_multiple_tool_calls_in_one_response(self, mock_execute_tool):
        """Agent handles multiple tool_use blocks in a single response."""
        mock_execute_tool.side_effect = ["pods output", "services output"]

        mock_client = MagicMock()

        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.content = [
            self._make_tool_use_block(
                "kubectl",
                {"subcommand": "get", "args": ["pods"]},
                "t1",
            ),
            self._make_tool_use_block(
                "kubectl",
                {"subcommand": "get", "args": ["services"]},
                "t2",
            ),
        ]

        final_response = MagicMock()
        final_response.stop_reason = "end_turn"
        final_response.content = [self._make_text_block("Found pods and services.")]

        mock_client.messages.create.side_effect = [tool_response, final_response]

        result = run_agent("show everything", client=mock_client)
        assert result == "Found pods and services."
        assert mock_execute_tool.call_count == 2

    def test_messages_include_system_prompt_and_tools(self):
        """Verify the API call includes system prompt and tool definitions."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [self._make_text_block("ok")]
        mock_client.messages.create.return_value = mock_response

        run_agent("hello", client=mock_client)

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] is not None
        assert call_kwargs.kwargs["tools"] is not None
        assert len(call_kwargs.kwargs["tools"]) == 1


# ---------------------------------------------------------------------------
# _estimate_tokens
# ---------------------------------------------------------------------------


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
