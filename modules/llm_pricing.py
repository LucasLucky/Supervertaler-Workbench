"""
LLM Pricing Module for Supervertaler
=====================================

Simple token cost estimation based on provider/model pricing tables.
Prices are approximate and may lag behind actual provider pricing.
"""

from typing import Optional


# Pricing per 1M tokens: (input_price_usd, output_price_usd)
PRICING = {
    "claude": {
        "claude-opus-4-7": (15.0, 75.0),
        "claude-sonnet-4-6": (3.0, 15.0),
        "claude-sonnet-4-5-20250514": (3.0, 15.0),
        "claude-opus-4-6": (15.0, 75.0),
        "claude-opus-4-1-20250410": (15.0, 75.0),
        "claude-haiku-4-5-20251001": (1.0, 5.0),
        "claude-3-5-sonnet-20241022": (3.0, 15.0),
        "claude-3-5-haiku-20241022": (0.80, 4.0),
    },
    "openai": {
        "gpt-4o": (2.50, 10.0),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.0, 30.0),
        "gpt-5": (10.0, 30.0),
        "gpt-5.4": (10.0, 30.0),
        "gpt-5.4-mini": (1.0, 4.0),
        "o1": (15.0, 60.0),
        "o1-mini": (3.0, 12.0),
        "o3": (10.0, 40.0),
        "o3-mini": (1.10, 4.40),
    },
    "gemini": {
        "gemini-2.5-flash": (0.15, 0.60),
        "gemini-2.5-pro": (1.25, 10.0),
        "gemini-3-flash-preview": (0.15, 0.60),
        "gemini-3.1-pro-preview": (1.25, 10.0),
    },
    "mistral": {
        "mistral-large-latest": (2.0, 6.0),
        "mistral-small-latest": (0.20, 0.60),
        "open-mistral-nemo": (0.15, 0.15),
    },
    "openrouter": {
        # OpenRouter passes through provider pricing + small markup
        "anthropic/claude-sonnet-4.6": (3.0, 15.0),
        "anthropic/claude-opus-4.7": (15.0, 75.0),
        "anthropic/claude-opus-4.6": (15.0, 75.0),
        "openai/gpt-5.4": (10.0, 30.0),
        "openai/gpt-5.4-mini": (1.0, 4.0),
        "openai/gpt-4o": (2.50, 10.0),
        "google/gemini-3.1-pro-preview": (1.25, 10.0),
        "google/gemini-3-flash-preview": (0.15, 0.60),
        "mistralai/mistral-small-2603": (0.20, 0.60),
    },
}


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    """
    Estimate USD cost for a given API call.

    Returns:
        - 0.0  when tokens are 0, or for genuinely free providers (ollama, custom_openai).
        - float (> 0) computed cost for a model with a known pricing entry.
        - None when the model is not in the pricing table for its provider.
            Callers should render this as "unknown" (NOT "free") so users
            don't mistake a non-curated OpenRouter model for a free one.

    Pre-v1.9.462 this function returned 0.0 for unknown models, which
    callers couldn't distinguish from genuinely free.
    """
    if not input_tokens and not output_tokens:
        return 0.0

    provider = provider.lower()
    if provider in ("ollama", "custom_openai"):
        return 0.0

    provider_pricing = PRICING.get(provider, {})

    # Try exact match first
    prices = provider_pricing.get(model)

    # Try partial match (model ID may have date suffix)
    if not prices:
        for known_model, p in provider_pricing.items():
            if model.startswith(known_model) or known_model.startswith(model):
                prices = p
                break

    if not prices:
        return None

    input_price, output_price = prices
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    return round(cost, 4)
