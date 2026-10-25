"""In-memory project reset controller for Manga Translate Studio.

Place this module at: src/frontend/project_reset.py
Clears translation queues, loaded script data, and visual layers while preserving preferences.
"""

from __future__ import annotations

import ctypes
import gc
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QMessageBox

from src.utils.logger import logger


class ProjectResetController:
    """Limpia la memoria del proyecto actual sin cerrar la ventana principal."""

    @staticmethod
    def reset(main_window) -> bool:
        mw = main_window

        # Evitar resetear si hay una petición a la API o un lote en curso
        if getattr(mw, "worker_thread", None) is not None or getattr(mw, "is_batching", False):
            QMessageBox.warning(
                mw,
                "Estudio Ocupado",
                "No se puede reiniciar el proyecto mientras haya una traducción o procesamiento por lotes activo.\n\n"
                "Espera a que finalice el proceso o detén la tarea antes de reiniciar.",
            )
            return False

        translator = getattr(mw, "translator_page", None)
        canvas = getattr(mw, "canvas", None)

        has_project_data = bool(
            (hasattr(mw, "file_list") and mw.file_list.count() > 0)
            or getattr(mw, "current_img_path", None)
            or getattr(mw, "image_sessions", {})
            or (translator and getattr(translator, "loaded_script_path", None))
            or (translator and getattr(translator, "path_dialogues_map", {}))
            or (translator and getattr(translator, "page_bubbles_data", {}))
        )

        has_canvas_img = bool(canvas is not None and getattr(canvas, "cv_img", None) is not None)

        if not has_project_data and not has_canvas_img:
            return False

        answer = QMessageBox.question(
            mw,
            "Reiniciar Proyecto",
            "¿Deseas vaciar el proyecto actual de la memoria?\n\n"
            "Se eliminarán las páginas cargadas, las traducciones en sesión y las colas activas. "
            "Los archivos en disco y tus credenciales de API se conservarán intactos.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return False

        # Desvincular ruta activa antes de limpiar la UI para evitar reentradas de señales
        mw.current_img_path = None

        # Limpiar estados internos de imágenes y colas
        if hasattr(mw, "image_sessions"):
            mw.image_sessions.clear()
        if hasattr(mw, "page_states"):
            mw.page_states.clear()
        if hasattr(mw, "batch_queue"):
            mw.batch_queue.clear()
        if hasattr(mw, "failed_batch_tasks"):
            mw.failed_batch_tasks.clear()

        mw.is_batching = False
        mw.total_batch_tasks = 0
        mw.completed_batch_tasks = 0
        mw.stop_requested = False
        mw.stop_reason = None

        # Limpiar lista visual de archivos
        if hasattr(mw, "chk_all"):
            mw.chk_all.blockSignals(True)
            mw.chk_all.setChecked(False)
            mw.chk_all.blockSignals(False)

        if hasattr(mw, "file_list"):
            mw.file_list.clear()

        # Limpiar lienzo gráfico
        if canvas is not None:
            canvas.blockSignals(True)
            try:
                canvas.cv_img = None
                if hasattr(canvas, "image_item") and canvas.image_item is not None:
                    canvas.image_item.setPixmap(QPixmap())
                if hasattr(canvas, "scene") and canvas.scene is not None:
                    canvas.scene.clearSelection()
                    canvas.scene.setSceneRect(0, 0, 0, 0)
                canvas.resetTransform()
                if hasattr(canvas, "set_locked"):
                    canvas.set_locked(False)
            finally:
                canvas.blockSignals(False)

        # Liberar worker si quedó referenciado
        mw.worker = None
        mw.worker_thread = None

        # Limpiar datos específicos del panel de traducción
        if translator is not None:
            translator.loaded_script_path = None
            translator.path_dialogues_map.clear()
            translator.page_bubbles_data.clear()

            if hasattr(translator, "lbl_script_status"):
                translator.lbl_script_status.setText("Script: None")

            if hasattr(translator, "populate_bubble_editor"):
                translator.populate_bubble_editor([])

            if hasattr(translator, "refresh_translations_scripts_list"):
                translator.refresh_translations_scripts_list()

            if hasattr(translator, "lbl_api_status"):
                translator.lbl_api_status.setVisible(False)

        # Restablecer barra de progreso y botones
        if hasattr(mw, "progress_bar"):
            mw.progress_bar.setValue(0)
            mw.progress_bar.setVisible(False)

        if hasattr(mw, "btn_batch"):
            mw.btn_batch.setText("▶ RUN BATCH TRANSLATE")
            mw.btn_batch.setEnabled(True)

        mw.setCursor(Qt.ArrowCursor)

        # Liberación forzada de memoria RAM
        gc.collect()
        ProjectResetController._trim_linux_heap()

        try:
            mw.update_telemetry()
        except Exception as exc:
            logger.debug(f"[RESET] Telemetría omitida: {exc}")

        logger.info("[STUDIO] Reinicio de proyecto completado; memoria liberada con éxito.")
        QMessageBox.information(
            mw,
            "Proyecto Reiniciado",
            "El estudio se ha vaciado por completo y está listo para abrir una nueva carpeta de trabajo.",
        )
        return True

    @staticmethod
    def _trim_linux_heap() -> None:
        """Devuelve memoria libre al SO en sistemas Linux con glibc."""
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