"""
Main application controller and primary window orchestration.

Manages layout components, asynchronous batch translation queues, rate limiting,
provider usage summaries, and bidirectional synchronization with the canvas and translation engine.
"""

import os
import re
import cv2
import time
import html
import numpy as np
from enum import Enum, auto

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QFrame, QSplitter, QFileDialog,
    QMessageBox, QGraphicsView, QProgressBar, QCheckBox, QDialog,
    QComboBox, QMenu, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QThread
from PySide6.QtGui import QCloseEvent

from src.frontend.widgets import FileListWidget
from src.frontend.canvas import MangaCanvas
from src.frontend.help_system import HelpSystem
from src.utils.config import Config
from src.utils import i18n
from src.utils.logger import logger
from src.backend.translator import TranslatorPanel, TranslationScriptEngine
from src.backend.ai_client import AIClientManager, MultimodalTranslationWorker
from src.backend.providers.base_provider import ProviderStatus, TranslationResult
from src.frontend.project_reset import ProjectResetController
from src.backend.usage_manager import UsageManager
from src.frontend.usage_pricing import UsagePricingDialog
from src.utils.i18n import tr

# /////////////////////////////////#
#          PAGE STATE ENUM         #
# /////////////////////////////////#
class PageState(Enum):
    """Execution state tracking for imported chapter pages."""
    UNMODIFIED = auto()
    MODIFIED = auto()
    SCRIPT_SYNCED = auto()
    WAITING = auto()
    PROCESSING = auto()
    UPDATING = auto()
    READY = auto()
    EMPTY = auto()
    SAFETY = auto()
    BUSY = auto()
    ERROR = auto()


# /////////////////////////////////#
#     STUDIO MAIN CONTROLLER       #
# /////////////////////////////////#

