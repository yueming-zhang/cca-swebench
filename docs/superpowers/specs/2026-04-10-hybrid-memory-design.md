# Hybrid Memory for ChatAgent — Design Spec

## Goal

Enhance `ChatAgent` to handle arbitrarily long conversations by automatically summarizing older messages when the conversation approaches 50% of the model's context window, while keeping the last 20 messages verbatim.

## Architecture

Inline in `ChatAgent` (Approach A). Before each API call, the agent checks token usage via `client.messages.count_tokens()`. When usage exceeds 50% of `max_context_tokens`, the agent splits history into old + recent (last 20), summarizes old messages via a separate Claude call, and replaces history with `[summary_pair] + recent`.

## Decisions

- **Trigger:** Token-count based via `client.messages.count_tokens()`, threshold at 50% of `max_context_tokens`.
- **Recent messages kept:** 20 (10 turns).
- **Summarization:** LLM-generated via `client.messages.create()` with a focused system prompt, `max_tokens=1024`.
- **Summary injection:** As a user/assistant pair at index 0 to maintain message alternation. User message: `"[Conversation summary]: <summary>"`. Assistant message: `"Understood, I'll keep this context in mind."`.
- **Edge case:** If history has <= 20 messages, skip compaction regardless of token count.

## New Constructor Parameters

- `max_context_tokens: int = 200_000`
- `summary_threshold: float = 0.5`
- `recent_messages_to_keep: int = 20`

## Testing

- Unit: mock `count_tokens` and `messages.create`, verify compaction logic.
- Integration: multi-turn conversation that triggers compaction, verify recall of summarized facts.
