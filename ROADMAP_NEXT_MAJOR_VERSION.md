# Roadmap for the Next Major Version

This document is an implementation guide for the next major release of Manga Translate Studio. It describes intended behavior, the existing code areas to inspect, compatibility concerns, and the validation expected before packaging. It is not authorization to change the current stable release branch without first confirming the target version and release plan.

## Goals

1. Let users request an English equivalent for comic sound effects when the source language uses Asian scripts, while retaining the existing SFX extraction and target-language localization behavior.
2. Add a separate **text extraction only** workflow that transcribes selected comic text into a dedicated JSON artifact without asking the model to translate it.
3. Review and update `TECHNICAL_AUDIT_1.6.0.md` for the new implementation before building the next executable.

## 1. Optional English SFX equivalent

### Intended behavior

- Add a user setting that enables or disables English equivalents for sound effects, for example `sfx_english_equivalent`.
- The option is meaningful only when SFX/onomatopoeia extraction is enabled. Disable its control when the parent SFX option is off, following the existing dependent-option pattern used for SFX meaning and duplicate suppression.
- When enabled, request the English equivalent only for SFX entities and only for source languages where the current prompt already supports this reference (`ko`, `ja`, and `zh`). Do not add the field to dialogue, narration, or outside-text entities.
- When disabled, omit the English-equivalent field from the requested schema and omit the corresponding instruction. The actual `direct` value must continue to be localized into the selected target language exactly as it is today.
- Preserve the existing behavior for older settings files: a missing setting must receive an intentional default, and malformed or unknown option data must not prevent startup.

### Existing code to inspect

- `src/backend/prompt_manager.py`: `DEFAULT_EXTRACTION_OPTIONS`, `_load_options()`, `save_options()`, `build_full_prompt()`, the conditional schema fields, and the prompt preview. Today the `sfx_en` field is added when SFX is enabled and `is_asian_source(src_lang)` is true.
- `src/backend/languages.py`: `ASIAN_LANG_CODES`, `is_asian_source()`, and the English-equivalent instruction in `get_sfx_rule_for_target()`.
- `src/backend/translator.py`: `RulesDialog` option definitions, dependency enable/disable behavior, and the SFX card rendering of `sfx_en`.
- `locales/en.json` and every secondary locale catalog: add translated title/help text for the new control; preserve matching keys and placeholders. Run the repository locale checker and approval/release workflow.
- Provider normalization and any export/rendering paths: confirm optional `sfx_en` survives successful extraction and remains absent when not requested. Do not add it to `.TXT` exports unless a separate product requirement explicitly calls for that.

### Implementation notes

- Keep the setting persisted with the other prompt options in `cache/prompt_options.json`; do not introduce a second preference store for this toggle.
- Treat the setting as subordinate to `sfx`. If SFX is disabled, no SFX-only schema fields or instructions should be emitted, regardless of the saved child setting.
- Keep source-language detection based on the selected language code/display value, not visual script guessing. Do not expand the supported Asian language set without reviewing the language-specific prompt behavior.
- Make the prompt preview use the same prompt-building function as actual requests so the displayed schema cannot drift from the sent schema.
- Decide and document the default explicitly. The current behavior automatically asks for `sfx_en` for Asian-script sources when SFX is enabled; preserving that behavior suggests a default of enabled. If the product instead chooses an opt-in default, call out the behavior change in release notes.

## 2. Text extraction only workflow and JSON format

### Intended behavior

Add a mode that transcribes comic text and does not translate it. This mode must be a distinct workflow from the current translation workflow, which generates target-language text and supports the Manga Cleaner `.TXT` script integration.

The extraction-only workflow must:

- Extract speech bubbles and narration/caption text, plus SFX/onomatopoeia when enabled.
- Allow users to disable SFX extraction. Disabled entity categories must be explicitly excluded from both the prompt and the expected output.
- Preserve exact source text in reading order and identify each entity's category (`bubble`, `narration`, or `sfx`). Review whether the existing `outside` category should be offered in this mode; do not silently change the stated required scope.
- Write extraction results to a dedicated, documented JSON file format. Do not overwrite, reinterpret, or silently convert existing translation `.TXT` scripts or translation data.
- Accept and validate that extraction-only JSON on import, with clear errors for malformed JSON, unsupported schema versions, missing required fields, or invalid entity types.
- Keep translation-specific fields such as target language, variants, subtext, and translated `direct` text out of the extraction-only contract unless a future requirement explicitly adds them.

### Design before implementation

Before coding, inspect how page results are currently represented and persisted. `TranslationResult` carries a `bubbles` list; `BaseAIProvider.normalize_bubbles()` normalizes translation entities; the translator panel renders these entities and synchronizes translation scripts. Define a separate versioned JSON contract rather than assuming the existing translation response schema is automatically a suitable save-file format.

The implementation plan should decide and document:

