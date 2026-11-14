# UI Localization

This guide explains how to translate the **application interface**. It does not cover manga text or model prompts. `locales/en.json` is the source catalog; `locales/index.json` is the language manifest.

## Available interface languages

The catalogs currently registered in `locales/index.json` are:

| Code | Language |
|---|---|
| `en` | English |
| `es` | Spanish (Español) |
| `pt-BR` | Portuguese (Brazil) (Português do Brasil) |
| `fr` | French (Français) |
| `zh-CN` | Chinese, Simplified (简体中文) |
| `zh-TW` | Chinese, Traditional (繁體中文) |
| `ko` | Korean (한국어) |
| `ja` | Japanese (日本語) |
| `id` | Indonesian (Bahasa Indonesia) |
| `ar` | Arabic (العربية) |

These are interface languages. The source and target languages used to translate manga are configured separately.

## How to add or change interface text

1. Add a stable key and a non-empty English value to `locales/en.json`.
2. Request visible text in code through `tr()` or `tr_label()`; do not hard-code UI messages. Keep IDs, enum values, model/provider names, paths, file formats, shortcuts, and values used by program logic unchanged. For translated labels backed by stable IDs, store the ID as item data and read it with `currentData()`.
3. Use named placeholders such as `{path}` or `{count}` and preserve the same names in every catalog. Keep required HTML, literal tokens, file formats, and shortcut keys intact.
4. Update the translated catalogs either manually or with an LLM. For the LLM workflow, select and copy the complete contents of `locales/en.json` (or attach that file), ask the model to translate the values into the target language, and request one complete JSON catalog for the target locale code, such as `pt-BR.json`. Save the result as `locales/<code>.json`. This workflow is allowed; the key verifier is provided in part to catch missing, extra, or malformed keys and placeholders in generated catalogs. New strings may temporarily retain the English source value, but should be localized when a fluent contributor is available.
5. Approve and verify catalogs from the repository root:

   ```bash
   python tools/check_locales.py --approve
   python tools/check_locales.py --release
   ```

   Approval checks structure and updates generated fingerprints; it does not translate text or judge its quality. Review the diff and any copied English values. Do not edit fingerprints in `locales/index.json` manually.
6. Review the language in context and record localization credits, human-audit status, catalog status, and localization version in the table below.

When adding a language, create `locales/<code>.json` from `locales/en.json`, set `meta.language_name` in the native language and `meta.language_name_english` in English, then approve that catalog with `python tools/check_locales.py --approve locales/<code>.json`.

## Localization credits and review status

LLMs may help produce a first translation from the English catalog. Credit the model used when known. A fluent human must review the phrases in context for meaning, tone, natural phrasing, and fluency before marking **Human audit** as Yes. Structural verification is not a language audit.

The table uses these fields:

- **Language:** the catalog's locale code and display name. The code must match its filename and manifest entry.
- **Localization credits:** the human contributor and/or LLM that produced or substantially assisted with the translation. Do not claim a contributor or model that was not involved.
- **Human audit:** `Yes` only after a fluent human has reviewed wording and UI context. Otherwise use `No — requires human review`.
- **Catalog status:** `Included` means the catalog is registered and shipped; `structurally verified` means keys, placeholders, metadata, and fingerprints passed the checker. This status does not certify translation quality.
- **Localization version:** the application/source-catalog version for which this catalog was last fully updated and approved. It is not the app version currently installed on a user's computer.

| Language | Localization credits | Human audit | Catalog status | Localization version |
|---|---|---|---|---|
| English (`en`) | Project source catalog | N/A — source language | Included; source catalog | 1.6.0 |
| Spanish (`es`) | `santiagodvergara05-debug`; Google Gemini (LLM-assisted) | Yes — audited, corrected, and refined by the maintainer, a native Spanish speaker | Included; structurally verified | 1.6.0 |
| Portuguese (Brazil) (`pt-BR`) | Google Gemini (LLM-assisted) | No — requires human review | Included; structurally verified | 1.6.0 |
| French (`fr`) | Google Gemini (LLM-assisted) | No — requires human review | Included; structurally verified | 1.6.0 |
| Chinese, Simplified (`zh-CN`) | Google Gemini (LLM-assisted) | No — requires human review | Included; structurally verified | 1.6.0 |
| Chinese, Traditional (`zh-TW`) | Google Gemini (LLM-assisted) | No — requires human review | Included; structurally verified | 1.6.0 |
| Korean (`ko`) | Google Gemini (LLM-assisted) | No — requires human review | Included; structurally verified | 1.6.0 |
| Japanese (`ja`) | Google Gemini (LLM-assisted) | No — requires human review | Included; structurally verified | 1.6.0 |
| Indonesian (`id`) | Google Gemini (LLM-assisted) | No — requires human review | Included; structurally verified | 1.6.0 |
| Arabic (`ar`) | Google Gemini (LLM-assisted) | No — requires human review | Included; structurally verified | 1.6.0 |

