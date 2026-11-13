from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QTextEdit, QTextBrowser, QPushButton
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
            "<tr><td><b>Mouse Wheel</b></td><td>Scroll vertically through tall pages.</td></tr>"
            "<tr><td><b>[Ctrl] or [Alt] + Mouse Wheel</b></td><td>Zoom in / out centered on the cursor.</td></tr>"
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
        # TAB 3: THINKING LEVELS & TOKEN IMPACT
        # ==========================================
        tab_thinking = QTextEdit()
        tab_thinking.setReadOnly(True)
        tab_thinking.setHtml(
            "<h3 style='color: #00d4ff;'>🧠 Thinking Levels & Token Impact</h3>"
            "<h4>Thinking levels</h4>"
            "<ul>"
            "<li>The <b>Thinking level</b> setting is sent with Gemini requests when the selected model supports it. Available levels depend on the model ID; unsupported levels are not sent.</li>"
            "<li><b>Minimal</b> uses less reasoning where supported; it does not always mean zero thinking. <b>High</b> can improve difficult visual interpretation, but may add latency and many thinking tokens. Usage varies by page and model.</li>"
            "<li><b>Gemma 4</b> exposes two modes: Minimal (thinking off) and High (thinking on). Other models may have different levels or use their own default.</li>"
            "<li>The status under the Translate button shows the <i>configured</i> level. This app uses a non-streaming request, so it cannot show live thinking progress.</li>"
            "<li><b>R19 vocalization mode</b> adds prompt guidance to distinguish breathy vocalizations from laughter using artwork context. It is off by default and does not add JSON fields.</li>"
            "</ul>"
            "<h4>Reading token usage</h4>"
            "<ul>"
            "<li><b>Input tokens:</b> prompt instructions, the current page image, and any previous-page dialogue context.</li>"
            "<li><b>Output tokens:</b> extracted text and requested translation fields.</li>"
            "<li><b>Thinking tokens:</b> reasoning usage reported by the provider. High levels can increase this substantially. Provider pricing and free quotas differ.</li>"
            "<li>Batch continuity sends only up to three text pairs from the immediately previous page; it does <b>not</b> resend earlier images.</li>"
            "</ul>"
            "<h4>Extraction option indicators</h4>"
            "<p><b>⬆</b> can add response tokens when the page contains that content. <b>⬇</b> indicates an option that can reduce tokens when disabled. These are qualitative hints, not fixed token counts.</p>"
            "<ul>"
            "<li><b>Sound effects, narration, and floating text:</b> including them can add detected entries; disabling them can reduce the prompt and output when such text is present.</li>"
            "<li><b>Translation variants:</b> adds formal, aggressive, and natural fields. This can increase the response, especially when alternatives are generated. Disable it for direct translations only.</li>"
            "<li><b>Subtext:</b> adds an optional tone-note field. A note uses extra output tokens; disabling it removes that field. Subtext is for editor guidance and is not written to the translation .TXT.</li>"
            "<li><b>Explain sound-effect meaning:</b> adds a concise target-language meaning note to SFX cards only. It requires SFX extraction, adds output tokens for SFX, and is not written to the .TXT.</li>"
            "<li><b>Skip identical repeated sound effects:</b> asks the model to return the first occurrence only when the same visible SFX lettering repeats on one page. It requires SFX extraction and may reduce duplicate output; distinct text and non-SFX entities remain unaffected.</li>"
            "<li><b>R19 vocalization mode:</b> adds a small amount of prompt text but no response field. It guides short vocalizations; the model may still interpret ambiguous lettering differently.</li>"
            "</ul>"
            "<h4>Usage, cache, and price tables</h4>"
            "<ul>"
            "<li>The <b>Usage / Prices</b> button opens request history and editable USD-per-million-token prices.</li>"
            "<li>Usage history can be filtered by provider. Each request is associated with its saved connection profile. <b>Clear all history</b> removes request records for every provider but keeps price tables and Gemini RPD counters.</li>"
            "<li>Import and export price rows as JSON. Imports merge by provider, model, and plan: matching rows are updated and unrelated rows are kept, so you can import several provider files. The community JSON files are in <code>Pricing_Models_Providers</code>. Prices are snapshots; check provider rates before relying on an estimate.</li>"
            "<li>New installations start with an empty price table and Gemini RPD limit set to 0 (meter off). <b>Not configured</b> means the app has no price rate to estimate against; add values from your provider's pricing source.</li>"
            "<li>API Settings has saved <b>Connection profiles</b> that switch provider credentials and model together. Usage history and Gemini RPD values are tracked per connection profile.</li>"
            "<li>The main header's <b>API pace</b> selector applies to single and batch translations for every provider. Theoretical request-start ceilings are about <b>14.6 RPM</b> for <b>LOW</b> (4.1 seconds), <b>40 RPM</b> for <b>HIGH</b> (1.5 seconds), and <b>120 RPM</b> for <b>MAX</b> (0.5 seconds). Actual rates can be lower because of API processing time; MAX can trigger provider rate limits or HTTP 429 responses.</li>"
            "<li>Cache counts and percentages come from provider response metadata. A zero means that request reported no cached input; it does not identify why a cache miss occurred.</li>"
            "<li>When Google (Gemini) is selected, <b>API Settings</b> shows editable <b>RPD limit</b> and <b>RPD in use</b> fields for the selected connection profile and model. Set the limit to 0 to turn off the local meter. The main header keeps a compact status indicator; usage resets at midnight Pacific time while the limit is kept.</li>"
            "</ul>"
            "<p style='color: #9aa0ad;'><i>Actual token use and costs depend on the image, selected options, model, cache hit, account tier, and the price rows currently loaded.</i></p>"
            "<p><b>Developer console:</b> when debug logging is enabled, the API response may include text marked as thought and opaque signature metadata. These are diagnostics, not translation text, and are not written to the .TXT script.</p>"
        )

        # ==========================================
        # TAB 4: VISUAL STATUS CODES & ICONS
        # ==========================================
        tab_status = QTextEdit()
        tab_status.setReadOnly(True)
        tab_status.setHtml(
            "<h3 style='color: #00d4ff;'>🏷️ Page Status Icons & Indicators</h3>"
            "<p>Each page in the <b>Project Assets</b> list reflects its exact processing state through color-coded vector icons:</p>"
            "<table border='0' cellpadding='6' width='100%'>"
            "<tr><td width='25%'><b style='color: #32323e;'>● Unassigned</b></td><td>Page has not yet been processed by the AI inference engine.</td></tr>"
            "<tr><td><b style='color: #ffd600;'>⏳ Waiting</b></td><td>Page is queued and waiting for its turn to be sent to the provider.</td></tr>"
            "<tr><td><b style='color: #00d2ff;'>🔒 Processing</b></td><td>The API is processing a page that had no existing translation text.</td></tr>"
            "<tr><td><b style='color: #b388ff;'>🔄 Updating</b></td><td>The API is reprocessing a page that already has text. The existing result remains visible until the response arrives.</td></tr>"
            "<tr><td><b style='color: #00e676;'>✔ Ready</b></td><td>Dialogues successfully detected, translated, and structured.</td></tr>"
            "<tr><td><b style='color: #8faecf;'>💬 Silent (Empty)</b></td><td>Panel analyzed successfully with zero dialogues (action/scenery panel).</td></tr>"
            "<tr><td><b style='color: #ff9800;'>⚠ Server Busy</b></td><td>The provider reported temporary overload or rate limiting (for example, HTTP 429 / 503). Retry after the provider allows it.</td></tr>"
            "<tr><td><b style='color: #ff3344;'>🛡️ Safety Blocked</b></td><td>Content moderation filter triggered. Switch LLM engine to proceed.</td></tr>"
            "<tr><td><b style='color: #e000d0;'>◆ Modified</b></td><td>Dialogue text was edited locally in the studio and has not necessarily been exported.</td></tr>"
            "<tr><td><b style='color: #00d2ff;'>▣ Script Synced</b></td><td>Dialogue text was loaded from a script or successfully written to the linked .TXT file.</td></tr>"
            "<tr><td><b style='color: #ff3d00;'>✖ Error</b></td><td>Unrecoverable client error, invalid API key, or corrupted payload.</td></tr>"
            "</table>"
        )

        # ==========================================
        # TAB 5: SCRIPT ENGINE & FILE STRUCTURE
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
        # TAB 6: BATCH ORCHESTRATION & CADENCE
        # ==========================================
        tab_batch = QTextEdit()
        tab_batch.setReadOnly(True)
        tab_batch.setHtml(
            "<h3 style='color: #00d4ff;'>⚡ Batch Orchestration & Request Pacing</h3>"
            "<h4>Execution Flow & Safeguards</h4>"
            "<ul>"
            "<li><b>Request pacing:</b> The app uses conservative intervals between requests. This does not change provider-side limits or enforcement.</li>"
            "<li><b>Batch review:</b> The selected image stays in place as the queue advances. Completed pages can be opened and edited during the run; queued and currently processing pages stay locked. Scroll the editor and image while the batch runs.</li>"
            "<li><b>Session Isolation:</b> Every page request is dispatched statelessly without accumulating conversation history, eliminating token overflow crashes.</li>"
            "<li><b>Daily Quota Interruption (RPD):</b> When a daily limit is reached, batch execution safely halts, preserving remaining unparsed pages for effortless resumption.</li>"
            "<li><b>Automatic Retry Targeting:</b> If tasks fail or encounter busy servers, they remain checked in the assets list for immediate re-execution.</li>"
            "</ul>"
        )

        tabs.addTab(tab_shortcuts, "Navigation")
        tabs.addTab(tab_ai, "Vision AI")
        tabs.addTab(tab_thinking, "Thinking & Usage")
        tabs.addTab(tab_status, "Page Status")
        tabs.addTab(tab_script, "TXT Scripts")
        tabs.addTab(tab_batch, "Batch & API Pace")

        # ==========================================
        # TAB 7: PROJECT LINKS & CONTRIBUTION
        # ==========================================
        tab_contribute = QTextBrowser()
        tab_contribute.setOpenExternalLinks(True)
        tab_contribute.setHtml(
            "<h3 style='color: #00d4ff;'>🤝 Project, Credits & Contributions</h3>"
            "<p><b>Sibling project:</b> <a href='https://github.com/NeTRuNNeRGLiTCH/manga-cleaner'>Manga Cleaner Studio</a>. "
            "The original project and base studio architecture were created by "
            "<a href='https://github.com/NeTRuNNeRGLiTCH'>NeTRuNNeRGLiTCH</a>. "
            "Manga Translate Studio is led and maintained by "
            "<a href='https://github.com/santiagodvergara05-debug'>santiagodvergara05-debug</a>.</p>"
            "<p><b>Repository:</b> <a href='https://github.com/santiagodvergara05-debug/manga-translate-studio'>"
            "Manga Translate Studio on GitHub</a></p>"
            "<p><b>Repository:</b> <a href='https://github.com/NeTRuNNeRGLiTCH/manga-cleaner'>"
            "Manga Cleaner Studio on GitHub</a></p>"
            "<h4>Report issues or contribute</h4>"
            "<p>Use the repository's <a href='https://github.com/santiagodvergara05-debug/manga-translate-studio/issues'>Issues</a> "
            "to report bugs or suggest improvements. You can open a "
            "<a href='https://github.com/santiagodvergara05-debug/manga-translate-studio/pulls'>Pull Request (PR)</a> "
            "to fix errors, add UI translations, improve prompts, or implement and document a provider integration.</p>"
            "<h4>Provider availability</h4>"
            "<p>OpenAI (ChatGPT), xAI (Grok), Anthropic (Claude), OpenRouter, and DeepSeek currently appear as integration scaffolds only. "
            "They do not send API requests and cannot be saved as active providers yet. Each scaffold is connected to the shared "
            "<code>BaseAIProvider</code> contract so contributors can implement it in its own provider module.</p>"
            "<p>Each provider integration needs to be tested against that provider's API. Google (Gemini) is currently the only "
            "integration the maintainer can test with available access. Contributors who can test or verify another provider's API "
            "can help by submitting a PR with safe error handling, reported usage metadata, and setup notes.</p>"
            "<p>Before opening a PR, review the repository's <a href='https://github.com/santiagodvergara05-debug/manga-translate-studio/blob/main/CONTRIBUTING.md'>"
            "CONTRIBUTING.md</a> and keep credentials, prompts, and personal usage data out of commits.</p>"
        )
        tabs.addTab(tab_contribute, "Providers & Contribution")

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