- File scope: per-page extraction JSON, one project-level JSON containing page entries, or both. Prefer one predictable project-level file unless the existing workflow provides a strong reason for per-page files.
- A schema version field, stable page identity (relative path or stable page key), entity ordering, entity type, exact `original` transcription, and optional source-language/medium metadata.
- Whether empty pages are represented as an empty entity list, and how re-extraction merges or replaces data for a page.
- Where the output is saved, how users choose/load it, and how the UI makes the current mode visible.
- Whether users can edit extracted text in the existing entity editor. If reused, ensure translation controls are hidden or disabled and do not imply a translation exists.
- How to prevent loading an extraction-only file as a translation script, or vice versa, and how to report format mismatch without losing data.
- How older application data and missing optional fields are handled. Import should validate before modifying in-memory or on-disk project state.

### Code areas to inspect

- `src/backend/prompt_manager.py`: create a mode-specific prompt and JSON schema. Extraction-only prompts must request exact transcription and entity type, with no target-language instruction or translation fields. Reuse existing entity-category toggles where their meaning matches; keep SFX dependent sub-options unavailable if they require translated SFX output.
- `src/backend/translator.py`: inspect request dispatch, result handlers, entity cards, output controls, and existing `.TXT` import/export. Add explicit mode selection and mode-aware controls without breaking normal translation.
- `src/backend/providers/base_provider.py`: decide whether provider response normalization should be shared or split. Avoid making translation fields mandatory for extraction-only responses. Validate entity types and text while retaining the exact transcription (do not apply translation cleanup that changes the original).
- `src/backend/providers/gemini_provider.py` and `src/backend/providers/ollama_provider.py`: verify both provider paths honor the chosen prompt/schema and return a consistent result; inspect finish reasons, malformed/truncated JSON handling, and empty-page behavior.
- `src/backend/ai_client.py` and `src/frontend/main_window.py`: follow worker dispatch, success/error states, page status, batch operation, reset behavior, and per-page result storage for the new mode.
- `src/utils/paths.py`, `src/frontend/project_reset.py`, and persistence helpers: define the output location, project reset semantics, and safe handling of missing or invalid files.
- `src/frontend/help_system.py` and localization catalogs: explain the mode and add all visible strings to the localization system.
- `build_exe.py` and `MangaTranslate.spec`: ensure the application code and any schema/template resources required at runtime are packaged. User-generated extraction JSON must remain external runtime data, not bundled into the executable.

### Compatibility and data-safety requirements

- Existing translation mode remains the default for existing installations unless a deliberate migration is approved.
- Existing `cache/prompt_options.json` files continue to load; new keys get explicit defaults.
- Do not change the Manga Cleaner `.TXT` format or script synchronization semantics as a side effect of adding JSON extraction.
- Detect format/mode mismatch before import and show a localized, actionable message.
- Save atomically (temporary file then replace) where practical, and preserve the prior valid JSON if a write fails.
- Do not silently discard unknown fields from a newer schema version. Reject unsupported major schema versions with a clear message or provide a documented forward-compatible handling strategy.
- Do not place API credentials, prompts, page images, or unrelated usage history in the extraction JSON.

## 3. Required review of the 1.6.0 technical audit before the next executable

`TECHNICAL_AUDIT_1.6.0.md` documents the 1.6.0 source audit and its remaining Windows validation. Keep its historical findings accurate. Before the next major-version executable is built:

1. Perform a new source audit for the SFX English-equivalent toggle and extraction-only JSON mode; do not mark the 1.6.0 audit as having covered code that did not exist then.
2. Add a new, dated follow-up section or create a version-specific audit document. Record inspected files, findings, fixes, unresolved issues, and exact validation results.
3. Review dead code and call/signal connectivity introduced or made obsolete by the new modes. Remove code only when repository-wide references and compatibility obligations have been checked; explain retained extension points.
4. Review JSON schema validation, atomic writes, import/export boundaries, mode switching, project reset, and failure handling.
5. Run locale structural/release validation, Python compilation, GUI checks, provider checks, and packaged-executable smoke checks in the Windows developer environment. Record which checks actually passed; source inspection alone is not an executable audit.

## Acceptance checklist

- [ ] English SFX equivalent can be enabled and disabled independently of the primary SFX extraction toggle, with the child control correctly disabled when SFX is off.
- [ ] Prompt preview and provider request contain the same conditional SFX fields and instructions.
- [ ] Non-Asian source, SFX-disabled, and English-equivalent-disabled combinations do not request `sfx_en`.
- [ ] Existing settings without the new option load with the documented default.
- [ ] Extraction-only prompt requests exact source transcription for bubbles and narration, and SFX only when enabled; it requests no translation or variants.
- [ ] Extraction-only JSON schema is versioned, validated, and documented; malformed or mismatched files do not alter existing project data.
- [ ] Translation `.TXT` workflow and existing projects retain their current behavior.
- [ ] Single-page and batch extraction work with each available provider and handle empty, malformed, truncated, and failed responses visibly.
- [ ] All new UI text is localized, locale catalogs pass the release checker, and long translations fit the interface.
- [ ] Help and README explain both modes, output locations, JSON format, and compatibility behavior.
- [ ] New dated audit review is complete and remaining limitations are stated before building the next `.exe`.
- [ ] Clean packaged build contains required application resources and passes Windows smoke checks without bundling user data.