class MainWindow(QMainWindow):
    """Main window controller for Manga Translate Studio."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("main.app_name_v_version_script_generator", app_name=Config.APP_NAME, version=Config.VERSION))
        self.resize(1420, 860)

        self.usage_manager = UsageManager()
        
        # Batch Processing Management (AI Inference Queue)
        self.worker_thread = None
        self.worker = None
        self.is_batching = False
        self.is_paused = False
        self._active_batch_path = None
        self.batch_queue = []
        self._batch_previous_states = {}
        self._cancelled_pending_paths = []
        self.total_batch_tasks = 0
        self.completed_batch_tasks = 0
        self.failed_batch_tasks = []      # List of tuples: (filename, error_msg, full_path)
        
        # Execution flow & cadence control
        self.stop_requested = False
        self.stop_reason = None           # None | "user" | "quota"
        self._request_status = "Ready"
        self._header_info = ""
        self._job_started_at = None
        self._last_job_duration = None

        # Viewport navigation state
        self.is_space_moving = False

        # Image sessions & persistent state maps
        self.current_img_path = None
        self.image_sessions = {}
        self.page_states = {}

        self.init_ui()

        # Provider usage summary refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_usage_summary)
        self.timer.start(2000)
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._update_elapsed_display)
        logger.info("--- MANGA TRANSLATE STUDIO INTERFACE READY ---")

    def init_ui(self):
        """Builds central layout, header navigation bar, sidebars, and main graphics view."""
        self.central = QWidget()
        self.setCentralWidget(self.central)
        main_lay = QVBoxLayout(self.central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # /////////////////////////////////#
        #           NAVIGATION BAR         #
        # /////////////////////////////////#
        self.nav = QFrame()
        self.nav.setObjectName("NavBar")
        self.nav.setMinimumHeight(118)
        nav_lay = QVBoxLayout(self.nav)
        nav_lay.setContentsMargins(10, 6, 10, 6)
        nav_lay.setSpacing(4)
        nav_actions = QHBoxLayout()
        nav_status = QHBoxLayout()
        nav_actions.setSpacing(8)
        nav_status.setSpacing(8)

        title = QLabel(f"{Config.APP_NAME.upper()} {Config.VERSION}")
        title.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-weight: bold; font-size: 17px;")
        title.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)

        self.btn_reset = QPushButton(tr("main.reset"))
        self.btn_reset.setObjectName("ActionBtn")
        self.btn_reset.setToolTip(tr("main.close_current_project_and_purge_applicat"))
        self.btn_reset.setFixedHeight(30)
        self.btn_reset.clicked.connect(self.on_project_reset_requested)

        self.lbl_usage_summary = QLabel(tr("main.provider_loading"))
        self.lbl_usage_summary.setTextFormat(Qt.RichText)
        self.lbl_usage_summary.setStyleSheet("font-size: 10px; font-weight: bold;")
        self.lbl_usage_summary.setMinimumWidth(250)
        self.lbl_usage_summary.setMaximumWidth(520)
        self.lbl_usage_summary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.lbl_usage_summary.setWordWrap(True)
        self.header_info_card = QFrame()
        self.header_info_card.setObjectName("HeaderInfoCard")
        header_card_layout = QVBoxLayout(self.header_info_card)
        header_card_layout.setContentsMargins(9, 5, 9, 5)
        header_card_layout.addWidget(self.lbl_usage_summary)
        self.header_info_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Keep the compact green quota status in the header; editable RPD values
        # now live in API Settings alongside the selected Gemini connection.
        self.lbl_rpd_status = QLabel()
        self.lbl_rpd_status.setStyleSheet("color: #00e676; font-size: 9px; font-weight: bold;")
        self.lbl_rpd_status.setMinimumWidth(92)
        self.lbl_rpd_status.setMaximumWidth(145)
        self.lbl_rpd_status.setAlignment(Qt.AlignCenter)
        self.lbl_rpd_status.setToolTip(tr("main.gemini_daily_request_usage_and_configure"))
        self.lbl_rpd_status.setVisible(False)

        pacing_tooltip = tr("main.request_pacing_tooltip")
        self.request_pacing_combo = QComboBox()
        self.request_pacing_combo.addItem(tr("main.low"), "low")
        self.request_pacing_combo.addItem(tr("main.high"), "high")
        self.request_pacing_combo.addItem(tr("main.max"), "max")
        # Let translated pace names determine the combo width instead of
        # clipping them to the former English-only fixed width.
        self.request_pacing_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.request_pacing_combo.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.request_pacing_combo.setToolTip(pacing_tooltip)
        self.request_pacing_label = QLabel(tr("main.api_pace"))
        # Give translated labels breathing room, especially for scripts whose
        # glyphs need more visual separation at the start/end of a short label.
        self.request_pacing_label.setContentsMargins(6, 0, 6, 0)
        self.request_pacing_label.setToolTip(pacing_tooltip)

        # This menu changes only UI localization, never manga translation
        # languages. Its catalog list is discovered from locales/index.json.
        self.btn_ui_language = QPushButton()
        self.btn_ui_language.setObjectName("ActionBtn")
        self.btn_ui_language.setFixedHeight(30)
        self.btn_ui_language.setMinimumWidth(112)
        self.btn_ui_language.setMaximumWidth(300)
        self.btn_ui_language.setToolTip(tr("settings.language.label"))
        self.ui_language_menu = QMenu(self)
        automatic_action = self.ui_language_menu.addAction(tr("settings.language.auto"))
        automatic_action.triggered.connect(
            lambda _checked=False: self._save_ui_language("auto")
        )
        self.ui_language_menu.addSeparator()
        for language_code, display_name in i18n.available_languages():
            action = self.ui_language_menu.addAction(display_name)
            action.triggered.connect(
                lambda _checked=False, code=language_code:
                    self._save_ui_language(code)
            )
        self.btn_ui_language.setMenu(self.ui_language_menu)
        self._update_ui_language_button()

        self.btn_usage = QPushButton(tr("main.usage_prices"))
        self.btn_usage.setFixedHeight(30)
        self.btn_usage.setToolTip(tr("main.view_request_history_and_editable_provid"))
        self.btn_usage.clicked.connect(self.open_usage_pricing)

        btn_help = QPushButton(tr("main.help"))
        btn_help.setMinimumWidth(60)
        btn_help.setFixedHeight(30)
        btn_help.clicked.connect(lambda: HelpSystem.show_guide(self))

        self.btn_open = QPushButton(tr("main.import_folder"))
        self.btn_open.setFixedHeight(30)
        self.btn_open.clicked.connect(self.on_open_folder)

        # Separate branding/actions from provider status. The status card may
        # grow with localized text instead of being clipped by a fixed-height bar.
        nav_actions.addWidget(title)
        nav_actions.addStretch(1)
        nav_actions.addWidget(self.btn_usage)
        nav_actions.addWidget(self.btn_ui_language)
        nav_actions.addWidget(btn_help)
        nav_actions.addWidget(self.btn_open)
        nav_actions.addWidget(self.btn_reset)

        nav_status.addWidget(self.request_pacing_label)
        nav_status.addWidget(self.request_pacing_combo)
        nav_status.addWidget(self.header_info_card, 1)
        nav_status.addWidget(self.lbl_rpd_status)

        nav_lay.addLayout(nav_actions)
        nav_lay.addLayout(nav_status, 1)
        main_lay.addWidget(self.nav)

        split = QSplitter(Qt.Horizontal)

        # /////////////////////////////////#
        #           LEFT PANEL             #
        # /////////////////////////////////#
        self.lp = QFrame()
        self.lp.setObjectName("SidePanel")
        lp_lay = QVBoxLayout(self.lp)

        header_lay = QHBoxLayout()
        self.chk_all = QCheckBox()
        self.chk_all.toggled.connect(self.toggle_all_files)
        lbl_assets = QLabel(tr("main.project_assets"))
        lbl_assets.setStyleSheet("color: #888888; font-weight: bold; font-size: 11px;")
        header_lay.addWidget(self.chk_all)
        header_lay.addWidget(lbl_assets)
        header_lay.addStretch()

        self.file_list = FileListWidget()
        self.file_list.itemClicked.connect(self.on_file_clicked)

        # Batch Action 1: Sequential AI Inference & Pause/Resume
        self.btn_batch = QPushButton(tr("common.run_batch_translate"))
        self.btn_batch.setObjectName("ActionBtn")
        self.btn_batch.setFixedHeight(34)
        self.btn_batch.setToolTip(tr("main.start_or_pause_sequential_batch_translat"))
        self.btn_batch.clicked.connect(self.on_batch_button_clicked)

        # Batch Action 2: Stop / Abort Batch Completely
        self.btn_cancel_batch = QPushButton(tr("main.cancel_batch"))
        self.btn_cancel_batch.setFixedHeight(28)
        self.btn_cancel_batch.setStyleSheet("""
            QPushButton {
                background-color: #241418;
                border: 1px solid #772233;
                color: #ff5566;
                font-size: 10px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #381920;
                border: 1px solid #ff3344;
                color: #ffffff;
            }
            QPushButton:disabled {
                background-color: #16161c;
                border: 1px solid #252530;
                color: #4a4a58;
            }
        """)
        self.btn_cancel_batch.setToolTip(tr("main.immediately_abort_batch_execution_and_re"))
        self.btn_cancel_batch.setEnabled(False)
        self.btn_cancel_batch.clicked.connect(self.on_cancel_batch_clicked)

        # Batch Action 3: Export all audited pages to .TXT
        self.btn_save_all_txt = QPushButton(tr("main.write_all_to_txt"))
        self.btn_save_all_txt.setFixedHeight(32)
        self.btn_save_all_txt.setStyleSheet("background-color: #1e1e28; border: 1px solid #00d2ff; color: #00d2ff; font-weight: bold; font-size: 11px;")
        self.btn_save_all_txt.setToolTip(tr("main.export_all_reviewed_page_dialogues_into"))
        self.btn_save_all_txt.clicked.connect(self.on_batch_write_all_to_txt)

        lp_lay.addLayout(header_lay)
        lp_lay.addWidget(self.file_list)
        lp_lay.addWidget(self.btn_batch)
        lp_lay.addWidget(self.btn_cancel_batch)
        lp_lay.addWidget(self.btn_save_all_txt)

        # /////////////////////////////////#
        #         CANVAS (VIEWER)          #
        # /////////////////////////////////#
        self.canvas = MangaCanvas()

        # /////////////////////////////////#
        #       RIGHT PANEL (TRANSLATOR)   #
        # /////////////////////////////////#
        self.rp = QFrame()
        self.rp.setObjectName("SidePanel")
        rp_lay = QVBoxLayout(self.rp)
        rp_lay.setContentsMargins(4, 4, 4, 4)
        rp_lay.setSpacing(6)

        self.translator_page = TranslatorPanel(self)
        pacing = str(self.translator_page.cred_manager.data.get("request_pacing", "low")).lower()
        pacing_index = self.request_pacing_combo.findData(pacing)
        self.request_pacing_combo.setCurrentIndex(pacing_index if pacing_index >= 0 else 0)
        self.request_pacing_combo.currentIndexChanged.connect(self._request_pacing_changed)
        rp_lay.addWidget(self.translator_page, 1)

        # Styled dark cyan progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #2a2a35;
                border-radius: 3px;
                text-align: center;
                background-color: #121218;
                color: #00d2ff;
                font-size: 9px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #00d2ff;
                border-radius: 2px;
            }
        """)
        rp_lay.addWidget(self.progress_bar)

        split.addWidget(self.lp)
        split.addWidget(self.canvas)
        split.addWidget(self.rp)
        split.setSizes([220, 880, 350])
        main_lay.addWidget(split, 1)

    # --- UI LOCKING & WORKSPACE ISOLATION ---
    def set_batch_ui_locked(self, locked: bool):
        """
        Disables or enables navigation, import, and reset controls
        to prevent race conditions and unintended project mutation during execution.
        """
        self.btn_open.setEnabled(not locked)
        self.btn_reset.setEnabled(not locked)
        self.btn_save_all_txt.setEnabled(not locked)
        self.chk_all.setEnabled(not locked)
        self.translator_page.set_locked(locked, allow_audit=locked)
        self._update_current_page_audit_lock()

    def is_page_blocked_by_batch(self, path: str) -> bool:
        """True for queued or currently translating pages during a batch."""
        return bool(
            self.is_batching
            and path
            and (path == self._active_batch_path or path in self.batch_queue)
        )

    def page_has_existing_text(self, path: str) -> bool:
        """Return whether a page already has dialogue text before a new inference run."""
        panel = getattr(self, "translator_page", None)
        if not path or panel is None:
            return False
        if path == self.current_img_path:
            panel.save_current_page_editor()
        bubbles = getattr(panel, "page_bubbles_data", {}).get(path, [])
        if any(
            str(item.get("direct") or item.get("final") or "").strip()
            for item in bubbles if isinstance(item, dict)
        ):
            return True
        return any(str(line).strip() for line in getattr(panel, "path_dialogues_map", {}).get(path, []))

    def mark_page_inference_started(self, path: str):
        """Show a lock for a fresh page or a distinct refresh icon for existing text."""
        has_text = self.page_has_existing_text(path)
        state_key = "updating" if has_text else "processing"
        self.page_states[path] = PageState.UPDATING if has_text else PageState.PROCESSING
        message = tr(
            "widgets.status_retranslating_page" if has_text
            else "widgets.status_processing_page"
        )
        self.file_list.update_item_state(path, state_key, message)

    def set_page_status(self, path: str, state_name: str):
        """Synchronize an individual translation's terminal enum state with its list icon."""
        try:
            state = PageState[state_name.upper()]
        except KeyError:
            logger.warning(f"[PAGE STATUS] Unknown page state: {state_name}")
            return
        self.page_states[path] = state

    def _update_current_page_audit_lock(self):
        if hasattr(self, "translator_page") and self.is_batching:
            self.translator_page.set_page_audit_blocked(
                self.is_page_blocked_by_batch(self.current_img_path)
            )

    def on_project_reset_requested(self):
        """Prevents project wipe when inference processes are actively running."""
        if self.is_batching or (self.worker_thread and self.worker_thread.isRunning()):
            QMessageBox.warning(
                self, 
                tr("common.studio_busy"),
                tr("main.cannot_reset_workspace_while_translation")
            )
            return
        ProjectResetController.reset(self)

    # --- BATCH TRANSLATION ORCHESTRATION ---
    def on_batch_button_clicked(self):
        """Starts a new batch run or toggles pause/resume states on an existing queue."""
        if not self.is_batching:
            self.on_start_batch_translate()
        else:
            if not self.is_paused:
                self.is_paused = True
                self.btn_batch.setText(tr("main.resume_batch"))
                logger.info("[BATCH] Processing paused by user.")
            else:
                self.is_paused = False
                self.btn_batch.setText(tr("main.pause_batch"))
                logger.info("[BATCH] Processing resumed by user.")
                self.step_batch_translate()

    def on_cancel_batch_clicked(self):
        """Immediately stops the batch queue and prevents remaining pages from dispatching."""
        if not self.is_batching:
            return

        self.stop_requested = True
        self.stop_reason = "user"
        self.is_paused = False
        
        # Clear remaining queued tasks immediately
        self._cancelled_pending_paths = list(self.batch_queue)
        self.batch_queue.clear()
        
        self.btn_cancel_batch.setEnabled(False)
        self.btn_batch.setEnabled(False)
        self.btn_batch.setText(tr("main.stopping"))

        # If no background inference is in flight, finalize immediately
        if not self.worker_thread or not self.worker_thread.isRunning():
            self.finalize_batch_translate()

    def on_start_batch_translate(self):
        """Validates credentials, prepares the processing queue, and triggers execution."""
        if self.file_list.count() == 0:
            return

        # Include unsaved edits on the currently visible page when classifying retranslation.
        self.translator_page.save_current_page_editor()

        api_config = self.translator_page.get_active_api_config()
        if not api_config["has_credentials"]:
            QMessageBox.warning(
                self,
                tr("common.api_credentials_required"),
                tr("main.open_api_settings_and_configure_provider", provider_name=api_config['provider_name']),
            )
            return

        all_paths = [self.file_list.item(i).data(Qt.UserRole) for i in range(self.file_list.count())]
        paths = [
            self.file_list.item(i).data(Qt.UserRole)
            for i in range(self.file_list.count())
            if self.file_list.item(i).checkState() == Qt.Checked
        ]

        # If nothing is explicitly checked, target pending, error, busy, or unhandled pages
        if not paths:
            paths = [
                p for p in all_paths
                if self.page_states.get(p) in (
                    PageState.UNMODIFIED, 
                    PageState.ERROR, 
                    PageState.BUSY, 
                    PageState.SAFETY, 
                    PageState.WAITING
                )
            ]
            if not paths:
                QMessageBox.information(
                    self, tr("main.all_pages_completed"),
                    tr("main.all_pages_have_already_been_processed")
                )
                return

            marked = set(paths)
            self.chk_all.blockSignals(True)
            self.chk_all.setChecked(False)
            self.chk_all.blockSignals(False)
            for i in range(self.file_list.count()):
                it = self.file_list.item(i)
                it.setCheckState(Qt.Checked if it.data(Qt.UserRole) in marked else Qt.Unchecked)

        self.batch_queue = list(paths)
        self._batch_previous_states = {
            path: self.page_states.get(path, PageState.UNMODIFIED)
            for path in self.batch_queue
        }
        self._cancelled_pending_paths = []
        self.total_batch_tasks = len(paths)
        self.completed_batch_tasks = 0
        self.failed_batch_tasks.clear()
        self.is_batching = True
        self._active_batch_path = None
        self.is_paused = False
        self.stop_requested = False
        self.stop_reason = None
        self._start_timed_job("Waiting to send")

        for path in self.batch_queue:
            self.page_states[path] = PageState.WAITING
            self.file_list.update_item_state(path, "waiting", tr("widgets.status_queued_for_batch"))

        # Lock entire UI for configuration safety
        self.set_batch_ui_locked(True)

        self.progress_bar.setRange(0, self.total_batch_tasks)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        self.btn_batch.setText(tr("main.pause_batch"))
        self.btn_batch.setEnabled(True)
        self.btn_cancel_batch.setEnabled(True)

        self.step_batch_translate()

    def _schedule_next(self):
        """Schedules the next page; the worker applies the configured provider pacing."""
        if self.stop_requested or not self.batch_queue:
            self.finalize_batch_translate()
        elif not self.is_paused:
            self._set_request_status("Waiting for next page")
            QTimer.singleShot(0, self.step_batch_translate)

    def step_batch_translate(self):
        """Dispatches the next image inference task in a background QThread."""
        if self.stop_requested or not self.batch_queue:
            self.finalize_batch_translate()
            return

        if self.is_paused:
            return

        self._set_request_status("Waiting to send")

        target_path = self.batch_queue.pop(0)
        self._active_batch_path = target_path
        self.mark_page_inference_started(target_path)
        self._update_current_page_audit_lock()

        api_config = self.translator_page.get_active_api_config()
        provider_id = api_config["provider_id"]

        # Keep stable translation rules as the system prefix, and send only page-specific context with the image.
        if hasattr(self.translator_page, "build_request_prompts"):
            system_prompt, page_prompt = self.translator_page.build_request_prompts(target_path)
        else:
            system_prompt, page_prompt = "", self.translator_page.get_full_prompt()

        estimate_prompt = f"{system_prompt}\n\n{page_prompt}" if system_prompt else page_prompt
        self.translator_page.update_token_estimate(target_path, estimate_prompt)
        self.translator_page.pending_language_pairs[target_path] = self.translator_page.current_language_pair()

        self.worker_thread = QThread()
        self.worker = MultimodalTranslationWorker(
            image_path=target_path,
            full_prompt=page_prompt,
            provider=provider_id,
            model_name=api_config["model"],
            api_key=api_config["api_key"],
            ollama_url=api_config["endpoint_url"],
            ollama_token=api_config["token"],
            thinking_level=api_config["thinking_level"],
            system_prompt=system_prompt,
            connection_profile_id=api_config["connection_profile_id"],
            request_pacing=api_config["request_pacing"],
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_batch_page_finished)
        self.worker.error.connect(self.on_batch_page_error)
        self.worker.request_started.connect(self._on_request_started)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.translator_page.show_inference_status(
            target_path,
            self.completed_batch_tasks + 1,
            self.total_batch_tasks,
        )
        self.worker_thread.start()

    def on_batch_page_finished(self, path: str, result: TranslationResult):
        """Processes background inference results and transitions page state."""
        # Gracefully release background thread handle
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None

        self.completed_batch_tasks += 1
        self.progress_bar.setValue(self.completed_batch_tasks)

        status = result.status
        fname = os.path.basename(path)
        request_language_pair = self.translator_page.pending_language_pairs.pop(path, None)
        usage = result.usage or {}
        self.translator_page.page_token_usage[path] = usage.copy()
        if path == self.current_img_path:
            self.translator_page.show_token_usage(usage)

        if status == ProviderStatus.SUCCESS:
            self.translator_page.page_language_pairs[path] = (
                request_language_pair or self.translator_page.current_language_pair()
            )
            self.page_states[path] = PageState.READY
            self.file_list.update_item_state(
                path, "ready",
                tr("widgets.status_translated_dialogues", count=len(result.bubbles)),
            )
            self.translator_page.page_bubbles_data[path] = result.bubbles
            self.translator_page.path_dialogues_map[path] = [b.get("direct") for b in result.bubbles if b.get("direct")]

        elif status == ProviderStatus.EMPTY:
            self.translator_page.page_language_pairs.pop(path, None)
            self.page_states[path] = PageState.EMPTY
            self.file_list.update_item_state(
                path, "empty", result.message or tr("widgets.status_silent_panel")
            )
            self.translator_page.page_bubbles_data[path] = []
            self.translator_page.path_dialogues_map.pop(path, None)

        elif status == ProviderStatus.SAFETY_BLOCKED:
            self.page_states[path] = PageState.SAFETY
            self.file_list.update_item_state(path, "safety", result.message)
            self.failed_batch_tasks.append((fname, result.message, path))

        elif status == ProviderStatus.SERVER_BUSY:
            self.page_states[path] = PageState.BUSY
            self.file_list.update_item_state(path, "busy", result.message)
            self.failed_batch_tasks.append((fname, result.message, path))

        else:  # ERROR
            self.page_states[path] = PageState.ERROR
            self.file_list.update_item_state(
                path, "error", result.message or tr("widgets.status_translation_failed")
            )
            self.failed_batch_tasks.append((fname, result.message, path))

        if path == self._active_batch_path:
            self._active_batch_path = None
        if path == self.current_img_path and status in (ProviderStatus.SUCCESS, ProviderStatus.EMPTY):
            self.translator_page.populate_bubble_editor(result.bubbles)
        if path == self.current_img_path:
            self._update_current_page_audit_lock()

        self.refresh_usage_summary()
        if self.stop_requested:
            self.finalize_batch_translate()
        else:
            self._schedule_next()

    def _update_ui_language_button(self):
        """Show the saved locale choice without loading additional catalogs."""
        selected = i18n.get_saved_language() or "auto"
        if selected.casefold() == "auto":
            display_name = tr("settings.language.auto")
        else:
            normalized = selected.replace("_", "-").casefold()
            display_name = next(
                (
                    name for code, name in i18n.available_languages()
                    if code.replace("_", "-").casefold() == normalized
                ),
                selected,
            )
        # Keep the selector compact with the native name, while retaining the
        # bilingual catalog label in its tooltip and in the menu itself.
        native_name = display_name
        if " (" in display_name and display_name.endswith(")"):
            native_name = display_name.rsplit(" (", 1)[1][:-1]
        button_text = f"🌐 {native_name}"
        metrics = self.btn_ui_language.fontMetrics()
        requested_width = metrics.horizontalAdvance(button_text) + 42
        button_width = max(112, min(300, requested_width))
        available_text_width = max(50, button_width - 42)
        visible_name = metrics.elidedText(native_name, Qt.ElideRight, available_text_width)
        self.btn_ui_language.setText(f"🌐 {visible_name}")
        self.btn_ui_language.setFixedWidth(button_width)
        self.btn_ui_language.setToolTip(display_name)

    def _save_ui_language(self, code):
        """Persist the interface locale; the active UI reloads on next launch."""
        selected = i18n.get_saved_language() or "auto"
        if selected.casefold() == code.casefold():
            return
        if not i18n.save_language(code):
            QMessageBox.warning(
                self,
                i18n.tr("settings.language.save_error.title"),
                i18n.tr("settings.language.save_error.body"),
            )
            return
        self._update_ui_language_button()
        if code != i18n.current_language():
            QMessageBox.information(
                self,
                i18n.tr("settings.language.restart_required.title"),
                i18n.tr("settings.language.restart_required.body"),
            )

    def on_batch_page_error(self, path: str, error_msg: str):
        """Handles unhandled worker thread errors during batch translation."""
        self.translator_page.pending_language_pairs.pop(path, None)
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None

        # Immediate shutdown on Daily Quota exhaustion (RPD) to preserve remaining tasks
        if "DAILY_QUOTA" in error_msg:
            self.batch_queue.insert(0, path)
            self.page_states[path] = PageState.UNMODIFIED
            self.file_list.update_item_state(path, "unmodified", tr("widgets.status_daily_quota_exhausted"))
            self.stop_requested = True
            self.stop_reason = "quota"
            self._active_batch_path = None
            logger.warning(f"[BATCH QUOTA] Daily quota exhausted on {os.path.basename(path)}. Halting batch.")
            self.finalize_batch_translate()
            return

        self.completed_batch_tasks += 1
        self.progress_bar.setValue(self.completed_batch_tasks)

        fname = os.path.basename(path)
        self.page_states[path] = PageState.ERROR
        self.file_list.update_item_state(path, "error", error_msg[:60])
        self.failed_batch_tasks.append((fname, error_msg[:60], path))
        if path == self._active_batch_path:
            self._active_batch_path = None
        self._update_current_page_audit_lock()

        logger.error(f"[BATCH ERROR] on {path}: {error_msg}")

        if self.stop_requested:
            self.finalize_batch_translate()
        else:
            self._schedule_next()

    def finalize_batch_translate(self):
        """Concludes the batch run, unlocks controls, and reports completed and failed tasks."""
        self.is_batching = False
        self.is_paused = False
        self._active_batch_path = None
        self._finish_timed_job(
            "Batch complete" if not self.stop_requested and not self.failed_batch_tasks else "Batch finished"
        )
        self.progress_bar.setVisible(False)
        self.btn_batch.setEnabled(True)
        self.btn_batch.setText(tr("common.run_batch_translate"))
        self.btn_cancel_batch.setEnabled(False)

        # Unlock UI controls completely
        self.set_batch_ui_locked(False)

        pending = list(self.batch_queue)
        self.batch_queue.clear()
        pending = list(dict.fromkeys(pending + self._cancelled_pending_paths))
        self._cancelled_pending_paths = []
        for path in pending:
            previous_state = self._batch_previous_states.get(path, PageState.UNMODIFIED)
            self.page_states[path] = previous_state
            state_key = previous_state.name.lower()
            self.file_list.update_item_state(
                path, state_key,
                tr("widgets.status_batch_stopped_before_send", state=tr(f"widgets.state_{state_key}")),
            )
        self._batch_previous_states.clear()
        successful_count = self.completed_batch_tasks - len(self.failed_batch_tasks)
        if not self.stop_requested and not self.failed_batch_tasks and not pending:
            self.translator_page.show_status_message(
                tr(
                    "main.batch_status_complete",
                    successful_count=successful_count,
                    total_count=self.total_batch_tasks,
                ),
                "#00e676",
            )
        else:
            self.translator_page.show_status_message(
                tr(
                    "main.batch_status_finished",
                    successful_count=successful_count,
                    failed_count=len(self.failed_batch_tasks),
                    pending_count=len(pending),
                ),
                "#ffd600",
            )

        if not self.failed_batch_tasks and not pending and not self.stop_requested:
            QMessageBox.information(
                self, 
                tr("main.batch_complete"),
                tr("main.all_pages_successful_count_total_batch", successful_count=successful_count, total_batch_tasks=self.total_batch_tasks)
            )
            return

        # Keep failed, busy, safety-blocked and pending tasks selected for fast retry
        retry_paths = {p for _, _, p in self.failed_batch_tasks} | set(pending)
        self.chk_all.blockSignals(True)
        self.chk_all.setChecked(False)
        self.chk_all.blockSignals(False)

        for i in range(self.file_list.count()):
            it = self.file_list.item(i)
            it.setCheckState(Qt.Checked if it.data(Qt.UserRole) in retry_paths else Qt.Unchecked)

        reason_keys = {
            "quota": "main.batch_reason_quota_exhausted",
            "user": "main.batch_reason_stopped_by_user",
        }
        head = tr(reason_keys.get(self.stop_reason, "main.batch_reason_some_issues"))

        failed_lines = [f"• {f} ➔ {r}" for f, r, _ in self.failed_batch_tasks]
        detail = "\n".join(failed_lines[:15])
        if len(failed_lines) > 15:
            detail += "\n" + tr("main.batch_more_failed_pages", count=len(failed_lines) - 15)

        box = QMessageBox(self)
        box.setWindowTitle(tr("main.batch_finished"))
        box.setIcon(QMessageBox.Warning if (self.failed_batch_tasks or self.stop_requested) else QMessageBox.Information)
        box.setText(
            tr("main.head_processed_successful_count_issues_c", head=head, successful_count=successful_count, count=len(self.failed_batch_tasks), count2=len(pending))
        )
        if detail:
            box.setDetailedText(detail)
        box.exec()

    # --- SCRIPT EXPORT AND PERSISTENCE ---
    def on_batch_write_all_to_txt(self):
        """Flushes active dialogues across all project pages into the target .txt script."""
        self.translator_page.save_current_page_editor()

        paths = self.translator_page._get_all_project_paths()
        if not paths:
            QMessageBox.warning(self, tr("common.notice"), tr("main.no_images_loaded_in_the_project"))
            return

        if not self.translator_page.path_dialogues_map:
            QMessageBox.warning(self, tr("common.notice"), tr("main.there_are_no_translated_or_reviewed"))
            return

        # Prompt template generation if no script file is currently bound
        if not self.translator_page.loaded_script_path:
            self.translator_page.on_generate_template()
            if not self.translator_page.loaded_script_path:
                return

        try:
            TranslationScriptEngine.sync_full_script_file(
                self.translator_page.loaded_script_path, 
                paths, 
                self.translator_page.path_dialogues_map
            )
            self.translator_page.lbl_script_status.setText(tr("main.saved_basename", basename=os.path.basename(self.translator_page.loaded_script_path)))
            self.translator_page.refresh_scripts_for_selected_series()
            
            for p in self.translator_page.path_dialogues_map.keys():
                self.page_states[p] = PageState.SCRIPT_SYNCED
                self.file_list.update_item_state(
                    p, "script_synced", tr("widgets.status_written_to_script")
                )

            QMessageBox.information(
                self, 
                tr("main.script_synchronized"),
                tr("main.all_dialogues_were_successfully_written", loaded_script_path=self.translator_page.loaded_script_path)
            )
        except Exception as e:
            QMessageBox.critical(self, tr("main.save_error"), tr("main.could_not_write_script_file_e", e=e))

    # --- PAGE NAVIGATION & ASSET SYNCHRONIZATION ---
    def on_open_folder(self):
        """Opens directory picker and initializes project assets."""
        p = QFileDialog.getExistingDirectory(self, tr("main.select_folder"))
        if p:
            self.image_sessions.clear()
            self.page_states.clear()
            self.file_list.clear()
            self.translator_page.page_bubbles_data.clear()
            self.translator_page.path_dialogues_map.clear()
            self.translator_page.page_token_usage.clear()
            self.translator_page.page_language_pairs.clear()
            self.translator_page.pending_language_pairs.clear()
            self.current_img_path = None

            natural_key = lambda name: [int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", name)]
            for f in sorted(os.listdir(p), key=natural_key):
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    full_path = os.path.join(p, f)
                    self.page_states[full_path] = PageState.UNMODIFIED
                    self.file_list.add_file(full_path)

            self.translator_page.populate_bubble_editor([])
            self.translator_page.refresh_series_folders()

    def mark_current_modified(self):
        """Marks active page as modified when user manually changes dialogues."""
        if self.current_img_path and not self.is_page_blocked_by_batch(self.current_img_path):
            if self.page_states.get(self.current_img_path) != PageState.MODIFIED:
                self.page_states[self.current_img_path] = PageState.MODIFIED
                self.file_list.update_item_state(
                    self.current_img_path, "modified", tr("widgets.status_locally_modified")
                )

    def on_file_clicked(self, it):
        """Loads selected image into canvas viewer and renders its dialogue editor."""
        path_real = it.data(Qt.UserRole)
        if path_real == self.current_img_path:
            return

        if self.current_img_path:
            self.translator_page.save_current_page_editor()

        self.current_img_path = path_real

        if path_real in self.image_sessions:
            img = self.image_sessions[path_real]
            self.canvas.set_image(img)
        else:
            try:
                img_data = np.fromfile(path_real, dtype=np.uint8)
                img = cv2.imdecode(img_data, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    if len(img.shape) == 2:
                        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                    elif len(img.shape) == 3 and img.shape[2] == 4:
                        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                    else:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                    self.canvas.set_image(img)
                    self.image_sessions[path_real] = img
                else:
                    QMessageBox.warning(self, tr("main.image_decode_error"), tr("main.failed_to_decode_image_file_basename", basename=os.path.basename(path_real)))
            except Exception as e:
                QMessageBox.warning(self, tr("main.image_load_error"), tr("main.could_not_load_image_file_e", e=e))

        self.translator_page.load_page_state(path_real)

    def toggle_all_files(self, checked):
        """Toggles check state for all items in the assets list."""
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(state)

    def keyPressEvent(self, event):
        """Activates hand drag mode while Spacebar is held down."""
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.is_space_moving = True
            self.canvas.setDragMode(QGraphicsView.ScrollHandDrag)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Restores normal canvas cursor upon Spacebar release."""
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.is_space_moving = False
            self.canvas.setDragMode(QGraphicsView.NoDrag)
        super().keyReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent):
        """Attempts to stop batch work before closing; see the shutdown audit note."""
        # AUDIT: a provider call runs synchronously inside its worker. quit() cannot
        # interrupt it, and this bounded wait can expire while it is still running.
        # Single-page workers also need to be included in a future close-pending flow.
        if self.is_batching:
            self.stop_requested = True
            self.batch_queue.clear()
            if self.worker_thread and self.worker_thread.isRunning():
                # Disconnect signals to avoid delivering events to destroyed UI elements
                if self.worker:
                    try:
                        self.worker.finished.disconnect()
                        self.worker.error.disconnect()
                    except RuntimeError:
                        pass
                self.worker_thread.quit()
                self.worker_thread.wait(1000)
        super().closeEvent(event)

    def refresh_usage_summary(self):
        """Refresh the colored provider summary and Gemini's compact quota status."""
        if not hasattr(self, "translator_page"):
            return
        config = self.translator_page.get_active_api_config()
        provider = config["provider_id"]
        model = config["model"]
        thinking = str(config.get("thinking_level", "")).strip().lower()
        thinking_available = (
            provider == "gemini"
            and bool(thinking)
            and bool(AIClientManager.get_provider("gemini").supported_thinking_levels(model))
        )
        if not thinking_available:
            thinking_label = tr("main.thinking_not_available")
        else:
            thinking_label = tr(f"main.thinking_{thinking}")
        provider_label = html.escape(str(config.get("provider_name") or provider.title()))
        model_label = html.escape(str(model or tr("main.no_model_selected")))
        thinking_label = html.escape(thinking_label)
        thinking_color = "#00d4ff" if thinking_available else "#ff5252"
        self._header_info = (
            f"<span style='color:#c1c1ce'>{tr('common.provider')}</span> <span style='color:#00d4ff'>{provider_label}</span><br>"
            f"<span style='color:#c1c1ce'>{tr('api_settings.model')}</span> <span style='color:#00d4ff'>{model_label}</span><br>"
            f"<span style='color:#c1c1ce'>{tr('main.thinking_label')}</span> "
            f"<span style='color:{thinking_color}'>{thinking_label}</span>"
        )
        if not config["has_credentials"] and self._job_started_at is None:
            self._request_status = "Credentials needed"
        elif config["has_credentials"] and self._request_status == "Credentials needed":
            self._request_status = "Ready"
        self._update_elapsed_display()
        self.lbl_usage_summary.setToolTip(
            tr("main.request_pacing_upper_provider_model_and", upper=config['request_pacing'].upper())
        )
        self.lbl_rpd_status.setVisible(provider == "gemini" and bool(model))
        if provider == "gemini" and model:
            state = self.usage_manager.get_gemini_rpd(config["connection_profile_id"], model)
            self._refresh_gemini_rpd_status(state["limit"], state["used"])

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        total = max(0, int(seconds))
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"

    def _update_elapsed_display(self):
        if not hasattr(self, "lbl_usage_summary"):
            return
        if self._job_started_at is not None:
            elapsed = time.monotonic() - self._job_started_at
            duration = self._format_elapsed(elapsed)
            time_color = "#00d4ff"
            time_label = tr("main.elapsed_time", duration=duration)
        elif self._last_job_duration is not None:
            duration = self._format_elapsed(self._last_job_duration)
            time_color = "#00e676" if self._request_status in ("Complete", "Batch complete") else "#ffd600"
            time_label = tr("main.total_work_time", duration=duration)
        else:
            time_label = ""
        activity = self._localized_request_status()
        activity_color = "#ff5252"
        if self._request_status in ("Ready", "Batch complete"):
            activity_color = "#00e676"
        elif self._request_status in (
            "Waiting to send", "Waiting for next page",
            "Working — waiting for API response", "Stopping",
        ):
            activity_color = "#00d4ff"
        self.lbl_usage_summary.setText(
            tr(
                "main.header_info_status_escape",
                header_info=self._header_info,
                activity_color=activity_color,
                escape=html.escape(activity),
                time_line=(
                    f"<br><span style='color:{time_color}'>{html.escape(time_label)}</span>"
                    if time_label else ""
                ),
            )
        )

    def _localized_request_status(self):
        """Translate fixed request states while keeping internal state values stable."""
        keys = {
            "Ready": "main.status_ready",
            "Complete": "main.status_complete",
            "Failed": "main.status_failed",
            "Credentials needed": "main.status_credentials_needed",
            "Waiting to send": "main.status_waiting_to_send",
            "Waiting for next page": "main.status_waiting_for_next_page",
            "Working — waiting for API response": "main.status_working_waiting_api",
            "Stopping": "main.status_stopping",
            "Batch complete": "main.status_batch_complete",
            "Batch finished": "main.status_batch_finished",
        }
        key = keys.get(self._request_status)
        return tr(key) if key else self._request_status

    def _start_timed_job(self, status: str = "Waiting to send"):
        self.elapsed_timer.stop()
        self._job_started_at = None
        self._last_job_duration = None
        self._request_status = status
        self._update_elapsed_display()

    def _on_request_started(self):
        if self._job_started_at is None:
            self._job_started_at = time.monotonic()
            self._last_job_duration = None
            self.elapsed_timer.start()
        # Each batch page changes the state back to "Waiting to send". Always
        # switch to the in-flight state when its paced request actually starts,
        # even while the batch-wide elapsed timer is already running.
        self._request_status = "Working — waiting for API response"
        self._update_elapsed_display()

    def _finish_timed_job(self, status: str):
        if self._job_started_at is not None:
            self._last_job_duration = time.monotonic() - self._job_started_at
        self._job_started_at = None
        self.elapsed_timer.stop()
        self._request_status = status
        self._update_elapsed_display()

    def _set_request_status(self, status: str):
        self._request_status = status
        self._update_elapsed_display()

    def _request_pacing_changed(self, *_):
        mode = str(self.request_pacing_combo.currentData() or "low").lower()
        self.translator_page.cred_manager.save({"request_pacing": mode})
        self.refresh_usage_summary()

    def _refresh_gemini_rpd_status(self, limit: int, used: int):
        """Show the Gemini meter state without exposing editable fields in the header."""
        if limit > 0 and used > limit:
            text = f"RPD: {used} / {limit}"
            color = "#ff5252"
        elif limit == 0:
            text = f"RPD: {used} / 0"
            color = "#a0a0ad"
        else:
            text = f"RPD: {used} / {limit}"
            color = "#00e676"
        self.lbl_rpd_status.setText(text)
        self.lbl_rpd_status.setStyleSheet(f"color: {color}; font-size: 9px; font-weight: bold;")

    def open_usage_pricing(self):
        """Opens editable price tables and request history."""
        config = self.translator_page.get_active_api_config()
        dialog = UsagePricingDialog(
            self.usage_manager,
            config["provider_id"],
            config["model"],
            config["connection_profile_id"],
            self,
            connection_profile_name=config["connection_profile_name"],
            connection_profiles={
                profile_id: str(profile.get("name") or "Unnamed connection")
                for profile_id, profile in self.translator_page.cred_manager.get_connection_profiles().items()
            },
        )
        if dialog.exec() == QDialog.Accepted:
            self.refresh_usage_summary()
