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

## Follow-up static audit (2026-11-13)

The pass reviewed all tracked Python modules under `src/`, plus `main.py`, `build_exe.py`, and `generate_icons.py`. It traced UI signal handlers, worker dispatch, provider registry entries, and references for suspicious low-use methods. This is a source-level audit only; it does not certify runtime behavior or third-party API compatibility.

### Confirmed findings to address before release

#### High — closing the window can leave a translation QThread running

- `MainWindow.closeEvent` only handles `is_batching`; a single-page request runs in `TranslatorPanel.active_worker` and is not joined or otherwise stopped on close.
- During batch close, `QThread.quit()` only asks the event loop to exit. The worker is executing a synchronous provider call and `wait(1000)` can time out while the HTTP request is still running (provider request timeouts are much longer). The handler then accepts the close event regardless.
- This creates a shutdown race and can produce a running-thread-destroyed error or an abrupt exit. A follow-up should use a safe close-pending state: request cancellation where supported, keep the window alive while the synchronous request finishes, and close only after worker completion. A forced thread termination is not recommended because it can corrupt Python/Qt state.
- References: `src/frontend/main_window.py:891-909`, `src/backend/translator.py:1130-1173`, `src/backend/ai_client.py:230-281`, and provider request timeouts in `src/backend/providers/gemini_provider.py:172` / `ollama_provider.py:159,244`.

#### Medium — request pacing is global across providers, despite its per-provider description

- `RequestPacer` stores last-start timestamps by provider, but holds one class-wide lock while sleeping. If a request for one provider is waiting for its interval, another provider cannot pass the same lock. Thus the implementation couples independent providers and can delay unrelated work.
- This is not dead code; it is on the request path for both single-page and batch translations. The next change should use per-provider locks (or reserve start times under a short global critical section and sleep after releasing it).
- Reference: `src/backend/ai_client.py:30-50,178`.

#### Medium — source-mode debug logging exposes prompts and model output by default

- `DEBUG_AI_LOGS` defaults to enabled in non-frozen runs because `MTS_DEBUG` defaults to `"1"`. The request log prints the full system prompt and page/context prompt, and response logging can print raw provider output and extracted text.
- These logs can contain user rules, story text, and sensitive page content. Packaged builds disable this path, but developers and source users are opted in unless they explicitly set `MTS_DEBUG=0`.
- Before public source distribution, consider defaulting diagnostics off and requiring an explicit opt-in. Keep token/status diagnostics available without content logging.
- References: `src/backend/ai_client.py:27,73-107,165-174`; Gemini thought summaries are also requested under the same default in `src/backend/providers/gemini_provider.py:163-169`.

### Dead-code and connection review

- No evidence was found that provider implementations registered in `PROVIDERS` are disconnected. Gemini and Ollama are active; OpenAI, xAI, Anthropic, OpenRouter, and DeepSeek deliberately inherit `ProviderScaffold` and are surfaced as unavailable placeholders. Keep them documented as scaffolds until real integrations replace them.
- `MainWindow.set_page_status` is connected to translation result/error paths; `mark_current_modified` is called by the editor change handler. Neither is dead.
- `CredentialManager.update_provider_credentials` has no internal callers in the current source tree. It is fully implemented and documented, so classify it as an unused public/helper candidate rather than deleting it without checking external integrations.
- `Paths.ensure_directories` has no internal caller but explicitly promises backward compatibility to external integrations. Retain it unless that compatibility promise is intentionally removed.
- `IconProvider`'s `"lock"` alias maps to the same asset as `"processing"`; no call site currently requests the alias. It is a safe cleanup candidate after confirming no external plugin depends on the state key.
- `BaseAIProvider` abstract methods and `ProviderScaffold` error results are required extension/fallback behavior, not dead code.
- The removed `src/utils/history.py` remains absent from the source tree and README tree.

### Comments and maintainability

- Complex lifecycle and persistence code already has useful docstrings/comments in `ProjectResetController`, `UsageManager`, `RequestPacer`, batch orchestration, prompt composition, and provider request handling. Avoid adding comments that merely restate a function name or each obvious assignment.
- The most valuable next comments are alongside the eventual fixes for worker shutdown and per-provider pacing, since they should explain lifecycle and concurrency invariants rather than narrate syntax.
- Localization remains deferred. Keep user-facing text identifiable during the later extraction pass, and do not translate provider payload/system rules as a side effect of this audit.

### Audit disposition

- Confirmed high/medium findings are recorded above; they were not silently changed during this documentation pass because they affect thread lifecycle, request scheduling, and privacy defaults.
- Unreferenced items are classified as candidates with compatibility context instead of automatically deleted. Static text search cannot prove that a public helper is unused by external scripts.
- No tests or GUI session were run. Recheck the thread shutdown behavior and cross-provider pacing in the Windows environment before calling the audit release-ready.
