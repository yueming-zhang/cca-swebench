# pyre-strict
from __future__ import annotations

from confucius.core.llm_manager.llm_params import LLMParams

# Default LLM params for file search agent - uses Claude Sonnet for efficiency
CLAUDE_SONNET_SEARCH = LLMParams(
    model="claude-sonnet-4-5",
    initial_max_tokens=8192,
    temperature=0.2,
    top_p=0.7,
)
