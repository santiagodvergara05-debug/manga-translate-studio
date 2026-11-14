# Manga Translate Studio 1.6.0 — Change Log

This is the cumulative change record for the **stable 1.6.0 release**. It covers the development work from Beta 1 through Beta 3 and the final release preparation. Beta headings preserve the history of when work entered the project; the feature inventory describes the resulting 1.6.0 code.

## Release overview

Version 1.6.0 is a substantial reconstruction and redesign of the application. Work across the beta cycle replaced or reorganized major parts of provider configuration, request handling, usage tracking, page review, localization, and packaging. The project was close to having to rebuild these areas around the new requirements; the work therefore includes both new capabilities and changes to the architecture and workflows that connect them.

This changelog is the stable release's detailed record. Features explicitly marked as removed or unavailable below are not active capabilities of the stable application.

## Beta 1 — new settings, usage tracking, and review workflow

- Added the API and Model Settings dialog and saved connection profiles. Profiles hold a provider, endpoint or credentials, selected model, and applicable model settings; users can add, rename, switch, and remove profiles.
- Added Gemini model-aware thinking controls, including supported Gemini 3 levels and Minimal/High options for applicable Gemma 4 models. Thinking settings are not sent to unsupported providers or models.
- Added LOW and HIGH request pacing for single-page and batch translation. LOW enforces at least 4.1 seconds between application request starts per provider; HIGH enforces at least 1.5 seconds. Provider processing and retry delays are separate.
- Separated stable system instructions from page-specific context. Gemini receives the system instruction through its system-instruction field; Ollama receives it as a system message/field. Each request includes the current page image rather than resending earlier page images.
- Added handling for provider-reported input, output, thinking, request-count, and cached-input usage where available. The application reports returned cache counts rather than inferring cache hits.
- Added configurable extraction options for SFX, narration, floating outside text, translation variants, tone notes, and R19 vocalization guidance. Added optional SFX meanings as editor guidance, excluded from exported scripts.
- Added a read-only system-prompt preview that reflects the selected medium, languages, user rules, and extraction options.
- Added target-aware SFX localization rules and language-pair checks for page continuity.
- Added Usage / Prices with local request history, editable USD-per-million-token price rows, optional cached-input rates and plan variants, price JSON import/export, and community reference price tables for Google and Ollama.
- Added Gemini RPD limit and usage tracking. The counter is local, grouped by the then-current usage identity and model, and follows the Pacific calendar date; it is not a live Google quota query.
- Added elapsed time for individual translations and whole batches, batch review while processing continues, and improved canvas scrolling and zoom for long pages.
- Expanded Help with guidance for thinking, extraction options, usage, pricing, cache reporting, RPD, and pacing.
- Removed RAM/hardware telemetry and its `psutil` dependency, the separate Gemini RPM/TPM limits view, and prefilled price/RPD values for new installations.

## Beta 2 — page states, profiles, and additional workflows

- Replaced the optional Usage group with saved connection profiles as the identity used for usage history and Gemini RPD tracking.
- Added MAX request pacing: at least 0.5 seconds between application request starts. The Help guidance documents theoretical ceilings of about 14.6 RPM for LOW, 40 RPM for HIGH, and 120 RPM for MAX. These are pacing ceilings; provider processing time can reduce actual throughput, and MAX can trigger provider rate limits or HTTP 429 responses.
- Moved Gemini RPD editing into API Settings, where the controls appear only for Gemini; kept a compact RPD indicator in the main header.
- Added optional suppression of repeated identical SFX lettering on the same page. It is disabled by default, requires SFX extraction, and does not deduplicate dialogue or other entity types.
- Added explicitly unavailable provider scaffolds for OpenAI, xAI, Anthropic, OpenRouter, and DeepSeek. They make no API calls and cannot be used as active integrations until implemented and verified.
- Added distinct page states and icons for queued work, active processing, retranslation of existing text, provider busy/rate-limit responses, local edits, and script synchronization. Manual editor changes now mark the page as modified.
- Kept existing text visible during retranslation and on provider errors. Successful responses replace the old result; empty-page responses clear it. Cancellation returns unsent pages to their prior states and preserves results from pages already processed.
- Corrected stale status/progress displays after batch completion and cancellation. Added a clear batch summary with completed, failed, pending, and elapsed-time information.
- Added Alt + mouse wheel as an additional canvas zoom shortcut alongside Ctrl + mouse wheel; ordinary wheel scrolling remains available for long pages.
- Removed the unused provider-logo directory and unused `src/utils/history.py` undo/redo module.
- Began the UI localization system: JSON catalogs, locale manifest and fingerprints, English fallback, migration and checking tools, and packaging support. Catalog migration and the initial language set were completed in Beta 3.

## Beta 3 — localization, interface refinement, and audit fixes

