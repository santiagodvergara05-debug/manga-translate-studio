# Technical Audit — Manga Translate Studio 1.6.0 Beta 3

Audit date: 2026-11-14
Purpose: final source and maintenance review before preparing the Windows executable.

## Scope and limits

Reviewed the tracked application code, provider and worker paths, UI signal wiring, JSON persistence and loading, locale catalogs and manifest, build entry points, README, and the 1.6.0 changelog. This is a source-level audit. It does not certify live API behavior, translation quality, every GUI layout, or a packaged executable.

The application could not be launched or compiled from this audit environment because Windows denied starting the repository's Python executable. Therefore the official locale release check, Python compilation, GUI smoke test, and executable build remain required in the developer's Windows environment. A PowerShell structural check parsed all ten locale catalogs and compared their 328 source keys, placeholders, and manifest display names; it did not assess translation quality or reproduce the checker's SHA-256 approval calculation.

## Changes made during this audit

### Request pacing

- Replaced the single provider-wide pacing lock with a lock per provider. Requests to the same provider remain serialized at the selected LOW, HIGH, or MAX minimum interval. Waiting on one service no longer blocks a different service.
- The short registry lock is used only to obtain the provider lock and is released before waiting. This preserves the per-provider timestamp invariant without holding a global lock during sleep.

### Diagnostic privacy

- Prompt/request and raw-response diagnostic logging is now opt-in for source runs with `MTS_DEBUG=1`; the default is off. Packaged builds continue to disable it.
- Gemini thought summaries follow the same opt-in setting. This avoids logging story text or requesting debug-only thought summaries during ordinary source use.

### Application shutdown

- Closing the main window during an active single-page or batch translation is now deferred until the synchronous provider worker has returned.
- A batch close stops dispatching queued pages and lets the in-flight request finish. It no longer relies on `QThread.quit()` or a one-second wait to interrupt a synchronous HTTP call; those cannot safely stop that call.
- Close-pending translation result handlers avoid opening modal error dialogs while shutdown is waiting.

### Localization and documentation

- The current locale index lists ten interface languages and the application loads the selected catalog rather than eagerly parsing every language file.
- README now describes English as the primary source catalog, additional catalogs generically, and `locales/index.json` as the available-language manifest. It intentionally does not enumerate locale JSON files in the tree.
- The Beta 3 changelog records the added catalogs, UI work, and audit changes.

## Findings and disposition

### Resolved in this audit

1. **Cross-provider pacing contention — fixed.** The request pacer had per-provider timestamps but held a shared lock while sleeping. Independent providers could block each other. Per-provider locks now match the documented behavior.
2. **Content diagnostics enabled by default — fixed.** Source-mode logs could include prompts, page text, and model responses. Those diagnostics now require explicit `MTS_DEBUG=1` opt-in.
3. **Unsafe window teardown during active requests — fixed in source.** The prior close path could accept the event while a synchronous provider call still ran, and did not account for the single-page worker. Shutdown now waits asynchronously for both worker paths. A Windows GUI test is still needed to confirm the lifecycle in the actual Qt runtime.
4. **Stale repository documentation — fixed.** README no longer describes localization as pending and the directory tree represents the current runtime layout without listing each locale file.

### Dead-code and connectivity review

- No disconnected active Gemini or Ollama provider path was identified. Both are registered and used by the client manager.
- OpenAI, xAI, Anthropic, OpenRouter, and DeepSeek files are intentional unavailable scaffolds surfaced as unavailable in settings. They are not dead code; they are extension points and should remain clearly marked until real provider integrations exist.
- `BaseAIProvider` abstract methods and provider scaffold/error results are required contracts and fallback paths.
- `MainWindow.set_page_status` and `mark_current_modified` are connected to status and editor-change flows. They must not be removed as unused helpers.
- `CredentialManager.update_provider_credentials` has no in-tree caller, but is a complete public/helper operation. Keep it unless external integration compatibility is intentionally dropped.
- `Paths.ensure_directories` has no in-tree caller and carries a backward-compatibility promise. Keep it for now; remove only with an explicit compatibility decision.
- The `IconProvider` `lock` alias currently resolves to the same asset as `processing`, and no in-tree call requests the alias. This is a low-risk cleanup candidate, not a confirmed runtime defect; retain until external consumers are ruled out.
- `src/utils/history.py` and `src/utils/system_info.py` are absent, and no in-tree imports reference them. Hardware telemetry is not needed for current usage/pricing features.

### Memory and JSON observations

- Runtime configuration and prompt option JSON are read at manager/dialog initialization, not repeatedly from a periodic UI refresh.
- Usage history is capped at 10,000 entries. Its manager caches parsed content and invalidates that cache after writes/clears or when the file signature changes. This avoids parsing the whole history on each refresh, while still retaining the bounded list in memory.
- Price tables are user-editable and loaded through the usage manager. Imported price JSON merges rows so unrelated providers/models are retained.
- Locale catalogs are selected through the small `locales/index.json` manifest. The UI should continue loading only the selected catalog plus its fallback instead of parsing every locale catalog into RAM.
- `MainWindow.image_sessions` retains decoded page arrays until project reset. Large image series may consume significant memory. This cache supports revisiting pages; consider a measured bounded LRU/active-page policy if profiling shows material memory pressure. No speculative eviction was introduced in this audit.

### Localization review

- Ten locale catalog entries are present: English plus Spanish, Brazilian Portuguese, French, Simplified Chinese, Traditional Chinese, Korean, Japanese, Indonesian, and Arabic.
- Structural validation in this review found valid JSON, 328 source keys per catalog, matching placeholder sets, and locale names aligned with the index. This does not review whether translations are idiomatic, complete in meaning, or visually correct at every display size.
- The repository's `tools/check_locales.py --release` remains the authoritative release gate because it validates approval markers and source/catalog fingerprints. It could not be run here.
- Arabic and longer translated labels need a visual RTL/layout pass in the real application. The README tree uses `locales/index.json` (the actual filename and runtime manifest), not a new `language.json` file.

## Pre-executable release checklist

Run these from the repository's Windows PowerShell environment with the project virtual environment available:

```powershell
python tools/check_locales.py --release
python -m compileall -q main.py src tools build_exe.py generate_icons.py
python main.py
python build_exe.py
```

Before publishing the executable, smoke-test at minimum:

- Start and close the app while a single-page request is active and while a batch request is active.
- Confirm batch cancellation stops pending pages but lets the active provider call finish without a Qt thread-destroyed error.
- Confirm LOW/HIGH/MAX pacing remains per provider and that separate providers do not serialize behind each other's delay.
- Open every interface catalog, including Arabic, and inspect header sizing, right-to-left behavior, long labels, API settings, rules, help, and status messages.
- Verify that credentials, prompt files, usage history, pricing state, project images, and generated output are not bundled as user data or committed.
- Run the packaged build from a clean directory to ensure assets, locale files, and the locale manifest are included and the fallback works.

## Audit conclusion

The confirmed source-level issues found in request pacing, diagnostic defaults, and worker shutdown have been corrected. No additional confirmed dead application path was found; low-use helpers and provider scaffolds are retained where they serve compatibility or extension purposes. The code is ready for developer-side Windows validation, but this audit does not claim that compilation, GUI checks, API integration checks, or executable packaging have passed.
