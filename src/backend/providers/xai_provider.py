"""Maintainer scaffold for the xAI vision provider integration.

This provider is visible in settings, but intentionally unavailable until its
authentication, vision request, response parsing, and usage handling are implemented.
"""

from src.backend.providers.base_provider import ProviderScaffold


class XAIProvider(ProviderScaffold):
    """Placeholder only; implement and verify the xAI API before enabling it."""

    display_name = "xAI (Grok)"

    def __init__(self):
        super().__init__("xai")
