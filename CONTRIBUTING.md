

# Contributing to Manga Translate Studio

Thank you for your interest in contributing to **Manga Translate Studio**! This document provides guidelines and step-by-step instructions for contributing to the project, specifically focusing on adding **new target/source languages** and **new AI vision providers** within our decoupled architecture.

---

## Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free experience for everyone, regardless of background, identity, or skill level.

### Our Standards
- **Respect and Professionalism**: Communicate with empathy and constructive intent. Respect differing viewpoints and technical approaches.
- **Constructive Collaboration**: Focus criticism on code and architecture, never on individuals. Welcome newcomers and help them understand the codebase.
- **Integrity**: Only submit code that you wrote, created with assistance from an AI agent, or have the explicit legal right to contribute under permissive terms. AI-assisted contributions are welcome, but the contributor must fully review and audit every submitted change, understand how it works, and take responsibility for its correctness and licensing. Never paste proprietary or non-permissive code.

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
- **Usage Data Privacy**: Never commit API keys, tokens, user rules, local usage history, account identifiers, or personal pricing configuration. Runtime state belongs in the git-ignored `cache/` folder.

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

The settings list also contains scaffolds for OpenAI, xAI, Anthropic (Claude), OpenRouter, and DeepSeek. These entries inherit the shared placeholder in `base_provider.py` and are deliberately marked unavailable: they do not make network requests and cannot be saved as active connections. A provider PR should replace the scaffold with a real integration, verify vision payload and response handling, report only usage values supplied by that API, and document required credentials and setup. Do not remove the unavailable guard until the integration has been tested against the provider.

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

> **Note**: `TranslatorPanel` automatically discovers and renders provider names from `AIClientManager`. Provider logo assets are not used by the current interface and should not be added as part of a provider integration.

---

### Provider Usage and Cache Metadata

- Report only usage values returned by the provider. Use normalized fields such as `prompt_tokens`, `output_tokens`, `total_tokens`, `request_count`, and, when actually reported, `cache_tokens` and `thought_tokens`.
- Do not infer cache hits from prompt length or elapsed time. Omit `cache_tokens` when the provider gives no cache metadata; an explicit zero means the provider reported zero cached tokens.
- Keep provider-specific quota behavior in the provider or usage layer. The local Gemini RPD meter is Gemini-specific; do not present it as a universal provider limit.
- Preserve the shared request path and system/user prompt separation when adding provider payloads. Do not persist user prompts or images for caching without an explicit product requirement.

---

## 3. Community Price Table Contributions

Reference rate files live in `Pricing_Models_Providers/`. They are downloaded and imported by users; they are separate from local editable `cache/pricing_tables.json`.

- Use the JSON format documented in `Pricing_Models_Providers/README.md`: a top-level `prices` array with provider ID, model ID or prefix, plan, and USD-per-million-token rates.
- Keep numeric rates as JSON numbers and use `null` for rates that are not published or do not apply. Do not put currency signs or formatted text in numeric fields.
- Verify every changed rate against an authoritative provider pricing source. Include the source URL, date checked, affected models/plans, and any limitations in the PR description or file notes.
- Keep provider tables independent so importing a new table updates matching provider/model/plan rows without deleting unrelated rates.
- Do not add personal usage records, account information, API credentials, or local cache files to the reference folder.

---

## 4. Pull Request Submission Checklist

Before opening a Pull Request, please ensure all items on this checklist are satisfied:

### General Checklist

* [ ] Code strictly adheres to project architecture and folder conventions.
* [ ] No hardcoded personal API keys, cloud tokens, or secrets exist in commit history.
* [ ] No temporary test assets, generated cache files, or `.log` files are staged.
* [ ] All comments, docstrings, variable names, and error traces are written in **technical English**.
* [ ] If AI agents assisted with the contribution, the AI Agent Assistance Checklist below is complete and the PR describes which areas received assistance.
* [ ] Syntax check passes across all modified files:
```powershell
python -m py_compile src/backend/<modified_file>.py

```


* [ ] The desktop application launches cleanly without warnings or runtime exceptions:
```powershell
python main.py

```


### AI Agent Assistance Checklist

AI coding agents and other AI tools may be used to explore, explain, draft, or modify code. They do not replace contributor review. The person opening the PR remains responsible for every submitted line, including code suggested or generated by an agent.

* [ ] I reviewed the complete diff, including every AI-assisted change, and can explain what each changed function or block does.
* [ ] I traced the affected call paths, imports, signals, and data flow to confirm the change is connected to the application and does not leave dead or unintended code.
* [ ] I checked the change against the project architecture, provider/API contracts, error handling, and relevant privacy/security requirements.
* [ ] I verified that generated code does not copy incompatible licensed material and that any external source or dependency is identified and permitted.
* [ ] I did not provide the agent with API keys, credentials, private usage logs, or other sensitive user data.
* [ ] I ran the relevant syntax checks and application/manual checks, and the PR states what was checked and any checks that could not be run.
* [ ] The PR description identifies the areas where an AI agent assisted and confirms that I reviewed and take responsibility for the final changes.

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
* [ ] Added default schema in `CredentialManager`.
* [ ] Registered in `AIClientManager.PROVIDERS`.
* [ ] Usage and cache token fields reflect provider-reported metadata only; missing cache metadata is not represented as a confirmed cache miss.

### Price Table PR Checklist

* [ ] JSON parses and follows the `prices` schema documented in `Pricing_Models_Providers/README.md`.
* [ ] Provider/model/plan identifiers match application conventions; rates are USD per million tokens and use numbers or `null`.
* [ ] Rates have been checked against an authoritative source, with source URL and verification date included in the PR.
* [ ] No local usage history, credentials, account identifiers, or personal configuration is included.

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
