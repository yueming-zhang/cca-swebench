import os

from anthropic import AnthropicBedrock

DEFAULT_MODEL_ID = "us.anthropic.claude-opus-4-6-v1"
DEFAULT_MAX_TOKENS = 4096

SUMMARY_SYSTEM_PROMPT = (
    "Summarize the following conversation concisely, preserving key facts, "
    "decisions, user preferences, and important context. Be thorough but brief."
)


class ChatAgent:
    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        aws_region: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_context_tokens: int = 200_000,
        summary_threshold: float = 0.5,
        recent_messages_to_keep: int = 20,
        client: AnthropicBedrock | None = None,
    ):
        self.model_id = model_id
        self.aws_region = aws_region or os.environ.get("AWS_REGION", "us-west-2")
        self.max_tokens = max_tokens
        self.max_context_tokens = max_context_tokens
        self.summary_threshold = summary_threshold
        self.recent_messages_to_keep = recent_messages_to_keep
        self.history: list[dict] = []
        self._client = client or AnthropicBedrock(aws_region=self.aws_region)

    def chat(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})

        full_text = ""
        with self._client.messages.stream(
            model=self.model_id,
            max_tokens=self.max_tokens,
            messages=list(self.history),
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                full_text += text
        print()

        self.history.append({"role": "assistant", "content": full_text})
        return full_text

    def _count_history_tokens(self) -> int:
        """Count tokens in current history via the API."""
        result = self._client.messages.count_tokens(
            model=self.model_id,
            messages=self.history,
        )
        return result.input_tokens

    def _summarize_messages(self, messages: list[dict]) -> str:
        """Summarize a list of messages into a concise text."""
        conversation_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages
        )
        response = self._client.messages.create(
            model=self.model_id,
            max_tokens=1024,
            system=SUMMARY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": conversation_text}],
        )
        return response.content[0].text

    def _maybe_compact_history(self) -> None:
        """Compact history if token count exceeds the threshold."""
        if len(self.history) <= self.recent_messages_to_keep:
            return

        token_count = self._count_history_tokens()
        if token_count <= self.max_context_tokens * self.summary_threshold:
            return

        # Split: old messages to summarize, recent to keep verbatim
        old_messages = self.history[: -self.recent_messages_to_keep]
        recent_messages = self.history[-self.recent_messages_to_keep :]

        summary = self._summarize_messages(old_messages)

        self.history = [
            {"role": "user", "content": f"[Conversation summary]: {summary}"},
            {"role": "assistant", "content": "Understood, I'll keep this context in mind."},
        ] + recent_messages

    def reset(self):
        self.history.clear()
