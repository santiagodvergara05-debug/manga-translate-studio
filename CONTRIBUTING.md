

# Contributing to Manga Translate Studio

Thank you for your interest in contributing to **Manga Translate Studio**! This document provides guidelines and step-by-step instructions for contributing to the project, specifically focusing on adding **new target/source languages** and **new AI vision providers** within our decoupled architecture.

---

## Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free experience for everyone, regardless of background, identity, or skill level.

### Our Standards
- **Respect and Professionalism**: Communicate with empathy and constructive intent. Respect differing viewpoints and technical approaches.
- **Constructive Collaboration**: Focus criticism on code and architecture, never on individuals. Welcome newcomers and help them understand the codebase.
- **Integrity**: Only submit code that you wrote or have the explicit legal right to contribute under permissive terms. Never paste proprietary or non-permissive code.

### Unacceptable Behavior
- Trolling, insulting, derogatory comments, or personal attacks.
- Harassment in any form, public or private.
- Publishing private information without explicit permission.

Maintainers are responsible for clarifying and enforcing our standards of acceptable behavior and will take appropriate corrective action in response to any behavior that they deem inappropriate, threatening, or harmful.

---

## Codebase Principles & Licensing



- **Apache 2.0 Licensing**: Manga Translate Studio is distributed under the **Apache License 2.0**. All contributions submitted via pull requests are licensed under these exact terms, including the explicit grant of patent rights and patent litigation termination provisions. Contributions containing copyleft-restricted code (GPL, AGPL) or non-commercial restrictions (CC-BY-NC) are strictly rejected.
- **Decoupled Architecture**: UI views (`main_window.py`, `canvas.py`, `widgets.py`) must never contain network logic, raw prompt engineering, or direct provider calls. Business logic resides in dedicated managers (`PromptManager`, `CredentialManager`, `AIClientManager`).
- **Standardized Interfaces**: Every provider must normalize API responses into the unified `TranslationResult` interface using canonical `ProviderStatus` enums.
- **Language Standard**: All source code comments, docstrings, variable names, log messages, and error traces must remain in **technical English**.
- **Decoupled Architecture**: UI views (`main_window.py`, `canvas.py`, `widgets.py`) must never contain network logic, raw prompt engineering, or direct provider calls. Business logic resides in dedicated managers (`PromptManager`, `CredentialManager`, `AIClientManager`).
- **Standardized Interfaces**: Every provider must normalize API responses into the unified `TranslationResult` interface using canonical `ProviderStatus` enums.
- **Language Standard**: All source code comments, docstrings, variable names, log messages, and error traces must remain in **technical English**.

---

## 1. How to Add a New Language

Language definitions, dialect constraints, and target-specific SFX localization rules reside exclusively in `src/backend/languages.py`.

### Step 1: Register Language Definitions

Open `src/backend/languages.py` and add your language to the corresponding list:

1. **Source Language** (if supported as input image text):
   Add an entry to `SUPPORTED_SOURCE_LANGUAGES`:
   ```python
   SUPPORTED_SOURCE_LANGUAGES = [
       # ... existing languages
       {"code": "tl", "name": "Tagalog", "native": "Tagalog"},
   ]



2. **Target Language** (if supported for translation output):
Add an entry to `SUPPORTED_TARGET_LANGUAGES`:
```python
SUPPORTED_TARGET_LANGUAGES = [
    # ... existing languages
    {"code": "pt-br", "name": "Portuguese (Brazil)", "native": "Português (Brasil)"},
]

```


3. **Asian Scripts & CJK Rules**:
If the language uses vertical orientation or Asian logographic characters (Korean, Japanese, Chinese, etc.), add its ISO code to `ASIAN_LANG_CODES`:
```python
ASIAN_LANG_CODES = {"ko", "ja", "zh"}

```



### Step 2: Implement SFX Localization Rules

Comic onomatopoeias (SFX) require language-specific adaptation. Extend `get_sfx_rule_for_target()` in `src/backend/languages.py`:

```python
def get_sfx_rule_for_target(target_display_text: str, is_asian_src: bool) -> str:
    # ...
    target_lower = target_clean.lower()

    if "spanish" in target_lower:
        rule_lines.append("Examples: ¡FUSH!, ¡PAM!, ¡CRASH!, ¡TOC-TOC!.")
    elif "portuguese" in target_lower:
        rule_lines.append("Examples: POW!, CRASH!, FWOOSH!, TOC-TOC!.")
    # Add localized comic sound conventions for your language here

```

---

## 2. How to Add a New AI Provider

Thanks to our dynamic provider schema, adding a new provider engine does not require altering UI form layouts.

### Step 1: Implement the Provider Class

Create a new module under `src/backend/providers/<provider_name>_provider.py` inheriting from `BaseAIProvider`:

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
    """Provider implementation for Custom Vision API."""

    # UI Schema Configuration (used by TranslatorPanel for automatic UI rendering)
    display_name = "CustomAI"
    requires_endpoint = False       # True if provider requires custom URL / proxy
    has_lan_mode = False            # True if provider supports local daemon (e.g. Ollama)
    is_primary_secret = True        # True to mask input as password (API key)
    primary_placeholder = "Enter CustomAI API Key..."
    secondary_placeholder = "Enter Token..."
    default_endpoint = ""
    default_models = ["custom-vision-v1", "custom-vision-fast"]

    def __init__(self):
        super().__init__("custom_key")

    def test_and_fetch_models(self, key_or_url: str, auth_token: str = "") -> tuple[bool, list[str], str]:
        """
        Validates API connectivity and retrieves available vision models.

        Returns:
            tuple[bool, list[str], str]: (success, list_of_models, message)
        """
        # Implement connection check
        return True, list(self.default_models), "Connected successfully."

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
        Sends multimodal payload and returns standardized TranslationResult.
        """
        b64_img = self.encode_image(image_path)
        usage_info = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        try:
            # 1. Execute request with retry loop for transient status codes (429/500/503)
            # 2. Check for moderation blocks (return ProviderStatus.SAFETY_BLOCKED)
            # 3. Clean raw output into normalized JSON
            parsed_json = self.clean_json_response(raw_text)
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
                message="Request timed out. Infrastructure busy, retry later."
            )
        except Exception as e:
            return TranslationResult(
                status=ProviderStatus.ERROR,
                message=f"Execution error: {str(e)}",
                raw_error=str(e)
            )

```

