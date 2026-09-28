"""Resolves "provider:model" strings to a provider instance.

Only Anthropic is registered for now. Adding a provider = one adapter implementing
`LLMProvider` + one line here; no pipeline code changes.
"""

from __future__ import annotations

from backend.llm.anthropic_provider import AnthropicProvider
from backend.llm.base import LLMProvider

_FACTORIES = {
    "anthropic": AnthropicProvider,
}
_instances: dict[str, LLMProvider] = {}


def resolve(spec: str) -> tuple[LLMProvider, str]:
    provider, sep, model = spec.partition(":")
    if not sep:
        provider, model = "anthropic", spec
    if provider not in _FACTORIES:
        raise ValueError(f"Unknown provider '{provider}'. Registered: {', '.join(_FACTORIES)}")
    if provider not in _instances:
        _instances[provider] = _FACTORIES[provider]()
    return _instances[provider], model
