"""Unit tests for K8s agent.

All tests use mocks — no LLM calls or real kubectl required.
"""

from unittest.mock import MagicMock, patch

import pytest

from claude_agents.k8s.agent import (
    DANGEROUS_PATTERN,
    TOOLS,
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
    def test_exactly_three_tools(self):
        assert len(TOOLS) == 3

    def test_tool_names(self):
        names = {t["name"] for t in TOOLS}
        assert names == {"kubectl_get", "kubectl_describe", "kubectl_logs"}

    def test_all_tools_have_required_fields(self):
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"


# ---------------------------------------------------------------------------
# execute_tool
# ---------------------------------------------------------------------------


class TestExecuteTool:
    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_kubectl_get_default_namespace(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="NAME  READY\npod1  1/1\n", stderr=""
        )
        result = execute_tool("kubectl_get", {"resource": "pods"})
        mock_run.assert_called_once_with(
            ["kubectl", "get", "pods", "-n", "default"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "pod1" in result

    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_kubectl_get_custom_namespace(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")
        execute_tool("kubectl_get", {"resource": "services", "namespace": "kube-system"})
        mock_run.assert_called_once_with(
            ["kubectl", "get", "services", "-n", "kube-system"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_kubectl_describe(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Name: my-pod\nStatus: Running\n", stderr=""
        )
        result = execute_tool(
            "kubectl_describe", {"resource": "pod", "name": "my-pod"}
        )
        mock_run.assert_called_once_with(
            ["kubectl", "describe", "pod", "my-pod", "-n", "default"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "my-pod" in result

    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_kubectl_describe_custom_namespace(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="info", stderr="")
        execute_tool(
            "kubectl_describe",
            {"resource": "service", "name": "api-svc", "namespace": "prod"},
        )
        mock_run.assert_called_once_with(
            ["kubectl", "describe", "service", "api-svc", "-n", "prod"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_kubectl_logs_defaults(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="log line 1\nlog line 2\n", stderr=""
        )
        result = execute_tool("kubectl_logs", {"pod": "my-pod"})
        mock_run.assert_called_once_with(
            ["kubectl", "logs", "my-pod", "-n", "default", "--tail", "100"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "log line" in result

    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_kubectl_logs_custom_tail(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")
        execute_tool("kubectl_logs", {"pod": "web", "namespace": "staging", "tail": 50})
        mock_run.assert_called_once_with(
            ["kubectl", "logs", "web", "-n", "staging", "--tail", "50"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_unknown_tool_rejected(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            execute_tool("kubectl_delete", {"resource": "pod", "name": "x"})

    def test_get_rejects_shell_injection(self):
        with pytest.raises(ValueError, match="shell metacharacters"):
            execute_tool("kubectl_get", {"resource": "pods; rm -rf /"})

    def test_describe_rejects_shell_injection(self):
        with pytest.raises(ValueError, match="shell metacharacters"):
            execute_tool(
                "kubectl_describe",
                {"resource": "pod", "name": "x | cat /etc/passwd"},
            )

    def test_logs_rejects_shell_injection(self):
        with pytest.raises(ValueError, match="shell metacharacters"):
            execute_tool("kubectl_logs", {"pod": "x`whoami`"})

    def test_logs_rejects_dollar_paren(self):
        with pytest.raises(ValueError, match="shell metacharacters"):
            execute_tool("kubectl_logs", {"pod": "$(cat /etc/passwd)"})

    def test_namespace_rejects_shell_injection(self):
        with pytest.raises(ValueError, match="shell metacharacters"):
            execute_tool("kubectl_get", {"resource": "pods", "namespace": "ns;evil"})

    @patch("claude_agents.k8s.agent.subprocess.run")
    def test_nonzero_exit_returns_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error: resource not found"
        )
        result = execute_tool("kubectl_get", {"resource": "pods"})
        assert result.startswith("Error:")
        assert "resource not found" in result

    def test_logs_rejects_negative_tail(self):
        with pytest.raises(ValueError, match="Invalid tail value"):
            execute_tool("kubectl_logs", {"pod": "my-pod", "tail": -1})


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
            self._make_tool_use_block("kubectl_get", {"resource": "pods"})
        ]

        # Second response: final text
        final_response = MagicMock()
        final_response.stop_reason = "end_turn"
        final_response.content = [self._make_text_block("Found 1 pod: pod1")]

        mock_client.messages.create.side_effect = [tool_response, final_response]

        result = run_agent("list pods", client=mock_client)
        assert result == "Found 1 pod: pod1"
        assert mock_client.messages.create.call_count == 2
        mock_execute_tool.assert_called_once_with("kubectl_get", {"resource": "pods"})

    @patch("claude_agents.k8s.agent.execute_tool")
    def test_tool_error_fed_back(self, mock_execute_tool):
        """When execute_tool raises, error is sent back as tool_result."""
        mock_execute_tool.side_effect = ValueError("Invalid input: contains shell metacharacters: 'bad;input'")

        mock_client = MagicMock()

        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.content = [
            self._make_tool_use_block("kubectl_get", {"resource": "bad;input"})
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
            self._make_tool_use_block("kubectl_get", {"resource": "pods"}, "t1"),
            self._make_tool_use_block("kubectl_get", {"resource": "services"}, "t2"),
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
        assert len(call_kwargs.kwargs["tools"]) == 3
