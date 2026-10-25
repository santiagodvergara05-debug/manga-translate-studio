import os
import re
import json
import subprocess
import unicodedata

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFileDialog, QMessageBox, QComboBox, QLineEdit, QScrollArea, 
    QFrame, QDialog, QTextEdit, QTabWidget, QCheckBox, QInputDialog
)
from PySide6.QtCore import Qt

from src.utils.config import Config
from src.utils.paths import Paths
from src.utils.logger import logger
from src.backend.providers.base_provider import ProviderStatus, TranslationResult
from src.backend.ai_client import FetchModelsWorker, MultimodalTranslationWorker, AIClientManager
from src.backend.languages import (
    get_source_display_names, 
    get_target_display_names, 
    is_asian_source, 
    get_sfx_rule_for_target
)


def _nfc(s: str) -> str:
    """Normalizes Unicode strings to NFC standard for strict compatibility with Manga Cleaner."""
    return unicodedata.normalize("NFC", s) if s else ""


READING_ORDER = {
    "Manhwa": "Vertical webtoon scroll: top-to-bottom, left-to-right within the same row.",
    "Manga": "Japanese format: right-to-left, top-to-bottom.",
    "Comic": "Western format: left-to-right, top-to-bottom.",
    "Manhua": "Vertical scroll: top-to-bottom, left-to-right within the same row.",
}

DEFAULT_CORE_RULES = r"""# CORE EXTRACTION ENGINE
Extract every text entity on the attached page, following the reading order given in ACTIVE MEDIUM:
speech bubbles, narration boxes/captions, sound effects (SFX) and floating outside text.

RULES
1. One element per visual unit. Never merge separate bubbles or panels. Never skip short or incomplete fragments (a single word, or a sentence cut off at a page edge such as "HOW LONG HAS IT"), including text at the very top or bottom.
2. Transcribe the exact text into "original" so the editor can verify it. Translate strictly from the source language to the target language.
3. Sentences often continue across bubbles and pages. If a PREVIOUS PAGE CONTEXT block is present, use it only for continuity; it is not part of this page, never return it.
4. IGNORE and do not return: watermarks, scanlator or studio credits, logos, URLs, page numbers and isolated symbols (#, *, ♪).
5. Variants (formal, aggressive, natural): fill one only if it differs meaningfully from "direct"; otherwise use "". Never fill them for SFX.
6. "subtext": one short sentence only when the tone is not obvious; otherwise "". Never name a character in subtext unless an explicit name label is visible on the page.
7. If the page has no translatable text, return {"bubbles": []}.
8. Follow the USER RULES below for tone, pronouns, glossary and lore.
9. Write every translation as a single clean line. Never insert line breaks (\n), even if the original text is split across several lines inside the bubble.
10. Continuity punctuation: if a sentence is split across bubbles or page boundaries, the opening fragment must open with ¿ or ¡ (if applicable) and not end with a period; the continuing fragment must begin in lowercase and close with ? or !.
"""

DEFAULT_USER_RULES = ""


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
        raw_title = self.txt_title.text().strip() or "Untitled_Series"
        raw_chapter = self.txt_chapter.text().strip() or "1"
        clean_title = re.sub(r'[\\/*?:"<>|]', "", raw_title).strip()
        clean_chap = re.sub(r'[\\/*?:"<>|]', "", raw_chapter).strip()
        return f"{clean_title} - Chapter {clean_chap}.txt"

    def _update_preview(self):
        filename = self._get_clean_filename()
        self.lbl_preview.setText(f"Generated filename: {filename}")

    def _validate_and_accept(self):
        if not self.txt_title.text().strip():
            QMessageBox.warning(self, "Validation Notice", "Please provide a series title.")
            self.txt_title.setFocus()
            return
        self.accept()

    def get_data(self) -> tuple[str, str, str]:
        title = self.txt_title.text().strip()
        chapter = self.txt_chapter.text().strip()
        filename = self._get_clean_filename()
        return title, chapter, filename


