"""
Translation workspace panel, dialogue card manager, and script file synchronization engine.

Coordinates UI inputs, multimodal inference triggers, and bidirectional synchronization 
between active editor fields and structured Manga Cleaner translation scripts (.txt).
"""

import os
import re
import subprocess
import unicodedata

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFileDialog, QMessageBox, QComboBox, QLineEdit, QScrollArea, 
    QFrame, QDialog, QTextEdit, QTabWidget, QCheckBox, QInputDialog
)

from src.utils.config import Config
from src.utils.paths import Paths
from src.utils.logger import logger
from src.backend.prompt_manager import PromptManager
from src.backend.credential_manager import CredentialManager
from src.backend.providers.base_provider import ProviderStatus, TranslationResult
from src.backend.ai_client import MultimodalTranslationWorker, AIClientManager
from src.backend.usage_manager import UsageManager
from src.backend.providers.gemini_provider import GeminiProvider
from src.frontend.api_settings import APISettingsDialog
from src.backend.languages import (
    get_source_display_names, 
    get_target_display_names
)


def _nfc(s: str) -> str:
    """Normalizes Unicode strings to NFC standard for strict compatibility with Manga Cleaner."""
    return unicodedata.normalize("NFC", s) if s else ""


# /////////////////////////////////#
#       CREATE SCRIPT DIALOG       #
# /////////////////////////////////#

class CreateScriptDialog(QDialog):
    """Modal dialog prompting for Series Title and Chapter to generate a compliant script file."""

    def __init__(self, default_series: str = "", default_chapter: str = "1", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Translation Script")
        self.setFixedSize(460, 220)
        self.setStyleSheet(f"background-color: {Config.COLOR_PANEL}; color: {Config.COLOR_TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        lbl_title = QLabel("Series Title:")
        lbl_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #00d2ff;")
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("e.g. My Favorite Webtoon Series")
        self.txt_title.setText(default_series)
        self.txt_title.setStyleSheet("background-color: #121218; border: 1px solid #2a2a35; padding: 5px; font-size: 11px;")
        self.txt_title.textChanged.connect(self._update_preview)

        lbl_chapter = QLabel("Chapter:")
        lbl_chapter.setStyleSheet("font-size: 11px; font-weight: bold; color: #00d2ff;")
        self.txt_chapter = QLineEdit()
        self.txt_chapter.setPlaceholderText("e.g. 1, 04, Special")
        self.txt_chapter.setText(default_chapter)
        self.txt_chapter.setStyleSheet("background-color: #121218; border: 1px solid #2a2a35; padding: 5px; font-size: 11px;")
        self.txt_chapter.textChanged.connect(self._update_preview)

        self.lbl_preview = QLabel("File: ")
        self.lbl_preview.setStyleSheet("color: #888899; font-size: 10px; font-style: italic;")

        layout.addWidget(lbl_title)
        layout.addWidget(self.txt_title)
        layout.addWidget(lbl_chapter)
        layout.addWidget(self.txt_chapter)
        layout.addWidget(self.lbl_preview)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        self.btn_create = QPushButton("Create Script")
        self.btn_create.setObjectName("PrimaryBtn")
        self.btn_create.setStyleSheet("background-color: #00d2ff; color: black; font-weight: bold; padding: 6px 16px;")
        self.btn_create.clicked.connect(self._validate_and_accept)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_create)
        layout.addLayout(btn_layout)

        self._update_preview()

    def _get_clean_filename(self) -> str:
        """Sanitizes user input to create a safe filename across Windows and Linux."""
        raw_title = self.txt_title.text().strip() or "Untitled_Series"
        raw_chapter = self.txt_chapter.text().strip() or "1"
        clean_title = re.sub(r'[\\/*?:"<>|]', "", raw_title).strip()
        clean_chap = re.sub(r'[\\/*?:"<>|]', "", raw_chapter).strip()
        return f"{clean_title} - Chapter {clean_chap}.txt"

    def _update_preview(self):
        """Updates live generated filename preview label."""
        filename = self._get_clean_filename()
        self.lbl_preview.setText(f"Generated filename: {filename}")

    def _validate_and_accept(self):
        """Validates that mandatory fields are populated prior to dialog completion."""
        if not self.txt_title.text().strip():
            QMessageBox.warning(self, "Validation Notice", "Please provide a series title.")
            self.txt_title.setFocus()
            return
        self.accept()

    def get_data(self) -> tuple[str, str, str]:
        """Returns series title, chapter identifier, and cleaned target filename."""
        title = self.txt_title.text().strip()
        chapter = self.txt_chapter.text().strip()
        filename = self._get_clean_filename()
        return title, chapter, filename


# /////////////////////////////////#
#       RULES & USER DIALOG        #
# /////////////////////////////////#

class RulesDialog(QDialog):
    """Configuration dialog for customizing engine constraints and user-defined glossary rules."""

    def __init__(
        self,
        user_rules: str,
        core_rules: str,
        options: dict = None,
        parent=None,
        *,
        prompt_manager: PromptManager = None,
        src_lang: str = "English",
        tgt_lang: str = "Spanish (Neutral)",
        medium: str = "Manhwa",
    ):
        super().__init__(parent)
        self.preview_manager = prompt_manager or PromptManager()
        self.preview_manager.core_rules = core_rules
        self.preview_src_lang = src_lang
        self.preview_tgt_lang = tgt_lang
        self.preview_medium = medium
        self.setWindowTitle("Rules & System Prompt Configuration")
        self.resize(760, 580)
        self.setStyleSheet(f"background-color: {Config.COLOR_PANEL}; color: {Config.COLOR_TEXT};")

        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            f"QTabBar::tab {{ background: #1b1b22; color: #a0a0b0; padding: 6px 12px; }} "
            f"QTabBar::tab:selected {{ background: #2a2a35; color: {Config.COLOR_ACCENT}; font-weight: bold; }}"
        )

        tab_user = QWidget()
        lay_u = QVBoxLayout(tab_user)
        lbl_u = QLabel("Custom style guidelines, lore, glossary, and tone (stored in 'cache/user_rules.txt'):")
        lbl_u.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 11px;")
        self.txt_user_rules = QTextEdit()
        self.txt_user_rules.setPlaceholderText(
            "Optional: Write character names, glossary items, pronouns (formal/informal), or series-specific lore rules..."
        )
        self.txt_user_rules.setStyleSheet(f"background-color: {Config.COLOR_BG}; border: 1px solid #2a2a35; font-family: Consolas, monospace; font-size: 11px; padding: 6px;")
        self.txt_user_rules.setPlainText(user_rules)
        lay_u.addWidget(lbl_u)
        lay_u.addWidget(self.txt_user_rules)

        from src.backend.prompt_manager import DEFAULT_EXTRACTION_OPTIONS
        option_values = dict(DEFAULT_EXTRACTION_OPTIONS)
        if isinstance(options, dict):
            option_values.update(options)

        tab_prompt = QWidget()
        lay_p = QVBoxLayout(tab_prompt)
        lbl_p = QLabel("Base prompt sent to the model (previous-page continuity may be appended per page). Read-only; reflects the current medium, rules, and options when this tab is opened.")
        lbl_p.setWordWrap(True)
        lbl_p.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 11px;")
        lay_p.addWidget(lbl_p)

        lbl_medium = QLabel(f"Current medium: {medium}")
        lbl_medium.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px;")
        lay_p.addWidget(lbl_medium)

        self.txt_prompt_preview = QTextEdit()
        self.txt_prompt_preview.setReadOnly(True)
        self.txt_prompt_preview.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.txt_prompt_preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.txt_prompt_preview.setStyleSheet(f"background-color: {Config.COLOR_BG}; border: 1px solid #2a2a35; font-family: Consolas, monospace; font-size: 11px; padding: 6px;")
        lay_p.addWidget(self.txt_prompt_preview, 1)

        tab_options = QWidget()
        lay_o = QVBoxLayout(tab_options)
        lbl_o = QLabel(
            "Choose which content and optional output fields the model should generate. "
            "Token arrows show possible impact, not a fixed estimate."
        )
        lbl_o.setWordWrap(True)
        lbl_o.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 11px;")
        lay_o.addWidget(lbl_o)

        option_specs = [
            ("sfx", "Sound effects and onomatopoeias", "Extract and translate comic sound lettering. ⬆ More output if found · ⬇ off saves those items."),
            ("sfx_meaning", "Explain sound-effect meaning", "Adds a concise meaning note to SFX cards in the selected target language. ⬆ Extra output for SFX only · requires SFX."),
            ("narration", "Narration boxes and captions", "Include narration outside speech bubbles. ⬆ More output if found · ⬇ off saves those items."),
            ("outside", "Floating outside text", "Include signs, labels, and other text outside bubbles. ⬆ More output if found · ⬇ off saves those items."),
            ("variants", "Translation variants", "⬆ Formal, aggressive, and natural alternatives can add output tokens. Disable for direct translation only."),
            ("subtext", "Tone notes (subtext)", "⬆ Optional short tone notes add output when generated. Disable to omit them."),
            ("r19_mode", "R19 vocalization mode", "Adds contextual rules for distinguishing breathy vocalizations from laughter. ⬆ Small prompt increase; no extra output fields."),
        ]
        self.option_checks = {}
        for key, title, description in option_specs:
            checkbox = QCheckBox(title)
            checkbox.setChecked(bool(option_values.get(key, True)))
            checkbox.setStyleSheet("font-size: 11px; font-weight: bold;")
            detail = QLabel(description)
            detail.setWordWrap(True)
            detail.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px; margin-left: 22px;")
            lay_o.addWidget(checkbox)
            lay_o.addWidget(detail)
            self.option_checks[key] = checkbox
            checkbox.toggled.connect(self._update_prompt_preview)
        self.option_checks["sfx"].toggled.connect(self._sync_sfx_meaning_option)
        self._sync_sfx_meaning_option(self.option_checks["sfx"].isChecked())
        self.tabs.addTab(tab_user, "User Rules (Tone & Lore)")
        self.tabs.addTab(tab_prompt, "System Prompt (Read-only)")
        self.tabs.addTab(tab_options, "Extraction Options")
        lay.addWidget(self.tabs)

        self.txt_user_rules.textChanged.connect(self._update_prompt_preview)

        btn_row = QHBoxLayout()
        self.btn_restore = QPushButton("Restore Defaults")
        self.btn_restore.clicked.connect(self._restore_defaults)
        btn_save = QPushButton("Save Rules to Disk")
        btn_save.setObjectName("PrimaryBtn")
        btn_save.setStyleSheet("background-color: #00d2ff; color: black; font-weight: bold; padding: 6px 16px;")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(self.btn_restore)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._update_restore_button(self.tabs.currentIndex())

    def _current_options(self) -> dict:
        return {key: checkbox.isChecked() for key, checkbox in self.option_checks.items()}

    def _sync_sfx_meaning_option(self, sfx_enabled: bool):
        """Locks the dependent meaning option when SFX extraction is disabled."""
        meaning_checkbox = self.option_checks["sfx_meaning"]
        if not sfx_enabled:
            meaning_checkbox.setChecked(False)
        meaning_checkbox.setEnabled(sfx_enabled)
        meaning_checkbox.setToolTip(
            "Enable Sound effects and onomatopoeias first."
            if not sfx_enabled else
            "Show a concise sound-effect meaning note; this does not change the translation or .TXT output."
        )

    def _update_prompt_preview(self, *_):
        """Rebuilds the read-only prompt preview from the current unsaved controls."""
        if self.tabs.currentIndex() != 1:
            return
        prompt = self.preview_manager.build_full_prompt(
            src_lang=self.preview_src_lang,
            tgt_lang=self.preview_tgt_lang,
            medium=self.preview_medium,
            user_rules=self.txt_user_rules.toPlainText().strip(),
            options=self._current_options(),
        )
        self.txt_prompt_preview.setPlainText(prompt)

    def _on_tab_changed(self, tab_index: int):
        self._update_restore_button(tab_index)
        if tab_index == 1:
            self._update_prompt_preview()

    def _update_restore_button(self, tab_index: int):
        self.btn_restore.setEnabled(tab_index != 1)

    def _restore_defaults(self):
        """Restores defaults for the currently selected editable settings tab."""
        from src.backend.prompt_manager import (
            DEFAULT_USER_RULES,
            DEFAULT_EXTRACTION_OPTIONS,
        )
        if self.tabs.currentIndex() == 0:
            self.txt_user_rules.setPlainText(DEFAULT_USER_RULES)
        else:
            for key, checkbox in self.option_checks.items():
                checkbox.setChecked(DEFAULT_EXTRACTION_OPTIONS[key])

    def get_results(self) -> tuple[str, dict]:
        """Returns editable user rules and extraction option values."""
        return self.txt_user_rules.toPlainText().strip(), self._current_options()


