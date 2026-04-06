# Confucius Code Agent (CCA) — Paper Reference

> Based on: *Confucius Code Agent: An Open-sourced AI Software Engineer at Industrial Scale*
> (arXiv:2512.10398, Dec 2025)
> Authors: Zhaodong Wang, Zhenting Qi, Sherman Wong, Nathan Hu, et al. (Meta & Harvard)

---

## 1. Overview

CCA is an open-sourced AI software engineer built atop the **Confucius SDK**, designed for industrial-scale repositories. The SDK is organized around three complementary design axes:

| Axis | Focus | Description |
|------|-------|-------------|
| **AX** (Agent Experience) | Agent's internal workspace | Distilled working memory, hierarchical memories, adaptive summaries |
| **UX** (User Experience) | Human-facing interface | Readable logs, execution traces, artifact previews, trust & transparency |
| **DX** (Developer Experience) | Building & improving agents | Observability, modular interfaces, reproducibility, ablations, debugging |

**Key insight**: AX and UX are deliberately decoupled — users see rich streaming diffs, while the agent sees compressed summaries.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Confucius SDK                          │
│  ┌──────────────┐  ┌────────────┐  ┌──────────────────┐ │
│  │ Orchestrator │  │  Memory    │  │   Extensions     │ │
│  │              │  │            │  │                  │ │
│  │ System Prompt│  │ Hierarchical│ │ Plug-ins, APIs,  │ │
│  │ LLM          │  │ Note System│  │ Tools            │ │
│  │ Output Parse │  │ Note-taking│  │                  │ │
│  │              │  │ Agent      │  │                  │ │
│  └──────────────┘  └────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
   Customized Task    Long-term Memory    Environment
   + User I/O        (Read/Write)        (File System,
                                          Database,
                                          Console, ...)
