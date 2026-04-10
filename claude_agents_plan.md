# Plan: Two Parallel Agent Work Streams with Sapling

## Context

Build two independent agents using the Claude API (via AWS Bedrock) in parallel,
following [ezyang's parallel agents workflow](https://blog.ezyang.com/2026/03/parallel-agents-heart-sapling/)
and [AI-assisted programming post](https://blog.ezyang.com/2026/03/ai-assisted-programming-for-spmd-types/).

### Key ideas from the blog posts

- **One terminal per worktree**, each running a Claude Code session
- **Sapling stack** (linear chain of draft commits) as the source of truth
- **`sl follow`** — after a parent commit is amended, follow the successor chain
- **`sl adopt`** — after inserting a commit in the middle, rebase children onto it
- **Review every line** the LLM produces; don't multitask during review

### Limitation: `sl wt` requires EdenFS (Meta-internal)

The blog post uses `sl wt add` for worktrees, which requires EdenFS — not available
in open-source Sapling. We use **`git worktree`** instead (the repo is git-backed).
`sl` commands (`sl smartlog`, `sl follow`, `sl adopt`, `sl amend`) work in git
worktrees since Sapling reads the same git objects.

### Gotcha: `.sl/config` aliases not loaded in git-backed repos

The `follow` and `adopt` aliases must be in the **global** Sapling user config.
`.sl/config` in a git-backed repo is not read.

```bash
mkdir -p ~/.config/sapling
cat > ~/.config/sapling/sapling.conf << 'EOF'
[alias]
follow = goto last(successors(.))
adopt = rebase -s 'children(parents(.)) - .' -d .
EOF

# Verify
sl adopt --help    # should show "alias for: rebase ..."
```

---

## Step 0: Create the Sapling Stack

```bash
# From the repo root (/workspaces/cca-swebench)

# 1. Create the base commit (shared scaffolding + dependency)
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

# 4. Verify the stack
sl smartlog
```

## Step 1: Create Worktrees

```bash
# git worktree (since sl wt requires EdenFS)
git worktree add ../cca-chat HEAD~1    # at the [chat] commit
git worktree add ../cca-k8s  HEAD      # at the [k8s] commit
```

| Workspace | Path | Stack position |
|-----------|------|----------------|
| Main repo | `/workspaces/cca-swebench` | Bottom (scaffold) |
| Chat worktree | `/workspaces/cca-chat` | Middle ([chat] commit) |
| K8s worktree | `/workspaces/cca-k8s` | Top ([k8s] commit) |

## Step 2: Install dependency

```bash
cd /workspaces/cca-swebench
.venv/bin/pip install "anthropic[bedrock]"
# Add anthropic[bedrock] to requirements.txt
```

## Step 3: Open parallel sessions

Open two VS Code terminals (click `+` in the terminal panel).

**Terminal 1 — Chat agent worktree:**
```bash
cd /workspaces/cca-chat
claude
```

Prompt:
> Implement a simple chat agent under `claude_agents/chat/` using `AnthropicBedrock`
> from the `anthropic` SDK (AWS Bedrock, region from `AWS_REGION` env var).
> Simple REPL loop: read input → call Claude → print response. Maintain conversation
> history. Support exit/Ctrl+C. Add `__main__.py` entry point.
> Create unit tests in `my_agents/tests/unit/test_chat_agent.py` (mock the client)
> and integration tests in `my_agents/tests/integration/test_chat_agent_integration.py`.
> Do NOT commit when done — leave changes uncommitted.

**Terminal 2 — K8s agent worktree:**
```bash
cd /workspaces/cca-k8s
claude
```

Prompt:
> Implement a K8s readonly agent under `claude_agents/k8s/` using `AnthropicBedrock`
> from the `anthropic` SDK (AWS Bedrock, region from `AWS_REGION` env var).
> Whitelist exactly 3 readonly kubectl commands as tools:
> 1. `kubectl get <resource> [-n namespace]`
> 2. `kubectl describe <resource> <name> [-n namespace]`
> 3. `kubectl logs <pod> [-n namespace] [--tail N]`
> Use `subprocess.run()` with `shell=False`. Validate inputs reject shell
> metacharacters (`;`, `|`, `&&`, backticks, `$()`).
> Use the manual agentic loop (while stop_reason == "tool_use").
> Add `__main__.py` entry point.
> Create unit tests in `my_agents/tests/unit/test_k8s_agent.py` (mock client + subprocess)
> and integration tests in `my_agents/tests/integration/test_k8s_agent_integration.py`.
> Do NOT commit when done — leave changes uncommitted.

---

## Step 4: Commit with Sapling

> **Important:** With `git worktree` (unlike `sl wt`), `sl amend` does NOT
> auto-restack children. You must manually rebase the k8s commit onto the
> amended chat commit.

**4a. Chat agent (do this first — it's lower in the stack):**
```bash
cd /workspaces/cca-chat
sl add .
sl amend
# Output shows: OLD_HASH -> NEW_HASH "[chat] WIP chat agent"
# Note the NEW_HASH — you'll need it below.
```

**4b. Rebase k8s onto the amended chat commit:**
```bash
cd /workspaces/cca-swebench
sl smartlog
# You'll see a fork: new chat commit and k8s on separate branches.
# Rebase k8s onto the new chat commit (use hashes from smartlog):
sl rebase -s <K8S_HASH> -d <NEW_CHAT_HASH>
sl smartlog                     # verify the stack is linear
```

**4c. K8s agent:**
```bash
cd /workspaces/cca-k8s
sl follow                       # follow to the restacked k8s commit
sl add .
sl amend
sl smartlog                     # verify the final stack
```

**4d. Go to top of stack in main repo:**
```bash
cd /workspaces/cca-swebench
sl next --top                   # now all code is visible in main working copy
```

> **Key command (from the blog post):**
> - `sl follow` — in a worktree sitting on a stale commit,
>   jump to the latest successor (carrying uncommitted changes)

## Step 5: Clean up worktrees

```bash
git worktree remove ../cca-chat
git worktree remove ../cca-k8s
```

---

## Work Stream 1: Chat Agent Details

### `claude_agents/chat/agent.py`
- Initialize `AnthropicBedrock(aws_region=os.environ.get("AWS_REGION", "us-west-2"))`
- Use `client.messages.create()` with appropriate Bedrock model ID
- Maintain conversation history as a list of messages
- Loop: read user input → append to messages → call API → print response → append assistant message
- Support `Ctrl+C` / "exit" to quit

### `claude_agents/chat/__main__.py`
Entry point: `python -m claude_agents.chat`

### Tests
- `my_agents/tests/unit/test_chat_agent.py` — mock client, test history management
- `my_agents/tests/integration/test_chat_agent_integration.py` — real Bedrock call

---

## Work Stream 2: K8s Agent Details

### Whitelisted commands
1. **`kubectl get`** — list resources (pods, services, deployments, nodes, etc.)
2. **`kubectl describe`** — show detailed info about a resource
3. **`kubectl logs`** — view container logs

### `claude_agents/k8s/agent.py`
- Initialize `AnthropicBedrock` client
- Define 3 tools (manual JSON schema definitions):
  - `kubectl_get(resource, namespace="default")`
  - `kubectl_describe(resource, name, namespace="default")`
  - `kubectl_logs(pod, namespace="default", container="", tail=100)`
- Input validation: reject shell metacharacters
- `subprocess.run(["kubectl", ...], shell=False, capture_output=True)`
- Manual agentic loop until `stop_reason != "tool_use"`
- System prompt: "You are a Kubernetes assistant. Use the provided kubectl tools to answer questions."

### `claude_agents/k8s/__main__.py`
Entry point: `python -m claude_agents.k8s`

### Tests
- `my_agents/tests/unit/test_k8s_agent.py` — mock client + subprocess, test input validation
- `my_agents/tests/integration/test_k8s_agent_integration.py` — real Bedrock call

---

## Verification

```bash
# Unit tests (no external deps)
.venv/bin/python -m pytest my_agents/tests/unit/test_chat_agent.py -v
.venv/bin/python -m pytest my_agents/tests/unit/test_k8s_agent.py -v

# Integration tests (needs AWS creds + Bedrock access)
.venv/bin/python -m pytest my_agents/tests/integration/test_chat_agent_integration.py -v
.venv/bin/python -m pytest my_agents/tests/integration/test_k8s_agent_integration.py -v

# Manual smoke test
.venv/bin/python -m claude_agents.chat
.venv/bin/python -m claude_agents.k8s
```