The non-English credits above record the LLM-assisted localization workflow for these catalogs. Update credits and audit status if the actual contribution or review history differs.

## Localization version: 1.6.0

`locales/en.json` defines the keys and English source values. When a new application version adds keys, contributors should add each key to the translated catalogs. An English value may be used temporarily for a new key so the catalog stays complete; update the localization version only after the catalog has been updated and approved for the current English source.

If the English source changes while a secondary catalog's approval is stale, the application does **not** silently treat that catalog as current: verification fails and the UI falls back to English for that session with a warning. After the catalog is updated and approved, any intentionally untranslated English values display in English while the rest of the interface uses the selected language. This is why a catalog's localization version and approval must be kept current.

## Localization checklist

### Code and catalog

- [ ] New or changed user-visible strings use `tr()` or `tr_label()` and have a non-empty source value in `locales/en.json`.
- [ ] Internal IDs and logic values remain stable; named placeholders and required markup/tokens match the English source.
- [ ] Each catalog has correct native and English display names and is listed in `locales/index.json` through the approval tool.
- [ ] Run `python tools/check_locales.py --release` successfully before packaging.
- [ ] Inspect the affected screens in the translated language and English; include RTL and long-label layout checks when relevant.

### LLM-assisted localization

- [ ] Use the current `locales/en.json` as the source. You may select and copy the entire JSON into an LLM, or attach the file; specify the target language and locale code.
- [ ] Tell the LLM to return a complete JSON catalog for `locales/<code>.json`, not a partial translation, summary, or list of changed strings. Preserve every key, placeholder, format token, shortcut, and required markup; do not invent approval fingerprints or metadata.
- [ ] Compare the output with the English source. Correct mistranslations, omissions, unnatural phrasing, inconsistent terminology, and any unrelated or added content.
- [ ] Validate and approve the catalog with `python tools/check_locales.py --approve locales/<code>.json`, then run `python tools/check_locales.py --release`.
- [ ] Review all verifier findings. The tool checks that keys and placeholders are structurally consistent; it does not prove that the LLM translated every value accurately or naturally.
- [ ] Have a fluent human review the translated phrases in the application context before marking **Human audit** as Yes. Until then, record `No — requires human review`.
- [ ] Record the LLM and human contributors accurately, set the localization version to the source version actually reviewed, and report which checks were run.

## Integrity and review policy

Every localization must preserve the English source's meaning, intent, and tone. Do not add unrelated text, change the message, or introduce profanity, slurs, hateful or harassing language, or other prohibited content absent from the source. This applies to catalog values, displayed metadata, and other localized content.

Maintainers review reported translations against the English source and surrounding context. They may consult multiple independent LLMs as advisory reviewers; model votes alone do not establish misconduct. If maintainers confirm a deliberate or material policy violation, they may remove the affected catalog and its credit and restrict further localization submissions. They should document evidence and rationale. Accidental errors should be corrected and do not automatically warrant sanctions.

## Runtime and validation notes

- The app reads `locales/index.json` for language names and loads only the selected catalog during normal startup. English is the source and recovery language; a stale or invalid secondary catalog falls back to English for that session.
- The selected user catalog replaces its bundled counterpart; catalogs are not merged key by key. Keep catalogs complete and independently approved.
- Arabic uses right-to-left application layout. Keep code tokens, paths, and keyboard shortcuts unchanged within translated strings.
- The build includes catalog JSON files listed by the locale manifest and excludes generated `*.sources.json` developer reports.
- `python tools/check_locales.py` inspects catalogs; add `locales/<code>.json` to check one. `--approve` updates structural approval, and `--release` is the final gate. The checker verifies JSON, key coverage, unexpected/empty keys, placeholders, metadata, and fingerprints; it cannot evaluate fluency or meaning.
- `tools/extract_strings.py` and `tools/migrate_to_tr.py` support string inventory and reviewed migration. Inspect their reports and diffs; they are not substitutes for code review or human translation review.

