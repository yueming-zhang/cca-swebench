"""Integration tests for K8s agent.

Uses real Bedrock LLM calls and real kubectl against a live cluster.
Requires: AWS credentials, Bedrock access, and a reachable K8s cluster.
"""

import subprocess

import pytest

from claude_agents.k8s.agent import TOOLS, create_client, run_agent

# Skip all tests if kubectl can't reach a cluster
pytestmark = pytest.mark.skipif(
    subprocess.run(
        ["kubectl", "cluster-info"], capture_output=True, timeout=10
    ).returncode
    != 0,
    reason="No K8s cluster available",
)


@pytest.mark.timeout(120)
class TestK8sAgentIntegration:
    def test_agent_calls_kubectl_get_for_pod_question(self):
        """Real Bedrock call + real kubectl: ask about pods."""
        client = create_client()
        result, steps = run_agent(
            "List all pods in the default namespace", client=client
        )
        assert len(result) > 0
        assert len(steps) >= 2  # at least llm_request + llm_response
        assert steps[0]["type"] == "llm_request"
        assert steps[-1]["type"] == "llm_response"

    def test_agent_describes_node(self):
        """Real Bedrock call + real kubectl: ask to describe a node."""
        client = create_client()
        result, steps = run_agent(
            "Describe any one node in the cluster", client=client
        )
        assert len(result) > 0
        assert any(s["type"] == "tool_use" for s in steps)
        assert any(s["type"] == "tool_result" for s in steps)

    def test_tool_definitions_single_kubectl(self):
        """Verify exactly one generic kubectl tool is defined."""
        assert len(TOOLS) == 1
        assert TOOLS[0]["name"] == "kubectl"