# //////////////////////////////////////////////////////#
#   SCRIPT ENGINE (100% COMPATIBLE WITH MANGA CLEANER) #
# //////////////////////////////////////////////////////#

class TranslationScriptEngine:
    """Parses, creates, and synchronizes standard structured .txt script templates."""

    @staticmethod
    def generate_template(project_paths: list, series_title: str = "", chapter_num: str = "") -> str:
        """Generates a structured skeleton script file for all project image paths."""
        header = (
            "# =====================================================================\n"
            "# MANGA CLEANER - TRANSLATION SCRIPT TEMPLATE\n"
            "# =====================================================================\n"
            "# Instructions:\n"
            "# 1. DO NOT MODIFY OR DELETE the <translation> ... </translation> tags.\n"
            "#    Only text strictly inside those tags will be read.\n"
            "# 2. Each '-' represents a dialogue bubble / text box on that image.\n"
            "# 3. Empty '-' lines are automatically ignored (leave as-is if page has no text).\n"
            "# 4. Add as many '-' lines under an image as needed. Use '//' for manual line breaks.\n"
            "# 5. If 'Match pages by [filename]' is unchecked in the UI, the [brackets] are\n"
            "#    ignored and dialogues are loaded strictly by image order (Image 1, Image 2...).\n"
            "# 6. You may add as many optional notes or comments as desired outside the\n"
            "#    <translation> ... </translation> tags; Manga Cleaner will ignore them.\n"
            "# =====================================================================\n\n"
            f"### SERIES TITLE: {series_title}\n"
            f"### CHAPTER: {chapter_num}\n\n"
            "<translation>\n\n"
        )
        body_blocks = [f"Image {idx} [{_nfc(os.path.basename(path))}]\n-\n-\n" for idx, path in enumerate(project_paths, start=1)]
        footer = "\n</translation>\n"
        return header + "\n".join(body_blocks) + footer

    @staticmethod
    def parse_script(raw_text: str) -> list:
        """
        Parses an imported translation script extracting page entries and dialogue lines.
        
        Returns:
            list[dict]: List of entries with 'index', 'filename', and 'lines'.
        """
        non_comment_lines = [
            line for line in raw_text.splitlines()
            if not line.strip().startswith("#")
        ]
        cleaned_text = "\n".join(non_comment_lines)

        tag_pattern = re.compile(
            r"^\s*<translation>\s*$(.*?)^\s*</translation>\s*$",
            re.IGNORECASE | re.DOTALL | re.MULTILINE
        )
        match = tag_pattern.search(cleaned_text)
        if not match:
            fallback = re.compile(r"<translation>(.*?)</translation>", re.IGNORECASE | re.DOTALL)
            match = fallback.search(cleaned_text)

        if not match:
            raise ValueError(
                "Could not find <translation> ... </translation> tags in the selected file.\n"
                "Please ensure the tags were not modified or deleted."
            )

        inner_content = match.group(1)
        entries = []
        current_entry = None
        img_header_re = re.compile(r"^\s*image\s+(\d+)(?:\s*\[([^\]]+)\])?", re.IGNORECASE)

        for raw_line in inner_content.splitlines():
            line = raw_line.strip()
            if not line or (line.startswith("(") and not line.startswith("-")):
                continue

            header_match = img_header_re.match(line)
            if header_match:
                img_idx = int(header_match.group(1))
                bracket_name = _nfc(header_match.group(2).strip()) if header_match.group(2) else None
                current_entry = {
                    "index": img_idx,
                    "filename": bracket_name,
                    "lines": []
                }
                entries.append(current_entry)
                continue

            if line.startswith("-") and current_entry is not None:
                dialogue = _nfc(line[1:].strip())
                if dialogue:
                    dialogue = dialogue.replace("//", "\n")
                    current_entry["lines"].append(dialogue)

        return entries

    @staticmethod
    def sync_full_script_file(script_path: str, project_paths: list, page_dialogues_map: dict):
        """Writes or updates an existing .txt script file preserving external metadata."""
        existing_header = None
        existing_footer = None

        if os.path.exists(script_path):
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    old_text = f.read()

                tag_match = re.search(r"([\s\S]*?<translation>\s*\n)([\s\S]*?)(\n\s*</translation>[\s\S]*)", old_text, re.IGNORECASE)
                if tag_match:
                    existing_header = tag_match.group(1)
                    existing_footer = tag_match.group(3)
            except Exception as e:
                logger.error(f"[SCRIPT_ENGINE] Error reading existing script: {e}")

        if not existing_header:
            existing_header = (
                "# =====================================================================\n"
                "# MANGA CLEANER - TRANSLATION SCRIPT TEMPLATE\n"
                "# =====================================================================\n"
                "### SERIES TITLE: \n"
                "### CHAPTER: \n\n"
                "<translation>\n\n"
            )
            existing_footer = "\n\n</translation>\n"

        body_blocks = []
        for idx, path in enumerate(project_paths, start=1):
            fname = _nfc(os.path.basename(path))
            lines = page_dialogues_map.get(path, [])

            block = [f"Image {idx} [{fname}]"]
            if not lines:
                block.append("-")
                block.append("-")
            else:
                for line in lines:
                    formatted = line.replace("\n", " // ").strip()
                    if formatted:
                        block.append(f"-{formatted}")

            body_blocks.append("\n".join(block))

        full_content = existing_header + "\n\n".join(body_blocks) + existing_footer
        
        os.makedirs(os.path.dirname(script_path), exist_ok=True)
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(full_content)


