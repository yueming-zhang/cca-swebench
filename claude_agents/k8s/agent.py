"""K8s agent using AnthropicBedrock.

Provides a generic kubectl tool that supports any subcommand, with a
blocklist for destructive operations and input validation against shell
metacharacters. Uses a manual agentic loop.
"""

import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from anthropic import AnthropicBedrock

MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

SYSTEM_PROMPT = (
    "You are a Kubernetes assistant. Use the kubectl tool to answer "
    "questions. You can use any kubectl subcommand except delete. "
    "Pass arguments as an array of strings."
)

# Reject shell metacharacters: ; | && ` $()
DANGEROUS_PATTERN = re.compile(r"[;|`]|\$\(|&&")

BLOCKED_SUBCOMMANDS = frozenset({"delete"})


def validate_input(value: str) -> None:
    """Reject values containing shell metacharacters."""
    if DANGEROUS_PATTERN.search(value):
        raise ValueError(f"Invalid input: contains shell metacharacters: {value!r}")


TOOLS = [
    {
        "name": "kubectl",
        "description": (
            "Run a kubectl command. Specify a subcommand (e.g. 'get', 'describe', "
            "'logs', 'top', 'exec', 'apply') and any arguments. "
            "The 'delete' subcommand is blocked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subcommand": {
                    "type": "string",
                    "description": (
                        "The kubectl subcommand, e.g. 'get', 'describe', "
                        "'logs', 'top'."
                    ),
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Arguments after the subcommand, e.g. "
                        "['pods', '-n', 'kube-system']."
                    ),
                },
            },
            "required": ["subcommand"],
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a kubectl command and return its output."""
    if tool_name != "kubectl":
        raise ValueError(f"Unknown tool: {tool_name}")

    subcommand = tool_input["subcommand"]
    args = tool_input.get("args", [])

    validate_input(subcommand)
    if subcommand in BLOCKED_SUBCOMMANDS:
        raise ValueError(f"Blocked subcommand: {subcommand!r} is not allowed")

    for arg in args:
        if not isinstance(arg, str):
            raise ValueError(f"Invalid arg: expected string, got {type(arg).__name__}")
        validate_input(arg)

    cmd = ["kubectl", subcommand, *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return result.stdout


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


def create_client() -> AnthropicBedrock:
    """Create an AnthropicBedrock client."""
    return AnthropicBedrock(
        aws_region=os.environ.get("AWS_REGION", "us-west-2"),
    )


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
