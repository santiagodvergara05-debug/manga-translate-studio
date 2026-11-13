# Manga Translate Studio 1.6.0 — Change Log

This document records the application changes made for the 1.6.0 development cycle. The desktop title may continue to show **1.6.0 BETA** until the stable release is prepared.

## Added

### Provider settings and request handling

- Added a dedicated **API and Model Settings** dialog with saved connection profiles. A profile groups a provider with its endpoint or credentials, selected model, and model-specific settings; users can add, rename, switch, and remove profiles.
- Added an optional **Usage group** name for grouping credentials that share an account, project, or connection. When left blank, the application derives a local profile fingerprint from connection details. API keys and tokens are not written to usage history.
- Added model-aware Gemini thinking-level choices, including Gemini 3 model levels and the Minimal/High modes exposed for Gemma 4. Unsupported providers and models do not receive a thinking setting.
- Added request pacing choices shared by single-page and batch translation: **LOW** waits at least 4.1 seconds between application request starts for a provider, while **HIGH** waits at least 1.5 seconds. Provider-side retry delays remain separate.
- Split stable system instructions from page-specific text context in requests. Gemini receives the stable prompt through `systemInstruction`; Ollama sends it as a system message/field. The current page image is sent with the user request, and earlier page images are not resent.
- Added usage metadata handling for provider-reported input, output, thinking, request-count, and cached-input tokens where available. The application displays actual reported cache counts; it does not infer cache hits.

### Configurable extraction prompts

- Added persisted extraction options in `cache/prompt_options.json`: sound effects, narration, floating outside text, translation variants, tone notes (subtext), R19 vocalization guidance, and SFX meaning.
- Added an SFX meaning option that is disabled by default and available only while SFX extraction is enabled. Meanings appear as editor guidance and are omitted from exported translation scripts.
- Added an optional R19 vocalization mode, disabled by default, to help distinguish breathing, effort, pain, surprise, and laughter using the artwork context. It does not add an output field.
- Added a read-only system-prompt preview that updates to reflect the selected medium, languages, user rules, and extraction options.
- Kept SFX localization target-aware through `get_sfx_rule_for_target()`. Language-specific examples are selected only for the corresponding target; other supported targets receive a general rule based on the selected language.
- Added language-pair checks to page continuity so translations from a different source/target pair are not injected into a request.

### Usage, pricing, and Gemini RPD

- Added **Usage / Prices** with a local request history filtered by provider and usage group. History includes timestamp, model, request count, reported input/cache/output tokens, and estimated cost; it does not store prompts, images, or API credentials.
- Added editable price rows using USD per million tokens, including optional cached-input rates and plan variants. Cost estimates use reported usage and the currently matching provider/model/plan rates; missing rates are shown as **Not configured**.
- Added price JSON import/export. Imports merge by provider, model, and plan, updating matching rows while retaining unrelated rows so users can load several providers' tables.
- Added community reference tables in `Pricing_Models_Providers/` for Google Gemini/Gemma and Ollama. The application’s local price table starts empty; users choose which public tables to import.
- Added a **Clear all history** action. It removes request records across providers and groups while preserving price rows and Gemini RPD counters.
- Added optional, editable Gemini **RPD limit** and **RPD in use** fields in the main header. A zero limit disables the local meter. Counters are grouped by usage profile and model and roll over using the Pacific calendar date; this is a local tracker, not a live Google quota query.

### Translation review and interface

- Replaced the hardware-memory indicator with a header showing the active provider, model, Gemini thinking level when applicable, request state, and a **USAGE / PRICES** button.
- Added elapsed-time feedback for an individual request and total batch duration. A new job resets the timer; a batch keeps one timer across its pages.
- Improved batch auditing: completed pages can be selected and edited while processing continues; queued and currently active pages remain locked. The batch no longer needs to switch the selected image automatically for each request.
- Improved the canvas for long pages: the mouse wheel scrolls vertically, `Ctrl` + wheel zooms, and changing the selected image returns the viewport to the top.
- Expanded the Help dialog with thinking-level, token-impact, extraction-option, cache, pricing, usage-group, RPD, and request-pacing guidance.

## Changed

- Updated provider requests and normalized results to carry system prompts, thinking settings, usage groups, request pacing, and provider-reported usage metadata through the worker layer.
- Extended Gemini model discovery to include Gemma 4 and exposed thinking levels according to the selected model identifier.
- Updated Ollama response parsing to retain cache counters when returned by cloud-compatible or local endpoints.
- Expanded normalized entity data so optional SFX meanings can be displayed in the editor without changing `.TXT` output.
- Updated project reset handling to clear the new per-page language and usage state along with translation session data.
- Updated PyInstaller configuration and dependencies to match the revised feature set.
- Changed the application version constant to `1.6.0 BETA` for the current development build.

## Removed

- Removed the RAM/hardware telemetry widget and `src/utils/system_info.py`, along with the `psutil` dependency and its packaging import. The header space now presents translation provider and usage information.
- Removed the separate Gemini limits tab and its RPM, TPM, and external-request table. The remaining local quota helper is the optional Gemini RPD limit/count in the main header.
- Removed prefilled local price and Gemini RPD defaults for new installations. Price references are distributed separately under `Pricing_Models_Providers/` and imported by the user.

## New repository files

- `src/backend/usage_manager.py` — local usage, pricing, cache metadata, profile identity, and Gemini RPD persistence.
- `src/frontend/api_settings.py` — provider settings and saved connection-profile dialog.
- `src/frontend/usage_pricing.py` — usage history, price editing, and JSON import/export UI.
- `Pricing_Models_Providers/README.md` — price-table format and contribution notes.
- `Pricing_Models_Providers/google_models.json` — Google reference pricing rows.
- `Pricing_Models_Providers/ollama_models.json` — Ollama reference pricing rows.

## Removed repository file

- `src/utils/system_info.py` — hardware/process memory telemetry implementation.

## Local runtime files

The following files are created under the git-ignored `cache/` directory and should not be committed:

- `api_config.json` — provider credentials/settings and saved connection profiles.
- `core_rules.txt`, `user_rules.txt`, and `prompt_options.json` — prompt configuration.
- `pricing_tables.json` — locally imported and edited prices plus Gemini RPD state.
- `usage_history.json` — local usage records.
