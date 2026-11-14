# 🌌 Manga Translate Studio (MTS)
**Multimodal vision translation workbench for comics, manga, and webtoons**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/Python-3.13-00d4ff)](https://www.python.org/)
[![UI Framework](https://img.shields.io/badge/GUI-PySide6%20(Qt6)-green)](https://www.qt.io/)
[![Sibling App](https://img.shields.io/badge/Sibling_Project-Manga_Cleaner_Studio-ff007f)](https://github.com/NeTRuNNeRGLiTCH/manga-cleaner)

---

## 📖 Overview

**Manga Translate Studio (MTS)** is a desktop scanlation workbench built with Python and PySide6 (Qt6). It works alongside **Manga Cleaner** and uses multimodal vision models through the implemented Google Gemini and Ollama integrations.

MTS sends page images for multimodal analysis without a separate OCR stage. It identifies dialogue, narration, floating text, and comic sound effects (SFX), then organizes translations into `.txt` scripts for review and use with [Manga Cleaner Studio](https://github.com/NeTRuNNeRGLiTCH/manga-cleaner).

The interface language is separate from the source and target languages used for manga translation. Ten interface languages are listed in `locales/index.json`; at startup, MTS loads the selected catalog rather than every catalog. If a non-English catalog cannot be verified, the app warns and uses English for that session. See [TRANSLATION.md](TRANSLATION.md) for catalog contribution and verification.

---

## 🖥️ Studio Workflow & Interface

![MANGA TRANSLATE STUDIO UI](.github/Ui.png)

> **Image note:** The comic panel in this screenshot is included solely to demonstrate the application's interface and translation workflow. The artwork remains the property of its respective rights holders.

---

## ✨ Key Features

* **Image-based extraction and translation**: Implemented integrations for Google Gemini and Ollama, including local Ollama and compatible cloud endpoints.
* **Page continuity and script export**: Supplies eligible preceding-page text as context and writes reviewed translations to `.txt` scripts using the Manga Cleaner `<translation>...</translation>` format.
* **Batch review**: Translates pages sequentially. Completed pages remain available for review while the batch continues; unsent and active pages are protected from editing. Cancellation stops queued work, while an active provider request is allowed to finish.
* **Request pacing**: LOW, HIGH, and MAX set minimum delays between request starts per provider. Pacing can reduce rate-limit risk but cannot guarantee that a provider will not return HTTP 429.
* **Prompt controls**: Configure user rules and extraction options, and preview the resulting system prompt. Options include SFX meanings, repeated-SFX suppression, and contextual R19 vocalization guidance.
* **Connection profiles**: Save and switch provider credentials/endpoints, models, and supported model settings.
* **Usage and prices**: Review provider-reported token/cache metadata, estimate costs from editable USD-per-million-token rates, and import or export optional community price tables.
* **Gemini RPD meter**: An optional local daily request limit and counter, editable in API Settings and tracked by connection profile and model. It is not a live Google quota lookup.
* **Interface localization**: Choose from ten interface catalogs. Localization is separate from the languages used for manga translation.
* **Provider contribution points**: OpenAI, xAI, Anthropic, OpenRouter, and DeepSeek appear as unavailable scaffolds. They do not make API calls; see Help → Providers & Contribution before implementing one.

See [CHANGELOG_1.6.0.md](CHANGELOG_1.6.0.md) for the detailed 1.6.0 change list.

---

## 📂 Project Directory Structure

```text
Manga Translate Studio/
├── .github/
│   └── Ui.png                         # Repository UI screenshot
├── .gitignore                          # Excludes local credentials, history, and generated files
├── assets/                            # Application icons and branding
├── locales/                           # UI language catalogs
│   ├── en.json                        # English source strings and primary language
│   ├── <language>.json                # Additional catalogs; see index.json
│   └── index.json                     # Available languages and source fingerprints
├── Pricing_Models_Providers/          # Community JSON price references for import
│   ├── PRICING_TABLES.md              # Price schema, import behavior, and contribution guidance
│   ├── google_models.json             # Google Gemini and Gemma reference rates
│   └── ollama_models.json             # Ollama Cloud reference rates
├── cache/                             # Runtime user data (git-ignored; created by the app)
│   ├── api_config.json                # Provider settings and saved connection profiles
│   ├── core_rules.txt                 # Technical prompt rules
│   ├── pricing_tables.json            # Imported/editable prices and Gemini RPD settings
│   ├── prompt_options.json            # Extraction and prompt feature toggles
│   ├── ui_settings.json               # Saved interface locale (created when changed)
│   ├── usage_history.json             # Local request and token history
│   └── user_rules.txt                 # User glossary, lore, and style rules
├── logs/                              # Runtime diagnostics (git-ignored)
├── translations/                      # User translation scripts (git-ignored)
├── processed/                         # Output staging directory (git-ignored)
├── src/
│   ├── backend/
│   │   ├── providers/
│   │   │   ├── base_provider.py       # Provider interface and normalized result schema
│   │   │   ├── anthropic_provider.py  # Unavailable provider scaffold for Claude
│   │   │   ├── deepseek_provider.py   # Unavailable provider scaffold for DeepSeek
│   │   │   ├── gemini_provider.py     # Gemini Vision API, thinking levels and usage metadata
│   │   │   ├── openai_provider.py     # Unavailable provider scaffold for OpenAI
│   │   │   ├── ollama_provider.py     # Ollama local and OpenAI-compatible cloud integration
│   │   │   ├── openrouter_provider.py # Unavailable provider scaffold for OpenRouter
│   │   │   └── xai_provider.py        # Unavailable provider scaffold for xAI
│   │   ├── ai_client.py               # Provider orchestration, request pacing and workers
│   │   ├── credential_manager.py      # Persistent settings and connection profiles
│   │   ├── languages.py               # Supported languages and localized SFX directives
│   │   ├── prompt_manager.py          # Prompt construction, options and continuity context
│   │   ├── translator.py              # Translation UI, prompt configuration and script engine
│   │   └── usage_manager.py           # Pricing, usage history, cache data and Gemini RPD state
│   ├── frontend/
│   │   ├── api_settings.py            # Provider, connection profile and model settings dialog
│   │   ├── canvas.py                  # Image viewport, scrolling and Ctrl/Alt+wheel zoom
│   │   ├── help_system.py             # In-app guide for navigation, prompts and usage
│   │   ├── main_window.py             # Main UI, batch workflow, pacing and RPD controls
│   │   ├── project_reset.py           # Project/session reset and memory cleanup
│   │   ├── styles.qss                 # Application visual theme
│   │   ├── usage_pricing.py           # Usage history, price editor and JSON import/export
│   │   └── widgets.py                 # SVG icon provider and project asset list
│   └── utils/
│       ├── config.py                  # Global constants, version and color palette
│       ├── i18n.py                    # Verified JSON locale loading and fallback
│       ├── logger.py                  # Runtime logging
│       └── paths.py                   # Source/frozen path resolver
├── tools/
│   ├── check_locales.py               # Catalog structure and release verification
│   ├── extract_strings.py             # UI string extraction and review report
│   └── migrate_to_tr.py               # Dry-run-first UI localization migration
├── build_exe.py                       # PyInstaller packaging script
├── CONTRIBUTING.md                    # Contribution and pull request guidelines
├── TRANSLATION.md                     # UI localization and catalog verification guide
├── CHANGELOG_1.6.0.md                 # Detailed changes in version 1.6.0
├── TECHNICAL_AUDIT_1.6.0.md           # Maintenance audit and follow-up notes
├── generate_icons.py                  # Application icon generation utility
├── LICENSE                            # Apache License 2.0
├── main.py                            # Application entry point
├── README.md                          # Project overview and setup guide
└── requirements.txt                   # Runtime dependencies
```

---

## 🤝 Sibling Ecosystem & Credits

**Manga Translate Studio** is a sibling project to **Manga Cleaner Studio**, sharing design language, technical principles, and file conventions.

**Repository:** [Manga Cleaner Studio on GitHub](https://github.com/NeTRuNNeRGLiTCH/manga-cleaner)

We would like to give credit to the original creators and key contributors of the ecosystem:

* **[NeTRuNNeRGLiTCH](https://github.com/NeTRuNNeRGLiTCH)**: Creator of the original [Manga Cleaner Studio](https://github.com/NeTRuNNeRGLiTCH/manga-cleaner) project and the base studio architecture.
* **[MavikBow](https://github.com/MavikBow)**: Original creator of the multi-task batch queue system, dark theme stabilization, and UI enhancement architecture introduced in Manga Cleaner Studio v3.2.0.
* **[santiagodvergara05-debug](https://github.com/santiagodvergara05-debug)**: Core contributor to Manga Cleaner Studio, including v3.2.0 canvas stabilization and Workspaces, and lead architect of **Manga Translate Studio**.

---

## 🚀 Getting Started

### 1. Prerequisites

* Python 3.13 (64-bit; the 1.6.0 Windows release build used Python 3.13.14).
* Git installed on your system.

### 2. Clone the Repository

```bash
git clone https://github.com/santiagodvergara05-debug/manga-translate-studio.git
cd manga-translate-studio

```

### 3. Setup Virtual Environment

```bash
python -m venv venv

# Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Linux / macOS:
source venv/bin/activate

```

### 4. Install Dependencies

```bash
python -m pip install -r requirements.txt

```

### 5. Run from Source

```bash
python main.py

```

---

## 📦 Portable Windows Build (`.EXE` package)

Manga Translate Studio uses an isolated build configuration so it can coexist alongside Manga Cleaner without dependency collisions. Keep the applications in separate folders:

```bash
python -m pip install PyInstaller
python build_exe.py

```

### How Coexistence Works

`build_exe.py` validates the localization catalogs before packaging, then places runtime dependencies and bundled resources in an isolated `MangaTranslate_Data/` folder. The executable depends on that folder and must not be distributed by itself. For a release, archive and upload the **entire `dist/MangaTranslate/` directory**:

```text
dist/
└── MangaTranslate/              # Archive this entire folder for release
    ├── MangaTranslate_Data/     # Isolated dependencies, assets, styles, and locales
    ├── cache/                   # Persistent app settings and runtime data
    ├── logs/                    # Diagnostics
    ├── translations/            # Translation scripts (.txt)
    ├── processed/               # Processed output
    └── MangaTranslate.exe       # Application launcher

```

The packaged dependencies are isolated. Users can still select the same translation-script folder from either application when needed.

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Description |
| --- | --- |
| `Hold [Space]` | Toggle hand tool for smooth canvas panning |
| `Mouse Wheel` | Scroll vertically through long pages |
| `Ctrl + Mouse Wheel` or `Alt + Mouse Wheel` | Zoom centered on the cursor |
| `Middle Click` | Reset canvas zoom scale to 1:1 original size |
| `Space + Click Drag` | Pan across ultra-high-resolution pages |

---

## 📜 License

Distributed under the **Apache License 2.0**. See the repository's [LICENSE](LICENSE) file.

