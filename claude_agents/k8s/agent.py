"""K8s readonly agent using AnthropicBedrock.

Provides 3 whitelisted kubectl tools (get, describe, logs) with input
validation against shell metacharacters. Uses a manual agentic loop.
"""

import os
import re
import subprocess
import sys

from anthropic import AnthropicBedrock

MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

SYSTEM_PROMPT = (
    "You are a Kubernetes assistant. Use the provided kubectl tools to answer "
    "questions. Only use the tools provided — do not suggest running other commands."
)

# Reject shell metacharacters: ; | && ` $()
DANGEROUS_PATTERN = re.compile(r"[;|`]|\$\(|&&")


def validate_input(value: str) -> None:
    """Reject values containing shell metacharacters."""
    if DANGEROUS_PATTERN.search(value):
        raise ValueError(f"Invalid input: contains shell metacharacters: {value!r}")


TOOLS = [
    {
        "name": "kubectl_get",
        "description": "Run 'kubectl get <resource>' to list Kubernetes resources.",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource": {
                    "type": "string",
                    "description": "Resource type, e.g. pods, services, deployments, nodes",
                },
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace (omit for 'default')",
                },
            },
            "required": ["resource"],
        },
    },
    {
        "name": "kubectl_describe",
        "description": "Run 'kubectl describe <resource> <name>' to show detailed info about a specific resource.",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource": {
                    "type": "string",
                    "description": "Resource type, e.g. pod, service, deployment",
                },
                "name": {
                    "type": "string",
                    "description": "Name of the resource",
                },
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace (omit for 'default')",
                },
            },
            "required": ["resource", "name"],
        },
    },
    {
        "name": "kubectl_logs",
        "description": "Run 'kubectl logs <pod>' to view container logs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pod": {
                    "type": "string",
                    "description": "Pod name",
                },
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace (omit for 'default')",
                },
                "tail": {
                    "type": "integer",
                    "description": "Number of recent log lines to show (default: 100)",
                },
            },
            "required": ["pod"],
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a whitelisted kubectl command and return its output."""
    if tool_name == "kubectl_get":
        resource = tool_input["resource"]
        namespace = tool_input.get("namespace", "default")
        validate_input(resource)
        validate_input(namespace)
        cmd = ["kubectl", "get", resource, "-n", namespace]

    elif tool_name == "kubectl_describe":
        resource = tool_input["resource"]
        name = tool_input["name"]
        namespace = tool_input.get("namespace", "default")
        validate_input(resource)
        validate_input(name)
        validate_input(namespace)
        cmd = ["kubectl", "describe", resource, name, "-n", namespace]

    elif tool_name == "kubectl_logs":
        pod = tool_input["pod"]
        namespace = tool_input.get("namespace", "default")
        tail = tool_input.get("tail", 100)
        validate_input(pod)
        validate_input(namespace)
        if not isinstance(tail, int) or tail < 0:
            raise ValueError(f"Invalid tail value: {tail}")
        cmd = ["kubectl", "logs", pod, "-n", namespace, "--tail", str(tail)]

    else:
        raise ValueError(f"Unknown tool: {tool_name}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return result.stdout


def create_client() -> AnthropicBedrock:
    """Create an AnthropicBedrock client."""
    return AnthropicBedrock(
        aws_region=os.environ.get("AWS_REGION", "us-west-2"),
    )


def run_agent(user_message: str, client: AnthropicBedrock | None = None) -> str:
    """Run the K8s agent with a single user message. Returns the final text."""
    if client is None:
        client = create_client()

    messages = [{"role": "user", "content": user_message}]

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
                try:
                    result = execute_tool(block.name, block.input)
                except (ValueError, subprocess.TimeoutExpired) as e:
                    result = f"Error: {e}"
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

    return "\n".join(
        block.text for block in response.content if hasattr(block, "text")
    )


def main() -> None:
    """Interactive REPL for the K8s agent."""
    client = create_client()
    print("K8s Agent (type 'exit' or Ctrl+C to quit)")
    print("-" * 40)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if not user_input or user_input.lower() == "exit":
            print("Bye!")
            break

        try:
            response = run_agent(user_input, client=client)
            print(f"\nAssistant: {response}")
        except Exception as e:
            print(f"\nError: {e}", file=sys.stderr)
