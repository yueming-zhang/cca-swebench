import os

from anthropic import AnthropicBedrock

DEFAULT_MODEL_ID = "us.anthropic.claude-opus-4-6-v1"
DEFAULT_MAX_TOKENS = 4096


class ChatAgent:
    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        aws_region: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: AnthropicBedrock | None = None,
    ):
        self.model_id = model_id
        self.aws_region = aws_region or os.environ.get("AWS_REGION", "us-west-2")
        self.max_tokens = max_tokens
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

    def reset(self):
        self.history.clear()
