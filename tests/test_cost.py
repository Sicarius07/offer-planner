from backend import config
from backend.llm.anthropic_provider import cost
from backend.llm.base import Usage


def test_every_selectable_model_has_pricing():
    for m in config.SELECTABLE_MODELS:
        model = m["id"].split(":", 1)[1]
        assert cost(model, Usage(input_tokens=1)) > 0, model


def test_cost_counts_every_token_kind():
    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000, cache_read_tokens=1_000_000,
              cache_write_5m_tokens=1_000_000, cache_write_1h_tokens=1_000_000,
              thinking_tokens=400_000)
    # opus-5: 5 + 25 + 0.5 + 6.25 + 10. Thinking is inside output, so not added again.
    assert cost("claude-opus-5", u) == 46.75


def test_dated_model_id_uses_base_price():
    assert cost("claude-haiku-4-5-20251001", Usage(output_tokens=1_000_000)) == 5.0


def test_unknown_model_costs_zero():
    assert cost("claude-unknown", Usage(input_tokens=1_000_000)) == 0.0
