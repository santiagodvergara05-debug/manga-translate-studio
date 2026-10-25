import os
import re
import cv2
import time
import numpy as np
from enum import Enum, auto

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QFrame, QSplitter, QFileDialog,
    QMessageBox, QGraphicsView, QProgressBar, QCheckBox
)
from PySide6.QtCore import Qt, QTimer, QThread
from PySide6.QtGui import QCloseEvent

from src.frontend.widgets import FileListWidget, HardwareMonitor
from src.frontend.canvas import MangaCanvas
from src.frontend.help_system import HelpSystem
from src.utils.system_info import SystemMonitor
from src.utils.config import Config
from src.utils.logger import logger
from src.backend.translator import TranslatorPanel, TranslationScriptEngine
from src.backend.ai_client import MultimodalTranslationWorker
from src.backend.providers.base_provider import ProviderStatus, TranslationResult
from src.frontend.project_reset import ProjectResetController

# Minimum interval between request starts to respect API rate limits (Gemini: 15 RPM = 4s + margin)
MIN_INTERVAL = {"gemini": 4.5, "ollama": 0.5}


# /////////////////////////////////#
#          PAGE STATE ENUM         #
# /////////////////////////////////#
class PageState(Enum):
    UNMODIFIED = auto()
    MODIFIED = auto()
    WAITING = auto()
    READY = auto()
    EMPTY = auto()
    SAFETY = auto()
    BUSY = auto()
    ERROR = auto()


