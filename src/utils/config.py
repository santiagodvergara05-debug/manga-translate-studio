"""
Global application configuration and UI styling constants.

Provides centralized access to application metadata, versioning,
and the primary Deep Obsidian color palette.
"""


class Config:
    """Centralized constant registry for application parameters and visual themes."""

    APP_NAME: str = "Manga Translate Studio"
    VERSION: str = "1.5.0"

    # Deep Obsidian Theme Palette
    COLOR_BG: str = "#0b0b0e"
    COLOR_PANEL: str = "#121217"
    COLOR_ACCENT: str = "#00d4ff"
    COLOR_TEXT: str = "#e0e0e0"
    COLOR_TEXT_DIM: str = "#808085"
    COLOR_ERROR: str = "#ff4d4d"