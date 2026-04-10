# K8s Agent: Human-in-the-Loop Approval & Step Tracking

## Problem

The K8s agent currently executes kubectl commands autonomously. There is no
human gate before execution, and no structured record of what happened during
an agent run. This makes the agent unsuitable for production use where oversight
is required, and difficult to evaluate programmatically.

## Changes

### 1. Human approval via `confirm_fn`

`run_agent()` accepts a new optional parameter:

```python
confirm_fn: Callable[[str, list[str]], bool] | None = None
```

- Receives `(subcommand, args)` before every kubectl execution.
- Returns `True` to approve, `False` to deny.
- When `None` (default), uses a built-in `input()`-based prompt that prints
  the command and asks `[y/n]`.
- On denial, the tool result sent back to the LLM is
  `"Command denied by user."` so the model can adjust its plan.

### 2. Step tracking

`run_agent()` builds a `list[dict]` internally and returns it alongside the
final text. The return type changes from `str` to `tuple[str, list[dict]]`.

Step types and their fields:

| type             | fields                                          |
|------------------|-------------------------------------------------|
| `llm_request`    | `timestamp`                                     |
| `tool_proposed`  | `timestamp`, `subcommand`, `args`               |
| `tool_approved`  | `timestamp`, `subcommand`, `args`               |
| `tool_denied`    | `timestamp`, `subcommand`, `args`               |
| `tool_result`    | `timestamp`, `subcommand`, `args`, `output`     |
| `tool_error`     | `timestamp`, `subcommand`, `args`, `error`      |
| `llm_response`   | `timestamp`, `text`                             |

Timestamps are ISO 8601 strings from `datetime.datetime.utcnow().isoformat()`.

### 3. Impact on existing code

- **`main()` REPL**: Passes no `confirm_fn` (uses default stdin prompt).
  Discards the steps list — the REPL is for interactive use, not evaluation.
- **`execute_tool()`**: Unchanged. Approval happens in the agentic loop before
  calling `execute_tool()`.

### 4. Default confirm function

```python
def default_confirm(subcommand: str, args: list[str]) -> bool:
    cmd_str = " ".join(["kubectl", subcommand, *args])
    answer = input(f"Allow: {cmd_str}? [y/n] ").strip().lower()
    return answer in ("y", "yes")
```

### 5. Testing

**Unit tests** (no external deps):
- Existing `run_agent` tests pass `confirm_fn=lambda s, a: True` to auto-approve.
- New test: denial flow — `confirm_fn` returns `False`, verify "denied" is fed
  back to LLM and tracked in steps.
- New test: step tracking — verify step list contains expected types in order.
- New test: `default_confirm` with mocked `input()`.

**Integration tests** (real Bedrock + kubectl):
- Pass `confirm_fn=lambda s, a: True` to auto-approve (no stdin in CI).
- Verify steps list is non-empty and contains expected step types.
