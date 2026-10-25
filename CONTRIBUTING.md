
---

# Contributing to Manga Translate Studio

Thank you for your interest in contributing to **Manga Translate Studio**! Contributions from the community help make this tool more versatile for scanlators and translation teams worldwide.

This document outlines guidelines and provides step-by-step instructions for extending the application through Pull Requests (PRs), specifically focusing on adding **new target/source languages** and **new AI vision providers**.

---

## Codebase Principles & Licensing

* **Strict MIT Compatibility**: Ensure that no code, snippets, or logic derived from copyleft licenses (such as GPL, AGPL, or CC-BY-NC) are introduced into this repository. All contributions must be original work or compatible with permissive licenses (MIT, Apache 2.0, BSD).
* **Decoupled Architecture**: Providers must never communicate directly with UI widgets. Every provider translates its network or moderation responses into the unified `TranslationResult` interface.
* **Language Standard**: Code comments, docstrings, variable names, and error traces must remain in **technical English**.

---

## 1. How to Add a New Language

Language definitions, dialect constraints, and target-specific SFX rules reside in `src/backend/languages.py`.

### Step 1: Register Language Identifiers

Open `src/backend/languages.py` and add your language to the corresponding tuples or dictionaries:

1. Add the display name and code to `SOURCE_LANGUAGES` (if applicable) or `TARGET_LANGUAGES`:
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


2. If the language belongs to the CJK group (Chinese, Japanese, Korean) or Asian scripts, register it under `ASIAN_SOURCE_LANGUAGES` to trigger proper reading order and romanization hints.

### Step 2: Implement SFX Localization Rules

Every target language must handle comic onomatopoeias (SFX) according to publishing standards. Implement or update the localized prompt rule inside `get_sfx_rule_for_target`:

```python
def get_sfx_rule_for_target(target_lang: str, is_asian_source: bool = False) -> str:
    # Example for Portuguese
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

Every AI engine must inherit from `BaseAIProvider` and return standardized `TranslationResult` instances.

### Step 1: Implement the Provider Class

Create a new file under `src/backend/providers/<provider_name>_provider.py`:

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
        super().__init__("custom_provider_key")

    def test_and_fetch_models(self, key_or_url: str, auth_token: str = "") -> tuple[bool, list[str], str]:
        """
        Validates connectivity and credentials.
        Returns:
            tuple[bool, list[str], str]: (success, list_of_models, message)
        """
        # Implement model discovery or return supported vision models
        return True, ["custom-model-vision-1"], "Connected successfully."

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
        Encodes the image, executes inference, and maps API responses
        into a TranslationResult.
        """
        b64_img = self.encode_image(image_path)
        usage_info = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        try:
            # 1. Perform network request
            # 2. Check for content moderation/safety filters
            #    If blocked, return TranslationResult(status=ProviderStatus.SAFETY_BLOCKED, ...)
            
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
                message="Provider request timed out. Infrastructure overloaded, retry later."
            )
        except Exception as e:
            return TranslationResult(
                status=ProviderStatus.ERROR,
                message=f"Provider failed: {str(e)}",
                raw_error=str(e)
            )

```

### Step 2: Register in `AIClientManager`

Register the new instance inside `src/backend/ai_client.py`:

```python
from src.backend.providers.custom_provider import CustomProvider

PROVIDERS: dict[str, BaseAIProvider] = {
    "gemini": GeminiProvider(),
    "ollama": OllamaProvider(),
    "custom": CustomProvider(),  # <-- Register key here
}

```

### Step 3: Add Provider Vector Icon

1. Design or locate an official SVG vector for the provider.
2. Ensure the SVG is optimized for **SVG Tiny / Qt compatibility**:
* Avoid complex `<mask id="...">` and Gaussian blur filters (`<feGaussianBlur>`).
* Use high-contrast shapes visible over dark backgrounds (`#121218`).


3. Save the vector inside `assets/icon_provider/<provider_name>.svg` (in lowercase, matching the provider key).
4. Register the provider in the selection UI inside `src/backend/translator.py` (`TranslatorPanel.init_ui`):
```python
self.provider_combo.addItem(_get_provider_icon("custom"), "CustomProvider")

```



---

## 3. Pull Request Submission Checklist

Before submitting your PR, verify:

* [ ] All new files follow the project structure (`src/backend/providers/`, `assets/icon_provider/`).
* [ ] Code is formatted cleanly without syntax errors (`python -m py_compile <file.py>`).
* [ ] No hardcoded personal API keys or credentials exist in the commit history.
* [ ] The application starts cleanly via `python main.py` and passes basic tests on both single-page translation and batch queues.
* [ ] Vector assets render sharply in the UI without throwing `QSvgRenderer` warnings in the terminal.