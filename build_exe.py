"""
PyInstaller automated build script for Manga Translate Studio.

Packages runtime dependencies and resources inside 'MangaTranslate_Data' so the
distribution stays isolated from sibling application Manga Cleaner.
"""

import os
import json
import importlib.util
import sys
import subprocess


def validate_build_inputs(root_dir):
    """Fail early when source files or verified runtime catalogs are incomplete."""
    required_files = [
        "main.py",
        os.path.join("assets", "icon.ico"),
        os.path.join("src", "frontend", "styles.qss"),
        os.path.join("locales", "en.json"),
        os.path.join("locales", "index.json"),
        os.path.join("tools", "check_locales.py"),
    ]
    missing = [path for path in required_files if not os.path.isfile(os.path.join(root_dir, path))]
    if missing:
        raise FileNotFoundError("Required build inputs are missing: " + ", ".join(missing))

    if importlib.util.find_spec("PyInstaller") is None:
        raise RuntimeError(
            "PyInstaller is not installed in this Python environment. "
            "Install it with: python -m pip install PyInstaller"
        )

    locales_dir = os.path.join(root_dir, "locales")
    with open(os.path.join(locales_dir, "index.json"), "r", encoding="utf-8-sig") as file:
        manifest = json.load(file)
    languages = manifest.get("languages") if isinstance(manifest, dict) else None
    if not isinstance(languages, dict) or not languages:
        raise ValueError("locales/index.json must contain a non-empty 'languages' object")

    missing_catalogs = [
        f"locales/{code}.json"
        for code in languages
        if not os.path.isfile(os.path.join(locales_dir, f"{code}.json"))
    ]
    if missing_catalogs:
        raise FileNotFoundError("Catalogs listed in locales/index.json are missing: " + ", ".join(missing_catalogs))

    # Release mode is non-interactive and blocks packaging stale/unapproved catalogs.
    subprocess.run(
        [sys.executable, os.path.join(root_dir, "tools", "check_locales.py"), "--release"],
        cwd=root_dir,
        check=True,
    )


def build():
    """Executes PyInstaller build workflow with explicit folder layout."""
    print("[*] Starting Manga Translate Studio compilation...")

    root_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(root_dir, "dist")
    icon_path = os.path.join(root_dir, "assets", "icon.ico")
    locales_dir = os.path.join(root_dir, "locales")
    validate_build_inputs(root_dir)

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
        "--hidden-import=src.backend.providers.gemini_provider",
        "--hidden-import=src.backend.providers.ollama_provider",
        "--hidden-import=src.backend.providers.openai_provider",
        "--hidden-import=src.backend.providers.xai_provider",
        "--hidden-import=src.backend.providers.anthropic_provider",
        "--hidden-import=src.backend.providers.openrouter_provider",
        "--hidden-import=src.backend.providers.deepseek_provider",
        "--hidden-import=src.backend.credential_manager",
        "--hidden-import=src.backend.prompt_manager",
        "main.py"
    ]

    # Include only the manifest and locale catalogs; generated source-location
    # reports (for example, en.sources.json) are not runtime resources.
    locale_files = sorted(
        os.path.join(locales_dir, name)
        for name in os.listdir(locales_dir)
        if name.lower().endswith(".json")
        and not name.lower().endswith(".sources.json")
    )
    for locale_file in locale_files:
        cmd.insert(-1, f"--add-data={locale_file}{os.pathsep}locales")

    print("[*] Executing PyInstaller build command...")
    subprocess.run(cmd, check=True)

    output_folder = os.path.join(dist_dir, "MangaTranslate")
    print(f"[*] Verifying distribution layout at: {output_folder}")

    executable = os.path.join(output_folder, "MangaTranslate.exe")
    bundled_data = os.path.join(output_folder, "MangaTranslate_Data")
    expected_resources = [
        executable,
        os.path.join(bundled_data, "assets", "icon.ico"),
        os.path.join(bundled_data, "src", "frontend", "styles.qss"),
        os.path.join(bundled_data, "locales", "index.json"),
    ]
    expected_resources.extend(
        os.path.join(bundled_data, "locales", name)
        for name in os.listdir(locales_dir)
        if name.lower().endswith(".json")
        and not name.lower().endswith(".sources.json")
    )
    missing_output = [path for path in expected_resources if not os.path.isfile(path)]
    if missing_output:
        raise FileNotFoundError(
            "Build completed but required distribution files are missing: "
            + ", ".join(os.path.relpath(path, output_folder) for path in missing_output)
        )

    # Ensure shared persistent directories exist in the build output
    for folder in ["cache", "logs", "translations", "processed"]:
        os.makedirs(os.path.join(output_folder, folder), exist_ok=True)

    print("\n" + "=" * 70)
    print(" COMPILATION COMPLETED SUCCESSFULLY!")
    print(f" Output folder: {output_folder}")
    print(f" Executable:    {executable}")
    print(f" Data folder:   {bundled_data} (required at runtime)")
    print(" Release:       Distribute/archive the entire MangaTranslate folder, not the EXE alone.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    build()
