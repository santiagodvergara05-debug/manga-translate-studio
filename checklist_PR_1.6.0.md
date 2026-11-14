# Manga Translate Studio 1.6.0 — Beta Closure and Release Checklist

This checklist consolidates the applicable requirements from `CONTRIBUTING.md`, `TRANSLATION.md`, and the 1.6.0 change/audit records. Use it to review the final Beta 3 diff, prepare the executable, and close the beta before publishing the stable 1.6.0 release.

This document records work to verify; checking a box means the item was actually completed and reviewed. Do not mark an unavailable check as passed.

The checks marked below are limited to source review, repository documentation, static packaging-path inspection, locale structure validation, and `git diff --check`. They do not indicate that Python execution, GUI/API behavior, or executable packaging has been tested.

## 1. Final source review

- [x] Review the complete `git diff` and confirm every change is intentional, connected to the application, and understood by the submitter.
- [x] Confirm the final code follows the project architecture: UI code does not make provider requests or construct provider payloads directly; provider and business logic stay in their backend modules/managers.
- [x] Trace affected imports, signal/slot connections, event handlers, workers, status updates, persistence paths, and error paths. Remove genuinely dead code only after confirming it has no compatibility or extension role.
- [ ] Ensure all comments, docstrings, identifiers, logs, and error traces added to source code use technical English and explain non-obvious behavior rather than restating syntax.
- [ ] Confirm no TODO/debug scaffolding, temporary code, stale beta-only behavior, or misleading documentation remains in the stable release path.
- [ ] Confirm no hard-coded credentials, API keys, tokens, account identifiers, user prompts/rules, personal usage history, or private pricing configuration appear in files or commit history.
- [ ] Confirm temporary images, test outputs, cache files, logs, `__pycache__`, virtual environments, and PyInstaller build artifacts are not staged.
- [x] Run `git diff --check` and resolve whitespace errors. Review line-ending warnings separately; warnings alone are not a failed check.

## 2. Python and application validation

- [ ] From the repository root, compile the application and tools:

  ```powershell
  python -m compileall -q main.py src tools build_exe.py generate_icons.py
  ```

- [ ] Launch the source application with `python main.py`; confirm startup and shutdown have no traceback, uncaught exception, or unexpected warning.
- [ ] Check single-page translation and batch translation with an available provider. Confirm normal success, empty-page, server-busy/rate-limit, safety-blocked, and unrecoverable-error states remain understandable and do not break the queue.
- [ ] Test closing the app during an active single-page request and during an active batch. Confirm the app waits for the synchronous request to finish, queued batch pages stop dispatching, and there is no `QThread: Destroyed while thread is still running` error.
- [ ] Test batch pause/resume/cancel and retranslation of a page with existing text. Confirm active/queued pages are locked as intended, completed pages remain reviewable, previous content survives until a replacement response arrives, and cancellation restores unsent pages.
- [ ] Confirm manual edits mark pages Modified and script synchronization updates the correct page states.
- [ ] Confirm `ProjectResetController.reset()` clears project/session state, active queues, worker/UI state, page image references, and timers without deleting persistent user settings, credentials, or on-disk projects.
- [ ] Verify HIGH/LOW/MAX pacing in single-page and batch flows. Requests to one provider must respect that provider's interval; waiting for one provider must not block another provider.
- [ ] Confirm prompt diagnostics are off by default and only enabled for source runs through explicit `MTS_DEBUG=1`; packaged builds must not emit sensitive prompt or raw-response diagnostics.

## 3. Provider and usage behavior

- [ ] Confirm Gemini and Ollama are registered and their settings, model selection, connection checks, request payloads, normalized responses, and errors work with valid credentials/connections.
- [x] Confirm OpenAI, xAI (Grok), Anthropic (Claude), OpenRouter, and DeepSeek remain clearly marked unavailable scaffolds until their integrations have been implemented and tested; they must not make accidental requests or save as active providers.
- [ ] Confirm Gemini thinking configuration is sent only for supported models and is reflected accurately in the UI. Do not infer thinking support for a provider/model that does not expose it.
- [ ] Confirm usage and cached-token counts are recorded only from metadata reported by the provider. Missing cache metadata must remain “not reported,” not be inferred as zero or a cache hit.
- [ ] Confirm price estimates use the imported/editable provider, model/prefix, plan, and per-million-token rates; unknown/unconfigured rates must be shown as not configured rather than silently treated as free.
- [ ] Confirm price-table import merges matching rows without deleting unrelated providers/models, and that clear/remove operations persist only after the intended save action.
- [ ] Confirm usage history clearing and profile selection behave as documented; no obsolete Usage group UI or grouping behavior remains.
- [ ] Confirm Gemini RPD controls are Gemini-specific, persist correctly, and do not appear as universal provider limits.
- [ ] Confirm rate/usage history and pricing data contain no prompts, images, API keys, or other secrets.