### Step 2: Register Provider in `AIClientManager`

Open `src/backend/ai_client.py`, import your class, and register it inside `PROVIDERS`:

```python
from src.backend.providers.custom_provider import CustomProvider

PROVIDERS: dict[str, BaseAIProvider] = {
    "gemini": GeminiProvider(),
    "ollama": OllamaProvider(),
    "custom_key": CustomProvider(),  # <-- Registered provider instance
}

```

### Step 3: Register Defaults in `CredentialManager`

Open `src/backend/credential_manager.py` and declare the default credential schema inside `self.default_config`:

```python
"custom_key": {
    "key": "",
    "model": "custom-vision-v1",
    "models_list": ["custom-vision-v1", "custom-vision-fast"]
}

```

### Step 4: Add Provider Vector Icon

1. Place the official SVG logo inside `assets/icon_provider/<provider_id>.svg` (matching your provider key in lowercase, e.g. `assets/icon_provider/custom_key.svg`).
2. Adhere to **Qt SVG Tiny specifications**:
* Avoid complex clip-paths, filters (`<feGaussianBlur>`), and embedded CSS stylesheets.
* Use simple vector paths with high-contrast fills (`#ffffff` or bright accents) legible on dark backgrounds (`#121218`).



> **Note**: `TranslatorPanel` automatically discovers and renders all registered providers from `AIClientManager`. No manual UI changes are needed.

---

## 3. Pull Request Submission Checklist

Before opening a Pull Request, please ensure all items on this checklist are satisfied:

### General Checklist

* [ ] Code strictly adheres to project architecture and folder conventions.
* [ ] No hardcoded personal API keys, cloud tokens, or secrets exist in commit history.
* [ ] No temporary test assets, generated cache files, or `.log` files are staged.
* [ ] All comments, docstrings, variable names, and error traces are written in **technical English**.
* [ ] Syntax check passes across all modified files:
```powershell
python -m py_compile src/backend/<modified_file>.py

```


* [ ] The desktop application launches cleanly without warnings or runtime exceptions:
```powershell
python main.py

```


### New Language PR Checklist

* [ ] Language is registered with standard ISO code, English name, and native script label.
* [ ] If applicable, Asian logographic scripts are added to `ASIAN_LANG_CODES`.
* [ ] SFX onomatopoeia conventions and capitalization directives are defined in `get_sfx_rule_for_target`.
* [ ] Verified that text continuity and inverted punctuation rules (e.g. `¿` / `¡` for Spanish) function properly.

### New Provider PR Checklist

* [ ] Provider inherits from `BaseAIProvider` and implements both `test_and_fetch_models()` and `execute_translation()`.
* [ ] Class UI attributes (`display_name`, `requires_endpoint`, etc.) are declared.
* [ ] Distinguishes between transient rate limits (RPM / 429) and daily quota exhaustion (`DailyQuotaExceeded`).
* [ ] Content moderation blocks are mapped to `ProviderStatus.SAFETY_BLOCKED`.
* [ ] Vector icon added to `assets/icon_provider/<provider_id>.svg`.
* [ ] Added default schema in `CredentialManager`.
* [ ] Registered in `AIClientManager.PROVIDERS`.

### Core Engine, UI & Bug Fix PR Checklist

Use this checklist if your pull request modifies the UI layout, graphics canvas, batch worker logic, prompt engine, or script generator:

- [ ] **Thread & UI Safety**:
  - Long-running operations, network requests, or file I/O must execute asynchronously inside a worker `QThread`. The main Qt GUI thread must never be blocked.
  - Signal-slot connections across threads must pass safe or copied primitives (`str`, `dict`, standard Python objects) to prevent race conditions.
- [ ] **Manga Cleaner Protocol Compatibility**:
  - Any changes to `TranslationScriptEngine` must strictly retain the `<translation> ... </translation>` tag format and `Image X [filename]` line structure.
  - Unicode strings written to disk or matched in memory must use NFC normalization (`_nfc()`).
- [ ] **Path Resolution & Packaging**:
  - File paths must never be hardcoded as local relative strings (e.g., avoid `"./cache"` or `"assets/..."`). Always resolve paths via `Paths.CACHE`, `Paths.TRANSLATIONS`, `Paths.LOGS`, or `Paths.BUNDLE_DIR`.
  - Verified that modifications do not break portable PyInstaller builds or write inside `MangaTranslate_Data/` instead of the root persistent folders.
- [ ] **Memory & Canvas Stability**:
  - Tested with high-resolution vertical manhwa/manga pages (4K+ height) to ensure canvas zoom, dragging, and panning remain responsive.
  - Verified that `ProjectResetController.reset()` and page transitions release image arrays from memory without lingering references.
- [ ] **Core Prompt Guardrail**:
  - If editing `DEFAULT_CORE_RULES` in `prompt_manager.py`, verify that Rule 7 (`{"bubbles": []}` on silent panels) and the strict JSON output shape remain intact.