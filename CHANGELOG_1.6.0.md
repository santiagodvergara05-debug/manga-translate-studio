# Manga Translate Studio 1.6.0 — Change Log

This document records the application changes made for the 1.6.0 development cycle. The desktop title now show **1.6.0 BETA 2** until the stable release is prepared.

## Beta 2 — changes since the published Beta 1

This section summarizes the changes made after the **1.6.0 BETA 1** release. The sections below remain the cumulative change record for the full 1.6.0 development cycle.

- Replaced the optional **Usage group** with saved connection profiles as the identity for request history and Gemini RPD tracking. The field and its grouping behavior were removed.
- Expanded shared request pacing with **MAX** (at least 0.5 seconds between request starts); the Help tooltip now documents the theoretical RPM ceilings for LOW, HIGH, and MAX.
- Moved Gemini RPD editing into **API Settings**, where it appears only for Gemini. The main header retains a compact meter/status display.
- Added optional suppression of repeated, identical SFX lettering on the same page. It requires SFX extraction and is disabled by default.
- Added OpenAI, xAI, Anthropic, OpenRouter, and DeepSeek provider scaffolds. They are explicitly unavailable and make no API requests until contributors implement and verify them.
- Improved translation review during batches: completed pages remain editable, active/queued pages are locked, prior text remains visible during retranslation and on request errors, and cancellation restores unsent pages to their previous states.
- Added distinct page indicators for waiting, processing, updating, modified, and script-synchronized states; connected manual edits to the Modified state and corrected stale progress/status updates after a batch ends.
- Added **Alt + mouse wheel** as an additional canvas zoom shortcut while preserving normal wheel scrolling and Ctrl + wheel zoom.
- Removed the unused provider-logo directory and the unused `src/utils/history.py` undo/redo module.
- Expanded Help, contribution guidance, and project documentation for the new provider scaffolds and revised UI behavior.

## Added

### Provider settings and request handling

- Added a dedicated **API and Model Settings** dialog with saved connection profiles. A profile groups a provider with its endpoint or credentials, selected model, and model-specific settings; users can add, rename, switch, and remove profiles.
- Added model-aware Gemini thinking-level choices, including Gemini 3 model levels and the Minimal/High modes exposed for Gemma 4. Unsupported providers and models do not receive a thinking setting.
- Added request pacing choices shared by single-page and batch translation: **LOW** waits at least 4.1 seconds between application request starts for a provider (~14.6 theoretical RPM maximum), **HIGH** at least 1.5 seconds (40 RPM), and **MAX** at least 0.5 seconds (120 RPM). Provider processing/retry delays can reduce actual rates; MAX may trigger provider rate limits or HTTP 429 responses.
- Split stable system instructions from page-specific text context in requests. Gemini receives the stable prompt through `systemInstruction`; Ollama sends it as a system message/field. The current page image is sent with the user request, and earlier page images are not resent.
- Added usage metadata handling for provider-reported input, output, thinking, request-count, and cached-input tokens where available. The application displays actual reported cache counts; it does not infer cache hits.
- Added provider scaffolds for OpenAI, xAI, Anthropic (Claude), OpenRouter, and DeepSeek. They appear in API Settings but fail closed: no API calls are made, and unavailable providers cannot be saved as active connections. The Help guide links contributors to the repository and implementation guidance.

### Configurable extraction prompts

- Added persisted extraction options in `cache/prompt_options.json`: sound effects, narration, floating outside text, translation variants, tone notes (subtext), R19 vocalization guidance, and SFX meaning.
- Added an SFX meaning option that is disabled by default and available only while SFX extraction is enabled. Meanings appear as editor guidance and are omitted from exported translation scripts.
- Added an optional setting to return only the first occurrence of identical SFX lettering on a page. It is disabled by default, requires SFX extraction, and does not deduplicate dialogue or other entity types.
- Added an optional R19 vocalization mode, disabled by default, to help distinguish breathing, effort, pain, surprise, and laughter using the artwork context. It does not add an output field.
- Added a read-only system-prompt preview that updates to reflect the selected medium, languages, user rules, and extraction options.
- Kept SFX localization target-aware through `get_sfx_rule_for_target()`. Language-specific examples are selected only for the corresponding target; other supported targets receive a general rule based on the selected language.
- Added language-pair checks to page continuity so translations from a different source/target pair are not injected into a request.

### Usage, pricing, and Gemini RPD

- Added **Usage / Prices** with a local request history filtered by provider. Each request is associated with its saved connection profile. History includes timestamp, model, request count, reported input/cache/output tokens, and estimated cost; it does not store prompts, images, or API credentials.
- Added editable price rows using USD per million tokens, including optional cached-input rates and plan variants. Cost estimates use reported usage and the currently matching provider/model/plan rates; missing rates are shown as **Not configured**.
- Added price JSON import/export. Imports merge by provider, model, and plan, updating matching rows while retaining unrelated rows so users can load several providers' tables.
- Added community reference tables in `Pricing_Models_Providers/` for Google Gemini/Gemma and Ollama. The application’s local price table starts empty; users choose which public tables to import.
- Added a **Clear all history** action. It removes request records across providers and connection profiles while preserving price rows and Gemini RPD counters.
- Added optional, editable Gemini **RPD limit** and **RPD in use** fields in API Settings. The main header keeps a compact status indicator. A zero limit disables the local meter. Counters are grouped by saved connection profile and model and roll over using the Pacific calendar date; this is a local tracker, not a live Google quota query.

### Translation review and interface