# /////////////////////////////////#
#     STUDIO MAIN CONTROLLER       #
# /////////////////////////////////#

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{Config.APP_NAME} v{Config.VERSION} - Script Generator")
        self.resize(1420, 860)

        self.monitor = SystemMonitor()
        
        # Batch Processing Management (AI Inference Queue)
        self.worker_thread = None
        self.worker = None
        self.is_batching = False
        self.is_paused = False
        self.batch_queue = []
        self.total_batch_tasks = 0
        self.completed_batch_tasks = 0
        self.failed_batch_tasks = []      # List of tuples: (filename, error_msg, full_path)
        
        # Execution flow & cadence control
        self.stop_requested = False
        self.stop_reason = None           # None | "user" | "quota"
        self._last_request_ts = 0.0

        # Viewport navigation state
        self.is_space_moving = False

        # Image sessions & persistent state maps
        self.current_img_path = None
        self.image_sessions = {}
        self.page_states = {}

        self.init_ui()

        # Telemetry refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_telemetry)
        self.timer.start(2000)
        logger.info("--- MANGA TRANSLATE STUDIO INTERFACE READY ---")

    def init_ui(self):
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
        self.nav.setFixedHeight(55)
        nav_lay = QHBoxLayout(self.nav)

        title = QLabel(f"{Config.APP_NAME.upper()} {Config.VERSION}")
        title.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-weight: bold; font-size: 17px;")

        self.btn_reset = QPushButton("RESET")
        self.btn_reset.setObjectName("ActionBtn")
        self.btn_reset.setToolTip("Close current project and purge application memory")
        self.btn_reset.setFixedSize(65, 30)
        self.btn_reset.clicked.connect(self.on_project_reset_requested)

        self.hw_mon = HardwareMonitor()

        btn_help = QPushButton("HELP")
        btn_help.setFixedSize(50, 30)
        btn_help.clicked.connect(lambda: HelpSystem.show_guide(self))

        self.btn_open = QPushButton("IMPORT FOLDER")
        self.btn_open.setFixedHeight(30)
        self.btn_open.clicked.connect(self.on_open_folder)

        nav_lay.addWidget(title)
        nav_lay.addStretch()
        nav_lay.addWidget(self.hw_mon)
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
        Completely disables/enables navigation, import, and reset controls
        to prevent race conditions and unintended project mutation during execution.
        """
        self.btn_open.setEnabled(not locked)
        self.btn_reset.setEnabled(not locked)
        self.btn_save_all_txt.setEnabled(not locked)
        self.chk_all.setEnabled(not locked)
        self.translator_page.set_locked(locked)

    def on_project_reset_requested(self):
        """Prevents project wipe when inference processes are running."""
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
        if not self.is_batching:
            self.on_start_batch_translate()
        else:
            # Toggle Pause / Resume state
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
        """Fully terminates batch queue execution immediately."""
        if not self.is_batching:
            return

        self.stop_requested = True
        self.stop_reason = "user"
        self.is_paused = False
        self.btn_cancel_batch.setEnabled(False)
        self.btn_batch.setEnabled(False)
        self.btn_batch.setText("⏳ Stopping...")

        # If a worker thread is running, abort cleanly
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait(1500)
            self.worker_thread = None

        self.finalize_batch_translate()

    def on_start_batch_translate(self):
        if self.file_list.count() == 0:
            return

        provider = self.translator_page.provider_combo.currentText().lower()
        if provider == "gemini" and not self.translator_page.gemini_key:
            QMessageBox.warning(self, "API Key Required", "Please enter your Gemini API Key in the right panel.")
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
        self.total_batch_tasks = len(paths)
        self.completed_batch_tasks = 0
        self.failed_batch_tasks.clear()
        self.is_batching = True
        self.is_paused = False
        self.stop_requested = False
        self.stop_reason = None
        self._last_request_ts = 0.0

        # Lock entire UI for configuration safety
        self.set_batch_ui_locked(True)

        self.progress_bar.setRange(0, self.total_batch_tasks)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        self.btn_batch.setText("⏸ PAUSE BATCH")
        self.btn_batch.setEnabled(True)
        self.btn_cancel_batch.setEnabled(True)

        self.step_batch_translate()

    def _next_delay_ms(self) -> int:
        provider = self.translator_page.provider_combo.currentText().lower()
        wait = MIN_INTERVAL.get(provider, 1.0) - (time.monotonic() - self._last_request_ts)
        return int(max(0.3, wait) * 1000)

    def _schedule_next(self):
        if self.stop_requested or not self.batch_queue:
            self.finalize_batch_translate()
        elif not self.is_paused:
            QTimer.singleShot(self._next_delay_ms(), self.step_batch_translate)

    def step_batch_translate(self):
        if self.stop_requested or not self.batch_queue:
            self.finalize_batch_translate()
            return

        if self.is_paused:
            return

        target_path = self.batch_queue.pop(0)

        # Synchronize visual selection in viewer
        for i in range(self.file_list.count()):
            it = self.file_list.item(i)
            if it.data(Qt.UserRole) == target_path:
                self.on_file_clicked(it)
                break

        self.page_states[target_path] = PageState.WAITING
        self.file_list.update_item_state(target_path, "waiting", "Translating in progress...")

        provider = self.translator_page.provider_combo.currentText().lower()
        selected_model = self.translator_page.model_combo.currentText().strip()
        is_ollama = (provider == "ollama")

        if is_ollama:
            ollama_url = "http://localhost:11434" if self.translator_page.chk_lan_mode.isChecked() else self.translator_page.ollama_url
            ollama_token = "" if self.translator_page.chk_lan_mode.isChecked() else self.translator_page.ollama_token
            gemini_key = ""
            if not selected_model:
                selected_model = "gemma4:31b-cloud"
        else:
            gemini_key = self.translator_page.gemini_key
            ollama_url = ""
            ollama_token = ""
            if not selected_model:
                selected_model = "gemini-3.1-flash-lite"

        # Inject continuity context from previous page if applicable
        if hasattr(self.translator_page, "build_prompt_for"):
            full_prompt = self.translator_page.build_prompt_for(target_path)
        else:
            full_prompt = self.translator_page.get_full_prompt()

        self._last_request_ts = time.monotonic()

        self.worker_thread = QThread()
        self.worker = MultimodalTranslationWorker(
            image_path=target_path,
            full_prompt=full_prompt,
            provider=provider,
            model_name=selected_model,
            api_key=gemini_key,
            ollama_url=ollama_url,
            ollama_token=ollama_token
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_batch_page_finished)
        self.worker.error.connect(self.on_batch_page_error)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def on_batch_page_finished(self, path: str, result: TranslationResult):
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None

        self.completed_batch_tasks += 1
        self.progress_bar.setValue(self.completed_batch_tasks)

        status = result.status
        fname = os.path.basename(path)

        if status == ProviderStatus.SUCCESS:
            self.page_states[path] = PageState.READY
            self.file_list.update_item_state(path, "ready", f"Translated ({len(result.bubbles)} dialogues)")
            self.translator_page.page_bubbles_data[path] = result.bubbles
            self.translator_page.path_dialogues_map[path] = [b.get("direct") for b in result.bubbles if b.get("direct")]

        elif status == ProviderStatus.EMPTY:
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

        if path == self.current_img_path:
            self.translator_page.populate_bubble_editor(result.bubbles)

        self._schedule_next()

    def on_batch_page_error(self, path: str, error_msg: str):
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
            logger.warning(f"[BATCH QUOTA] Daily quota exhausted on {os.path.basename(path)}. Halting batch.")
            self._schedule_next()
            return

        self.completed_batch_tasks += 1
        self.progress_bar.setValue(self.completed_batch_tasks)

        fname = os.path.basename(path)
        self.page_states[path] = PageState.ERROR
        self.file_list.update_item_state(path, "error", error_msg[:60])
        self.failed_batch_tasks.append((fname, error_msg[:60], path))

        logger.error(f"[BATCH ERROR] on {path}: {error_msg}")
        self._schedule_next()

    def finalize_batch_translate(self):
        self.is_batching = False
        self.is_paused = False
        self.progress_bar.setVisible(False)
        self.btn_batch.setEnabled(True)
        self.btn_batch.setText("▶ RUN BATCH TRANSLATE")
        self.btn_cancel_batch.setEnabled(False)

        # Unlock UI controls completely
        self.set_batch_ui_locked(False)

        pending = list(self.batch_queue)
        self.batch_queue.clear()
        successful_count = self.completed_batch_tasks - len(self.failed_batch_tasks)

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
                self.file_list.update_item_state(p, "modified", "Written into translation script")

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
        p = QFileDialog.getExistingDirectory(self, "Select Folder")
        if p:
            self.image_sessions.clear()
            self.page_states.clear()
            self.file_list.clear()
            self.translator_page.page_bubbles_data.clear()
            self.translator_page.path_dialogues_map.clear()
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
        if self.current_img_path:
            if self.page_states.get(self.current_img_path) != PageState.MODIFIED:
                self.page_states[self.current_img_path] = PageState.MODIFIED
                self.file_list.update_item_state(self.current_img_path, "modified", "Locally modified")

    def on_file_clicked(self, it):
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

        self.translator_page.load_page_state(path_real)

    def toggle_all_files(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(state)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.is_space_moving = True
            self.canvas.setDragMode(QGraphicsView.ScrollHandDrag)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.is_space_moving = False
            self.canvas.setDragMode(QGraphicsView.NoDrag)
        super().keyReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent):
        if self.is_batching:
            self.stop_requested = True
            self.batch_queue.clear()
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker_thread.quit()
                self.worker_thread.wait(2000)
        super().closeEvent(event)

    def update_telemetry(self):
        ram, _ = self.monitor.get_stats()
        self.hw_mon.lbl.setText(f"RAM: {ram}MB")
        self.hw_mon.bar.setValue(min(ram // 40, 100))