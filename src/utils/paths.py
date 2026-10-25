"""
File system path manager for Manga Translate Studio.

Resolves persistent shared data directories (cache, logs, translations)
and static bundled asset paths across source execution and PyInstaller environments.
"""

import os
import sys


class Paths:
    """
    Central path resolver guaranteeing compatibility between development mode
    and PyInstaller frozen binary distributions.
    """

    # 1. BASE_DIR: Persistent directory next to executable or project repository root
    if getattr(sys, "frozen", False):
        BASE_DIR = os.path.dirname(sys.executable)
        BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
    else:
        BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        BUNDLE_DIR = BASE_DIR

    # 2. Shared persistent directories (Read & Write)
    CACHE = os.path.join(BASE_DIR, "cache")
    LOGS = os.path.join(BASE_DIR, "logs")
    TRANSLATIONS = os.path.join(BASE_DIR, "translations")
    PROCESSED = os.path.join(BASE_DIR, "processed")

    # 3. Static bundled assets packaged inside binary distribution
    ASSETS = os.path.join(BUNDLE_DIR, "assets")

    @classmethod
    def initialize(cls):
        """
        Creates mandatory persistent directories on disk if not already present.
        """
        os.makedirs(cls.CACHE, exist_ok=True)
        os.makedirs(cls.LOGS, exist_ok=True)
        os.makedirs(cls.TRANSLATIONS, exist_ok=True)
        os.makedirs(cls.PROCESSED, exist_ok=True)

    @classmethod
    def ensure_directories(cls):
        """Alias for backward compatibility with external tool integrations."""
        cls.initialize()


# Preemptive initialization on module load
Paths.initialize()