## 4. Prompt, image, canvas, and script compatibility

- [ ] Verify user-configurable extraction options persist, update the read-only prompt preview, and respect dependencies (SFX meaning and repeated-SFX suppression require SFX extraction).
- [ ] Confirm optional SFX meanings, tone notes, variants, R19 vocalization guidance, and repeated identical SFX handling match the selected options and do not leak into exported `.txt` dialogue unless explicitly part of the script format.
- [ ] Confirm shared prompt rules do not hard-code a target UI language; target-language behavior is generated from the selected translation language. Keep technical prompt text separate from UI localization catalogs.
- [ ] Confirm prior-page context includes text only, is invalidated when the target language changes, and never resends previous page images.
- [ ] Verify image processing preserves the full page for model analysis and confirm any image resizing/encoding behavior is intentional and documented.
- [ ] Test high-resolution and long vertical manga/manhwa pages. Mouse wheel scrolls the canvas; Ctrl+wheel and Alt+wheel zoom around the pointer; pan and image-change reset behavior remain usable.
- [ ] Confirm script export retains the Manga Cleaner protocol: `<translation> ... </translation>`, `Image X [filename]` structure, expected empty-page behavior, Unicode NFC normalization, and filename matching options.
- [ ] Confirm `.txt` export contains only intended translations and excludes editor-only notes such as tone/subtext or SFX meaning.

## 5. UI localization and catalog integrity

- [x] Confirm `locales/en.json` remains the required primary/source catalog and `locales/index.json` remains the actual language manifest. Do not rename it to `language.json` unless runtime code and documentation are deliberately migrated together.
- [x] Confirm all available catalogs are represented in `locales/index.json`; this release currently targets English, Spanish, French, Brazilian Portuguese, Simplified Chinese, Traditional Chinese, Korean, Japanese, Indonesian, and Arabic.
- [x] Ensure user-visible strings are requested through `tr()`/`tr_label()` and have non-empty source values in `locales/en.json`. Do not translate stable IDs, model names, provider IDs, paths, shortcuts, formats, or values used by program logic.
- [x] Confirm named placeholders are structurally consistent across the locale catalogs.
- [ ] Review required HTML, keyboard shortcut tokens, literal strings, and file-format tokens in each changed translation in context.
- [ ] Review translations against English for meaning, intent, and tone. Do not add unrelated material, change meaning, or introduce profanity, slurs, hateful/harassing, or otherwise prohibited content absent from the source.
- [ ] Attribute localization contributors accurately. Structural validation, machine translation, and AI code review do not count as a fluent human language audit; keep audit status truthful.
- [ ] Run the catalog inspection and approval workflow from the repository root when source strings/catalogs have changed:

  ```powershell
  python tools/check_locales.py --approve
  python tools/check_locales.py --release
  ```

- [ ] Resolve every missing, empty, extra, or placeholder-mismatched key. Do not manually edit generated fingerprints; let `check_locales.py` generate them.
- [ ] Review catalog approvals after any `en.json` change. A changed source invalidates secondary catalog approvals until they are rechecked.
- [ ] Visually inspect English and every available UI language, including Arabic RTL, long translated labels, header resizing/margins, tooltips, dialogs, help pages, extraction settings, API settings, batch/page states, and status/timer text.
- [x] Confirm runtime startup reads the manifest and only the selected locale (plus English only when needed for fallback); it must not parse all locale JSON files into memory.
- [x] Confirm all locale JSON files and `locales/index.json` are included in the executable, while developer-only `*.sources.json` reports are excluded.

## 6. Community files and documentation

