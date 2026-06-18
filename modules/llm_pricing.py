"""
LLM Pricing Module for Supervertaler
=====================================

Per-model token prices, loaded from the canonical ``pricing.json`` that is
shared verbatim with Supervertaler for Trados (single source of truth).

Resolution order:
  1. ``<home>/Supervertaler/pricing.json`` — the shared user override. Edit this
     one file to re-price BOTH Supervertaler products at once.
  2. ``modules/pricing.json`` bundled with this app — the default canonical list.
  3. a tiny hardcoded table — only if both files fail to load, so cost
     estimation never crashes.

Prices are USD per 1,000,000 tokens. Cache-discount multipliers are applied
elsewhere (per provider), not here.
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

# Providers whose models are never billed via these list prices (local, or the
# user is billed by their own endpoint). estimate_cost() returns 0.0 for these.
_FREE_PROVIDERS = ("ollama", "custom_openai")


def _load_pricing() -> Dict[str, Tuple[float, float]]:
    """Load ``model_id -> (input_per_1M, output_per_1M)`` from the canonical file.

    The shared override at ``~/Supervertaler/pricing.json`` (the default data
    root, matching the Trados plugin) wins over the bundled copy when present.
    """
    candidates = [
        Path.home() / "Supervertaler" / "pricing.json",       # shared override
        Path(__file__).resolve().parent / "pricing.json",     # bundled default
    ]
    for path in candidates:
        try:
            if path.is_file():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                table: Dict[str, Tuple[float, float]] = {}
                for model_id, p in (data.get("models") or {}).items():
                    if isinstance(p, dict) and "input" in p and "output" in p:
                        table[model_id] = (float(p["input"]), float(p["output"]))
                if table:
                    return table
        except Exception:
            continue
    # Minimal safety net — only reached if both files fail to load.
    return {
        "gpt-5.5": (5.0, 30.0),
        "claude-opus-4-8": (5.0, 25.0),
        "claude-sonnet-4-6": (3.0, 15.0),
        "claude-haiku-4-5-20251001": (1.0, 5.0),
        "gemini-3.1-flash-lite": (0.25, 1.50),
    }


# Flat map ``model_id -> (input_per_1M, output_per_1M)``. Loaded once at import.
PRICING: Dict[str, Tuple[float, float]] = _load_pricing()


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    """
    Estimate USD cost for a given API call.

    Returns:
        - 0.0  when tokens are 0, or for genuinely free providers (ollama, custom_openai).
        - float (> 0) computed cost for a model with a known pricing entry.
        - None when the model is not in the pricing table.
            Callers should render this as "unknown" (NOT "free") so users
            don't mistake a non-curated model for a free one.
    """
    if not input_tokens and not output_tokens:
        return 0.0

    if (provider or "").lower() in _FREE_PROVIDERS:
        return 0.0

    # Exact match first.
    prices = PRICING.get(model)

    # Partial match (model id may carry a date/variant suffix, or vice versa).
    if not prices and model:
        for known_model, p in PRICING.items():
            if model.startswith(known_model) or known_model.startswith(model):
                prices = p
                break

    if not prices:
        return None

    input_price, output_price = prices
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    return round(cost, 4)
