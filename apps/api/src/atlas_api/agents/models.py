"""Chat-model factory (Claude via LangChain)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas_api.config import Settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


def build_chat_model(settings: Settings) -> BaseChatModel:
    """Build a Claude chat model. Requires ``anthropic_api_key`` in settings."""
    from langchain_anthropic import ChatAnthropic

    if not settings.anthropic_api_key:
        raise ValueError("anthropic_api_key is required to build the research model")
    return ChatAnthropic(
        model_name=settings.research_model,
        timeout=60,
        max_retries=2,
        stop=None,
        api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
        max_tokens_to_sample=4096,
    )
