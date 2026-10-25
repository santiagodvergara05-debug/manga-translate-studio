# Contributing to Manga Translate Studio

Thank you for your interest in contributing to **Manga Translate Studio**! This document provides clear, step-by-step instructions for extending the application through Pull Requests (PRs), specifically focusing on adding **new target/source languages** and **new AI vision providers** within our decoupled architecture.



## Codebase Principles & Licensing

* **Permissive Licensing**: Ensure that no code or libraries derived from copyleft licenses (such as GPL, AGPL, or CC-BY-NC) are introduced. All contributions must be original work or compatible with permissive licenses (MIT, Apache 2.0, BSD).
* **Decoupled Architecture**: UI views (`translator.py`, `main_window.py`) must never contain network logic, raw system prompts, or direct provider calls. Business logic is strictly isolated into dedicated managers (`PromptManager`, `CredentialManager`, `AIClientManager`).
* **Standardized Results**: Every provider must normalize API responses into the unified `TranslationResult` interface.
* **Language Standard**: All source code comments, docstrings, variable names, and error traces must remain in **technical English**.

---

## 1. How to Add a New Language

Language definitions, dialect constraints, and target-specific SFX localization rules reside exclusively in `src/backend/languages.py`.

### Step 1: Register Language Identifiers

Open `src/backend/languages.py` and register your language:

1. Add the display name and code to `SOURCE_LANGUAGES` (if supported as input) or `TARGET_LANGUAGES`:
```python
TARGET_LANGUAGES = {
    # Existing languages...
    "pt-br": {
        "name": "Portuguese (Brazil)",
        "display": "Portuguese (Brazil) (Português do Brasil)",
        "code": "pt-BR",
    },
}

```


2. If the language belongs to the CJK group (Chinese, Japanese, Korean) or Asian scripts, add it to `ASIAN_SOURCE_LANGUAGES` to trigger vertical layout parsing and phonetic hints.

### Step 2: Implement SFX Localization Rules

Comic onomatopoeias (SFX) require language-specific translation rules. Update `get_sfx_rule_for_target` in `src/backend/languages.py`:

```python
def get_sfx_rule_for_target(target_lang: str, is_asian_source: bool = False) -> str:
    # Example for Brazilian Portuguese
    if "portuguese" in target_lang.lower():
        return (
            "SFX RULE\n"
            "Keep the original raw text in 'original'. In 'direct', provide the localized comic "
            "onomatopoeia in UPPERCASE suited for Brazilian Portuguese comics (e.g., ¡POW!, ¡CRASH!, ¡TOC-TOC!). "
            "If it represents a visual action rather than an audible sound, translate it as a concise action descriptor."
        )

```

---

## 2. How to Add a New AI Provider

Thanks to the decoupled design, adding a provider requires minimal UI changes. The provider engine, credential persistence, and prompt formatting are separated across modular files.

### Step 1: Implement the Provider Class

Create a new file under `src/backend/providers/<provider_name>_provider.py` inheriting from `BaseAIProvider`:

```python
import requests
from src.backend.providers.base_provider import (
    BaseAIProvider, 
    TranslationResult, 
    ProviderStatus,
    DailyQuotaExceeded
)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

class CustomProvider(BaseAIProvider):
    def __init__(self):
        super().__init__("custom_key")

    def test_and_fetch_models(self, key_or_url: str, auth_token: str = "") -> tuple[bool, list[str], str]:
        """
        Validates connection and returns available vision-compatible models.
        Returns:
            tuple[bool, list[str], str]: (success, list_of_models, message)
        """
        # Implement connection check
        return True, ["custom-vision-model-1"], "Connected successfully."

    def execute_translation(
        self,
        image_path: str,
        prompt: str,
        model: str,
        api_key: str = "",
        endpoint_url: str = "",
        token: str = ""
    ) -> TranslationResult:
        """
        Encodes the image, runs multimodal inference, and maps responses
        into a standardized TranslationResult.
        """
        b64_img = self.encode_image(image_path)
        usage_info = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        try:
            # 1. Execute API request
            # 2. Check for content moderation or policy blocks
            #    If blocked: return TranslationResult(status=ProviderStatus.SAFETY_BLOCKED, ...)

            # 3. Clean raw output into normalized JSON
            parsed_json = self.clean_json_response(raw_response_text)
            bubbles = self.normalize_bubbles(parsed_json)

            if not bubbles:
                return TranslationResult(
                    status=ProviderStatus.EMPTY,
                    bubbles=[],
                    usage=usage_info,
                    message="No text detected on this page (silent panel)."
                )

            return TranslationResult(
                status=ProviderStatus.SUCCESS,
                bubbles=bubbles,
                usage=usage_info,
                message=f"Successfully extracted {len(bubbles)} dialogue(s)."
            )

        except requests.exceptions.Timeout:
            return TranslationResult(
                status=ProviderStatus.SERVER_BUSY,
                message="Request timed out. Provider infrastructure overloaded, retry later."
            )
        except Exception as e:
            return TranslationResult(
                status=ProviderStatus.ERROR,
                message=f"Execution failed: {str(e)}",
                raw_error=str(e)
            )

```

### Step 2: Register Provider in `AIClientManager`

Open `src/backend/ai_client.py` and register the new engine:

```python
from src.backend.providers.custom_provider import CustomProvider

PROVIDERS: dict[str, BaseAIProvider] = {
    "gemini": GeminiProvider(),
    "ollama": OllamaProvider(),
    "custom_key": CustomProvider(),  # <-- Register new provider here
}

```

### Step 3: Add Credentials Defaults in `CredentialManager`

Open `src/backend/credential_manager.py` and declare the default credential schema in `self.default_config`:

```python
"custom_key": {
    "key": "",
    "model": "custom-vision-model-1",
    "models_list": ["custom-vision-model-1"]
}

```

### Step 4: Add Provider Vector Icon

1. Save the official SVG logo inside `assets/icon_provider/<provider_name>.svg` (lowercase filename matching the provider key).
2. Ensure the SVG is compatible with **Qt's `QSvgRenderer` (SVG Tiny specification)**:
* Avoid complex `<mask id="...">` and Gaussian blur filters (`<feGaussianBlur>`).
* Use high-contrast fills (e.g., `#ffffff` or clean gradients) visible over dark themes (`#121218`).



### Step 5: Expose Provider in UI (`translator.py`)

Add the item with its icon inside `TranslatorPanel.init_ui()`:

```python
self.provider_combo.addItem(_get_provider_icon("custom_key"), "Custom Provider")

```

---

## 3. Pull Request Submission Checklist

Before submitting your PR, verify the following:

* [ ] New files adhere strictly to project structure (`src/backend/providers/`, `assets/icon_provider/`).
* [ ] Code compiles cleanly without syntax errors (`python -m py_compile <file.py>`).
* [ ] No hardcoded personal API keys, access tokens, or credentials exist in commit history.
* [ ] All code comments, docstrings, and error messages are written in technical English.
* [ ] The application starts cleanly via `python main.py` and handles both single-page translation and batch processing without throwing uncaught exceptions.