import os
import sys
from PIL import Image
from PySide6.QtCore import Signal, QThread
from src.utils.logger import logger

from src.backend.providers.base_provider import (
    BaseAIProvider, 
    TranslationResult, 
    ProviderStatus, 
    DailyQuotaExceeded
)
from src.backend.providers.gemini_provider import GeminiProvider
from src.backend.providers.ollama_provider import OllamaProvider

DEBUG_AI_LOGS = (not getattr(sys, "frozen", False)) and os.environ.get("MTS_DEBUG", "1") == "1"

# Provider Registry
PROVIDERS: dict[str, BaseAIProvider] = {
    "gemini": GeminiProvider(),
    "ollama": OllamaProvider(),
}


def _print_debug_banner(title: str):
    print("\n" + "=" * 75)
    print(f" [AI DEBUG] - {title}")
    print("=" * 75)


def _debug_log_response(provider: str, result: TranslationResult):
    if not DEBUG_AI_LOGS:
        return
    _print_debug_banner(f"RESPONSE RECEIVED FROM {provider.upper()} [{result.status.name}]")
    usage = result.usage
    print(f"[*] Input Tokens: {usage.get('prompt_tokens', 0):,}")
    print(f"[*] Output Tokens: {usage.get('output_tokens', 0):,}")
    print(f"[*] Total Billed Tokens: {usage.get('total_tokens', 0):,}")
    print(f"[*] Status: {result.status.name}")
    if result.message:
        print(f"[*] Message: {result.message}")
    print("-" * 75)
    print(f"[*] Valid Detected Entities: {len(result.bubbles)}")
    for b in result.bubbles:
        orig = b.get("original", "").replace("\n", " ")
        direct = b.get("direct", "").replace("\n", " ")
        print(f"  • [#{b.get('id', '?')}] {b.get('type', 'bubble').upper()}: '{orig}' -> '{direct}'")
    if result.raw_error:
        print(f"[!] Raw Error Trace: {result.raw_error}")
    print("=" * 75 + "\n")


class AIClientManager:
    """Orchestrates AI providers, token estimation, and request dispatching."""

    @staticmethod
    def get_provider(provider_name: str) -> BaseAIProvider:
        key = provider_name.strip().lower()
        if key not in PROVIDERS:
            raise ValueError(f"Unsupported AI provider: '{provider_name}'")
        return PROVIDERS[key]

    @staticmethod
    def estimate_tokens(prompt: str, image_path: str = None) -> tuple[int, int, int]:
        text_tokens = max(1, int(len(prompt) / 3.6))
        image_tokens = 0

        if image_path and os.path.exists(image_path):
            try:
                with Image.open(image_path) as img:
                    w, h = img.size
                    tiles_w = max(1, (w + 511) // 512)
                    tiles_h = max(1, (h + 511) // 512)
                    total_tiles = min(tiles_w * tiles_h, 4)
                    image_tokens = 258 + (total_tiles * 280)
            except Exception:
                image_tokens = 1120
        else:
            image_tokens = 1120

        total = text_tokens + image_tokens
        return total, text_tokens, image_tokens

    @staticmethod
    def test_and_fetch_models(provider: str, key_or_url: str, auth_token: str = "") -> tuple[bool, list[str], str]:
        engine = AIClientManager.get_provider(provider)
        return engine.test_and_fetch_models(key_or_url, auth_token)

    @staticmethod
    def execute_translation_request(
        image_path: str,
        prompt: str,
        provider: str,
        model: str,
        api_key: str,
        endpoint_url: str,
        token: str
    ) -> TranslationResult:
        engine = AIClientManager.get_provider(provider)

        if DEBUG_AI_LOGS:
            _print_debug_banner("PAYLOAD SENT TO API")
            print(f"[*] Image: {os.path.basename(image_path)}")
            print(f"[*] Provider: {provider.upper()}")
            print(f"[*] Model: {model}")
            print("\n--- [PROMPT / INSTRUCTIONS] ---")
            print(prompt.strip())
            print("-" * 75)

        result = engine.execute_translation(
            image_path=image_path,
            prompt=prompt,
            model=model,
            api_key=api_key,
            endpoint_url=endpoint_url,
            token=token
        )

        _debug_log_response(provider, result)
        return result


class FetchModelsWorker(QThread):
    finished = Signal(bool, list, str)

    def __init__(self, provider: str, key_or_url: str, auth_token: str = ""):
        super().__init__()
        self.provider = provider
        self.key_or_url = key_or_url
        self.auth_token = auth_token

    def run(self):
        success, models, msg = AIClientManager.test_and_fetch_models(
            self.provider, self.key_or_url, self.auth_token
        )
        self.finished.emit(success, models, msg)


class MultimodalTranslationWorker(QThread):
    finished = Signal(str, object)  # Emite (image_path, TranslationResult)
    error = Signal(str, str)

    def __init__(
        self,
        image_path: str,
        full_prompt: str,
        provider: str,
        model_name: str,
        api_key: str = "",
        ollama_url: str = "",
        ollama_token: str = ""
    ):
        super().__init__()
        self.image_path = image_path
        self.full_prompt = full_prompt
        self.provider = provider
        self.model_name = model_name
        self.api_key = api_key
        self.ollama_url = ollama_url
        self.ollama_token = ollama_token

    def run(self):
        try:
            result = AIClientManager.execute_translation_request(
                image_path=self.image_path,
                prompt=self.full_prompt,
                provider=self.provider,
                model=self.model_name,
                api_key=self.api_key,
                endpoint_url=self.ollama_url,
                token=self.ollama_token
            )
            self.finished.emit(self.image_path, result)
        except DailyQuotaExceeded as dqe:
            self.error.emit(self.image_path, f"DAILY_QUOTA: {str(dqe)}")
        except Exception as e:
            logger.error(f"[AI_WORKER] Unexpected error on {self.image_path}: {e}")
            self.error.emit(self.image_path, str(e))