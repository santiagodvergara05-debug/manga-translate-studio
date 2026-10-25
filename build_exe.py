"""
PyInstaller automated build script for Manga Translate Studio.

Configures packaging flags to bundle internal dependencies inside 'MangaTranslate_Data',
enabling direct coexistence with sibling application Manga Cleaner in the same root folder.
"""

import os
import sys
import subprocess


def build():
    """Executes PyInstaller build workflow with explicit folder layout."""
    print("[*] Starting Manga Translate Studio compilation...")

    root_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(root_dir, "dist")
    icon_path = os.path.join(root_dir, "assets", "icon.ico")

    # PyInstaller execution configuration
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=MangaTranslate",
        "--noconfirm",
        "--clean",
        "--windowed",  # Suppress background console window
        f"--icon={icon_path}",
        # Direct all internal libraries and dependencies into MangaTranslate_Data
        "--contents-directory=MangaTranslate_Data",
        # Package static assets and stylesheets
        f"--add-data={os.path.join(root_dir, 'assets')}{os.pathsep}assets",
        f"--add-data={os.path.join(root_dir, 'src', 'frontend', 'styles.qss')}{os.pathsep}src/frontend",
        # Ensure dynamic vision modules and Qt libraries are discovered
        "--hidden-import=PySide6.QtSvg",
        "--hidden-import=PySide6.QtSvgWidgets",
        "--hidden-import=requests",
        "--hidden-import=PIL",
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--hidden-import=psutil",
        "--hidden-import=src.backend.providers.gemini_provider",
        "--hidden-import=src.backend.providers.ollama_provider",
        "--hidden-import=src.backend.credential_manager",
        "--hidden-import=src.backend.prompt_manager",
        "main.py"
    ]

    print("[*] Executing PyInstaller build command...")
    subprocess.run(cmd, check=True)

    output_folder = os.path.join(dist_dir, "MangaTranslate")
    print(f"[*] Verifying distribution layout at: {output_folder}")

    # Ensure shared persistent directories exist in the build output
    for folder in ["cache", "logs", "translations", "processed"]:
        os.makedirs(os.path.join(output_folder, folder), exist_ok=True)

    print("\n" + "=" * 70)
    print(" COMPILATION COMPLETED SUCCESSFULLY!")
    print(f" Output folder: {output_folder}")
    print(" Executable:    MangaTranslate.exe")
    print(" Data folder:   MangaTranslate_Data (Isolated from Manga Cleaner)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    build()