# /////////////////////////////////#
#       RULES & USER DIALOG        #
# /////////////////////////////////#

class RulesDialog(QDialog):
    def __init__(self, user_rules: str, core_rules: str, parent=None):
        super().__init__(parent)
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

        tab_core = QWidget()
        lay_c = QVBoxLayout(tab_core)
        lbl_c = QLabel("Fixed engine constraints and extraction schema:")
        lbl_c.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 11px;")
        self.txt_core_rules = QTextEdit()
        self.txt_core_rules.setStyleSheet(f"background-color: {Config.COLOR_BG}; border: 1px solid #2a2a35; font-family: Consolas, monospace; font-size: 11px; padding: 6px;")
        self.txt_core_rules.setPlainText(core_rules)
        lay_c.addWidget(lbl_c)
        lay_c.addWidget(self.txt_core_rules)

        self.tabs.addTab(tab_user, "User Rules (Tone & Lore)")
        self.tabs.addTab(tab_core, "Core Engine (Technical)")
        lay.addWidget(self.tabs)

        btn_row = QHBoxLayout()
        btn_restore = QPushButton("Restore Defaults")
        btn_restore.clicked.connect(self._restore_defaults)
        btn_save = QPushButton("Save Rules to Disk")
        btn_save.setObjectName("PrimaryBtn")
        btn_save.setStyleSheet("background-color: #00d2ff; color: black; font-weight: bold; padding: 6px 16px;")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_restore)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)

    def _restore_defaults(self):
        if self.tabs.currentIndex() == 0:
            self.txt_user_rules.setPlainText(DEFAULT_USER_RULES)
        else:
            self.txt_core_rules.setPlainText(DEFAULT_CORE_RULES)

    def get_results(self) -> tuple[str, str]:
        return self.txt_user_rules.toPlainText().strip(), self.txt_core_rules.toPlainText().strip()


# //////////////////////////////////////////////////////#
#   SCRIPT ENGINE (100% COMPATIBLE WITH MANGA CLEANER) #
# //////////////////////////////////////////////////////#

class TranslationScriptEngine:
    @staticmethod
    def generate_template(project_paths: list, series_title: str = "", chapter_num: str = "") -> str:
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
                logger.error(f"Error reading existing script: {e}")

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
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(full_content)


# /////////////////////////////////#
#     TRANSLATOR UI WORKSPACE      #
# /////////////////////////////////#

class TranslatorPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.loaded_script_path = None
        self.path_dialogues_map = {}
        self.current_bubbles_widgets = []
        self.active_worker = None
        self.fetch_worker = None

        self.page_bubbles_data = {}

        self.user_rules_file = os.path.join(Paths.CACHE, "user_rules.txt")
        self.core_rules_file = os.path.join(Paths.CACHE, "core_rules.txt")
        self.api_config_file = os.path.join(Paths.CACHE, "api_config.json")

        self.user_rules = self._load_file_or_default(self.user_rules_file, DEFAULT_USER_RULES)
        self.core_rules = self._load_file_or_default(self.core_rules_file, DEFAULT_CORE_RULES)
        
        if '"original":' in self.core_rules or "Never skip short or incomplete fragments" not in self.core_rules:
            self.core_rules = DEFAULT_CORE_RULES
            self._save_file(self.core_rules_file, self.core_rules)

        self.gemini_key = ""
        self.gemini_model = "gemini-3.1-flash-lite"
        self.gemini_models_list = ["gemini-3.1-flash-lite", "gemini-1.5-flash", "gemini-1.5-pro"]

        self.ollama_url = "https://ollama.com/v1"
        self.ollama_token = ""
        self.ollama_lan_mode = True
        self.ollama_model = ""
        self.ollama_models_list = []

        self._loading_config = False

        self.init_ui()
        self._load_session_credentials()
        self.refresh_series_folders()

    def _load_file_or_default(self, file_path: str, default_text: str) -> str:
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                pass
        return default_text

    def _save_file(self, file_path: str, text: str):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            logger.error(f"Error saving {file_path}: {e}")

    def _load_session_credentials(self):
        if not os.path.exists(self.api_config_file):
            return

        self._loading_config = True
        try:
            with open(self.api_config_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            provider = data.get("provider", "Gemini")
            mode = data.get("mode", "Manhwa")
            src_lang = data.get("src_lang", "English")
            tgt_lang = data.get("tgt_lang", "Spanish (Neutral)")

            if "gemini" in data:
                g_data = data["gemini"]
                self.gemini_key = g_data.get("key", "")
                self.gemini_model = g_data.get("model", "gemini-3.1-flash-lite")
                self.gemini_models_list = g_data.get("models_list", ["gemini-3.1-flash-lite", "gemini-1.5-flash", "gemini-1.5-pro"])
            else:
                self.gemini_key = data.get("gemini_key", "")
                self.gemini_model = data.get("model", "gemini-3.1-flash-lite")
                self.gemini_models_list = data.get("models_list", ["gemini-3.1-flash-lite", "gemini-1.5-flash", "gemini-1.5-pro"])

            if "ollama" in data:
                o_data = data["ollama"]
                self.ollama_url = o_data.get("url", "https://ollama.com/v1")
                self.ollama_token = o_data.get("token", "")
                self.ollama_lan_mode = bool(o_data.get("lan_mode", True))
                self.ollama_model = o_data.get("model", "")
                self.ollama_models_list = o_data.get("models_list", [])
            else:
                self.ollama_url = data.get("ollama_url", "https://ollama.com/v1")
                self.ollama_token = data.get("ollama_token", "")
                self.ollama_lan_mode = bool(data.get("ollama_lan_mode", True))
                self.ollama_model = data.get("model", "")
                self.ollama_models_list = data.get("models_list", [])

            p_idx = self.provider_combo.findText(provider)
            if p_idx >= 0:
                self.provider_combo.setCurrentIndex(p_idx)

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

            self.chk_lan_mode.setChecked(self.ollama_lan_mode)
            self._update_fields_for_provider()

        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
        finally:
            self._loading_config = False

    def _save_session_credentials(self):
        if self._loading_config:
            return

        try:
            curr_provider = self.provider_combo.currentText()
            is_ollama = (curr_provider == "Ollama")

            if is_ollama:
                if not self.chk_lan_mode.isChecked():
                    self.ollama_url = self.primary_input.text().strip() or "https://ollama.com/v1"
                    self.ollama_token = self.secondary_input.text().strip()
                else:
                    self.ollama_url = "http://localhost:11434"
                self.ollama_lan_mode = self.chk_lan_mode.isChecked()
                self.ollama_model = self.model_combo.currentText()
                self.ollama_models_list = [self.model_combo.itemText(i) for i in range(self.model_combo.count())]
            else:
                self.gemini_key = self.primary_input.text().strip()
                self.gemini_model = self.model_combo.currentText()
                self.gemini_models_list = [self.model_combo.itemText(i) for i in range(self.model_combo.count())]

            payload = {
                "provider": curr_provider,
                "mode": self.mode_combo.currentText(),
                "src_lang": self.src_lang_combo.currentText(),
                "tgt_lang": self.tgt_lang_combo.currentText(),
                "gemini": {
                    "key": self.gemini_key,
                    "model": self.gemini_model,
                    "models_list": self.gemini_models_list
                },
                "ollama": {
                    "lan_mode": self.ollama_lan_mode,
                    "url": self.ollama_url,
                    "token": self.ollama_token,
                    "model": self.ollama_model,
                    "models_list": self.ollama_models_list
                }
            }

            with open(self.api_config_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

            self.update_token_estimate()
        except Exception as e:
            logger.error(f"Error saving session config: {e}")

    def get_full_prompt(self) -> str:
        src = self.src_lang_combo.currentText()
        tgt = self.tgt_lang_combo.currentText()
        medium = self.mode_combo.currentText()
        asian_src = is_asian_source(src)

        medium_block = (
            f"[ACTIVE MEDIUM: {medium.upper()}]\n"
            f"- Reading order: {READING_ORDER.get(medium, READING_ORDER['Manhwa'])}"
        )
        lang_block = (
            "[LANGUAGE]\n"
            f"- Source language: {src}\n"
            f"- Target language: {tgt} (fluid, natural, high-quality scanlation)"
        )

        sfx_rule = get_sfx_rule_for_target(tgt, asian_src)
        sfx_en_line = (',\n    "sfx_en": "English equivalent for SFX, otherwise empty string"'
                       if asian_src else "")
        schema_block = (
            "OUTPUT: valid JSON only, no markdown, no comments, exactly this shape:\n"
            '{"bubbles": [\n  {\n'
            '    "id": 1,\n'
            '    "type": "bubble",\n'
            '    "original": "exact text on the page",\n'
            '    "direct": "primary translation",\n'
            '    "formal": "variant or empty string",\n'
            '    "aggressive": "variant or empty string",\n'
            '    "natural": "variant or empty string",\n'
            '    "subtext": "short note or empty string"' + sfx_en_line + "\n"
            "  }\n]}\n"
            '"type" must be one of: bubble, narration, sfx, outside.'
        )

        prompt_parts = [self.core_rules, sfx_rule, medium_block, lang_block, schema_block]
        if self.user_rules and self.user_rules.strip():
            prompt_parts.append(f"# USER RULES\n{self.user_rules.strip()}")

        return "\n\n".join(prompt_parts)

    def _build_prev_context(self, target_path: str, n: int = 3) -> str:
        paths = self._get_all_project_paths()
        if target_path not in paths or paths.index(target_path) == 0:
            return ""
        prev = paths[paths.index(target_path) - 1]

        pairs = []
        for b in self.page_bubbles_data.get(prev) or []:
            if b.get("type") == "sfx":
                continue
            orig = str(b.get("original", "")).replace("\n", " ").strip()
            tr = (b.get("final") or b.get("direct") or "").replace("\n", " ").strip()
            if orig and tr:
                pairs.append((orig, tr))
        pairs = pairs[-n:]
        if not pairs:
            return ""

        lines = "\n".join(f'- "{o}" -> "{t}"' for o, t in pairs)
        return (
            "\n\n# PREVIOUS PAGE CONTEXT (continuity only; do NOT return these lines)\n"
            f"{lines}\n"
            "If the first bubble(s) of this page continue one of these fragments, translate them "
            "so both parts read as one natural sentence, adapting to the translation above.\n"
        )

    def build_prompt_for(self, path: str) -> str:
        return self.get_full_prompt() + self._build_prev_context(path)

    def update_token_estimate(self):
        prompt = self.get_full_prompt()
        path = self.mw.current_img_path
        total, txt_tok, img_tok = AIClientManager.estimate_tokens(prompt, path)
        self.lbl_token_counter.setText(f"⚡ Est. Tokens: ~{total:,} (Text: ~{txt_tok:,} | Img: ~{img_tok:,})")

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

        def _get_provider_icon(name: str):
            p = os.path.join(Paths.BUNDLE_DIR, "assets", "icon_provider", f"{name.lower()}.svg")
            return QIcon(p) if os.path.exists(p) else QIcon()

        self.provider_combo = QComboBox()
        self.provider_combo.setIconSize(QSize(18, 18))
        self.provider_combo.addItem(_get_provider_icon("gemini"), "Gemini")
        self.provider_combo.addItem(_get_provider_icon("ollama"), "Ollama")
        self.provider_combo.currentIndexChanged.connect(self._on_provider_change)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Manhwa", "Manga", "Comic", "Manhua"])
        self.mode_combo.currentIndexChanged.connect(self._save_session_credentials)

        self.btn_rules = QPushButton("⚙ Rules")
        self.btn_rules.setStyleSheet("background-color: #1e1e26; border: 1px solid #333342; font-size: 11px; font-weight: bold; padding: 4px 10px;")
        self.btn_rules.clicked.connect(self.on_open_rules_dialog)

        row_top.addWidget(self.provider_combo, 1)
        row_top.addWidget(self.mode_combo, 1)
        row_top.addWidget(self.btn_rules, 1)
        lay.addLayout(row_top)

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

        self.chk_lan_mode = QCheckBox("LAN Mode (Localhost:11434)")
        self.chk_lan_mode.setStyleSheet("color: #00d2ff; font-weight: bold; font-size: 10px;")
        self.chk_lan_mode.setChecked(True)
        self.chk_lan_mode.toggled.connect(self._on_lan_mode_toggled)
        lay.addWidget(self.chk_lan_mode)

        row_primary = QHBoxLayout()
        self.primary_input = QLineEdit()
        self.primary_input.editingFinished.connect(self._save_session_credentials)

        self.btn_connect = QPushButton("🔄 Connect")
        self.btn_connect.setStyleSheet("background-color: #1b1b24; border: 1px solid #00d2ff; color: #00d2ff; font-weight: bold; padding: 4px 10px;")
        self.btn_connect.clicked.connect(self.on_test_connection_and_fetch_models)

        row_primary.addWidget(self.primary_input, 1)
        row_primary.addWidget(self.btn_connect)
        lay.addLayout(row_primary)

        self.secondary_input = QLineEdit()
        self.secondary_input.setPlaceholderText("Enter Ollama Cloud API Key...")
        self.secondary_input.setEchoMode(QLineEdit.Password)
        self.secondary_input.editingFinished.connect(self._save_session_credentials)
        lay.addWidget(self.secondary_input)

        row_model = QHBoxLayout()
        lbl_model = QLabel("Model:")
        lbl_model.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px;")
        self.model_combo = QComboBox()
        self.model_combo.currentIndexChanged.connect(self._save_session_credentials)
        row_model.addWidget(lbl_model)
        row_model.addWidget(self.model_combo, 1)
        lay.addLayout(row_model)

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

        self._update_fields_for_provider()

    def _update_fields_for_provider(self):
        is_ollama = (self.provider_combo.currentText() == "Ollama")
        self.chk_lan_mode.setVisible(is_ollama)

        self.primary_input.blockSignals(True)
        self.secondary_input.blockSignals(True)
        self.model_combo.blockSignals(True)

        if is_ollama:
            is_lan = self.chk_lan_mode.isChecked()
            if is_lan:
                self.primary_input.setText("http://localhost:11434")
                self.primary_input.setEnabled(False)
                self.primary_input.setPlaceholderText("Localhost (127.0.0.1:11434)")
                self.primary_input.setEchoMode(QLineEdit.Normal)
                self.secondary_input.setVisible(False)
                self.secondary_input.setEnabled(False)
            else:
                self.primary_input.setEnabled(True)
                self.primary_input.setPlaceholderText("https://ollama.com/v1")
                self.primary_input.setEchoMode(QLineEdit.Normal)
                self.primary_input.setText(self.ollama_url or "https://ollama.com/v1")
                self.secondary_input.setVisible(True)
                self.secondary_input.setEnabled(True)
                self.secondary_input.setText(self.ollama_token)

            self.model_combo.clear()
            if self.ollama_models_list:
                self.model_combo.addItems(self.ollama_models_list)
            if self.ollama_model and self.model_combo.findText(self.ollama_model) >= 0:
                self.model_combo.setCurrentText(self.ollama_model)
        else:
            self.primary_input.setEnabled(True)
            self.primary_input.setPlaceholderText("Enter Gemini API Key...")
            self.primary_input.setEchoMode(QLineEdit.Password)
            self.primary_input.setText(self.gemini_key)
            self.secondary_input.setVisible(False)
            self.secondary_input.setEnabled(False)

            self.model_combo.clear()
            if self.gemini_models_list:
                self.model_combo.addItems(self.gemini_models_list)
            if self.gemini_model and self.model_combo.findText(self.gemini_model) >= 0:
                self.model_combo.setCurrentText(self.gemini_model)

        self.primary_input.blockSignals(False)
        self.secondary_input.blockSignals(False)
        self.model_combo.blockSignals(False)

    def _on_lan_mode_toggled(self, checked: bool):
        self.ollama_lan_mode = checked
        self._update_fields_for_provider()
        self._save_session_credentials()

    def _on_provider_change(self):
        self._update_fields_for_provider()
        self._save_session_credentials()

    def set_locked(self, locked: bool):
        """
        Locks or unlocks all configuration controls, settings, and editor panels 
        to ensure data consistency during active inference or batch jobs.
        """
        # Section 1: Engine, Models, Rules & Languages
        self.provider_combo.setEnabled(not locked)
        self.mode_combo.setEnabled(not locked)
        self.btn_rules.setEnabled(not locked)
        self.src_lang_combo.setEnabled(not locked)
        self.tgt_lang_combo.setEnabled(not locked)
        self.chk_lan_mode.setEnabled(not locked)
        self.primary_input.setEnabled(not locked)
        self.btn_connect.setEnabled(not locked)
        self.secondary_input.setEnabled(not locked)
        self.model_combo.setEnabled(not locked)
        self.btn_translate_page.setEnabled(not locked)

        # Section 2: Dialogue editor & variants
        self.scroll.setEnabled(not locked)
        self.btn_add_bubble.setEnabled(not locked)

        # Section 3: Script file hierarchy
        self.combo_series_folder.setEnabled(not locked)
        self.btn_new_series_folder.setEnabled(not locked)
        self.btn_open_folder.setEnabled(not locked)
        self.combo_folder_scripts.setEnabled(not locked)
        self.btn_new_txt.setEnabled(not locked)
        self.btn_load_txt.setEnabled(not locked)

        if locked:
            self.lbl_api_status.setText("🔒 LOCKED: Inference engine busy...")
            self.lbl_api_status.setStyleSheet("color: #00d2ff; font-size: 10px; font-weight: bold; padding: 2px;")
            self.lbl_api_status.setVisible(True)
            if self.mw.current_img_path:
                self.mw.file_list.update_item_state(self.mw.current_img_path, "lock", "Translating in progress...")

    def on_test_connection_and_fetch_models(self):
        provider = self.provider_combo.currentText()
        is_ollama = (provider == "Ollama")

        if is_ollama:
            if self.chk_lan_mode.isChecked():
                key_or_url = "http://localhost:11434"
                auth_token = ""
            else:
                key_or_url = self.primary_input.text().strip() or "https://ollama.com/v1"
                auth_token = self.secondary_input.text().strip()
                if not auth_token:
                    QMessageBox.warning(self, "API Key Required", "Please enter your Ollama Cloud API Key.")
                    return
        else:
            key_or_url = self.primary_input.text().strip()
            auth_token = ""
            if not key_or_url:
                QMessageBox.warning(self, "API Key Required", "Please enter your Gemini API Key.")
                return

        self.btn_connect.setEnabled(False)
        self.btn_connect.setText("⏳ Checking...")

        self.fetch_worker = FetchModelsWorker(provider, key_or_url, auth_token)
        self.fetch_worker.finished.connect(self._on_fetch_models_result)
        self.fetch_worker.start()

    def _on_fetch_models_result(self, success: bool, models: list, message: str):
        self.btn_connect.setEnabled(True)
        self.btn_connect.setText("🔄 Connect")

        if success:
            provider = self.provider_combo.currentText()
            current_choice = self.model_combo.currentText()

            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            self.model_combo.addItems(models)
            if current_choice and self.model_combo.findText(current_choice) >= 0:
                self.model_combo.setCurrentText(current_choice)
            self.model_combo.blockSignals(False)

            if provider == "Gemini":
                self.gemini_models_list = list(models)
                self.gemini_model = self.model_combo.currentText()
            else:
                self.ollama_models_list = list(models)
                self.ollama_model = self.model_combo.currentText()

            self._save_session_credentials()
            QMessageBox.information(self, "Connection Successful", f"{message}\n\nModels ready: {len(models)}")
        else:
            QMessageBox.critical(self, "Connection Error", message)

    def on_open_rules_dialog(self):
        dialog = RulesDialog(self.user_rules, self.core_rules, self)
        if dialog.exec() == QDialog.Accepted:
            new_user, new_core = dialog.get_results()
            self.user_rules = new_user
            self.core_rules = new_core
            self._save_file(self.user_rules_file, new_user)
            self._save_file(self.core_rules_file, new_core)
            self.update_token_estimate()
            QMessageBox.information(self, "Rules Saved", "User rules and engine technical guidelines were saved to disk.")

    def _get_all_project_paths(self) -> list:
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
        data = self.combo_series_folder.currentData()
        if data and os.path.exists(data):
            return data
        return Paths.TRANSLATIONS

    def _on_series_folder_changed(self):
        self.refresh_scripts_for_selected_series()

    def refresh_scripts_for_selected_series(self):
        """Populates .txt files strictly belonging to the active series. Never loads automatically."""
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
        """Allows creating a new series subfolder directly inside translations/."""
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
        """Loads script only when user deliberately clicks an item."""
        if index <= 0:
            return
        selected_path = self.combo_folder_scripts.itemData(index)
        if selected_path and os.path.exists(selected_path):
            self.import_script_from_path(selected_path)

    def on_open_translations_folder(self):
        """Opens active series directory in Windows File Explorer."""
        folder = self.get_selected_series_dir()
        os.makedirs(folder, exist_ok=True)
        if os.name == "nt":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", folder])

    def load_page_state(self, path: str):
        self.update_token_estimate()
        if path in self.page_bubbles_data:
            self.populate_bubble_editor(self.page_bubbles_data[path])
        elif path in self.path_dialogues_map:
            saved_lines = self.path_dialogues_map[path]
            fake_bubbles = [{"id": i, "type": "bubble", "original": "", "direct": l, "translations": [l]} for i, l in enumerate(saved_lines, start=1)]
            self.populate_bubble_editor(fake_bubbles)
        else:
            self.populate_bubble_editor([])

    def save_current_page_editor(self):
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
        if not self.mw.current_img_path or not os.path.exists(self.mw.current_img_path):
            QMessageBox.warning(self, "Notice", "Select a page in the left assets list first.")
            return

        provider = self.provider_combo.currentText().lower()
        selected_model = self.model_combo.currentText().strip()
        is_ollama = (provider == "ollama")

        if is_ollama:
            if self.chk_lan_mode.isChecked():
                ollama_url = "http://localhost:11434"
                ollama_token = ""
            else:
                ollama_url = self.primary_input.text().strip() or "https://ollama.com/v1"
                ollama_token = self.secondary_input.text().strip()
                if not ollama_token:
                    QMessageBox.warning(self, "API Key Required", "Please enter your Ollama Cloud API Key.")
                    return
            gemini_key = ""
            if not selected_model:
                selected_model = "gemma4:31b-cloud"
        else:
            gemini_key = self.primary_input.text().strip()
            ollama_url = ""
            ollama_token = ""
            if not gemini_key:
                QMessageBox.warning(self, "API Key Required", "Please enter your Gemini API Key.")
                return
            if not selected_model:
                selected_model = "gemini-3.1-flash-lite"

        self.set_locked(True)

        self.active_worker = MultimodalTranslationWorker(
            image_path=self.mw.current_img_path,
            full_prompt=self.build_prompt_for(self.mw.current_img_path),
            provider=provider,
            model_name=selected_model,
            api_key=gemini_key,
            ollama_url=ollama_url,
            ollama_token=ollama_token
        )
        self.active_worker.finished.connect(self._on_translation_success)
        self.active_worker.error.connect(self._on_translation_failed)
        self.active_worker.start()

    def _on_translation_success(self, path: str, result: TranslationResult):
        self.set_locked(False)

        status = result.status
        fname = os.path.basename(path)

        if status == ProviderStatus.SAFETY_BLOCKED:
            self.lbl_api_status.setText("🛡 Blocked by Content Moderation")
            self.lbl_api_status.setStyleSheet("color: #ff3344; font-size: 10px; font-weight: bold; padding: 2px;")
            self.lbl_api_status.setVisible(True)
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
            self.lbl_api_status.setText("⏳ Provider Busy / Overloaded")
            self.lbl_api_status.setStyleSheet("color: #ffd600; font-size: 10px; font-weight: bold; padding: 2px;")
            self.lbl_api_status.setVisible(True)
            self.mw.file_list.update_item_state(path, "busy", result.message)
            QMessageBox.warning(self, "Server Busy", f"{result.message}\n\nPlease retry in a couple of minutes.")
            return

        if status == ProviderStatus.EMPTY:
            self.lbl_api_status.setText("💬 Silent Page (No text detected)")
            self.lbl_api_status.setStyleSheet("color: #8faecf; font-size: 10px; font-weight: bold; padding: 2px;")
            self.lbl_api_status.setVisible(True)
            self.page_bubbles_data[path] = []
            self.path_dialogues_map.pop(path, None)
            self.mw.file_list.update_item_state(path, "empty", result.message or "Silent panel (No text detected)")
            self.populate_bubble_editor([])
            return

        if status == ProviderStatus.ERROR:
            self.lbl_api_status.setText("✖ Translation error")
            self.lbl_api_status.setStyleSheet("color: #ff5252; font-size: 10px; font-weight: bold; padding: 2px;")
            self.lbl_api_status.setVisible(True)
            self.mw.file_list.update_item_state(path, "error", result.message or "Translation failed")
            QMessageBox.critical(self, "Translation Error", f"Failed to translate {fname}:\n{result.message}")
            return

        # SUCCESS
        self.lbl_api_status.setText("✔ Translation generated successfully")
        self.lbl_api_status.setStyleSheet("color: #00e676; font-size: 10px; font-weight: bold; padding: 2px;")
        self.lbl_api_status.setVisible(True)

        usage = result.usage
        p_tok = usage.get("prompt_tokens", 0)
        c_tok = usage.get("output_tokens", 0)
        t_tok = usage.get("total_tokens", p_tok + c_tok)
        if t_tok > 0:
            self.lbl_token_counter.setText(
                f"⚡ Input: {p_tok:,} | Output: {c_tok:,} | Total: {t_tok:,} tokens"
            )

        self.page_bubbles_data[path] = result.bubbles
        self.path_dialogues_map[path] = [b.get("direct") for b in result.bubbles if b.get("direct")]
        self.mw.file_list.update_item_state(path, "ready", f"Translated ({len(result.bubbles)} dialogues)")

        if path == self.mw.current_img_path:
            self.populate_bubble_editor(result.bubbles)

    def _on_translation_failed(self, path: str, error_msg: str):
        self.set_locked(False)
        self.lbl_api_status.setText("✖ Translation failed")
        self.lbl_api_status.setStyleSheet("color: #ff5252; font-size: 10px; font-weight: bold; padding: 2px;")
        self.lbl_api_status.setVisible(True)
        self.mw.file_list.update_item_state(path, "error", error_msg[:60])
        QMessageBox.critical(self, "Translation Error", f"Failed to translate {os.path.basename(path)}:\n{error_msg}")

    def on_manually_add_bubble(self):
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
        if card_widget in self.current_bubbles_widgets:
            self.current_bubbles_widgets.remove(card_widget)
            card_widget.deleteLater()
            self.save_current_page_editor()

    def _create_bubble_card(self, b: dict):
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
        card_lay.addWidget(line_edit)

        if hasattr(self, "_bottom_spacer") and self._bottom_spacer:
            idx = self.bubble_lay.indexOf(self._bottom_spacer)
            self.bubble_lay.insertWidget(idx, card)
        else:
            self.bubble_lay.addWidget(card)

        self.current_bubbles_widgets.append(card)
        card.line_edit = line_edit

    def populate_bubble_editor(self, bubbles: list):
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