- Completed the UI localization layer with English as the required source catalog and nine additional interface catalogs: Spanish, Brazilian Portuguese, French, Simplified Chinese, Traditional Chinese, Korean, Japanese, Indonesian, and Arabic.
- Added a language selector to the main header, using catalog display names. Its width adapts to longer translated names, and Arabic receives right-to-left handling.
- Localized visible application UI, including the main window, API settings, extraction options, Help, page and batch status, dialogs, and pacing guidance. Provider/model identifiers, thinking values, file formats, and other stable logic identifiers remain unchanged.
- Kept interface localization separate from manga source/target language selection and prompt construction. Changing the interface language does not change the language requested from the model.
- Added selected-catalog loading with manifest and fingerprint verification. The runtime loads the small locale index and selected catalog rather than eagerly parsing all catalogs. An invalid or unverified selected catalog falls back to English with a warning.
- Made `locales/en.json` the sole source catalog for new UI strings; excluded generated source-location metadata and duplicate source sidecars from runtime packaging.
- Added string extraction, reviewed migration, catalog structure/placeholder/fingerprint checks, approval and release validation. Documented the workflow and localization integrity/review policy in `TRANSLATION.md`; updated `CONTRIBUTING.md` with localization and review guidance.
- Refined header layout for translated labels, including spacing around the API pace selector, placement of the language selector beside Usage / Prices, and flexible sizing for provider, model, thinking, status, and elapsed-time text.
- Localized active and completed request/batch statuses and the elapsed-work timer. The timer runs only during translation work, displays the elapsed duration while active, and retains the final duration when the job ends.
- Expanded the locale catalog as manual UI review identified missing labels, connection states, tooltips, and in-progress/completion messages.
- Updated README's project tree and localization description to show `en.json` as the primary catalog and `index.json` as the language manifest without listing every language JSON individually.
- Fixed request pacing so concurrent work for one provider does not block requests to another provider.
- Made prompt/request and raw-response diagnostics opt-in for source runs using `MTS_DEBUG=1`; packaged builds keep these diagnostics disabled.
- Made application shutdown wait safely for synchronous provider work. Closing during a batch stops dispatch of queued pages and lets the active request return before teardown.

## Stable 1.6.0 — release preparation

- Set the application version to stable `1.6.0`.
- Updated `build_exe.py` to validate required source/build inputs and every catalog listed in `locales/index.json`, then run `tools/check_locales.py --release` before invoking PyInstaller.
- Added post-build checks for the executable, bundled icon, stylesheet, locale manifest, and catalog files. The build creates the persistent runtime directories and prints the distribution layout.
- Kept the onedir distribution isolated under `MangaTranslate_Data` so it can coexist with Manga Cleaner without sharing bundled dependencies. The complete `dist/MangaTranslate/` folder, including `MangaTranslate_Data`, must be distributed; the `.exe` alone is insufficient.
- The developer's release build completed with PyInstaller 6.22.3 and Python 3.13.14. Its locale release check reported zero errors and warnings for the nine translated catalogs, each containing 328 source keys. This confirms the reported catalog/build validation; it does not claim a full GUI or live-provider test on every configuration.
- Updated README's setup and packaging guidance for the stable application and full-folder Windows distribution.

## Final 1.6.0 feature record

### Providers, profiles, and request handling

- Google Gemini and Ollama are the implemented provider integrations. Ollama supports local instances and compatible cloud `/v1` endpoints.
- API Settings provides saved profiles for provider credentials or endpoint, model, and applicable provider settings. Gemini thinking levels are exposed only where supported.
- Gemini's optional local RPD limit and counter are editable in API Settings. The header displays the current compact meter. Counters are profile/model-specific and use the Pacific calendar day; they are not fetched from Google's quota service.
- LOW, HIGH, and MAX pace application request starts per provider at minimum intervals of 4.1, 1.5, and 0.5 seconds. Their theoretical maxima are approximately 14.6, 40, and 120 request starts per minute. Actual throughput can be lower because of provider processing and retries; aggressive pacing can receive rate-limit responses.
- Provider responses are normalized for the editor and usage history. Token/cache figures are recorded only when the provider reports them; the application does not infer cache hits.
- OpenAI, xAI, Anthropic, OpenRouter, and DeepSeek remain unavailable scaffolds, not working integrations.

### Prompt and extraction configuration

- User rules and extraction settings are persisted in the local `cache/` directory. Options cover comic SFX, narration, floating text, translation variants, tone notes, R19 vocalization guidance, optional SFX meaning, and optional repeated-SFX suppression.
- SFX meaning is editor guidance and is not exported into the translation script. Repeated-SFX suppression affects only identical SFX lettering on one page and requires SFX extraction.
- The read-only prompt preview reflects the active medium, source and target languages, user rules, and extraction options. Stable system instructions are kept separate from page-specific context.
- Page continuity checks the language pair before using prior translations. Earlier page images are not resent with a new page request.

### Usage and pricing

- Usage / Prices shows local request records by provider/profile, reported tokens and cache counts where available, and estimated cost based on the currently matching provider/model/plan rates.
- Price rows are editable in USD per million tokens and support optional cached-input rates and plan variants. JSON import/export merges matching provider/model/plan rows while retaining unrelated ones. Community Google and Ollama price references are available for user-selected import.
- A new local price table does not require bundled reference rates; migration code removes recognized legacy sample rows from existing tables. Missing rates are identified as not configured rather than treated as zero-cost.
- Clearing request history preserves price configuration and Gemini RPD counters. History does not store prompts, page images, API keys, or tokens.

