"""
In-memory project reset controller for Manga Translate Studio.

Clears translation queues, session dialogues, cached rasters, and visual layers 
while preserving user preferences and configured API credentials.
"""

from __future__ import annotations

import ctypes
import gc
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from src.utils.logger import logger


class ProjectResetController:
    """Manages workspace cleanup and dynamic RAM deallocation without closing the application."""

    @staticmethod
    def reset(main_window) -> bool:
        """
        Purges active project assets, memory sessions, and viewport items.

        Args:
            main_window (MainWindow): The parent studio main window instance.

        Returns:
            bool: True if project was successfully reset, False if aborted or redundant.
        """
        mw = main_window

        translator = getattr(mw, "translator_page", None)
        workers = (
            getattr(mw, "worker_thread", None),
            getattr(translator, "active_worker", None),
        )
        worker_active = False
        for worker in workers:
            if worker is None:
                continue
            try:
                worker_active = worker_active or worker.isRunning()
            except RuntimeError:
                # Qt may delete a finished QThread while Python still has a stale
                # wrapper reference. Ignore that stale reference only.
                continue

        # Do not clear objects still in use by an inference worker.
        if (
            worker_active
            or getattr(mw, "is_batching", False)
            or getattr(mw, "_job_started_at", None) is not None
        ):
            QMessageBox.warning(
                mw,
                "Studio Busy",
                "Cannot reset workspace while translation or batch processing is active.\n\n"
                "Please wait for the process to complete or abort the batch before resetting.",
            )
            return False

        canvas = getattr(mw, "canvas", None)

        has_project_data = bool(
            (hasattr(mw, "file_list") and mw.file_list.count() > 0)
            or getattr(mw, "current_img_path", None)
            or getattr(mw, "image_sessions", {})
            or (translator and getattr(translator, "loaded_script_path", None))
            or (translator and getattr(translator, "path_dialogues_map", {}))
            or (translator and getattr(translator, "page_bubbles_data", {}))
            or getattr(mw, "_request_status", "Ready") != "Ready"
            or getattr(mw, "_last_job_duration", None) is not None
            or (translator and getattr(translator, "lbl_api_status", None)
                and translator.lbl_api_status.isVisible())
        )

        has_canvas_img = bool(canvas is not None and getattr(canvas, "cv_img", None) is not None)

        if not has_project_data and not has_canvas_img:
            return False

        answer = QMessageBox.question(
            mw,
            "Reset Project",
            "Do you want to purge the current project from memory?\n\n"
            "Loaded pages, active translation sessions, and queues will be cleared. "
            "Files on disk and your configured API credentials will remain intact.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return False

        # Decouple active path before resetting UI to avoid signal recursion
        mw.current_img_path = None

        # Stop the batch/request timer before hiding the translator status;
        # otherwise a later timer tick can make the stale status visible again.
        elapsed_timer = getattr(mw, "elapsed_timer", None)
        if elapsed_timer is not None:
            elapsed_timer.stop()
        mw._job_started_at = None
        mw._last_job_duration = None
        mw._request_status = "Ready"
        mw._active_batch_path = None

        # Clear internal image sessions and queue tracking collections
        if hasattr(mw, "image_sessions"):
            mw.image_sessions.clear()
        if hasattr(mw, "page_states"):
            mw.page_states.clear()
        if hasattr(mw, "batch_queue"):
            mw.batch_queue.clear()
        if hasattr(mw, "failed_batch_tasks"):
            mw.failed_batch_tasks.clear()

        mw.is_batching = False
        mw.is_paused = False
        mw.total_batch_tasks = 0
        mw.completed_batch_tasks = 0
        mw.stop_requested = False
        mw.stop_reason = None

        # Reset asset file list and select-all toggle
        if hasattr(mw, "chk_all"):
            mw.chk_all.blockSignals(True)
            mw.chk_all.setChecked(False)
            mw.chk_all.blockSignals(False)

        if hasattr(mw, "file_list"):
            mw.file_list.clear()

        # Reset graphics canvas and viewport transformation
        if canvas is not None:
            canvas.blockSignals(True)
            try:
                if hasattr(canvas, "set_image"):
                    canvas.set_image(None)
                if hasattr(canvas, "scene") and canvas.scene is not None:
                    canvas.scene.clearSelection()
                canvas.resetTransform()
                if hasattr(canvas, "set_locked"):
                    canvas.set_locked(False)
            finally:
                canvas.blockSignals(False)

        # Release worker references if lingering
        mw.worker = None
        mw.worker_thread = None

        # Reset translation workspace data and dialogue cards
        if translator is not None:
            translator.loaded_script_path = None
            translator.active_worker = None
            translator.path_dialogues_map.clear()
            translator.page_bubbles_data.clear()
            if hasattr(translator, "page_language_pairs"):
                translator.page_language_pairs.clear()
            if hasattr(translator, "pending_language_pairs"):
                translator.pending_language_pairs.clear()
            if hasattr(translator, "page_token_usage"):
                translator.page_token_usage.clear()

            if hasattr(translator, "lbl_script_status"):
                translator.lbl_script_status.setText("Script: None")

            if hasattr(translator, "populate_bubble_editor"):
                translator.populate_bubble_editor([])

            # Synchronize two-tier script hierarchy combo boxes
            if hasattr(translator, "refresh_series_folders"):
                translator.refresh_series_folders()

            if hasattr(translator, "lbl_api_status"):
                translator.lbl_api_status.clear()
                translator.lbl_api_status.setVisible(False)
            if hasattr(translator, "_inference_progress"):
                translator._inference_progress = ""

            if hasattr(translator, "set_locked"):
                translator.set_locked(False)
            if hasattr(translator, "set_page_audit_blocked"):
                translator.set_page_audit_blocked(False)

            if hasattr(translator, "update_token_estimate"):
                translator.update_token_estimate()

        # Reset batch action buttons and progress indicator
        if hasattr(mw, "progress_bar"):
            mw.progress_bar.setValue(0)
            mw.progress_bar.setVisible(False)

        if hasattr(mw, "btn_batch"):
            mw.btn_batch.setText("▶ RUN BATCH TRANSLATE")
            mw.btn_batch.setEnabled(True)

        if hasattr(mw, "btn_cancel_batch"):
            mw.btn_cancel_batch.setEnabled(False)

        mw.setCursor(Qt.ArrowCursor)

        # Force immediate garbage collection and platform heap trimming
        gc.collect()
        ProjectResetController._trim_linux_heap()

        try:
            mw.refresh_usage_summary()
            if hasattr(mw, "_update_elapsed_display"):
                mw._update_elapsed_display()
        except Exception as exc:
            logger.debug(f"[RESET] Usage summary refresh skipped: {exc}")

        logger.info("[STUDIO] Project reset completed; memory reclaimed successfully.")
        QMessageBox.information(
            mw,
            "Project Reset",
            "The studio workspace has been cleared and is ready to load a new project folder.",
        )
        return True

    @staticmethod
    def _trim_linux_heap() -> None:
        """Reclaims unmapped dynamic heap memory on Linux glibc runtimes."""
        if not sys.platform.startswith("linux"):
            return
        try:
            libc = ctypes.CDLL("libc.so.6")
            trim = getattr(libc, "malloc_trim", None)
            if trim is not None:
                trim.argtypes = [ctypes.c_size_t]
                trim.restype = ctypes.c_int
                trim(0)
        except (OSError, AttributeError):
            pass