- [x] Confirm `README.md` describes current features and the current project tree. In the tree, show `en.json`, a generic `<language>.json` entry, and `index.json`; do not enumerate every locale JSON file.
- [x] Confirm `CHANGELOG_1.6.0.md` includes all Beta 3 changes, additions, removals, and relevant behavior changes without presenting unfinished beta notes as stable-release guarantees.
- [x] Confirm `TECHNICAL_AUDIT_1.6.0.md` distinguishes fixed findings from remaining risks and does not claim unrun tests or build steps passed.
- [ ] Confirm `CONTRIBUTING.md` and `TRANSLATION.md` agree on language/provider contribution steps, AI-agent-assisted contributions, audit responsibility, localization integrity policy, and release checks.
- [ ] Confirm provider contribution/help links and credits use the intended repository/user identifiers and do not expose a maintainer's private full name or account details beyond what they have chosen to publish.
- [ ] Confirm community price JSON files use the documented schema, authoritative source/date notes, and no local account/usage data. Keep user-imported/editable rates in ignored runtime cache only.
- [x] Confirm `.gitignore` excludes credentials, runtime cache contents, logs, project images, translated output, and packaging artifacts while allowing intentional reference catalogs and locale files.

## 7. Windows executable packaging

- [ ] Run the official locale release check and Python compile check successfully before packaging.
- [ ] Run `python build_exe.py` from the project's Windows environment and resolve all PyInstaller errors and warnings that affect runtime.
- [ ] Confirm the generated `dist/MangaTranslate` folder includes `MangaTranslate.exe`, required assets/styles, all available UI catalogs, and the locale manifest.
- [ ] Confirm runtime directories (`cache`, `logs`, `translations`, `processed`) are created as expected and are outside the bundled `MangaTranslate_Data` resources where the portable layout requires them.
- [ ] Test the executable from a clean output folder, without relying on the source tree or developer virtual environment.
- [ ] Verify a fresh install starts in English or the intended default language, locale selection persists, and invalid/missing locale data recovers to English with a clear message.
- [ ] Test API settings, a connection check, single translation, batch translation, cancel/close behavior, Usage / Prices, help, prompt options, script export, project reset, and application shutdown in the packaged build.
- [ ] Verify no credentials, prompts, user rules, usage history, imported prices, project files, logs, or other private local state were bundled into the release archive.
- [ ] Record the executable's version, architecture, build date, and any required runtime/dependency notes in the release material.

## 8. Beta closure and stable 1.6.0 release

- [ ] Confirm all release-blocking issues from the beta have been fixed or explicitly listed as known issues with user impact and workaround.
- [ ] Remove the temporary `BETA` label from the stable application version/title and update the version constants/spec metadata consistently to `1.6.0`.
- [ ] Review compatibility notes for prior-version settings and data. Clearly state which existing local data is compatible, migrated, or not guaranteed to migrate; do not imply that reset removes persistent credentials or user files unless it does.
- [ ] Finalize the 1.6.0 changelog and stable README/help references; merge Beta 1/2/3 notes into the cumulative stable record as intended.
- [ ] Confirm the release commit contains only reviewed files, then create the stable tag/release from the intended commit.
- [ ] Attach the verified executable/archive and source archive; publish checksums if the release process supports them.
- [ ] After publication, download the release artifact to a clean location and repeat a short startup/translation smoke test.
- [ ] Close the beta phase only after the published stable artifact passes the clean-folder smoke test and the release notes match the actual files.

## 9. AI-assisted contribution responsibility

- [ ] If an AI agent assisted, identify the areas it helped with in the PR or release notes where appropriate.
- [ ] Personally review every AI-assisted change, trace its call paths and data flow, and confirm there is no dead or unintended code.
- [ ] Confirm the final code is understood, licensed compatibly, and safe to publish; AI output is not a substitute for maintainer review.
- [ ] Confirm no secrets or private user data were supplied to an AI agent or included in the diff.
- [ ] Report honestly which checks were run, which passed, and which remain unverified. The submitter remains responsible for all submitted lines.

## Final sign-off

- [ ] Source review complete; no unaddressed release-blocking audit finding remains.
- [ ] Locale release validation, compile, GUI/source smoke test, and executable build passed.
- [ ] Clean-folder executable smoke test passed.
- [ ] Changelog, README, contribution/localization docs, version metadata, and release assets agree.
- [ ] Stable 1.6.0 release is ready to publish and the beta can be closed.
