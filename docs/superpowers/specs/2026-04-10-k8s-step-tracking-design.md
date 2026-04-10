# K8s Agent: Step Tracking for Model Evaluation

## Problem

The K8s agent has no structured record of what happened during an agent run.
This makes it difficult to evaluate model performance programmatically — e.g.,
did the model pick the right subcommand, how many LLM round-trips did it take,
what tool outputs did it see before producing its answer.

## Changes

### 1. Step tracking

`run_agent()` builds a `list[dict]` internally and returns it alongside the
final text. The return type changes from `str` to `tuple[str, list[dict]]`.

Step types and their fields:

| type             | fields                                          |
|------------------|-------------------------------------------------|
| `llm_request`    | `timestamp`                                     |
| `tool_use`       | `timestamp`, `subcommand`, `args`               |
| `tool_result`    | `timestamp`, `subcommand`, `args`, `output`     |
| `tool_error`     | `timestamp`, `subcommand`, `args`, `error`      |
| `llm_response`   | `timestamp`, `text`                             |

- `llm_request` — logged before each `messages.create` call.
- `tool_use` — logged when the model decides to call kubectl.
- `tool_result` — logged after successful execution with the output.
- `tool_error` — logged when execution raises (validation, timeout, etc.).
- `llm_response` — logged at the end with the final assistant text.

Timestamps are ISO 8601 strings from `datetime.datetime.utcnow().isoformat()`.

### 2. Impact on existing code

- **`run_agent()`**: Return type changes from `str` to `tuple[str, list[dict]]`.
- **`main()` REPL**: Unpacks the tuple, discards the steps list.
- **`execute_tool()`**: Unchanged.

### 3. Testing

**Unit tests** (no external deps):
- Existing `run_agent` tests updated to unpack the new `(text, steps)` return.
- New test: verify steps list contains expected types in correct order for a
  single tool-use loop (`llm_request`, `tool_use`, `tool_result`, `llm_request`,
  `llm_response`).
- New test: verify `tool_error` step is recorded when execution fails.

**Integration tests** (real Bedrock + kubectl):
- Updated to unpack the new return type.
- Verify steps list is non-empty and contains expected step types.
