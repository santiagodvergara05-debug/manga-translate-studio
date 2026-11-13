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
    QComboBox,
)
from PySide6.QtCore import Qt, QTimer, QThread
from PySide6.QtGui import QCloseEvent

from src.frontend.widgets import FileListWidget
from src.frontend.canvas import MangaCanvas
from src.frontend.help_system import HelpSystem
from src.utils.config import Config
from src.utils.logger import logger
from src.backend.translator import TranslatorPanel, TranslationScriptEngine
from src.backend.ai_client import AIClientManager, MultimodalTranslationWorker
from src.backend.providers.base_provider import ProviderStatus, TranslationResult
from src.frontend.project_reset import ProjectResetController
from src.backend.usage_manager import UsageManager
from src.frontend.usage_pricing import UsagePricingDialog

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
        self.setWindowTitle(f"{Config.APP_NAME} v{Config.VERSION} - Script Generator")
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
        self.nav.setFixedHeight(88)
        nav_lay = QHBoxLayout(self.nav)

        title = QLabel(f"{Config.APP_NAME.upper()} {Config.VERSION}")
        title.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-weight: bold; font-size: 17px;")

        self.btn_reset = QPushButton("RESET")
        self.btn_reset.setObjectName("ActionBtn")
        self.btn_reset.setToolTip("Close current project and purge application memory")
        self.btn_reset.setFixedSize(65, 30)
        self.btn_reset.clicked.connect(self.on_project_reset_requested)

        self.lbl_usage_summary = QLabel("Provider: loading…")
        self.lbl_usage_summary.setTextFormat(Qt.RichText)
        self.lbl_usage_summary.setStyleSheet("font-size: 10px; font-weight: bold;")
        self.lbl_usage_summary.setMinimumWidth(300)
        self.lbl_usage_summary.setMaximumWidth(370)
        self.lbl_usage_summary.setWordWrap(True)
        self.header_info_card = QFrame()
        self.header_info_card.setObjectName("HeaderInfoCard")
        header_card_layout = QVBoxLayout(self.header_info_card)
        header_card_layout.setContentsMargins(9, 5, 9, 5)
        header_card_layout.addWidget(self.lbl_usage_summary)

        # Keep the compact green quota status in the header; editable RPD values
        # now live in API Settings alongside the selected Gemini connection.
        self.lbl_rpd_status = QLabel()
        self.lbl_rpd_status.setStyleSheet("color: #00e676; font-size: 9px; font-weight: bold;")
        self.lbl_rpd_status.setMinimumWidth(105)
        self.lbl_rpd_status.setMaximumWidth(125)
        self.lbl_rpd_status.setAlignment(Qt.AlignCenter)
        self.lbl_rpd_status.setToolTip("Gemini daily request usage and configured limit.")
        self.lbl_rpd_status.setVisible(False)

        pacing_tooltip = (
            "Minimum delay between translation requests (tracked per provider):\n"
            "Theoretical maximum request starts per minute from the configured minimum delay:\n"
            "LOW: 4.1 seconds between requests — about 14.6 RPM maximum.\n"
            "HIGH: 1.5 seconds between requests — 40 RPM maximum.\n"
            "MAX: 0.5 seconds between requests — 120 RPM maximum.\n"
            "MAX can trigger provider rate limits or HTTP 429 responses.\n"
            "These are theoretical ceilings; API processing time can make the actual rate lower.\n"
            "Applies to single-page and batch translations."
        )
        self.request_pacing_combo = QComboBox()
        self.request_pacing_combo.addItem("LOW", "low")
        self.request_pacing_combo.addItem("HIGH", "high")
        self.request_pacing_combo.addItem("MAX", "max")
        self.request_pacing_combo.setFixedWidth(78)
        self.request_pacing_combo.setToolTip(pacing_tooltip)
        self.request_pacing_label = QLabel("API pace")
        self.request_pacing_label.setToolTip(pacing_tooltip)

        self.btn_usage = QPushButton("USAGE / PRICES")
        self.btn_usage.setFixedHeight(30)
        self.btn_usage.setToolTip("View request history and editable provider prices.")
        self.btn_usage.clicked.connect(self.open_usage_pricing)

        btn_help = QPushButton("HELP")
        btn_help.setFixedSize(50, 30)
        btn_help.clicked.connect(lambda: HelpSystem.show_guide(self))

        self.btn_open = QPushButton("IMPORT FOLDER")
        self.btn_open.setFixedHeight(30)
        self.btn_open.clicked.connect(self.on_open_folder)

        nav_lay.addWidget(title)
        nav_lay.addStretch()
        nav_lay.addWidget(self.request_pacing_label)
        nav_lay.addWidget(self.request_pacing_combo)
        nav_lay.addWidget(self.header_info_card)
        nav_lay.addWidget(self.lbl_rpd_status)
        nav_lay.addWidget(self.btn_usage)
        nav_lay.addSpacing(10)
        nav_lay.addWidget(btn_help)
        nav_lay.addWidget(self.btn_open)
        nav_lay.addWidget(self.btn_reset)
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
        lbl_assets = QLabel("PROJECT ASSETS")
        lbl_assets.setStyleSheet("color: #888888; font-weight: bold; font-size: 11px;")
        header_lay.addWidget(self.chk_all)
        header_lay.addWidget(lbl_assets)
        header_lay.addStretch()

        self.file_list = FileListWidget()
        self.file_list.itemClicked.connect(self.on_file_clicked)

        # Batch Action 1: Sequential AI Inference & Pause/Resume
        self.btn_batch = QPushButton("▶ RUN BATCH TRANSLATE")
        self.btn_batch.setObjectName("ActionBtn")
        self.btn_batch.setFixedHeight(34)
        self.btn_batch.setToolTip("Start or pause sequential batch translation across selected pages.")
        self.btn_batch.clicked.connect(self.on_batch_button_clicked)

        # Batch Action 2: Stop / Abort Batch Completely
        self.btn_cancel_batch = QPushButton("⏹ CANCEL BATCH")
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
        self.btn_cancel_batch.setToolTip("Immediately abort batch execution and retain completed pages.")
        self.btn_cancel_batch.setEnabled(False)
        self.btn_cancel_batch.clicked.connect(self.on_cancel_batch_clicked)

        # Batch Action 3: Export all audited pages to .TXT
        self.btn_save_all_txt = QPushButton("💾 WRITE ALL TO .TXT")
        self.btn_save_all_txt.setFixedHeight(32)
        self.btn_save_all_txt.setStyleSheet("background-color: #1e1e28; border: 1px solid #00d2ff; color: #00d2ff; font-weight: bold; font-size: 11px;")
        self.btn_save_all_txt.setToolTip("Export all reviewed page dialogues into Manga Cleaner script.")
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
        message = "Retranslating existing page text" if has_text else "Page is being processed by the API"
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
                "Studio Busy", 
                "Cannot reset workspace while translation or batch processing is active.\n"
                "Please cancel or wait for the process to complete before resetting."
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
                self.btn_batch.setText("▶ RESUME BATCH")
                logger.info("[BATCH] Processing paused by user.")
            else:
                self.is_paused = False
                self.btn_batch.setText("⏸ PAUSE BATCH")
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
        self.btn_batch.setText("⏳ Stopping...")

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
                "API credentials required",
                f"Open API Settings and configure {api_config['provider_name']} before starting a batch.",
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
                    self, "All Pages Completed", 
                    "All pages have already been processed.\nCheck specific pages in the list if you wish to re-translate them."
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
            self.file_list.update_item_state(path, "waiting", "Queued for batch translation")

        # Lock entire UI for configuration safety
        self.set_batch_ui_locked(True)

        self.progress_bar.setRange(0, self.total_batch_tasks)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        self.btn_batch.setText("⏸ PAUSE BATCH")
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
            self.file_list.update_item_state(path, "ready", f"Translated ({len(result.bubbles)} dialogues)")
            self.translator_page.page_bubbles_data[path] = result.bubbles
            self.translator_page.path_dialogues_map[path] = [b.get("direct") for b in result.bubbles if b.get("direct")]

        elif status == ProviderStatus.EMPTY:
            self.translator_page.page_language_pairs.pop(path, None)
            self.page_states[path] = PageState.EMPTY
            self.file_list.update_item_state(path, "empty", result.message or "Silent panel (No text detected)")
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
            self.file_list.update_item_state(path, "error", result.message or "Translation failed")
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
            self.file_list.update_item_state(path, "unmodified", "Daily quota exhausted")
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
        self.btn_batch.setText("▶ RUN BATCH TRANSLATE")
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
            self.file_list.update_item_state(path, state_key, f"Batch stopped before this page was sent · {state_key.title()}")
        self._batch_previous_states.clear()
        successful_count = self.completed_batch_tasks - len(self.failed_batch_tasks)
        duration_suffix = (
            f" · {self._format_elapsed(self._last_job_duration)}"
            if self._last_job_duration is not None else ""
        )
        if not self.stop_requested and not self.failed_batch_tasks and not pending:
            self.translator_page.show_status_message(
                f"✔ Batch complete · {successful_count}/{self.total_batch_tasks} pages translated{duration_suffix}",
                "#00e676",
            )
        else:
            self.translator_page.show_status_message(
                f"⚠ Batch finished · {successful_count} successful · "
                f"{len(self.failed_batch_tasks)} failed · {len(pending)} pending{duration_suffix}",
                "#ffd600",
            )

        if not self.failed_batch_tasks and not pending and not self.stop_requested:
            QMessageBox.information(
                self, 
                "Batch Complete", 
                f"All pages ({successful_count}/{self.total_batch_tasks}) were processed successfully.\n\n"
                "Review them page by page and click 'WRITE ALL TO .TXT'."
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

        reasons = {
            "quota": "Daily request limit (RPD) exhausted. Pending pages remain checked for easy resumption once quota resets.",
            "user": "Batch processing was stopped by user. Remaining pages remain selected for quick retry.",
        }
        head = reasons.get(self.stop_reason, "Some pages encountered issues during batch processing.")

        failed_lines = [f"• {f} ➔ {r}" for f, r, _ in self.failed_batch_tasks]
        detail = "\n".join(failed_lines[:15])
        if len(failed_lines) > 15:
            detail += f"\n... and {len(failed_lines) - 15} more page(s)."

        box = QMessageBox(self)
        box.setWindowTitle("Batch Finished")
        box.setIcon(QMessageBox.Warning if (self.failed_batch_tasks or self.stop_requested) else QMessageBox.Information)
        box.setText(
            f"{head}\n\n"
            f"✔ Processed: {successful_count}\n"
            f"✖ Issues: {len(self.failed_batch_tasks)}\n"
            f"⏸ Pending: {len(pending)}"
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
            QMessageBox.warning(self, "Notice", "No images loaded in the project.")
            return

        if not self.translator_page.path_dialogues_map:
            QMessageBox.warning(self, "Notice", "There are no translated or reviewed dialogues to save.")
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
            self.translator_page.lbl_script_status.setText(f"Saved: {os.path.basename(self.translator_page.loaded_script_path)}")
            self.translator_page.refresh_scripts_for_selected_series()
            
            for p in self.translator_page.path_dialogues_map.keys():
                self.page_states[p] = PageState.SCRIPT_SYNCED
                self.file_list.update_item_state(p, "script_synced", "Written into translation script")

            QMessageBox.information(
                self, 
                "Script Synchronized", 
                f"All dialogues were successfully written to:\n\n{self.translator_page.loaded_script_path}\n\n"
                "Ready to open directly in Manga Cleaner."
            )
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not write script file:\n{e}")

    # --- PAGE NAVIGATION & ASSET SYNCHRONIZATION ---
    def on_open_folder(self):
        """Opens directory picker and initializes project assets."""
        p = QFileDialog.getExistingDirectory(self, "Select Folder")
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
                self.file_list.update_item_state(self.current_img_path, "modified", "Locally modified")

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
                    QMessageBox.warning(self, "Image Decode Error", f"Failed to decode image file:\n{os.path.basename(path_real)}")
            except Exception as e:
                QMessageBox.warning(self, "Image Load Error", f"Could not load image file:\n{e}")

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
        thinking = str(config.get("thinking_level", "")).strip().title()
        thinking_available = (
            provider == "gemini"
            and bool(thinking)
            and bool(AIClientManager.get_provider("gemini").supported_thinking_levels(model))
        )
        if not thinking_available:
            thinking = "Not available"
        provider_label = html.escape(str(config.get("provider_name") or provider.title()))
        model_label = html.escape(str(model or "No model selected"))
        thinking_label = html.escape(thinking)
        thinking_color = "#00d4ff" if thinking_available else "#ff5252"
        self._header_info = (
            f"<span style='color:#c1c1ce'>Provider:</span> <span style='color:#00d4ff'>{provider_label}</span><br>"
            f"<span style='color:#c1c1ce'>Model:</span> <span style='color:#00d4ff'>{model_label}</span><br>"
            f"<span style='color:#c1c1ce'>Thinking:</span> "
            f"<span style='color:{thinking_color}'>{thinking_label}</span>"
        )
        if not config["has_credentials"] and self._job_started_at is None:
            self._request_status = "Credentials needed"
        elif config["has_credentials"] and self._request_status == "Credentials needed":
            self._request_status = "Ready"
        self._update_elapsed_display()
        self.lbl_usage_summary.setToolTip(
            f"Request pacing: {config['request_pacing'].upper()}. "
            "Provider, model, and thinking level come from the active API settings."
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
            activity = self._request_status
            elapsed_text = self._format_elapsed(elapsed)
            if hasattr(self, "translator_page"):
                self.translator_page.update_inference_elapsed(elapsed_text)
        elif self._last_job_duration is not None:
            activity = f"{self._request_status} · {self._format_elapsed(self._last_job_duration)}"
        else:
            activity = self._request_status
        activity_color = "#ff5252"
        activity_lower = activity.lower()
        if any(word in activity_lower for word in ("ready", "complete", "success")):
            activity_color = "#00e676"
        elif any(word in activity_lower for word in ("working", "waiting", "stopping")):
            activity_color = "#00d4ff"
        self.lbl_usage_summary.setText(
            f"{self._header_info}<br>"
            f"<span style='color:{activity_color}'>Status: {html.escape(activity)}</span>"
        )

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
