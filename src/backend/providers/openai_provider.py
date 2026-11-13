"""Maintainer scaffold for the OpenAI vision provider integration.

This provider is visible in settings, but intentionally unavailable until its
authentication, vision request, response parsing, and usage handling are implemented.
"""

from src.backend.providers.base_provider import ProviderScaffold


class OpenAIProvider(ProviderScaffold):
    """Placeholder only; implement and verify the OpenAI API before enabling it."""

    display_name = "OpenAI (ChatGPT)"

    def __init__(self):
        super().__init__("openai")