### Page review, batch work, and scripts

- Page indicators distinguish unassigned, queued, processing, updating an existing result, ready, empty, provider busy, safety blocked, locally modified, script synchronized, and unrecoverable error states.
- During retranslation, prior text stays visible until a response arrives. Success replaces it; a successful empty result clears it; API/provider errors leave it intact.
- Batch work is sequential. Completed pages remain reviewable/editable while work continues; active and queued pages are locked. Cancellation stops unsent work, restores queued pages' earlier states, and preserves completed results.
- Manual edits, variant changes, and dialogue add/remove actions mark the page as locally modified. Loading a script or successfully writing it marks pages as script synchronized.
- `.TXT` scripts preserve the `<translation>...</translation>` contract and are synchronized without editing the source manga images. The app supports creating/loading scripts and writing the project dialogues into the selected script.
- Active jobs show elapsed time and finished jobs retain their duration in the status/header. Idle state does not present a running timer.
- Project reset clears the current in-memory project/session and translation work state while preserving files on disk, configured API credentials, and persistent user settings.

### Interface, canvas, and localization

- The header presents the active provider, model, applicable thinking setting, request/batch status and duration, API pace, interface language, and Gemini RPD indicator.
- Canvas wheel scrolling navigates long pages; Ctrl or Alt + wheel zooms; selecting an image resets the viewport to the top. Space supports panning and middle click restores 1:1 zoom.
- Ten interface languages are currently registered in `locales/index.json`: English, Spanish, Brazilian Portuguese, French, Simplified Chinese, Traditional Chinese, Korean, Japanese, Indonesian, and Arabic.
- The interface-language catalogs are separate from translation source/target language choices. English is the source and fallback. The runtime loads only the selected catalog plus required fallback data and warns/falls back if verification fails.
- `tools/check_locales.py` is the structural/release gate for key parity, placeholders, locale manifest and fingerprints. A passing structural check does not establish linguistic quality or visual fit for every display and language.

### Privacy, reliability, and help

- Source-run prompt/request and raw-response diagnostics require explicit `MTS_DEBUG=1`; frozen executable builds keep them off.
- Closing during a synchronous API call is deferred until worker completion. Batch shutdown stops dispatching pending pages and allows the active call to return.
- Help documents request pacing, Gemini RPD, provider availability, page indicators, extraction options, usage/pricing, and localization-related interface behavior.

## Removed, replaced, and intentionally unavailable

- **Usage group:** removed and replaced by saved connection profiles as the history/RPD identity.
- **Gemini limits tab:** removed; RPM/TPM and external-request table are not part of 1.6.0. Gemini RPD remains a separate optional local tracker.
- **RAM/hardware widget:** removed with `src/utils/system_info.py` and the `psutil` dependency.
- **Provider logo directory:** removed because provider names are shown as text and no code uses those logo files.
- **Undo/redo module:** removed `src/utils/history.py`; the reviewed module was not connected to active workflows.
- **`en.source` sidecar:** not used. `locales/en.json` is the single English source catalog; generated `*.sources.json` metadata is developer-only and excluded from builds/versioned runtime content.
- **Additional provider names in settings:** OpenAI, xAI, Anthropic, OpenRouter, and DeepSeek are visible contribution scaffolds only. They do not send requests.
- **Translation-engine scope:** interface localization does not localize or rewrite model prompts, manga source text, or target-language instructions.

## New and maintained repository components

- `src/backend/usage_manager.py` — local usage history, price management, reported usage/cache metadata, profile identity, and Gemini RPD persistence.
- `src/frontend/api_settings.py` and `src/frontend/usage_pricing.py` — provider/profile settings and usage/pricing UI.
- `src/backend/providers/` — implemented Gemini/Ollama integrations, provider contract, and explicitly unavailable scaffolds for other providers.
- `assets/icon_waiting.svg`, `icon_updating.svg`, and `icon_script_synced.svg` — queued, retranslation, and script-synchronization indicators.
- `locales/en.json`, `locales/index.json`, and the registered catalogs — source strings, language manifest, and translations.
- `src/utils/i18n.py` and `tools/check_locales.py`, `extract_strings.py`, `migrate_to_tr.py` — locale runtime, extraction/migration workflow, verification, approval, and release validation.
- `build_exe.py` — validated isolated PyInstaller onedir build and distribution-resource verification.
- `TRANSLATION.md`, `CONTRIBUTING.md`, `TECHNICAL_AUDIT_1.6.0.md`, and `checklist_PR_1.6.0.md` — localization policy/workflow, contributor review, audit record, and release checklist.
- `Pricing_Models_Providers/` — community reference price data for user import; these files are not the user's private runtime price table.

## Local runtime data

The application creates or uses local, git-ignored data under `cache/`, `logs/`, `translations/`, and `processed/`. This includes provider settings and saved profiles, prompt/user rules, prompt options, pricing/RPD state, usage history, interface-language choice, logs, and user scripts/output. These user-specific files are not part of the repository's source catalogs or the packaged default user data.
