# Plan: Two Parallel Agent Work Streams with Sapling

## Context

You want to build two independent agents using the Claude API (via AWS Bedrock) and develop them in parallel using Sapling worktrees, following the pattern from [ezyang's blog post](https://blog.ezyang.com/2026/03/parallel-agents-heart-sapling/). The existing codebase uses boto3 for Bedrock — the `anthropic` package is not installed. We'll use `anthropic[bedrock]` which provides `AnthropicBedrock` client for a cleaner SDK experience with tool use.

---

## Step 0: Sapling Stack Setup

Create a linear stack of 3 draft commits, then open worktrees at each position:

```bash
# From the repo root (main @ 8f0336f)

# 1. Create the base commit (shared scaffolding)
mkdir -p claude_agents/chat claude_agents/k8s
touch claude_agents/__init__.py claude_agents/chat/__init__.py claude_agents/k8s/__init__.py
sl add claude_agents/
sl commit -m "[scaffold] Add claude_agents package structure"

# 2. Create placeholder commit for chat agent
echo "# chat agent WIP" > claude_agents/chat/agent.py
sl add claude_agents/chat/agent.py
sl commit -m "[chat] WIP chat agent"

# 3. Create placeholder commit for k8s agent
echo "# k8s agent WIP" > claude_agents/k8s/agent.py
sl add claude_agents/k8s/agent.py
sl commit -m "[k8s] WIP k8s agent"

# 4. Open worktrees at each commit
sl worktree add ../cca-chat -r .~1    # points at the [chat] commit
sl worktree add ../cca-k8s  -r .      # points at the [k8s] commit (top of stack)
```

Now you have 3 workspaces:
- `/workspaces/cca-swebench` — main repo (bottom of stack)
- `/workspaces/cca-chat` — worktree for chat agent development
- `/workspaces/cca-k8s` — worktree for k8s agent development

### Sapling Parallel Workflow Commands

| Command | Purpose |
|---------|---------|
| `sl follow` | After amending a parent commit, run in child worktree to rebase onto updated parent |
| `sl adopt` | After inserting a new commit in the middle, adopt existing children onto it |
| `sl smartlog` | See the full stack and which worktree is where |

---

## Step 1: Install `anthropic` with Bedrock support

In the main repo:
```bash
.venv/bin/pip install "anthropic[bedrock]"
```

Add `anthropic[bedrock]` to `requirements.txt`.

The `AnthropicBedrock` client uses your existing AWS credentials (env vars or `~/.aws/credentials`) — same as the current boto3 setup. No `ANTHROPIC_API_KEY` needed.

---

## Work Stream 1: Chat Agent (`claude_agents/chat/`)

**Worktree:** `/workspaces/cca-chat`

### How to start

Open a new terminal and launch a Claude Code session in the worktree:

```bash
cd /workspaces/cca-chat
claude
```

Then give Claude this prompt:

> Follow the "Work Stream 1: Chat Agent" section in `/workspaces/cca-swebench/claude_agents_plan.md`. Implement the chat agent under `claude_agents/chat/` and its tests. Use `AnthropicBedrock` from the `anthropic` SDK. Amend the current commit when done (`sl amend`).

### Files to create

#### `claude_agents/chat/agent.py`
A simple interactive chat agent using `AnthropicBedrock`:
- Initialize `AnthropicBedrock(aws_region=os.environ.get("AWS_REGION", "us-west-2"))`
- Use `client.messages.create()` with `model="us.anthropic.claude-sonnet-4-5-20250929-v1:0"` (or appropriate Bedrock model ID)
- Maintain conversation history as a list of messages
- Loop: read user input → append to messages → call API → print response → append assistant message
- Support `Ctrl+C` / "exit" to quit

#### `claude_agents/chat/__main__.py`
Entry point: `python -m claude_agents.chat` runs the chat loop.

### Tests

#### `my_agents/tests/unit/test_chat_agent.py`
- Mock `AnthropicBedrock` client
- Test conversation history management (messages alternate user/assistant)
- Test exit condition

#### `my_agents/tests/integration/test_chat_agent_integration.py`
- Real Bedrock call with a simple prompt
- Verify response structure

---

## Work Stream 2: K8s Agent (`claude_agents/k8s/`)

**Worktree:** `/workspaces/cca-k8s`

### How to start

Open another terminal and launch a Claude Code session in the worktree:

```bash
cd /workspaces/cca-k8s
claude
```

Then give Claude this prompt:

> Follow the "Work Stream 2: K8s Agent" section in `/workspaces/cca-swebench/claude_agents_plan.md`. Implement the k8s agent under `claude_agents/k8s/` and its tests. Use `AnthropicBedrock` from the `anthropic` SDK. Whitelist only kubectl get, describe, and logs. Amend the current commit when done (`sl amend`).

### Top 3 Readonly kubectl Commands (whitelisted)

1. **`kubectl get`** — List resources (pods, services, deployments, nodes, etc.)
2. **`kubectl describe`** — Show detailed info about a resource
3. **`kubectl logs`** — View container logs

### Files to create

#### `claude_agents/k8s/agent.py`
An agent that answers K8s questions using whitelisted kubectl commands:
- Initialize `AnthropicBedrock` client (same as chat agent)
- Define 3 tools using the `@beta_tool` decorator or manual tool definitions:
  - `kubectl_get(resource: str, namespace: str = "default", flags: str = "")` — runs `kubectl get <resource> -n <namespace> <flags>`
  - `kubectl_describe(resource: str, name: str, namespace: str = "default")` — runs `kubectl describe <resource> <name> -n <namespace>`  
  - `kubectl_logs(pod: str, namespace: str = "default", container: str = "", tail: int = 100)` — runs `kubectl logs <pod> -n <namespace> --tail=<tail>`
- **Security**: Each tool function validates inputs against an allowlist (no shell injection via `;`, `|`, `&&`, backticks, `$()`) and runs via `subprocess.run()` with `shell=False`
- Use the manual agentic loop (tool runner beta may not fully work with Bedrock):
  ```python
  while response.stop_reason == "tool_use":
      # execute whitelisted tool → feed result back
  ```
- System prompt: "You are a Kubernetes assistant. Use the provided kubectl tools to answer questions. Only use the tools provided — do not suggest running other commands."

#### `claude_agents/k8s/__main__.py`
Entry point: `python -m claude_agents.k8s`

### Tests

#### `my_agents/tests/unit/test_k8s_agent.py`
- Mock `AnthropicBedrock` client and `subprocess.run`
- Test tool dispatch (correct kubectl command constructed)
- Test input validation rejects shell metacharacters (`;`, `|`, `&&`, `` ` ``, `$()`)
- Test that only the 3 whitelisted commands are available

#### `my_agents/tests/integration/test_k8s_agent_integration.py`
- Real Bedrock call with a question like "list all pods in default namespace"
- Verify the agent calls the `kubectl_get` tool correctly

---

## Verification

```bash
# Run unit tests (no external deps)
.venv/bin/python -m pytest my_agents/tests/unit/test_chat_agent.py -v
.venv/bin/python -m pytest my_agents/tests/unit/test_k8s_agent.py -v

# Run integration tests (needs AWS creds + Bedrock access)
.venv/bin/python -m pytest my_agents/tests/integration/test_chat_agent_integration.py -v
.venv/bin/python -m pytest my_agents/tests/integration/test_k8s_agent_integration.py -v

# Manual smoke test
.venv/bin/python -m claude_agents.chat
.venv/bin/python -m claude_agents.k8s
```

## Merging the Stack

After both worktrees are done:
```bash
# In main repo
sl smartlog                    # verify the stack looks clean
sl goto <top-of-stack>         # go to the k8s commit
sl fold --from <scaffold>      # optionally fold into fewer commits
# Then submit/push as needed
```
