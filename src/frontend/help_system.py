from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QTextEdit, QPushButton
from src.utils.system_info import SystemMonitor
from src.utils.config import Config

# /////////////////////////////////#
#     STUDIO KNOWLEDGE BASE        #
# /////////////////////////////////#

class HelpSystem(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{Config.APP_NAME} - User Manual & Technical Guide")
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
            "<h3 style='color: #00d4ff;'>⌨️ Navigation & Keyboard Shortcuts</h3>"
            "<p><i>Note: Single-key shortcuts automatically suspend while editing text fields to prevent collisions.</i></p>"
            "<table border='0' cellpadding='5' width='100%'>"
            "<tr><td colspan='2'><b style='color: #00d4ff;'>— Viewport Navigation —</b></td></tr>"
            "<tr><td width='35%'><b>Hold [Space] + Drag</b></td><td>Smooth panning across the page canvas.</td></tr>"
            "<tr><td><b>Mouse Wheel</b></td><td>Zoom in / Zoom out centered on cursor position.</td></tr>"
            "<tr><td><b>[M]</b></td><td>Pan Tool toggle.</td></tr>"
            "<tr><td colspan='2'><hr color='#252530'></td></tr>"
            "<tr><td colspan='2'><b style='color: #00d4ff;'>— Page State & Assets —</b></td></tr>"
            "<tr><td><b>Left-Click Item</b></td><td>Loads image and syncs detected dialogue cards.</td></tr>"
            "<tr><td><b>Checkboxes</b></td><td>Marks target pages for sequential batch processing.</td></tr>"
            "<tr><td><b>Hover on Status Icon</b></td><td>Displays exact status telemetry (tokens, moderation reason, or silent panel).</td></tr>"
            "<tr><td colspan='2'><hr color='#252530'></td></tr>"
            "<tr><td colspan='2'><b style='color: #00d4ff;'>— Batch Controls —</b></td></tr>"
            "<tr><td><b>RUN BATCH TRANSLATE</b></td><td>Starts sequential translation across selected pages.</td></tr>"
            "<tr><td><b>PAUSE / RESUME</b></td><td>Temporarily pauses queue between pages without data loss.</td></tr>"
            "<tr><td><b>CANCEL BATCH</b></td><td>Immediately aborts queue execution and retains processed pages.</td></tr>"
            "</table>"
        )

        # ==========================================
        # TAB 2: MULTIMODAL AI & CONTENT MODERATION
        # ==========================================
        tab_ai = QTextEdit()
        tab_ai.setReadOnly(True)
        tab_ai.setHtml(
            "<h3 style='color: #00d4ff;'>🤖 Multimodal Vision AI & Moderation Handling</h3>"
            "<p>Manga Translate Studio bypasses conventional OCR by interacting directly with vision-capable Large Language Models (LLMs) such as Google Gemini and local/cloud Ollama instances.</p>"
            "<h4>1. Multimodal Translation Pipeline</h4>"
            "<ul>"
            "<li><b>Context-Aware Parsing:</b> The vision model analyzes layout hierarchy, reading order, and expression subtext simultaneously.</li>"
            "<li><b>Structured Dialogue Separation:</b> Enforces pure JSON output schemas to prevent visual bubbles from merging.</li>"
            "<li><b>Idiomatic Translation & Variants:</b> Extracts formal, aggressive, and natural adaptations alongside neutral primary translations.</li>"
            "</ul>"
            "<h4>2. Content Moderation & Provider Safety Policies</h4>"
            "<ul>"
            "<li><b>Google Gemini Restrictions:</b> Standard cloud APIs enforce safety thresholds on mature, explicit, or high-violence panels.</li>"
            "<li><b>Safety Rejection Handling (Shield Icon):</b> If a panel is blocked by Gemini via <code>promptFeedback.blockReason</code> or <code>finishReason: SAFETY</code>, the studio halts execution cleanly without retry loops to protect your API key.</li>"
            "<li><b>Alternative Engine Fallback:</b> Switch the provider combo to <b>Ollama (Local/Cloud)</b> or uncensored endpoints to process mature content seamlessly.</li>"
            "</ul>"
        )

        # ==========================================
        # TAB 3: VISUAL STATUS CODES & ICONS
        # ==========================================
        tab_status = QTextEdit()
        tab_status.setReadOnly(True)
        tab_status.setHtml(
            "<h3 style='color: #00d4ff;'>🏷️ Page Status Icons & Indicators</h3>"
            "<p>Each page in the <b>Project Assets</b> list reflects its exact processing state through color-coded vector icons:</p>"
            "<table border='0' cellpadding='6' width='100%'>"
            "<tr><td width='25%'><b style='color: #32323e;'>● Unassigned</b></td><td>Page has not yet been processed by the AI inference engine.</td></tr>"
            "<tr><td><b style='color: #00d2ff;'>🔒 Waiting / Locked</b></td><td>Image is actively being processed or reviewed in the editor.</td></tr>"
            "<tr><td><b style='color: #00e676;'>✔ Ready</b></td><td>Dialogues successfully detected, translated, and structured.</td></tr>"
            "<tr><td><b style='color: #8faecf;'>💬 Silent (Empty)</b></td><td>Panel analyzed successfully with zero dialogues (action/scenery panel).</td></tr>"
            "<tr><td><b style='color: #ffd600;'>⏳ Server Busy</b></td><td>Temporary network overload (503 / 429 / Read Timeout). Safe to retry later.</td></tr>"
            "<tr><td><b style='color: #ff3344;'>🛡️ Safety Blocked</b></td><td>Content moderation filter triggered. Switch LLM engine to proceed.</td></tr>"
            "<tr><td><b style='color: #e000d0;'>◆ Modified</b></td><td>Page dialogues audited or synchronized into the target script file.</td></tr>"
            "<tr><td><b style='color: #ff3d00;'>✖ Error</b></td><td>Unrecoverable client error, invalid API key, or corrupted payload.</td></tr>"
            "</table>"
        )

        # ==========================================
        # TAB 4: SCRIPT ENGINE & FILE STRUCTURE
        # ==========================================
        tab_script = QTextEdit()
        tab_script.setReadOnly(True)
        tab_script.setHtml(
            "<h3 style='color: #00d4ff;'>📄 Translation Script Specification (.TXT)</h3>"
            "<p>The script engine produces standard structured text files engineered for direct compatibility with Manga Cleaner and typesetting workflows.</p>"
            "<h4>Syntax and Structure Rules</h4>"
            "<ul>"
            "<li><b>Root Translation Block:</b> All valid dialogue must reside strictly between <code>&lt;translation&gt;</code> and <code>&lt;/translation&gt;</code> tags.</li>"
            "<li><b>Image Headers:</b> Declared using sequential indexing and filename matching brackets: <code>Image X [filename.jpg]</code>.</li>"
            "<li><b>Dialogue Hyphens:</b> Each dialogue bubble corresponds to a line opening with a hyphen (<code>-</code>). Empty hyphens are automatically ignored.</li>"
            "<li><b>Manual Line Breaks:</b> Use double slashes (<code>//</code>) inside a line to declare intended line wraps inside speech bubbles.</li>"
            "<li><b>Comments & Metadata:</b> Lines starting with <code>#</code> and text placed outside root tags are discarded by parsers.</li>"
            "</ul>"
        )

        # ==========================================
        # TAB 5: BATCH ORCHESTRATION & CADENCE
        # ==========================================
        tab_batch = QTextEdit()
        tab_batch.setReadOnly(True)
        tab_batch.setHtml(
            "<h3 style='color: #00d4ff;'>⚡ Batch Orchestration & Rate Limits</h3>"
            "<h4>Execution Flow & Safeguards</h4>"
            "<ul>"
            "<li><b>Pacing Controls (RPM):</b> Automatic request throttling protects against hitting provider rate limits (Gemini: 15 RPM).</li>"
            "<li><b>Session Isolation:</b> Every page request is dispatched statelessly without accumulating conversation history, eliminating token overflow crashes.</li>"
            "<li><b>Daily Quota Interruption (RPD):</b> When a daily limit is reached, batch execution safely halts, preserving remaining unparsed pages for effortless resumption.</li>"
            "<li><b>Automatic Retry Targeting:</b> If tasks fail or encounter busy servers, they remain checked in the assets list for immediate re-execution.</li>"
            "</ul>"
        )

        # ==========================================
        # TAB 6: SYSTEM SPECS & RUNTIME TELEMETRY
        # ==========================================
        specs = SystemMonitor.get_detailed_specs()
        tab_hardware = QTextEdit()
        tab_hardware.setReadOnly(True)
        tab_hardware.setHtml(
            "<h3 style='color: #00d4ff;'>💻 Runtime Diagnostics & Optimization</h3>"
            f"<p><b>Inference Target:</b> {specs.get('engine', 'CPU / Remote API')}</p>"
            f"<p><b>Total System Memory:</b> {specs.get('ram', 'N/A')} GB</p>"
            "<hr color='#252530'>"
            "<h4>Memory Management Features</h4>"
            "<ul>"
            "<li><b>Lazy Image Decoding:</b> Images decode via OpenCV only when actively loaded into the viewport and are released when navigating away.</li>"
            "<li><b>Dynamic Payload Compression:</b> High-resolution pages downscale in-memory before Base64 encoding to minimize latency and bandwidth footprint.</li>"
            "<li><b>Thread Safety:</b> All network interactions execute within isolated worker threads (<code>QThread</code>), ensuring an unblocked and responsive GUI.</li>"
            "</ul>"
        )

        tabs.addTab(tab_shortcuts, "Navigation")
        tabs.addTab(tab_ai, "AI & Safety")
        tabs.addTab(tab_status, "Status Icons")
        tabs.addTab(tab_script, "Script (.TXT)")
        tabs.addTab(tab_batch, "Batch Engine")
        tabs.addTab(tab_hardware, "System")
        layout.addWidget(tabs)

        close_btn = QPushButton("CLOSE")
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