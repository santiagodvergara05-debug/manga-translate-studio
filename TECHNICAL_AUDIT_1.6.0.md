# Technical Audit — Manga Translate Studio 1.6.0

## Scope

Static maintenance review of the Python modules, runtime JSON flows, UI-to-backend call paths, packaging entry points, and repository documentation. No translation behavior or provider payload format was intentionally changed during the audit. Runtime tests were not run.

## Changes made

### Repeated JSON parsing

- `UsageManager` now retains parsed usage history per manager instance and reuses it while the file's modification time and size remain unchanged. This removes repeated full-file JSON parsing during the main window's periodic usage refresh.
- The cache is invalidated after usage history is recorded or cleared. Writes remain atomic, and a different process/manager that replaces the file is detected through its file signature.
- Replaced a JSON encode/decode round-trip used to clone default pricing data with `copy.deepcopy`.

### Dead code

- Removed `src/utils/history.py`. Repository search found no imports or callers; its image and mask undo methods were stubs, and the remaining generic undo stack was unused. Removed its entry from the README directory tree.
- Kept `usage_profile` cleanup in `CredentialManager`: this is a one-time migration path for older local settings, not an active UI feature. Removing it would leave obsolete data in users' existing configuration files.
- Kept abstract provider methods and exception-handling fallbacks; these are intentional extension/error paths, not unimplemented application features.

## Findings by subsystem

### Provider and request layer

- `AIClientManager` centralizes provider selection, request pacing, dispatch, and usage recording. Provider-specific request construction and retry behavior are kept in the provider classes.
- `BaseAIProvider` owns shared image encoding and response normalization. Its abstract methods are required extension points.
- Prompt/image order and provider token reporting are provider-specific. Cache hit rates are reported by the API; the application should not infer cache hits from prompt equality.
- Debug mode prints prompt/request diagnostics and may print raw provider responses. This is useful during development but should remain disabled in packaged builds and should not be used with sensitive content when enabled.

### Usage and pricing JSON

- `pricing_tables.json` holds editable rates and Gemini RPD state. Pricing rows are loaded on demand; it is not a collection of locale files.
- `usage_history.json` is capped at 10,000 events and is the only potentially large JSON file in the current runtime flow. The UI refresh previously caused repeated parsing; that path now uses the parsed cache described above.
- API settings and prompt options are loaded once during their manager/dialog initialization. They do not currently cause repeated JSON reads in a timer loop.
- The usage history cache reduces parsing and temporary allocation churn, but intentionally retains one parsed history list in memory. For substantially larger histories, a database or bounded pagination would be a better follow-up than loading the full file.

### Image memory observation

- `MainWindow.image_sessions` retains decoded NumPy arrays for every visited page until project reset. Large chapters can therefore consume much more RAM than the JSON settings/history. This cache is used when navigating pages, so it was not removed as part of the JSON-specific change. A bounded LRU or keeping only the active image should be considered in a separate, measured change.

### Localization readiness

- UI strings and some defaults are currently embedded in Python/QSS, while source/target language metadata is centralized in `src/backend/languages.py`.
- The system prompt already receives the selected target language dynamically; avoid hard-coding a language in shared prompt rules.
- When localization is implemented, load only the selected locale JSON plus a small fallback catalog. Do not eagerly parse every locale JSON into RAM. Keep prompt-language instructions separate from UI translations so models continue receiving the intended English technical prompt.

### Maintenance notes

- `MainWindow` and `TranslatorPanel` remain large orchestration/UI modules. Their event handlers are connected from `init_ui` and Qt signals; moving code without following these signal paths can silently break user workflows. Future refactors should extract cohesive controllers incrementally.
- OpenAI, xAI, Anthropic, OpenRouter, and DeepSeek are registered as unavailable scaffolds that inherit the shared `ProviderScaffold` implementation. The settings dialog blocks connection testing and saving until a maintainer supplies and verifies a real integration.
- `CredentialManager._ensure_connection_profiles` intentionally mirrors the active saved profile into legacy provider fields and removes the obsolete usage-group field while migrating old settings.
- Provider error handling contains broad catches around external API and image operations because those operations can fail independently. Narrowing them should preserve user-facing errors and batch continuation behavior.

## Data safety

- Do not commit `cache/api_config.json`, `cache/usage_history.json`, `cache/pricing_tables.json`, prompt files, or user projects. The API configuration can contain credentials.
- Imported provider price JSON remains user data and should merge by provider/model/plan according to the import behavior, not replace unrelated providers' rates.

## Review limits

- `git diff --check` completed without whitespace errors.
- Python runtime/lint checks were not run in this audit environment. The changes should be exercised in the project's Windows virtual environment before release.
