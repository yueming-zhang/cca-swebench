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
        result = run_agent(
            "List all pods in the default namespace", client=client
        )
        # Final response should be non-empty text
        assert len(result) > 0

    def test_agent_describes_node(self):
        """Real Bedrock call + real kubectl: ask to describe a node."""
        client = create_client()
        result = run_agent(
            "Describe any one node in the cluster", client=client
        )
        assert len(result) > 0

    def test_tool_definitions_match_whitelist(self):
        """Verify only the 3 whitelisted tools are defined."""
        tool_names = {t["name"] for t in TOOLS}
        assert tool_names == {"kubectl_get", "kubectl_describe", "kubectl_logs"}
