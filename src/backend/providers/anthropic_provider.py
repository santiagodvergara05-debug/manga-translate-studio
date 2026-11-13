"""Maintainer scaffold for the Anthropic (Claude) vision provider integration.

This provider is visible in settings, but intentionally unavailable until its
authentication, vision request, response parsing, and usage handling are implemented.
"""

from src.backend.providers.base_provider import ProviderScaffold


class AnthropicProvider(ProviderScaffold):
    """Placeholder only; implement and verify the Anthropic (Claude) API before enabling it."""

    display_name = "Anthropic (Claude)"

    def __init__(self):
        super().__init__("anthropic")
