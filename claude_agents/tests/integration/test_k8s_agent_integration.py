"""Integration tests for K8s agent.

Uses real Bedrock LLM calls — requires AWS credentials and Bedrock access.
subprocess is mocked since a real K8s cluster may not be available.
"""

from unittest.mock import MagicMock, patch

import pytest

from claude_agents.k8s.agent import TOOLS, create_client, run_agent


@pytest.mark.timeout(120)
class TestK8sAgentIntegration:
    def test_agent_calls_kubectl_get_for_pod_question(self):
        """Real Bedrock call: ask about pods, verify agent invokes kubectl_get."""
        client = create_client()

        with patch("claude_agents.k8s.agent.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=(
                    "NAME        READY   STATUS    RESTARTS   AGE\n"
                    "nginx-pod   1/1     Running   0          1d\n"
                ),
                stderr="",
            )

            result = run_agent(
                "List all pods in the default namespace", client=client
            )

            # The LLM should have called at least one kubectl tool
            assert mock_run.called
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "kubectl"

            # Final response should be non-empty text
            assert len(result) > 0

    def test_agent_describes_pod(self):
        """Real Bedrock call: ask to describe a specific pod."""
        client = create_client()

        with patch("claude_agents.k8s.agent.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=(
                    "Name:         nginx-pod\n"
                    "Namespace:    default\n"
                    "Status:       Running\n"
                    "IP:           10.0.0.5\n"
                ),
                stderr="",
            )

            result = run_agent(
                "Describe the pod named nginx-pod in the default namespace",
                client=client,
            )

            assert mock_run.called
            assert len(result) > 0

    def test_tool_definitions_match_whitelist(self):
        """Verify only the 3 whitelisted tools are defined."""
        tool_names = {t["name"] for t in TOOLS}
        assert tool_names == {"kubectl_get", "kubectl_describe", "kubectl_logs"}