- Replaced the hardware-memory indicator with a header showing the active provider, model, thinking availability/value, request state, Gemini RPD status, API pace control, and a **USAGE / PRICES** button.
- Added elapsed-time feedback for an individual request and total batch duration. A new job resets the timer; a batch keeps one timer across its pages.
- Improved batch auditing: completed pages can be selected and edited while processing continues; queued and currently active pages remain locked. The batch no longer needs to switch the selected image automatically for each request.
- Improved the canvas for long pages: the mouse wheel scrolls vertically, `Ctrl` or `Alt` + wheel zooms, and changing the selected image returns the viewport to the top.
- Expanded the Help dialog with thinking-level, token-impact, extraction-option, cache, pricing, connection-profile, RPD, and request-pacing guidance.

### Page status and script synchronization

- Separated page-list indicators by meaning: queued pages use a waiting hourglass; a fresh in-flight page uses the lock; retranslation of a page with existing text uses a distinct updating icon; provider overload/rate-limit responses use the dedicated busy warning icon.
- Kept existing translations visible while a page is being reprocessed. A successful response replaces them, an empty-page response clears them, and provider/API errors leave the previous text in place.
- Restored queued pages to their prior states when a batch is stopped before they are sent. Successfully processed pages keep their result state; the batch summary now replaces the stale per-page “Model working” message when the run ends.
- Connected manual edits in dialogue text fields, variant selection, and add/remove dialogue actions to the local **Modified** state. The previously unconnected `mark_current_modified()` handler now runs when these edits occur.
- Added a separate **Script Synced** state and document-check icon for pages loaded from a translation script or successfully written to `.TXT`. **Modified** now means an unsynced local edit rather than imported/exported script data.
- Updated the Help guide's page-status legend to describe queued, processing, updating, server-busy, locally modified, and script-synced states separately.

## Changed

- Updated provider requests and normalized results to carry system prompts, thinking settings, connection profile IDs, request pacing, and provider-reported usage metadata through the worker layer.
- Replaced the optional usage-group mechanism with saved connection profiles as the single identity for usage history and Gemini RPD tracking.
- Extended Gemini model discovery to include Gemma 4 and exposed thinking levels according to the selected model identifier.
- Updated Ollama response parsing to retain cache counters when returned by cloud-compatible or local endpoints.
- Expanded normalized entity data so optional SFX meanings can be displayed in the editor without changing `.TXT` output.
- Updated project reset handling to clear the new per-page language and usage state along with translation session data.
- Updated PyInstaller configuration and dependencies to match the revised feature set.
- Changed the application version constant to `1.6.0 BETA` for the current development build.
- Updated the timer/status refresh flow so idle usage-summary refreshes no longer overwrite the completed translation or batch status with stale inference progress.

## Removed

- Removed the RAM/hardware telemetry widget and `src/utils/system_info.py`, along with the `psutil` dependency and its packaging import. The header space now presents translation provider and usage information.
- Removed the unused `assets/icon_provider/` directory and its Gemini/Ollama logos. The interface identifies providers by text, so these unreferenced assets only added packaging and maintenance overhead.
- Removed the unused `src/utils/history.py` undo/redo module. Repository search found no imports or callers; the image/mask undo methods were stubs and the remaining generic undo stack was unused.
- Removed the separate Gemini limits tab and its RPM, TPM, and external-request table. The remaining local quota helper is the optional Gemini RPD limit/count in API Settings with a compact status in the main header.
- Removed prefilled local price and Gemini RPD defaults for new installations. Price references are distributed separately under `Pricing_Models_Providers/` and imported by the user.

## New repository files

- `src/backend/usage_manager.py` — local usage, pricing, cache metadata, profile identity, and Gemini RPD persistence.
- `src/frontend/api_settings.py` — provider settings and saved connection-profile dialog.
- `src/frontend/usage_pricing.py` — usage history, price editing, and JSON import/export UI.
- `src/backend/providers/anthropic_provider.py` — unavailable provider scaffold for Anthropic (Claude).
- `src/backend/providers/deepseek_provider.py` — unavailable provider scaffold for DeepSeek.
- `src/backend/providers/openai_provider.py` — unavailable provider scaffold for OpenAI.
- `src/backend/providers/openrouter_provider.py` — unavailable provider scaffold for OpenRouter.
- `src/backend/providers/xai_provider.py` — unavailable provider scaffold for xAI.
- `Pricing_Models_Providers/README.md` — price-table format and contribution notes.
- `Pricing_Models_Providers/google_models.json` — Google reference pricing rows.
- `Pricing_Models_Providers/ollama_models.json` — Ollama reference pricing rows.
- `assets/icon_waiting.svg` — queued-page hourglass indicator.
- `assets/icon_updating.svg` — retranslation-in-progress indicator for pages with existing text.
- `assets/icon_script_synced.svg` — script-import/export synchronization indicator.
- `TECHNICAL_AUDIT_1.6.0.md` — maintainability audit notes and JSON-loading optimization summary.

## Removed repository file

- `src/utils/system_info.py` — hardware/process memory telemetry implementation.
- `src/utils/history.py` — unused undo/redo implementation and stubs.

## Local runtime files

The following files are created under the git-ignored `cache/` directory and should not be committed:

- `api_config.json` — provider credentials/settings and saved connection profiles.
- `core_rules.txt`, `user_rules.txt`, and `prompt_options.json` — prompt configuration.
- `pricing_tables.json` — locally imported and edited prices plus Gemini RPD state.
- `usage_history.json` — local usage records.