# /////////////////////////////////#
#     TRANSLATOR UI WORKSPACE      #
# /////////////////////////////////#

class TranslatorPanel(QWidget):
    """Primary right-hand panel for AI inference orchestration, editing, and script persistence."""

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.loaded_script_path = None
        self.path_dialogues_map = {}
        self.current_bubbles_widgets = []
        self.active_worker = None
        self.fetch_worker = None
        self.page_bubbles_data = {}
        self.page_token_usage = {}
        self.page_language_pairs = {}
        self.pending_language_pairs = {}

        # Core isolated managers
        self.prompt_manager = PromptManager()
        self.cred_manager = CredentialManager()

        self._loading_config = False

        self.init_ui()
        self._load_session_credentials()
        self.refresh_series_folders()

    def _load_session_credentials(self):
        """Loads configuration from persistent storage and synchronizes widget states."""
        self._loading_config = True
        try:
            cfg = self.cred_manager.data

            mode = cfg.get("mode", "Manhwa")
            src_lang = cfg.get("src_lang", "English")
            tgt_lang = cfg.get("tgt_lang", "Spanish (Neutral)")

            m_idx = self.mode_combo.findText(mode)
            if m_idx >= 0:
                self.mode_combo.setCurrentIndex(m_idx)

            for i in range(self.src_lang_combo.count()):
                if src_lang.lower() in self.src_lang_combo.itemText(i).lower():
                    self.src_lang_combo.setCurrentIndex(i)
                    break

            for i in range(self.tgt_lang_combo.count()):
                if tgt_lang.lower() in self.tgt_lang_combo.itemText(i).lower():
                    self.tgt_lang_combo.setCurrentIndex(i)
                    break

            self._refresh_api_summary()

        except Exception as e:
            logger.error(f"[TRANSLATOR] Error loading session credentials: {e}")
        finally:
            self._loading_config = False

    def _save_session_credentials(self):
        """Serializes current UI credentials dynamically into the persistent credential manager."""
        if self._loading_config:
            return

        try:
            payload = {
                "mode": self.mode_combo.currentText(),
                "src_lang": self.src_lang_combo.currentText(),
                "tgt_lang": self.tgt_lang_combo.currentText(),
            }

            self.cred_manager.save(payload)
            self.update_token_estimate()
        except Exception as e:
            logger.error(f"[TRANSLATOR] Error saving session config: {e}")

    def get_active_api_config(self) -> dict:
        """Returns the selected provider and its saved connection details."""
        provider_id = str(self.cred_manager.data.get("provider", "gemini")).lower()
        provider = AIClientManager.get_provider(provider_id)
        creds = self.cred_manager.get_provider_credentials(provider_id)
        requires_endpoint = bool(getattr(provider, "requires_endpoint", False))
        is_lan = bool(getattr(provider, "has_lan_mode", False) and creds.get("lan_mode", True))
        default_models = getattr(provider, "default_models", []) or [""]
        config = {
            "provider_id": provider_id,
            "provider_name": getattr(provider, "display_name", provider_id.title()),
            "model": str(creds.get("model", "")).strip()
            or default_models[0],
            "api_key": "",
            "endpoint_url": "",
            "token": "",
            "is_lan": is_lan,
            "thinking_level": str(creds.get("thinking_level", "minimal")).lower(),
            "request_pacing": str(self.cred_manager.data.get("request_pacing", "low")).lower(),
        }
        if requires_endpoint:
            config["endpoint_url"] = (
                getattr(provider, "default_endpoint", "http://localhost:11434")
                if is_lan else str(creds.get("url", "")).strip()
            )
            config["token"] = "" if is_lan else str(creds.get("token", "")).strip()
            config["has_credentials"] = is_lan or bool(config["token"])
        else:
            config["api_key"] = str(creds.get("key", "")).strip()
            config["has_credentials"] = bool(config["api_key"])
        config["usage_profile"] = UsageManager.make_profile_id(
            provider_id,
            explicit_name=creds.get("usage_profile", ""),
            api_key=config["api_key"],
            endpoint=config["endpoint_url"],
            token=config["token"],
        )
        return config

    def _refresh_api_summary(self):
        """Updates the compact provider summary shown in the translation panel."""
        if not hasattr(self, "api_summary"):
            return
        config = self.get_active_api_config()
        model = config["model"] or "No model selected"
        state = "Ready" if config["has_credentials"] else "Credentials needed"
        self.api_summary.setText(f"{config['provider_name']} · {model} · {state}")

    def on_open_api_settings(self):
        """Opens provider settings without exposing credentials in the main panel."""
        dialog = APISettingsDialog(self.cred_manager, self)
        if dialog.exec() == QDialog.Accepted:
            self._refresh_api_summary()
            self.update_token_estimate()
            if hasattr(self.mw, "refresh_usage_summary"):
                self.mw.refresh_usage_summary()

    def get_full_prompt(self) -> str:
        """Constructs system prompt utilizing the isolated prompt manager."""
        return self.prompt_manager.build_full_prompt(
            src_lang=self.src_lang_combo.currentText(),
            tgt_lang=self.tgt_lang_combo.currentText(),
            medium=self.mode_combo.currentText()
        )

    def build_prompt_for(self, path: str) -> str:
        """Builds full prompt including sequential context continuity across previous pages."""
        base_prompt = self.get_full_prompt()
        continuity = self.prompt_manager.build_continuity_context(
            current_path=path,
            all_project_paths=self._get_all_project_paths(),
            page_bubbles_data=self.page_bubbles_data,
            page_language_pairs=self.page_language_pairs,
            language_pair=self.current_language_pair(),
        )
        return base_prompt + continuity

    def current_language_pair(self) -> tuple[str, str]:
        return self.src_lang_combo.currentText(), self.tgt_lang_combo.currentText()

    def build_request_prompts(self, path: str) -> tuple[str, str]:
        """Separates stable system rules from per-page continuity and image instructions."""
        system_prompt = self.get_full_prompt()
        page_context = self.prompt_manager.build_continuity_context(
            current_path=path,
            all_project_paths=self._get_all_project_paths(),
            page_bubbles_data=self.page_bubbles_data,
            page_language_pairs=self.page_language_pairs,
            language_pair=self.current_language_pair(),
        ).strip()
        user_prompt = page_context or "Translate the attached page according to the system instructions."
        return system_prompt, user_prompt

    def update_token_estimate(self, path: str = None, prompt: str = None):
        """Shows a preflight estimate for the current page and its continuity context."""
        path = path or self.mw.current_img_path
        prompt = prompt if prompt is not None else (
            self.build_prompt_for(path) if path else self.get_full_prompt()
        )
        total, txt_tok, img_tok = AIClientManager.estimate_tokens(prompt, path)
        self.lbl_token_counter.setText(f"⚡ Est. Tokens: ~{total:,} (Text: ~{txt_tok:,} | Img: ~{img_tok:,})")
        self.lbl_token_counter.setStyleSheet("color: #00d4ff; font-size: 9px; font-weight: bold;")
        self.lbl_token_counter.setToolTip(
            "Approximate input tokens before sending. Actual usage appears after the response when the provider reports it."
        )

    def show_token_usage(self, usage: dict):
        """Displays provider-reported usage, keeping thinking separate from visible output."""
        usage = usage or {}
        input_tokens = int(usage.get("prompt_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        thinking_tokens = int(usage.get("thought_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", 0) or 0)
        if not any((input_tokens, output_tokens, thinking_tokens, total_tokens)):
            return False

        parts = [f"In {input_tokens:,}", f"Out {output_tokens:,}"]
        if "cache_tokens" in usage:
            cached_tokens = min(input_tokens, int(usage.get("cache_tokens", 0) or 0))
            cache_percent = 100 * cached_tokens / input_tokens if input_tokens else 0
            parts.insert(1, f"Cache {cached_tokens:,} ({cache_percent:.0f}%)")
        if thinking_tokens:
            parts.append(f"Think {thinking_tokens:,}")
        parts.append(f"Total {total_tokens or input_tokens + output_tokens + thinking_tokens:,}")
        if usage.get("cost_usd") is not None:
            parts.append(f"Cost ${float(usage['cost_usd']):.6f}")
        self.lbl_token_counter.setText("⚡ Real: " + " · ".join(parts))
        self.lbl_token_counter.setStyleSheet("color: #00e676; font-size: 9px; font-weight: bold;")
        self.lbl_token_counter.setToolTip(
            "Usage reported by the provider. Cache tokens are a subset of input; thinking tokens are separate when available."
        )
        return True

    def init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        title = QLabel("AI MULTIMODAL TRANSLATOR")
        title.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-size: 11px; font-weight: bold;")
        lay.addWidget(title)

        lbl_api = QLabel("1. AI ENGINE, FORMAT & RULES")
        lbl_api.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 9px; font-weight: bold;")
        lay.addWidget(lbl_api)

        row_top = QHBoxLayout()

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Manhwa", "Manga", "Comic", "Manhua"])
        self.mode_combo.currentIndexChanged.connect(self._save_session_credentials)

        self.btn_api_settings = QPushButton("⚙ API Settings")
        self.btn_api_settings.setStyleSheet("background-color: #1e1e26; border: 1px solid #333342; font-size: 11px; font-weight: bold; padding: 4px 10px;")
        self.btn_api_settings.clicked.connect(self.on_open_api_settings)

        self.btn_rules = QPushButton("⚙ Rules")
        self.btn_rules.setStyleSheet("background-color: #1e1e26; border: 1px solid #333342; font-size: 11px; font-weight: bold; padding: 4px 10px;")
        self.btn_rules.clicked.connect(self.on_open_rules_dialog)

        row_top.addWidget(self.mode_combo, 1)
        row_top.addWidget(self.btn_api_settings, 1)
        row_top.addWidget(self.btn_rules, 1)
        lay.addLayout(row_top)

        self.api_summary = QLabel("")
        self.api_summary.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 9px;")
        self.api_summary.setWordWrap(True)
        lay.addWidget(self.api_summary)

        # Extended Language Selectors
        row_lang = QHBoxLayout()
        lbl_from = QLabel("From:")
        lbl_from.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px;")
        self.src_lang_combo = QComboBox()
        self.src_lang_combo.addItems(get_source_display_names())
        self.src_lang_combo.currentIndexChanged.connect(self._save_session_credentials)

        lbl_to = QLabel("➔ To:")
        lbl_to.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px;")
        self.tgt_lang_combo = QComboBox()
        self.tgt_lang_combo.addItems(get_target_display_names())
        self.tgt_lang_combo.currentIndexChanged.connect(self._save_session_credentials)

        row_lang.addWidget(lbl_from)
        row_lang.addWidget(self.src_lang_combo, 1)
        row_lang.addWidget(lbl_to)
        row_lang.addWidget(self.tgt_lang_combo, 1)
        lay.addLayout(row_lang)

        self.lbl_token_counter = QLabel("⚡ Est. Tokens: ~1,450 (Text: ~330 | Img: ~1,120)")
        self.lbl_token_counter.setStyleSheet("color: #00d4ff; font-size: 9px; font-weight: bold;")
        lay.addWidget(self.lbl_token_counter)

        self.btn_translate_page = QPushButton("Translate Active Page")
        self.btn_translate_page.setObjectName("PrimaryBtn")
        self.btn_translate_page.setFixedHeight(34)
        self.btn_translate_page.clicked.connect(self.translate_current_page)
        lay.addWidget(self.btn_translate_page)

        self.lbl_api_status = QLabel("")
        self.lbl_api_status.setStyleSheet("font-size: 10px; font-weight: bold; padding: 2px;")
        self.lbl_api_status.setAlignment(Qt.AlignCenter)
        self.lbl_api_status.setWordWrap(True)
        self.lbl_api_status.setVisible(False)
        lay.addWidget(self.lbl_api_status)

        # --- SECTION 2: BUBBLES & VARIANTS ---
        row_ent_head = QHBoxLayout()
        self.lbl_bubbles = QLabel("2. DETECTED TEXT ENTITIES & VARIANTS")
        self.lbl_bubbles.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 9px; font-weight: bold;")
        
        self.btn_add_bubble = QPushButton("➕ Add Dialogue")
        self.btn_add_bubble.setToolTip("Manually insert a text entity that AI missed")
        self.btn_add_bubble.setStyleSheet("background-color: #1e1e28; border: 1px solid #444455; color: #00d2ff; font-size: 10px; font-weight: bold; padding: 2px 6px;")
        self.btn_add_bubble.clicked.connect(self.on_manually_add_bubble)

        row_ent_head.addWidget(self.lbl_bubbles, 1)
        row_ent_head.addWidget(self.btn_add_bubble)
        lay.addLayout(row_ent_head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(f"background: {Config.COLOR_BG}; border: 1px solid #2a2a32; border-radius: 4px;")
        self.bubble_container = QWidget()
        self.bubble_lay = QVBoxLayout(self.bubble_container)
        self.bubble_lay.setContentsMargins(6, 6, 6, 6)
        self.bubble_lay.setSpacing(8)
        self.scroll.setWidget(self.bubble_container)
        lay.addWidget(self.scroll, 1)

        # --- SECTION 3: SCRIPT FILE (.TXT) WITH TWO-TIER HIERARCHY ---
        lbl_script = QLabel("3. SCRIPT FILE (.TXT)")
        lbl_script.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 9px; font-weight: bold; margin-top: 4px;")
        lay.addWidget(lbl_script)

        # TIER 1: SERIES SELECTION
        row_series = QHBoxLayout()
        lbl_series = QLabel("Series:")
        lbl_series.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px; min-width: 42px;")
        
        self.combo_series_folder = QComboBox()
        self.combo_series_folder.setToolTip("Select series folder inside translations/")
        self.combo_series_folder.currentIndexChanged.connect(self._on_series_folder_changed)

        self.btn_new_series_folder = QPushButton("➕")
        self.btn_new_series_folder.setToolTip("Create new series folder in translations/")
        self.btn_new_series_folder.setFixedSize(26, 24)
        self.btn_new_series_folder.setStyleSheet("background-color: #1e1e28; border: 1px solid #333342; font-size: 11px;")
        self.btn_new_series_folder.clicked.connect(self.on_create_new_series_folder)

        self.btn_open_folder = QPushButton("📁")
        self.btn_open_folder.setToolTip("Open selected series folder in File Explorer")
        self.btn_open_folder.setFixedSize(26, 24)
        self.btn_open_folder.setStyleSheet("background-color: #1e1e28; border: 1px solid #333342; font-size: 11px;")
        self.btn_open_folder.clicked.connect(self.on_open_translations_folder)

        row_series.addWidget(lbl_series)
        row_series.addWidget(self.combo_series_folder, 1)
        row_series.addWidget(self.btn_new_series_folder)
        row_series.addWidget(self.btn_open_folder)
        lay.addLayout(row_series)

        # TIER 2: SCRIPT SELECTION
        row_script_sel = QHBoxLayout()
        lbl_pick = QLabel("Script:")
        lbl_pick.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px; min-width: 42px;")
        
        self.combo_folder_scripts = QComboBox()
        self.combo_folder_scripts.setToolTip("Scripts (.txt) available in the selected series folder")
        self.combo_folder_scripts.activated.connect(self.on_folder_script_selected)

        row_script_sel.addWidget(lbl_pick)
        row_script_sel.addWidget(self.combo_folder_scripts, 1)
        lay.addLayout(row_script_sel)

        row_script_btns = QHBoxLayout()
        self.btn_new_txt = QPushButton("New .TXT")
        self.btn_new_txt.clicked.connect(self.on_generate_template)
        self.btn_load_txt = QPushButton("Load .TXT")
        self.btn_load_txt.clicked.connect(self.on_import_script)
        row_script_btns.addWidget(self.btn_new_txt)
        row_script_btns.addWidget(self.btn_load_txt)
        lay.addLayout(row_script_btns)

        self.lbl_script_status = QLabel("Script: None")
        self.lbl_script_status.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px;")
        self.lbl_script_status.setWordWrap(True)
        lay.addWidget(self.lbl_script_status)

        self._refresh_api_summary()

    def set_locked(self, locked: bool, status_text: str = "", allow_audit: bool = False):
        """
        Locks or unlocks all configuration controls, settings, and editor panels 
        to ensure data consistency during active inference or batch jobs.
        """
        # Section 1: Engine, Models, Rules & Languages
        self.mode_combo.setEnabled(not locked)
        self.btn_api_settings.setEnabled(not locked)
        self.btn_rules.setEnabled(not locked)
        self.src_lang_combo.setEnabled(not locked)
        self.tgt_lang_combo.setEnabled(not locked)
        self.btn_translate_page.setEnabled(not locked)

        # During a batch, keep the editor scrollable and disable edits on queued / active pages.
        page_blocked = bool(
            allow_audit
            and self.mw.is_page_blocked_by_batch(self.mw.current_img_path)
        )
        self.scroll.setEnabled(not locked or allow_audit)
        self.btn_add_bubble.setEnabled(not locked or (allow_audit and not page_blocked))
        if allow_audit:
            self.set_page_audit_blocked(page_blocked)
        elif not locked:
            self.set_page_audit_blocked(False)

        # Section 3: Script file hierarchy
        self.combo_series_folder.setEnabled(not locked)
        self.btn_new_series_folder.setEnabled(not locked)
        self.btn_open_folder.setEnabled(not locked)
        self.combo_folder_scripts.setEnabled(not locked)
        self.btn_new_txt.setEnabled(not locked)
        self.btn_load_txt.setEnabled(not locked)

        if locked:
            self.lbl_api_status.setText(status_text or "⏳ Preparing translation request...")
            self.lbl_api_status.setStyleSheet("color: #00d2ff; font-size: 10px; font-weight: bold; padding: 2px;")
            self.lbl_api_status.setVisible(True)
            if self.mw.current_img_path and not allow_audit:
                self.mw.file_list.update_item_state(self.mw.current_img_path, "lock", "Translating in progress...")

    def set_page_audit_blocked(self, blocked: bool):
        """Block edits while keeping the dialogue list scrollable during a batch."""
        self.scroll.setEnabled(True)
        self.btn_add_bubble.setEnabled(not blocked)
        for card in self.current_bubbles_widgets:
            for attribute in ("orig_edit", "line_edit", "variant_combo", "delete_button"):
                widget = getattr(card, attribute, None)
                if widget is not None:
                    widget.setEnabled(not blocked)

    def show_inference_status(
        self,
        image_path: str,
        batch_position: int = None,
        batch_total: int = None,
    ):
        """Shows request context without claiming access to live model thoughts."""
        page_name = os.path.basename(image_path)
        if batch_position is not None and batch_total is not None:
            progress = f"Page {batch_position}/{batch_total} · {page_name}"
        else:
            progress = f"Page · {page_name}"

        self.lbl_api_status.setText(f"⏳ Model working · {progress}")
        self._inference_progress = f"⏳ Model working · {progress}"
        self.lbl_api_status.setStyleSheet(
            "color: #00d2ff; font-size: 10px; font-weight: bold; padding: 2px;"
        )
        self.lbl_api_status.setVisible(True)

    def update_inference_elapsed(self, elapsed: str, finished: bool = False):
        """Shows elapsed time in the request status line, without repeating model settings."""
        progress = getattr(self, "_inference_progress", "⏳ Model working")
        self.lbl_api_status.setText(f"{progress} · {elapsed}")
        self.lbl_api_status.setVisible(True)

    def _set_result_status(self, message: str, color: str):
        duration = getattr(self.mw, "_last_job_duration", None)
        if duration is not None:
            message = f"{message} · {self.mw._format_elapsed(duration)}"
        self.lbl_api_status.setText(message)
        self.lbl_api_status.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: bold; padding: 2px;"
        )
        self.lbl_api_status.setVisible(True)

    def show_status_message(self, message: str, color: str = "#00d2ff"):
        self.lbl_api_status.setText(message)
        self.lbl_api_status.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: bold; padding: 2px;"
        )
        self.lbl_api_status.setVisible(True)

    def on_open_rules_dialog(self):
        """Displays modal dialog for configuring core engine rules and custom lore."""
        dialog = RulesDialog(
            self.prompt_manager.user_rules,
            self.prompt_manager.core_rules,
            self.prompt_manager.options,
            self,
            prompt_manager=self.prompt_manager,
            src_lang=self.src_lang_combo.currentText(),
            tgt_lang=self.tgt_lang_combo.currentText(),
            medium=self.mode_combo.currentText(),
        )
        if dialog.exec() == QDialog.Accepted:
            new_user, new_options = dialog.get_results()
            self.prompt_manager.save_user_rules(new_user)
            self.prompt_manager.save_options(new_options)
            self.update_token_estimate()
            QMessageBox.information(self, "Rules Saved", "User rules and extraction options were saved to disk.")

    def _get_all_project_paths(self) -> list:
        """Retrieves absolute file paths for all images loaded in the project asset list."""
        return [self.mw.file_list.item(i).data(Qt.UserRole) for i in range(self.mw.file_list.count())]

    # --- TWO-TIER SCRIPT HIERARCHY ---
    def refresh_series_folders(self):
        """Populates the series combo with translations/ and its series subdirectories."""
        current_data = self.combo_series_folder.currentData()
        self.combo_series_folder.blockSignals(True)
        self.combo_series_folder.clear()

        base_dir = Paths.TRANSLATIONS
        os.makedirs(base_dir, exist_ok=True)

        self.combo_series_folder.addItem("📁 [Root] translations/", base_dir)

        natural_key = lambda name: [int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", name)]
        subdirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
        for d in sorted(subdirs, key=natural_key):
            sub_path = os.path.join(base_dir, d)
            self.combo_series_folder.addItem(f"📂 {d}", sub_path)

        idx = self.combo_series_folder.findData(current_data)
        if idx >= 0:
            self.combo_series_folder.setCurrentIndex(idx)
        else:
            self.combo_series_folder.setCurrentIndex(0)

        self.combo_series_folder.blockSignals(False)
        self.refresh_scripts_for_selected_series()

    def get_selected_series_dir(self) -> str:
        """Returns the active series directory on disk."""
        data = self.combo_series_folder.currentData()
        if data and os.path.exists(data):
            return data
        return Paths.TRANSLATIONS

    def _on_series_folder_changed(self):
        self.refresh_scripts_for_selected_series()

    def refresh_scripts_for_selected_series(self):
        """Populates .txt files strictly belonging to the active series without automatic loading."""
        target_dir = self.get_selected_series_dir()

        self.combo_folder_scripts.blockSignals(True)
        self.combo_folder_scripts.clear()
        self.combo_folder_scripts.addItem("Select script...", "")

        if os.path.exists(target_dir):
            natural_key = lambda name: [int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", name)]
            txt_files = [
                f for f in os.listdir(target_dir) 
                if f.lower().endswith(".txt") and os.path.isfile(os.path.join(target_dir, f))
            ]
            for fname in sorted(txt_files, key=natural_key):
                full_path = os.path.join(target_dir, fname)
                self.combo_folder_scripts.addItem(fname, full_path)

        self.combo_folder_scripts.setCurrentIndex(0)
        self.combo_folder_scripts.blockSignals(False)

    def on_create_new_series_folder(self):
        """Prompts user to create a new series subdirectory inside translations/."""
        folder_name, ok = QInputDialog.getText(
            self, "New Series Folder", "Enter series / comic title name:"
        )
        if ok and folder_name.strip():
            clean_name = re.sub(r'[\\/*?:"<>|]', "", folder_name.strip())
            new_path = os.path.join(Paths.TRANSLATIONS, clean_name)
            os.makedirs(new_path, exist_ok=True)
            self.refresh_series_folders()
            idx = self.combo_series_folder.findData(new_path)
            if idx >= 0:
                self.combo_series_folder.setCurrentIndex(idx)

    def on_folder_script_selected(self, index: int):
        """Loads script only when user deliberately activates a combo item."""
        if index <= 0:
            return
        selected_path = self.combo_folder_scripts.itemData(index)
        if selected_path and os.path.exists(selected_path):
            self.import_script_from_path(selected_path)

    def on_open_translations_folder(self):
        """Opens active series directory in the default operating system file manager."""
        folder = self.get_selected_series_dir()
        os.makedirs(folder, exist_ok=True)
        if os.name == "nt":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", folder])

    def load_page_state(self, path: str):
        """Populates the dialogue cards for the page currently loaded in the main viewer."""
        if not self.show_token_usage(self.page_token_usage.get(path, {})):
            self.update_token_estimate(path)
        if path in self.page_bubbles_data:
            self.populate_bubble_editor(self.page_bubbles_data[path])
        elif path in self.path_dialogues_map:
            saved_lines = self.path_dialogues_map[path]
            fake_bubbles = [{"id": i, "type": "bubble", "original": "", "direct": l, "translations": [l]} for i, l in enumerate(saved_lines, start=1)]
            self.populate_bubble_editor(fake_bubbles)
        else:
            self.populate_bubble_editor([])
        if self.mw.is_batching:
            self.set_page_audit_blocked(self.mw.is_page_blocked_by_batch(path))

    def save_current_page_editor(self):
        """Saves values from the active bubble editor cards into in-memory maps."""
        path = self.mw.current_img_path
        if not path:
            return

        lines = []
        updated = []
        for card in self.current_bubbles_widgets:
            if not hasattr(card, "line_edit"):
                continue
            line_val = card.line_edit.text().strip()
            if not line_val:
                continue

            entry = dict(getattr(card, "b_data", {}))
            entry.update({
                "id": getattr(card, "b_id", len(lines) + 1),
                "type": getattr(card, "b_type", "bubble"),
                "original": card.orig_edit.text().strip() if hasattr(card, "orig_edit") else "",
                "final": line_val,
            })
            if not entry.get("direct"):
                entry["direct"] = line_val

            lines.append(line_val)
            updated.append(entry)

        if lines:
            self.path_dialogues_map[path] = lines
            self.page_bubbles_data[path] = updated
        else:
            self.path_dialogues_map.pop(path, None)
            if path in self.page_bubbles_data:
                self.page_bubbles_data[path] = []

    def translate_current_page(self):
        """Dispatches an asynchronous single-page multimodal translation request."""
        if not self.mw.current_img_path or not os.path.exists(self.mw.current_img_path):
            QMessageBox.warning(self, "Notice", "Select a page in the left assets list first.")
            return

        api_config = self.get_active_api_config()
        if not api_config["has_credentials"]:
            QMessageBox.warning(
                self,
                "API credentials required",
                f"Open API Settings and configure {api_config['provider_name']} before translating.",
            )
            return

        request_path = self.mw.current_img_path
        self.pending_language_pairs[request_path] = self.current_language_pair()
        system_prompt, request_prompt = self.build_request_prompts(request_path)
        estimate_prompt = f"{system_prompt}\n\n{request_prompt}"
        self.update_token_estimate(request_path, estimate_prompt)
        self.set_locked(True)
        if hasattr(self.mw, "_start_timed_job"):
            self.mw._start_timed_job("Waiting to send")
        self.show_inference_status(request_path)

        self.active_worker = MultimodalTranslationWorker(
            image_path=request_path,
            full_prompt=request_prompt,
            provider=api_config["provider_id"],
            model_name=api_config["model"],
            api_key=api_config["api_key"],
            ollama_url=api_config["endpoint_url"],
            ollama_token=api_config["token"],
            thinking_level=api_config["thinking_level"],
            system_prompt=system_prompt,
            usage_profile=api_config["usage_profile"],
            request_pacing=api_config["request_pacing"],
        )
        self.active_worker.finished.connect(self._on_translation_success)
        self.active_worker.error.connect(self._on_translation_failed)
        if hasattr(self.mw, "_on_request_started"):
            self.active_worker.request_started.connect(self.mw._on_request_started)
        self.active_worker.start()

    def _on_translation_success(self, path: str, result: TranslationResult):
        """Processes successful inference output, updates item status, and renders editor cards."""
        self.set_locked(False)
        if hasattr(self.mw, "_finish_timed_job"):
            self.mw._finish_timed_job("Complete")

        status = result.status
        fname = os.path.basename(path)
        request_language_pair = self.pending_language_pairs.pop(path, None)
        usage = result.usage or {}
        self.page_token_usage[path] = usage.copy()
        if path == self.mw.current_img_path:
            self.show_token_usage(usage)
        if hasattr(self.mw, "refresh_usage_summary"):
            self.mw.refresh_usage_summary()

        if status == ProviderStatus.SAFETY_BLOCKED:
            self._set_result_status("🛡 Blocked by Content Moderation", "#ff3344")
            self.mw.file_list.update_item_state(path, "safety", result.message)
            QMessageBox.warning(
                self,
                "Content Blocked by LLM Provider",
                f"Page: {fname}\n\n"
                f"{result.message}\n\n"
                "Recommendation:\n"
                "To process sensitive, mature, or high-action scenes, switch to an alternative LLM provider (such as an uncensored local model via Ollama, or an alternative endpoint)."
            )
            return

        if status == ProviderStatus.SERVER_BUSY:
            self._set_result_status("⏳ Provider Busy / Overloaded", "#ffd600")
            self.mw.file_list.update_item_state(path, "busy", result.message)
            QMessageBox.warning(self, "Server Busy", f"{result.message}\n\nPlease retry in a couple of minutes.")
            return

        if status == ProviderStatus.EMPTY:
            self._set_result_status("💬 Silent Page (No text detected)", "#8faecf")
            self.page_bubbles_data[path] = []
            self.page_language_pairs.pop(path, None)
            self.path_dialogues_map.pop(path, None)
            self.mw.file_list.update_item_state(path, "empty", result.message or "Silent panel (No text detected)")
            self.populate_bubble_editor([])
            return

        if status == ProviderStatus.ERROR:
            self._set_result_status("✖ Translation error", "#ff5252")
            self.mw.file_list.update_item_state(path, "error", result.message or "Translation failed")
            QMessageBox.critical(self, "Translation Error", f"Failed to translate {fname}:\n{result.message}")
            return

        # Inference successful
        self.page_language_pairs[path] = request_language_pair or self.current_language_pair()
        self._set_result_status("✔ Translation generated successfully", "#00e676")

        self.page_bubbles_data[path] = result.bubbles
        self.path_dialogues_map[path] = [b.get("direct") for b in result.bubbles if b.get("direct")]
        self.mw.file_list.update_item_state(path, "ready", f"Translated ({len(result.bubbles)} dialogues)")

        if path == self.mw.current_img_path:
            self.populate_bubble_editor(result.bubbles)

    def _on_translation_failed(self, path: str, error_msg: str):
        """Handles unhandled worker thread exceptions."""
        self.set_locked(False)
        if hasattr(self.mw, "_finish_timed_job"):
            self.mw._finish_timed_job("Failed")
        self.pending_language_pairs.pop(path, None)
        self._set_result_status("✖ Translation failed", "#ff5252")
        self.mw.file_list.update_item_state(path, "error", error_msg[:60])
        QMessageBox.critical(self, "Translation Error", f"Failed to translate {os.path.basename(path)}:\n{error_msg}")

    def on_manually_add_bubble(self):
        """Manually appends an empty dialogue entity card to the editor."""
        if not self.mw.current_img_path:
            QMessageBox.warning(self, "Notice", "Select a page first.")
            return

        next_id = len(self.current_bubbles_widgets) + 1
        new_bubble_data = {
            "id": next_id,
            "type": "bubble",
            "original": "",
            "direct": "",
            "translations": [""]
        }
        self._create_bubble_card(new_bubble_data)
        self.save_current_page_editor()

    def _remove_bubble_card(self, card_widget):
        """Removes a dialogue card widget and refreshes cached dialogue lines."""
        if card_widget in self.current_bubbles_widgets:
            self.current_bubbles_widgets.remove(card_widget)
            card_widget.deleteLater()
            self.save_current_page_editor()

    def _create_bubble_card(self, b: dict):
        """Builds an interactive dialogue card with variant selectors and editable text fields."""
        card = QFrame()
        card.setSizePolicy(card.sizePolicy().horizontalPolicy(), card.sizePolicy().Policy.Maximum)
        card.setStyleSheet("background: #1b1b22; border: 1px solid #2a2a35; border-radius: 4px; padding: 5px;")
        
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(6, 6, 6, 6)
        card_lay.setSpacing(4)

        tag_type = b.get("type", "bubble").upper()
        card.b_type = b.get("type", "bubble")
        card.b_id = b.get("id", len(self.current_bubbles_widgets) + 1)
        card.b_data = dict(b)

        row_head = QHBoxLayout()
        lbl_num = QLabel(f"[{tag_type} #{card.b_id}]")
        lbl_num.setStyleSheet("color: #00d4ff; font-weight: bold; font-size: 11px;")

        btn_del = QPushButton("✕")
        btn_del.setToolTip("Delete dialogue")
        btn_del.setFixedSize(20, 20)
        btn_del.setStyleSheet("background-color: #331518; color: #ff5566; font-weight: bold; border: 1px solid #551e22; border-radius: 2px;")
        btn_del.clicked.connect(lambda: self._remove_bubble_card(card))
        card.delete_button = btn_del

        row_head.addWidget(lbl_num)
        row_head.addStretch()
        row_head.addWidget(btn_del)
        card_lay.addLayout(row_head)

        lbl_orig_tag = QLabel("Original:")
        lbl_orig_tag.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 9px; font-weight: bold;")
        
        orig_edit = QLineEdit()
        orig_edit.setFixedHeight(26)
        orig_edit.setPlaceholderText("Transcribed original text...")
        orig_edit.setText(b.get("original", "").strip())
        orig_edit.setStyleSheet("background: #15151b; border: 1px solid #2e2e3a; color: #cccccc; font-size: 10px; padding: 2px 4px;")
        orig_edit.textChanged.connect(self.save_current_page_editor)
        
        card_lay.addWidget(lbl_orig_tag)
        card_lay.addWidget(orig_edit)
        card.orig_edit = orig_edit

        sfx_en = (b.get("sfx_en") or "").strip()
        if sfx_en:
            lbl_en = QLabel(f"🔊 EN: {sfx_en}")
            lbl_en.setStyleSheet("color: #ffb74d; font-size: 10px; font-weight: bold;")
            card_lay.addWidget(lbl_en)

        sfx_meaning = (b.get("sfx_meaning") or "").strip()
        if card.b_type == "sfx" and sfx_meaning:
            lbl_meaning = QLabel(f"💡 Meaning: {sfx_meaning}")
            lbl_meaning.setStyleSheet("color: #b6a7ff; font-size: 10px; font-style: italic;")
            lbl_meaning.setWordWrap(True)
            card_lay.addWidget(lbl_meaning)

        subtext = b.get("subtext", "").strip()
        if subtext:
            lbl_sub = QLabel(f"💡 Subtext: {subtext}")
            lbl_sub.setStyleSheet("color: #a0a0b0; font-size: 10px; font-style: italic;")
            lbl_sub.setWordWrap(True)
            card_lay.addWidget(lbl_sub)

        direct_txt = (b.get("direct") or "").strip()
        options_dict, seen = {}, set()
        if direct_txt:
            options_dict["[Direct] " + direct_txt] = direct_txt
            seen.add(direct_txt.lower())

        for tag, key in (("Formal", "formal"), ("Aggressive/Cold", "aggressive"), ("Natural", "natural")):
            v = (b.get(key) or "").strip()
            if v and v.lower() not in seen:
                seen.add(v.lower())
                options_dict[f"[{tag}] {v}"] = v

        for opt in b.get("translations", []):
            if opt and opt.strip().lower() not in seen:
                seen.add(opt.strip().lower())
                options_dict[f"[Option] {opt}"] = opt

        combo = QComboBox()
        combo.setFixedHeight(24)
        combo.setStyleSheet(f"background: {Config.COLOR_BG}; border: 1px solid #333340; font-size: 10px; padding: 2px;")
        for display_label, actual_text in options_dict.items():
            combo.addItem(display_label, actual_text)

        line_edit = QLineEdit()
        line_edit.setFixedHeight(28)
        line_edit.setPlaceholderText("Translation to be exported into script...")
        line_edit.setStyleSheet(f"background: {Config.COLOR_BG}; border: 1px solid #444455; font-size: 11px; padding: 3px 5px; font-weight: 500;")
        
        final = (b.get("final") or "").strip()
        default_val = final or next(iter(options_dict.values()), direct_txt)
        line_edit.setText(default_val)

        if final and combo.findData(final) >= 0:
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(final))
            combo.blockSignals(False)

        combo.currentIndexChanged.connect(lambda idx, c=combo, le=line_edit: le.setText(c.currentData()))
        line_edit.textChanged.connect(self.save_current_page_editor)

        if options_dict:
            card_lay.addWidget(combo)
            card.variant_combo = combo
        card_lay.addWidget(line_edit)

        if hasattr(self, "_bottom_spacer") and self._bottom_spacer:
            idx = self.bubble_lay.indexOf(self._bottom_spacer)
            self.bubble_lay.insertWidget(idx, card)
        else:
            self.bubble_lay.addWidget(card)

        self.current_bubbles_widgets.append(card)
        card.line_edit = line_edit

    def populate_bubble_editor(self, bubbles: list):
        """Reconstructs the card layout for the specified bubble list."""
        while self.bubble_lay.count():
            item = self.bubble_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self.current_bubbles_widgets.clear()
        self._bottom_spacer = None

        if not bubbles:
            lbl_empty = QLabel("No text entities detected on this page.")
            lbl_empty.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-style: italic; margin-top: 10px;")
            lbl_empty.setAlignment(Qt.AlignCenter)
            self.bubble_lay.addWidget(lbl_empty)
            self.bubble_lay.addStretch(1)
            return

        for b in bubbles:
            self._create_bubble_card(b)

        spacer = QWidget()
        spacer.setStyleSheet("background: transparent;")
        self.bubble_lay.addWidget(spacer, 1)
        self._bottom_spacer = spacer

    # --- SCRIPT TEMPLATE CREATION ---
    def on_generate_template(self):
        """Displays dialog to initialize a compliant script skeleton file."""
        paths = self._get_all_project_paths()
        if not paths:
            QMessageBox.warning(self, "No Images Loaded", "Please import an image folder before creating a script.")
            return

        active_series = self.combo_series_folder.currentText().replace("📂 ", "").replace("📁 [Root] translations/", "").strip()
        if not active_series or active_series == "translations":
            active_series = os.path.basename(os.path.dirname(paths[0])) if paths else ""

        chap_match = re.search(r"(\d+)", os.path.basename(os.path.dirname(paths[0])) if paths else "")
        default_chap = chap_match.group(1) if chap_match else "1"

        dialog = CreateScriptDialog(default_series=active_series, default_chapter=default_chap, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        series_title, chapter_num, filename = dialog.get_data()
        target_dir = self.get_selected_series_dir()
        save_path = os.path.join(target_dir, filename)

        if os.path.exists(save_path):
            ans = QMessageBox.question(
                self, "File Exists", 
                f"The file '{filename}' already exists.\nDo you want to overwrite it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ans != QMessageBox.Yes:
                return

        try:
            content = TranslationScriptEngine.generate_template(
                paths, series_title=series_title, chapter_num=chapter_num
            )
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(content)

            self.loaded_script_path = save_path
            self.lbl_script_status.setText(f"Script: {filename}")
            
            self.refresh_scripts_for_selected_series()
            idx = self.combo_folder_scripts.findData(save_path)
            if idx >= 0:
                self.combo_folder_scripts.blockSignals(True)
                self.combo_folder_scripts.setCurrentIndex(idx)
                self.combo_folder_scripts.blockSignals(False)

            QMessageBox.information(
                self, "Script Created", 
                f"Translation script template created successfully:\n\n{filename}\n\n"
                f"Series: {series_title}\nChapter: {chapter_num}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Creation Error", str(e))

    def on_import_script(self):
        """Opens file dialog for user to select an existing .txt script."""
        paths = self._get_all_project_paths()
        if not paths:
            QMessageBox.warning(self, "No Images", "Please import an image folder first.")
            return

        target_dir = self.get_selected_series_dir()
        open_path, _ = QFileDialog.getOpenFileName(
            self, "Import Translation Script (.txt)", target_dir, "Text Files (*.txt)"
        )
        if not open_path:
            return

        self.import_script_from_path(open_path)

    def import_script_from_path(self, open_path: str):
        """Loads and resolves dialogue lines from a script file into project pages."""
        paths = self._get_all_project_paths()
        if not paths:
            return

        try:
            with open(open_path, "r", encoding="utf-8") as f:
                raw_text = f.read()

            entries = TranslationScriptEngine.parse_script(raw_text)
            self.loaded_script_path = open_path

            basename_to_path = {_nfc(os.path.basename(p)).lower(): p for p in paths}
            stem_to_path = {_nfc(os.path.splitext(os.path.basename(p))[0]).lower(): p for p in paths}
            resolved = {}

            for entry in entries:
                raw_fname = entry.get("filename")
                lines = entry.get("lines", [])
                if raw_fname and lines:
                    key = _nfc(raw_fname).lower()
                    target_path = basename_to_path.get(key) or stem_to_path.get(key)
                    if target_path:
                        resolved[target_path] = lines

            self.path_dialogues_map = resolved

            for p in resolved:
                self.page_bubbles_data.pop(p, None)
                self.page_token_usage.pop(p, None)
                self.page_language_pairs.pop(p, None)
                self.mw.file_list.update_item_state(p, "modified", "Imported from script")

            self.lbl_script_status.setText(f"Loaded: {os.path.basename(open_path)}")
            if self.mw.current_img_path:
                self.load_page_state(self.mw.current_img_path)

            QMessageBox.information(
                self, "Script Imported", 
                f"Loaded dialogues for {len(resolved)} page(s) from:\n{os.path.basename(open_path)}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))