```

---

## 3. Core Features

### F1: Context Management (C1; AX)

**Problem**: Long debugging sessions and multi-file refactors cause unbounded context growth.

**Solution**: Hierarchical working memory + adaptive context compression.

- Each agent backed by **hierarchical working-memory** with configurable visibility scopes (session, entry, runnable).
- An **Architect agent** (planner) is invoked when prompt length approaches thresholds.
- The Architect produces structured summaries preserving: task goals, decisions made, open TODOs, critical error traces.
- Summaries replace old history spans; a rolling window of recent messages is kept in original form.
- Reduces prompt length by ~40% without dropping key reasoning chains.
- Increases planning iterations per trajectory (2.7 vs 1.4 without).

**Ablation result**: Context management improved Resolve@1 from 42.0 to 48.6 on Claude 4 Sonnet.

### F2: Note-Taking Agent (C2; AX, UX)

**Problem**: Flat chat logs are verbose and don't transfer across sessions.

**Solution**: A dedicated note-taking agent distills trajectories into persistent hierarchical Markdown notes.

- Notes stored in file-system tree: `project/architecture.md`, `research/findings.md`, `solutions/bug_fix.md`
- **Hindsight notes** capture both successes AND failures (compilation errors, runtime exceptions, unproductive strategies)
- Indexed by error messages, stack traces, affected components for future retrieval
- SDK provides tools to search, read, write, edit, delete, import notes
- Notes organized into `shared/` (cross-project generic insights) and `projects/` (project-specific knowledge)

**Cross-session results** (151 tasks, Claude 4.5 Sonnet):
| Metric | Run 1 (scratch) | Run 2 (with notes) |
|--------|-----------------|-------------------|
| Avg Turns | 64 | 61 (-3) |
| Avg Token Cost | 104k | 93k (-11k) |
| Resolve Rate | 53.0% | 54.4% (+1.4%) |

### F3: Extensions (C1; AX, DX)

**Problem**: Tool behaviors are often wired into ad-hoc code, preventing reuse and auditing.

**Solution**: Modular extension system with typed callbacks.

Extensions register callbacks that are invoked at each orchestrator step:
- `on_input_messages` — shape prompts before LLM
- `on_plain_text` — handle text outputs
- `on_tag` — parse XML-style tool calls
- `on_llm_output` — process structured outputs

Extensions have access to shared **run context**: I/O interface, session storage, hierarchical memory, artifact store.

**Extension categories**:
| Category | Examples |
|----------|---------|
| **Perception** | File-edit parser, command-line parser |
| **Reasoning** | Planning module, "thinking" module |
| **Action** | Shell commands, file edits, code search, function calls |

CCA's extension bundle: file-editing, CLI, code search, planning, prompt-caching, and others.

### F4: Meta-Agent (DX)

**Problem**: Agent behavior is static — prompts and tool wiring are hand-designed and brittle.

**Solution**: A Meta Agent that builds and refines agents through a **build-test-improve loop**.

**Workflow**:
1. Developer describes target agent in natural language (e.g., "an agent that triages CI failures for our monorepo")
2. Meta-agent generates structured configuration form (repo scope, constraints, extensions, evaluation tasks)
3. Meta-agent synthesizes configuration, prompts, and wires extensions
4. Candidate agent is run on regression tasks
5. Failures are diagnosed; prompts, extensions, or tool wrappers are patched
6. Loop repeats until target metrics are met

**CCA itself was produced through this meta-agent process.**

---

## 4. The Orchestrator

The core execution loop (Algorithm 1):

```
1: Initialize session context, memory, extensions
2: while iteration < max_iters do
3:     Invoke LLM with system prompt + memory
4:     Parse LLM output into actions
5:     for all actions a do
6:         Route a to its extension
7:         Execute extension; update memory
8:         if extension signals continuation then
9:             add observations to memory; continue
10:    Check for completion; break if done
11: return final output and artifacts
```

**Output processing**: Dual interface — native JSON tool calls (Claude 4+) or XML-style tags (`<bash>...</bash>`) parsed to same format.

**Iteration control**: Bounded by max iterations. Terminates when agent emits no further actions. Extensions can signal continuation (e.g., Bash extension raises interrupt with command output).

---

## 5. How to Add a New Agent

Based on the paper's architecture, adding a new agent involves:

### Step 1: Define the Agent Specification
Describe in natural language what the agent should do, its constraints, and target environment. Examples from the paper:
- "An agent that triages CI failures for our monorepo"
- "A refactoring agent with read-only access to production configs"
- "A release-management agent"
- "A data-quality agent"

### Step 2: Select Extensions
Choose from available extensions or create new ones:

| Extension Type | Purpose | Callbacks |
|----------------|---------|-----------|
| Perception | Parse model outputs into structured actions | `on_tag`, `on_llm_output` |
| Reasoning | Rewrite/annotate prompts before LLM | `on_input_messages` |
| Action | Execute tools, persist results | `on_tag`, `on_plain_text` |

Each extension is a **typed configuration object** that registers callbacks and maintains its own state.

### Step 3: Configure Memory & Context
- Set hierarchical working-memory scopes (session, entry, runnable)
- Configure context compression thresholds
- Enable/disable note-taking agent
- Define note taxonomy (shared vs project-specific)

### Step 4: Write System Prompt
The system prompt is what the orchestrator sends to the LLM each iteration. It should:
- Define the agent's role and constraints
- Specify available tools/extensions
- Set output format expectations (XML tags or native tool calls)

### Step 5: Use Meta-Agent (Recommended)
Instead of hand-configuring, use the Meta-agent:
1. Provide natural language spec
2. Let it generate configuration + prompts
3. Run build-test-improve loop against representative tasks
4. Iterate until performance stabilizes

### Step 6: Register and Deploy
- Register the agent configuration with the SDK
- Use Trace UI for debugging and observability
- Use Eval UI for benchmark evaluations
- Use Playground for interactive prompt tuning

---

## 6. Extension Development Guide

To create a new extension:

1. **Define a typed configuration object** with the extension's parameters
2. **Register callbacks** for the orchestrator hooks you need:
   - `on_input_messages`: Modify messages before LLM invocation
   - `on_plain_text`: Handle plain text in LLM output
   - `on_tag`: Handle XML-style tagged actions (e.g., `<file_edit>`, `<bash>`)
   - `on_llm_output`: Post-process complete LLM output
3. **Access shared run context** for:
   - I/O interface
   - Session-wide storage
   - Hierarchical memory (read/write)
   - Artifact store
4. **Signal continuation** if the extension needs the orchestrator to loop again (e.g., after executing a command that produces output the agent should see)

**Key design principles**:
- Extensions should be composable and reusable across agents
- Each extension should have a narrow, well-defined contract
- Extensions' callbacks are logged for observability
- Extensions can interact with both memory and environment

---

## 7. Benchmark Results

### SWE-Bench-Pro (731 tasks)

| Backbone Model | Scaffold | Resolve@1 |
|----------------|----------|-----------|
| Claude 4 Sonnet | SWE-Agent | 42.7 |
| Claude 4 Sonnet | **CCA** | **45.5** |
| Claude 4.5 Sonnet | SWE-Agent | 43.6 |
| Claude 4.5 Sonnet | Live-SWE-Agent | 45.8 |
| Claude 4.5 Sonnet | **CCA** | **52.7** |
| Claude 4.5 Opus | Anthropic proprietary | 52.0 |
| Claude 4.5 Opus | **CCA** | **54.3** |

**Key finding**: A weaker model + strong scaffold (Claude 4.5 Sonnet + CCA = 52.7%) outperforms a stronger model + weaker scaffold (Claude 4.5 Opus + proprietary = 52.0%).

### SWE-Bench-Verified (500 tasks)

| Backbone Model | Scaffold | Resolve@1 |
|----------------|----------|-----------|
| Claude 4 Sonnet | SWE-Agent | 66.6 |
| Claude 4 Sonnet | OpenHands | 72.8 |
| Claude 4 Sonnet | **CCA** | **74.6** |
| Claude 4.5 Sonnet | mini-SWE-Agent | 70.6 |

### Multi-File Robustness

| Edited Files | Resolve@1 | Sample Count |
|-------------|-----------|-------------|
| 1-2 files | 57.8 | 294 |
| 3-4 files | 49.2 | 203 |
| 5-6 files | 44.1 | 86 |
| 7-10 files | 52.6 | 38 |
| 10+ files | 44.4 | 18 |

---

## 8. CCA vs Claude Code: Behavioral Differences

Based on PyTorch-Bench case studies (8 real PyTorch GitHub issues):

| Dimension | CCA (Single-Agent) | Claude Code (Multi-Agent) |
|-----------|-------------------|--------------------------|
| Architecture | All exploration in original context | Delegates to stateless subagents |
| Context | Full awareness of problem + history | Subagents lack main context |
| Solutions | Minimal, cautious, targeted fixes | More ambitious, comprehensive |
| Risk | May miss deeper issues | May over-engineer due to context loss |
| Validation | CCA's minimal fixes often matched official PyTorch team fixes | CC's broader fixes addressed more edge cases |

---

## 9. Future Directions

- **RL-based training**: AX traces are trajectory-friendly for RL. Meta-agent feedback signals can serve as reward functions.
- **Curriculum design**: Progressively richer toolsets and environments via the extensible orchestrator.
- **Specialized agents**: Release-management, data-quality, CI triage agents via Meta-agent.
- **Trajectory export**: Formalizing formats for end-to-end RL on foundation models.

---

## 10. Key Terminology

| Term | Definition |
|------|-----------|
| **Analect** | An instantiated agent configuration within the Confucius SDK |
| **Orchestrator** | The core execution loop that invokes LLM, parses outputs, routes to extensions |
| **Extension** | A modular component attached to the orchestrator via typed callbacks |
| **Hierarchical Working Memory** | Multi-scope memory (session/entry/runnable) for the agent |
| **Architect Agent** | The planner sub-agent that performs context compression |
| **Note-Taking Agent** | Sub-agent that distills trajectories into persistent Markdown notes |
| **Meta-Agent** | Agent that builds/refines other agents via build-test-improve loops |
| **Hindsight Notes** | Notes capturing failure modes and their resolutions |
