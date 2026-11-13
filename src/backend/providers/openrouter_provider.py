"""Maintainer scaffold for the OpenRouter vision provider integration.

This provider is visible in settings, but intentionally unavailable until its
authentication, vision request, response parsing, and usage handling are implemented.
"""

from src.backend.providers.base_provider import ProviderScaffold


class OpenRouterProvider(ProviderScaffold):
    """Placeholder only; implement and verify the OpenRouter API before enabling it."""

    display_name = "OpenRouter"

    def __init__(self):
        super().__init__("openrouter")
