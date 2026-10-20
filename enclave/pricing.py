"""Token to USD conversion. Prices are per million tokens (Claude API list)."""
from __future__ import annotations

PRICES = {
    # model: (input, output, cache_write, cache_read)
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 6.25, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
    "claude-fable-5-1": (10.00, 50.00, 12.50, 0.25),
}
DEFAULT = PRICES["claude-opus-5-5"]
WEB_SEARCH_PER_CALL = 0.01


def usage_to_usd(model: str, usage: dict) -> float:
    price = PRICES.get(model, DEFAULT)
    inp = usage.get("input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    cw = usage.get("cache_creation_input_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0
    searches = usage.get("web_search_requests", 0) or 0
    total = (inp * price[0] + out * price[1] + cw * price[2] + cr * price[3]) / 1_000_000
    total += searches * WEB_SEARCH_PER_CALL
    return round(total, 6)
