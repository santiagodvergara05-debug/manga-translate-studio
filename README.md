# Manga Translate Studio (MTS)

A high-performance desktop application built with Python and PySide6 designed to streamline manga, manhwa, and webtoon translation workflows using multimodal Vision LLMs (Google Gemini & Ollama).

Manga Translate Studio extracts, translates, and formats dialogue bubbles, captions, and onomatopoeias (SFX) directly into structured translation scripts fully compatible with [Manga Cleaner](https://github.com/).

---

## Key Features

- **Multimodal AI Vision Support**: Direct page-level analysis via Gemini (`gemini-3.1-flash-lite`, `gemini-1.5-flash`, etc.) and Ollama endpoints (Local LAN & Cloud).
- **Inter-Page Dialogue Continuity**: Tracks cut-off sentences across consecutive panels and page boundaries to preserve syntax and conversational flow.
- **Two-Tier Script Architecture**: Organize translation scripts by series folders inside the centralized `translations/` directory with automatic header population (`### SERIES TITLE`, `### CHAPTER`).
- **Full Manga Cleaner Script Compatibility**: Edits only inside designated `<translation> ... </translation>` tags, leaving editorial comments, flags, and headers intact.
- **Custom Lore & Tone Engine**: Dedicated User Rules workspace to enforce custom glossaries, formal/informal honorifics, and character voice constraints without bloating the base system prompt.
- **Batch Processing & Quota Protection**: Sequential batch translation featuring adaptive RPM pacing (15 RPM margin) and automatic halting on daily quota (`RPD`) exhaustion.

---

## Directory Structure

```text
Manga Translate Studio/
├── assets/                  # UI icons and static resources
├── cache/                   # Local configuration, rules, and cached models (git-ignored)
├── logs/                    # Runtime diagnostics and debug logs (git-ignored)
├── translations/            # Series folders and exported .txt scripts (git-ignored)
├── src/
│   ├── backend/
│   │   ├── ai_client.py     # Multimodal API client, worker threads & token estimator
│   │   └── translator.py   # Script generation engine, bubble parser & UI panel
│   ├── frontend/
│   │   ├── canvas.py        # GraphicsScene manga viewer
│   │   ├── main_window.py   # Main window controller and batch orchestrator
│   │   ├── project_reset.py # In-memory project cleaner & RAM optimizer
│   │   └── widgets.py       # Custom Qt asset list and telemetry monitors
│   └── utils/
│       ├── config.py        # Global constants and color palette
│       ├── logger.py        # Logging system configuration
│       └── paths.py         # Dynamic path resolver (supports source & PyInstaller .exe)
├── main.py                  # Application entry point
├── requirements.txt         # Project dependencies
└── README.md

```
---

## Building Executable (.EXE)

You can build a standalone, portable Windows application using PyInstaller:

1. **Install PyInstaller** in your virtual environment:
   ```bash
   pip install pyinstaller

```

2. **Generate Application Assets** (if not already generated):
```bash
python generate_icons.py

```


3. **Run the Automated Build Script**:
```bash
python build_exe.py

```


4. **Locate the Output**:
The final build will be located at:
```text
dist/MangaTranslateStudio/
├── _internal/
├── cache/
├── logs/
├── translations/
└── MangaTranslateStudio.exe

```

You can move or distribute the entire `MangaTranslateStudio/` folder as a portable app.