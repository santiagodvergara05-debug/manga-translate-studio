from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QTextEdit, QTextBrowser, QPushButton
from src.utils.config import Config
from src.utils.i18n import tr

# /////////////////////////////////#
#     STUDIO KNOWLEDGE BASE        #
# /////////////////////////////////#

class HelpSystem(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("help.app_name_user_manual_technical_guide", app_name=Config.APP_NAME))
        self.resize(780, 580)
        self.setStyleSheet(f"background-color: {Config.COLOR_PANEL}; color: {Config.COLOR_TEXT}; font-family: 'Segoe UI';")

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabBar::tab {{ background: #1b1b22; color: #a0a0b0; padding: 6px 14px; font-size: 11px; }} "
            f"QTabBar::tab:selected {{ background: #2a2a35; color: {Config.COLOR_ACCENT}; font-weight: bold; }}"
        )

        # ==========================================
        # TAB 1: WORKSPACE NAVIGATION & SHORTCUTS
        # ==========================================
        tab_shortcuts = QTextEdit()
        tab_shortcuts.setReadOnly(True)
        tab_shortcuts.setHtml(
            tr("help.tab_shortcuts_html")
        )

        # ==========================================
        # TAB 2: MULTIMODAL AI & CONTENT MODERATION
        # ==========================================
        tab_ai = QTextEdit()
        tab_ai.setReadOnly(True)
        tab_ai.setHtml(
            tr("help.tab_ai_html")
        )

        # ==========================================
        # TAB 3: THINKING LEVELS & TOKEN IMPACT
        # ==========================================
        tab_thinking = QTextEdit()
        tab_thinking.setReadOnly(True)
        tab_thinking.setHtml(
            tr("help.tab_thinking_html")
        )

        # ==========================================
        # TAB 4: VISUAL STATUS CODES & ICONS
        # ==========================================
        tab_status = QTextEdit()
        tab_status.setReadOnly(True)
        tab_status.setHtml(
            tr("help.tab_status_html")
        )

        # ==========================================
        # TAB 5: SCRIPT ENGINE & FILE STRUCTURE
        # ==========================================
        tab_script = QTextEdit()
        tab_script.setReadOnly(True)
        tab_script.setHtml(
            tr("help.tab_script_html")
        )

        # ==========================================
        # TAB 6: BATCH ORCHESTRATION & CADENCE
        # ==========================================
        tab_batch = QTextEdit()
        tab_batch.setReadOnly(True)
        tab_batch.setHtml(
            tr("help.tab_batch_html")
        )

        tabs.addTab(tab_shortcuts, tr("help.navigation"))
        tabs.addTab(tab_ai, tr("help.vision_ai"))
        tabs.addTab(tab_thinking, tr("help.thinking_usage"))
        tabs.addTab(tab_status, tr("help.page_status"))
        tabs.addTab(tab_script, tr("help.txt_scripts"))
        tabs.addTab(tab_batch, tr("help.batch_api_pace"))

        # ==========================================
        # TAB 7: PROJECT LINKS & CONTRIBUTION
        # ==========================================
        tab_contribute = QTextBrowser()
        tab_contribute.setOpenExternalLinks(True)
        tab_contribute.setHtml(
            tr("help.tab_contribute_html")
        )
        tabs.addTab(tab_contribute, tr("help.providers_contribution"))

        layout.addWidget(tabs)

        close_btn = QPushButton(tr("help.close"))
        close_btn.setStyleSheet(
            f"background-color: {Config.COLOR_BG}; padding: 6px; border: 1px solid #2a2a35; "
            "color: #00d2ff; font-weight: bold; font-size: 11px; border-radius: 3px;"
        )
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    @staticmethod
    def show_guide(parent):
        """Spawns the help knowledge base modal dialog."""
        dialog = HelpSystem(parent)
        dialog.exec()
