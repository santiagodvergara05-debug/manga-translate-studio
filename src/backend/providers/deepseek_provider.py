"""Maintainer scaffold for the DeepSeek vision provider integration.

This provider is visible in settings, but intentionally unavailable until its
authentication, vision request, response parsing, and usage handling are implemented.
"""

from src.backend.providers.base_provider import ProviderScaffold


class DeepSeekProvider(ProviderScaffold):
    """Placeholder only; implement and verify the DeepSeek API before enabling it."""

    display_name = "DeepSeek"

    def __init__(self):
        super().__init__("deepseek")
