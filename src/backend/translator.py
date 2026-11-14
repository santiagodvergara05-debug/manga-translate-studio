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
from src.backend.providers.gemini_provider import GeminiProvider
from src.frontend.api_settings import APISettingsDialog
from src.backend.languages import (
    get_source_display_names, 
    get_target_display_names
)
from src.utils.i18n import tr


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
        self.setWindowTitle(tr("translator.create_new_translation_script"))
        self.setFixedSize(460, 220)
        self.setStyleSheet(f"background-color: {Config.COLOR_PANEL}; color: {Config.COLOR_TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        lbl_title = QLabel(tr("translator.series_title"))
        lbl_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #00d2ff;")
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText(tr("translator.e_g_my_favorite_webtoon_series"))
        self.txt_title.setText(default_series)
        self.txt_title.setStyleSheet("background-color: #121218; border: 1px solid #2a2a35; padding: 5px; font-size: 11px;")
        self.txt_title.textChanged.connect(self._update_preview)

        lbl_chapter = QLabel(tr("translator.chapter"))
        lbl_chapter.setStyleSheet("font-size: 11px; font-weight: bold; color: #00d2ff;")
        self.txt_chapter = QLineEdit()
        self.txt_chapter.setPlaceholderText(tr("translator.e_g_1_04_special"))
        self.txt_chapter.setText(default_chapter)
        self.txt_chapter.setStyleSheet("background-color: #121218; border: 1px solid #2a2a35; padding: 5px; font-size: 11px;")
        self.txt_chapter.textChanged.connect(self._update_preview)

        self.lbl_preview = QLabel(tr("translator.file"))
        self.lbl_preview.setStyleSheet("color: #888899; font-size: 10px; font-style: italic;")

        layout.addWidget(lbl_title)
        layout.addWidget(self.txt_title)
        layout.addWidget(lbl_chapter)
        layout.addWidget(self.txt_chapter)
        layout.addWidget(self.lbl_preview)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton(tr("translator.cancel"))
        btn_cancel.clicked.connect(self.reject)

        self.btn_create = QPushButton(tr("translator.create_script"))
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
        self.lbl_preview.setText(tr("translator.generated_filename_filename", filename=filename))

    def _validate_and_accept(self):
        """Validates that mandatory fields are populated prior to dialog completion."""
        if not self.txt_title.text().strip():
            QMessageBox.warning(self, tr("translator.validation_notice"), tr("translator.please_provide_a_series_title"))
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
        self.setWindowTitle(tr("translator.rules_system_prompt_configuration"))
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
        lbl_u = QLabel(tr("translator.custom_style_guidelines_lore_glossary_an"))
        lbl_u.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 11px;")
        self.txt_user_rules = QTextEdit()
        self.txt_user_rules.setPlaceholderText(
            tr("translator.optional_write_character_names_glossary")
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
        lbl_p = QLabel(tr("translator.base_prompt_sent_to_the_model"))
        lbl_p.setWordWrap(True)
        lbl_p.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 11px;")
        lay_p.addWidget(lbl_p)

        lbl_medium = QLabel(tr("translator.current_medium_medium", medium=medium))
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
        options_scroll = QScrollArea()
        options_scroll.setWidgetResizable(True)
        options_scroll.setFrameShape(QFrame.NoFrame)
        options_content = QWidget()
        options_content.setMinimumWidth(0)
        options_layout = QVBoxLayout(options_content)
        options_layout.setContentsMargins(10, 8, 10, 8)
        options_layout.setSpacing(6)
        options_scroll.setWidget(options_content)
        lay_o.addWidget(options_scroll)
        lbl_o = QLabel(
            tr("translator.choose_which_content_and_optional_output")
        )
        lbl_o.setWordWrap(True)
        lbl_o.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 11px;")
        options_layout.addWidget(lbl_o)

        option_specs = [
            ("sfx", tr("translator.option_sfx_title"), tr("translator.option_sfx_description")),
            ("sfx_meaning", tr("translator.option_sfx_meaning_title"), tr("translator.option_sfx_meaning_description")),
            ("deduplicate_sfx", tr("translator.option_deduplicate_sfx_title"), tr("translator.option_deduplicate_sfx_description")),
            ("narration", tr("translator.option_narration_title"), tr("translator.option_narration_description")),
            ("outside", tr("translator.option_outside_title"), tr("translator.option_outside_description")),
            ("variants", tr("translator.option_variants_title"), tr("translator.option_variants_description")),
            ("subtext", tr("translator.option_subtext_title"), tr("translator.option_subtext_description")),
            ("r19_mode", tr("translator.option_r19_title"), tr("translator.option_r19_description")),
        ]
        self.option_checks = {}

        def add_option(target_layout, key, title, description):
            checkbox = QCheckBox(title)
            checkbox.setChecked(bool(option_values.get(key, True)))
            checkbox.setStyleSheet("font-size: 11px; font-weight: bold;")
            detail = QLabel(description)
            detail.setWordWrap(True)
            detail.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px; margin-left: 22px;")
            target_layout.addWidget(checkbox)
            target_layout.addWidget(detail)
            self.option_checks[key] = checkbox
            checkbox.toggled.connect(self._update_prompt_preview)

        add_option(options_layout, *option_specs[0])

        # Draw the SFX-only settings as child branches so their dependency is visible.
        dependent_options = QWidget()
        dependent_layout = QVBoxLayout(dependent_options)
        dependent_layout.setContentsMargins(24, 0, 0, 0)
        dependent_layout.setSpacing(4)
        for index, (key, title, description) in enumerate(option_specs[1:3]):
            branch_row = QHBoxLayout()
            branch_row.setContentsMargins(0, 0, 0, 0)
            branch_row.setSpacing(8)
            connector = QLabel("└─" if index == 1 else "├─")
            connector.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-family: Consolas, monospace;")
            branch_row.addWidget(connector, 0, Qt.AlignmentFlag.AlignTop)
            branch_content = QVBoxLayout()
            branch_content.setContentsMargins(0, 0, 0, 0)
            branch_content.setSpacing(2)
            branch_row.addLayout(branch_content, 1)
            dependent_layout.addLayout(branch_row)
            add_option(branch_content, key, title, description)
        options_layout.addWidget(dependent_options)
        self.sfx_dependent_options = dependent_options

        for key, title, description in option_specs[3:]:
            add_option(options_layout, key, title, description)

        options_layout.addStretch(1)
        self.option_checks["sfx"].toggled.connect(self._sync_sfx_dependent_options)
        self._sync_sfx_dependent_options(self.option_checks["sfx"].isChecked())
        self.tabs.addTab(tab_options, tr("translator.extraction_options"))
        self.tabs.addTab(tab_user, tr("translator.user_rules_tone_lore"))
        self.tabs.addTab(tab_prompt, tr("translator.system_prompt_read_only"))
        lay.addWidget(self.tabs)

        self.txt_user_rules.textChanged.connect(self._update_prompt_preview)

        btn_row = QHBoxLayout()
        self.btn_restore = QPushButton(tr("translator.restore_defaults"))
        self.btn_restore.clicked.connect(self._restore_defaults)
        btn_save = QPushButton(tr("translator.save_rules_to_disk"))
        btn_save.setObjectName("PrimaryBtn")
        btn_save.setStyleSheet("background-color: #00d2ff; color: black; font-weight: bold; padding: 6px 16px;")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton(tr("translator.cancel"))
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

    def _sync_sfx_dependent_options(self, sfx_enabled: bool):
        """Locks SFX-specific options when SFX extraction is disabled."""
        meaning_checkbox = self.option_checks["sfx_meaning"]
        deduplicate_checkbox = self.option_checks["deduplicate_sfx"]
        self.sfx_dependent_options.setEnabled(sfx_enabled)
        if not sfx_enabled:
            meaning_checkbox.setChecked(False)
            deduplicate_checkbox.setChecked(False)
        meaning_checkbox.setEnabled(sfx_enabled)
        deduplicate_checkbox.setEnabled(sfx_enabled)
        meaning_checkbox.setToolTip(
            tr("translator.enable_sound_effects_and_onomatopoeias_f")
            if not sfx_enabled else
            tr("translator.show_a_concise_sound_effect_meaning")
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

            # Persist the stable medium ID, not its localized display label.
            m_idx = self.mode_combo.findData(mode)
            if m_idx < 0:  # Compatibility with older session values.
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
                "mode": self.mode_combo.currentData(),
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
            "connection_profile_id": self.cred_manager.get_active_connection_profile_id() or f"legacy-{provider_id}",
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
        saved_profiles = self.cred_manager.get_connection_profiles()
        active_profile = saved_profiles.get(config["connection_profile_id"], {})
        config["connection_profile_name"] = str(active_profile.get("name") or "Legacy / unassigned")
        return config

    def _refresh_api_summary(self):
        """Updates the compact provider summary shown in the translation panel."""
        if not hasattr(self, "api_summary"):
            return
        config = self.get_active_api_config()
        model = config["model"] or tr("main.no_model_selected")
        state = tr("main.status_ready") if config["has_credentials"] else tr("main.status_credentials_needed")
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
            medium=self.mode_combo.currentData()
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
        self.lbl_token_counter.setText(tr("translator.est_tokens_total_text_txt_tok", total=format(total, ','), txt_tok=format(txt_tok, ','), img_tok=format(img_tok, ',')))
        self.lbl_token_counter.setStyleSheet("color: #00d4ff; font-size: 9px; font-weight: bold;")
        self.lbl_token_counter.setToolTip(
            tr("translator.approximate_input_tokens_before_sending")
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
        self.lbl_token_counter.setText(tr("translator.real_join", join=' · '.join(parts)))
        self.lbl_token_counter.setStyleSheet("color: #00e676; font-size: 9px; font-weight: bold;")
        self.lbl_token_counter.setToolTip(
            tr("translator.usage_reported_by_the_provider_cache")
        )
        return True

    def init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        title = QLabel(tr("translator.ai_multimodal_translator"))
        title.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-size: 11px; font-weight: bold;")
        lay.addWidget(title)

        lbl_api = QLabel(tr("translator.1_ai_engine_format_rules"))
        lbl_api.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 9px; font-weight: bold;")
        lay.addWidget(lbl_api)

        row_top = QHBoxLayout()

        self.mode_combo = QComboBox()
        # Keep provider/prompt-facing medium IDs stable while translating labels.
        for label_key, medium_id in (
            ("translator.manhwa", "Manhwa"),
            ("translator.manga", "Manga"),
            ("translator.comic", "Comic"),
            ("translator.manhua", "Manhua"),
        ):
            self.mode_combo.addItem(tr(label_key), medium_id)
        self.mode_combo.currentIndexChanged.connect(self._save_session_credentials)

        self.btn_api_settings = QPushButton(tr("translator.api_settings"))
        self.btn_api_settings.setStyleSheet("background-color: #1e1e26; border: 1px solid #333342; font-size: 11px; font-weight: bold; padding: 4px 10px;")
        self.btn_api_settings.clicked.connect(self.on_open_api_settings)

        self.btn_rules = QPushButton(tr("translator.rules"))
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
        lbl_from = QLabel(tr("translator.from"))
        lbl_from.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px;")
        self.src_lang_combo = QComboBox()
        self.src_lang_combo.addItems(get_source_display_names())
        self.src_lang_combo.currentIndexChanged.connect(self._save_session_credentials)

        lbl_to = QLabel(tr("translator.to"))
        lbl_to.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px;")
        self.tgt_lang_combo = QComboBox()
        self.tgt_lang_combo.addItems(get_target_display_names())
        self.tgt_lang_combo.currentIndexChanged.connect(self._save_session_credentials)

        row_lang.addWidget(lbl_from)
        row_lang.addWidget(self.src_lang_combo, 1)
        row_lang.addWidget(lbl_to)
        row_lang.addWidget(self.tgt_lang_combo, 1)
        lay.addLayout(row_lang)

        self.lbl_token_counter = QLabel(tr("translator.est_tokens_1_450_text_330"))
        self.lbl_token_counter.setStyleSheet("color: #00d4ff; font-size: 9px; font-weight: bold;")
        lay.addWidget(self.lbl_token_counter)

        self.btn_translate_page = QPushButton(tr("translator.translate_active_page"))
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
        self.lbl_bubbles = QLabel(tr("translator.2_detected_text_entities_variants"))
        self.lbl_bubbles.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 9px; font-weight: bold;")
        
        self.btn_add_bubble = QPushButton(tr("translator.add_dialogue"))
        self.btn_add_bubble.setToolTip(tr("translator.manually_insert_a_text_entity_that"))
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
        lbl_script = QLabel(tr("translator.3_script_file_txt"))
        lbl_script.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 9px; font-weight: bold; margin-top: 4px;")
        lay.addWidget(lbl_script)

        # TIER 1: SERIES SELECTION
        row_series = QHBoxLayout()
        lbl_series = QLabel(tr("translator.series"))
        lbl_series.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px; min-width: 42px;")
        
        self.combo_series_folder = QComboBox()
        self.combo_series_folder.setToolTip(tr("translator.select_series_folder_inside_translations"))
        self.combo_series_folder.currentIndexChanged.connect(self._on_series_folder_changed)

        self.btn_new_series_folder = QPushButton("➕")
        self.btn_new_series_folder.setToolTip(tr("translator.create_new_series_folder_in_translations"))
        self.btn_new_series_folder.setFixedSize(26, 24)
        self.btn_new_series_folder.setStyleSheet("background-color: #1e1e28; border: 1px solid #333342; font-size: 11px;")
        self.btn_new_series_folder.clicked.connect(self.on_create_new_series_folder)

        self.btn_open_folder = QPushButton("📁")
        self.btn_open_folder.setToolTip(tr("translator.open_selected_series_folder_in_file"))
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
        lbl_pick = QLabel(tr("translator.script"))
        lbl_pick.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px; min-width: 42px;")
        
        self.combo_folder_scripts = QComboBox()
        self.combo_folder_scripts.setToolTip(tr("translator.scripts_txt_available_in_the_selected"))
        self.combo_folder_scripts.activated.connect(self.on_folder_script_selected)

        row_script_sel.addWidget(lbl_pick)
        row_script_sel.addWidget(self.combo_folder_scripts, 1)
        lay.addLayout(row_script_sel)

        row_script_btns = QHBoxLayout()
        self.btn_new_txt = QPushButton(tr("translator.new_txt"))
        self.btn_new_txt.clicked.connect(self.on_generate_template)
        self.btn_load_txt = QPushButton(tr("translator.load_txt"))
        self.btn_load_txt.clicked.connect(self.on_import_script)
        row_script_btns.addWidget(self.btn_new_txt)
        row_script_btns.addWidget(self.btn_load_txt)
        lay.addLayout(row_script_btns)

        self.lbl_script_status = QLabel(tr("common.script_none"))
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
                self.mw.mark_page_inference_started(self.mw.current_img_path)

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
            progress = tr(
                "translator.page_progress_batch",
                position=batch_position,
                total=batch_total,
                page_name=page_name,
            )
        else:
            progress = tr("translator.page_progress_single", page_name=page_name)

        self.lbl_api_status.setText(tr("translator.model_working_progress", progress=progress))
        self.lbl_api_status.setStyleSheet(
            "color: #00d2ff; font-size: 10px; font-weight: bold; padding: 2px;"
        )
        self.lbl_api_status.setVisible(True)

    def _set_result_status(self, message: str, color: str):
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
            medium=self.mode_combo.currentData(),
        )
        if dialog.exec() == QDialog.Accepted:
            new_user, new_options = dialog.get_results()
            self.prompt_manager.save_user_rules(new_user)
            self.prompt_manager.save_options(new_options)
            self.update_token_estimate()
            QMessageBox.information(self, tr("translator.rules_saved"), tr("translator.user_rules_and_extraction_options_were"))

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

        self.combo_series_folder.addItem(tr("translator.root_translations"), base_dir)

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
        self.combo_folder_scripts.addItem(tr("translator.select_script"), "")

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
            self, tr("translator.new_series_folder"), tr("translator.enter_series_comic_title_name")
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

    def on_editor_content_changed(self, *_):
        """Persist a user edit and update the page's local-modification status."""
        self.save_current_page_editor()
        if hasattr(self.mw, "mark_current_modified"):
            self.mw.mark_current_modified()

    def translate_current_page(self):
        """Dispatches an asynchronous single-page multimodal translation request."""
        if not self.mw.current_img_path or not os.path.exists(self.mw.current_img_path):
            QMessageBox.warning(self, tr("common.notice"), tr("translator.select_a_page_in_the_left"))
            return

        api_config = self.get_active_api_config()
        if not api_config["has_credentials"]:
            QMessageBox.warning(
                self,
                tr("common.api_credentials_required"),
                tr("translator.open_api_settings_and_configure_provider", provider_name=api_config['provider_name']),
            )
            return

        request_path = self.mw.current_img_path
        self.save_current_page_editor()
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
            connection_profile_id=api_config["connection_profile_id"],
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
            self._set_result_status(tr("translator.status_blocked_by_content_moderation"), "#ff3344")
            self.mw.set_page_status(path, "safety")
            self.mw.file_list.update_item_state(path, "safety", result.message)
            if not getattr(self.mw, "_close_pending", False):
                QMessageBox.warning(
                    self,
                    tr("translator.content_blocked_by_llm_provider"),
                    tr("translator.page_fname_message_recommendation_to_pro", fname=fname, message=result.message)
                )
            return

        if status == ProviderStatus.SERVER_BUSY:
            self._set_result_status(tr("translator.status_provider_busy_overloaded"), "#ffd600")
            self.mw.set_page_status(path, "busy")
            self.mw.file_list.update_item_state(path, "busy", result.message)
            if not getattr(self.mw, "_close_pending", False):
                QMessageBox.warning(self, tr("translator.server_busy"), tr("translator.message_please_retry_in_a_couple", message=result.message))
            return

        if status == ProviderStatus.EMPTY:
            self._set_result_status(tr("translator.status_silent_page"), "#8faecf")
            self.mw.set_page_status(path, "empty")
            self.page_bubbles_data[path] = []
            self.page_language_pairs.pop(path, None)
            self.path_dialogues_map.pop(path, None)
            self.mw.file_list.update_item_state(
                path, "empty", result.message or tr("widgets.status_silent_panel")
            )
            self.populate_bubble_editor([])
            return

        if status == ProviderStatus.ERROR:
            self._set_result_status(tr("translator.status_translation_error"), "#ff5252")
            self.mw.set_page_status(path, "error")
            self.mw.file_list.update_item_state(
                path, "error", result.message or tr("widgets.status_translation_failed")
            )
            if not getattr(self.mw, "_close_pending", False):
                QMessageBox.critical(self, tr("translator.translation_error"), tr("translator.failed_to_translate_fname_message", fname=fname, message=result.message))
            return

        # Inference successful
        self.page_language_pairs[path] = request_language_pair or self.current_language_pair()
        self._set_result_status(tr("translator.status_translation_generated"), "#00e676")

        self.mw.set_page_status(path, "ready")
        self.page_bubbles_data[path] = result.bubbles
        self.path_dialogues_map[path] = [b.get("direct") for b in result.bubbles if b.get("direct")]
        self.mw.file_list.update_item_state(
            path, "ready",
            tr("widgets.status_translated_dialogues", count=len(result.bubbles)),
        )

        if path == self.mw.current_img_path:
            self.populate_bubble_editor(result.bubbles)

    def _on_translation_failed(self, path: str, error_msg: str):
        """Handles unhandled worker thread exceptions."""
        self.set_locked(False)
        if hasattr(self.mw, "_finish_timed_job"):
            self.mw._finish_timed_job("Failed")
        self.pending_language_pairs.pop(path, None)
        self._set_result_status(tr("translator.status_translation_failed"), "#ff5252")
        self.mw.set_page_status(path, "error")
        self.mw.file_list.update_item_state(path, "error", error_msg[:60])
        if not getattr(self.mw, "_close_pending", False):
            QMessageBox.critical(self, tr("translator.translation_error"), tr("translator.failed_to_translate_basename_error_msg", basename=os.path.basename(path), error_msg=error_msg))

    def on_manually_add_bubble(self):
        """Manually appends an empty dialogue entity card to the editor."""
        if not self.mw.current_img_path:
            QMessageBox.warning(self, tr("common.notice"), tr("translator.select_a_page_first"))
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
        self.on_editor_content_changed()

    def _remove_bubble_card(self, card_widget):
        """Removes a dialogue card widget and refreshes cached dialogue lines."""
        if card_widget in self.current_bubbles_widgets:
            self.current_bubbles_widgets.remove(card_widget)
            card_widget.deleteLater()
            self.on_editor_content_changed()

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
        btn_del.setToolTip(tr("translator.delete_dialogue"))
        btn_del.setFixedSize(20, 20)
        btn_del.setStyleSheet("background-color: #331518; color: #ff5566; font-weight: bold; border: 1px solid #551e22; border-radius: 2px;")
        btn_del.clicked.connect(lambda: self._remove_bubble_card(card))
        card.delete_button = btn_del

        row_head.addWidget(lbl_num)
        row_head.addStretch()
        row_head.addWidget(btn_del)
        card_lay.addLayout(row_head)

        lbl_orig_tag = QLabel(tr("translator.original"))
        lbl_orig_tag.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 9px; font-weight: bold;")
        
        orig_edit = QLineEdit()
        orig_edit.setFixedHeight(26)
        orig_edit.setPlaceholderText(tr("translator.transcribed_original_text"))
        orig_edit.setText(b.get("original", "").strip())
        orig_edit.setStyleSheet("background: #15151b; border: 1px solid #2e2e3a; color: #cccccc; font-size: 10px; padding: 2px 4px;")
        orig_edit.textChanged.connect(self.on_editor_content_changed)
        
        card_lay.addWidget(lbl_orig_tag)
        card_lay.addWidget(orig_edit)
        card.orig_edit = orig_edit

        sfx_en = (b.get("sfx_en") or "").strip()
        if sfx_en:
            lbl_en = QLabel(tr("translator.en_sfx_en", sfx_en=sfx_en))
            lbl_en.setStyleSheet("color: #ffb74d; font-size: 10px; font-weight: bold;")
            card_lay.addWidget(lbl_en)

        sfx_meaning = (b.get("sfx_meaning") or "").strip()
        if card.b_type == "sfx" and sfx_meaning:
            lbl_meaning = QLabel(tr("translator.meaning_sfx_meaning", sfx_meaning=sfx_meaning))
            lbl_meaning.setStyleSheet("color: #b6a7ff; font-size: 10px; font-style: italic;")
            lbl_meaning.setWordWrap(True)
            card_lay.addWidget(lbl_meaning)

        subtext = b.get("subtext", "").strip()
        if subtext:
            lbl_sub = QLabel(tr("translator.subtext_subtext", subtext=subtext))
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
        line_edit.setPlaceholderText(tr("translator.translation_to_be_exported_into_script"))
        line_edit.setStyleSheet(f"background: {Config.COLOR_BG}; border: 1px solid #444455; font-size: 11px; padding: 3px 5px; font-weight: 500;")
        
        final = (b.get("final") or "").strip()
        default_val = final or next(iter(options_dict.values()), direct_txt)
        line_edit.setText(default_val)

        if final and combo.findData(final) >= 0:
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(final))
            combo.blockSignals(False)

        combo.currentIndexChanged.connect(lambda idx, c=combo, le=line_edit: le.setText(c.currentData()))
        line_edit.textChanged.connect(self.on_editor_content_changed)

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
            lbl_empty = QLabel(tr("translator.no_text_entities_detected_on_this"))
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
            QMessageBox.warning(self, tr("translator.no_images_loaded"), tr("translator.please_import_an_image_folder_before"))
            return

        # The folder path is stable data; its visible label can be localized.
        selected_dir = self.combo_series_folder.currentData()
        active_series = os.path.basename(os.path.normpath(selected_dir)) if selected_dir else ""
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
                self, tr("translator.file_exists"),
                tr("translator.the_file_filename_already_exists_do", filename=filename),
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
            self.lbl_script_status.setText(tr("translator.script_filename", filename=filename))
            
            self.refresh_scripts_for_selected_series()
            idx = self.combo_folder_scripts.findData(save_path)
            if idx >= 0:
                self.combo_folder_scripts.blockSignals(True)
                self.combo_folder_scripts.setCurrentIndex(idx)
                self.combo_folder_scripts.blockSignals(False)

            QMessageBox.information(
                self, tr("translator.script_created"),
                tr("translator.translation_script_template_created_succ", filename=filename, series_title=series_title, chapter_num=chapter_num)
            )
        except Exception as e:
            QMessageBox.critical(self, tr("translator.creation_error"), str(e))

    def on_import_script(self):
        """Opens file dialog for user to select an existing .txt script."""
        paths = self._get_all_project_paths()
        if not paths:
            QMessageBox.warning(self, tr("translator.no_images"), tr("translator.please_import_an_image_folder_first"))
            return

        target_dir = self.get_selected_series_dir()
        open_path, _ = QFileDialog.getOpenFileName(
            self, tr("translator.import_translation_script_txt"), target_dir, tr("translator.text_files_txt")
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
                self.mw.set_page_status(p, "script_synced")
                self.mw.file_list.update_item_state(
                    p, "script_synced", tr("widgets.status_loaded_from_script")
                )

            self.lbl_script_status.setText(tr("translator.loaded_basename", basename=os.path.basename(open_path)))
            if self.mw.current_img_path:
                self.load_page_state(self.mw.current_img_path)

            QMessageBox.information(
                self, tr("translator.script_imported"),
                tr("translator.loaded_dialogues_for_count_page_s", count=len(resolved), basename=os.path.basename(open_path))
            )

        except Exception as e:
            QMessageBox.critical(self, tr("translator.import_error"), str(e))
