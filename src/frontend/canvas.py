import os
import cv2
import numpy as np

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QLabel
from PySide6.QtGui import QPixmap, QImage, QPainter, QBrush, QColor, QIcon
from PySide6.QtCore import Qt, QRectF
from src.utils.paths import Paths


class MangaCanvas(QGraphicsView):
    """Visor optimizado para navegación e inspección de páginas."""

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.setRenderHints(
            QPainter.Antialiasing | 
            QPainter.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        # Fondo oscuro neutro
        self.setBackgroundBrush(QBrush(QColor(14, 14, 18)))

        # Item contenedor de la imagen activa
        self.image_item = QGraphicsPixmapItem()
        self.scene.addItem(self.image_item)

        self.cv_img = None
        self.is_locked = False

        # Overlay indicador de bloqueo durante cargas
        self.lock_overlay = QLabel(self)
        lock_path = os.path.join(Paths.BUNDLE_DIR, "assets", "icon_lock.svg")
        if os.path.exists(lock_path):
            self.lock_overlay.setPixmap(QIcon(lock_path).pixmap(48, 48))
        self.lock_overlay.setStyleSheet("background: transparent;")
        self.lock_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lock_overlay.hide()

        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

    def set_image(self, cv_img):
        """Carga la imagen en el visor y ajusta el área de la escena."""
        self.cv_img = cv_img
        if cv_img is None:
            self.image_item.setPixmap(QPixmap())
            self.scene.setSceneRect(0, 0, 0, 0)
            return

        h, w = cv_img.shape[:2]
        if len(cv_img.shape) == 3 and cv_img.shape[2] == 4:
            q_img = QImage(cv_img.data, w, h, w * 4, QImage.Format_RGBA8888)
        else:
            q_img = QImage(cv_img.data, w, h, w * 3, QImage.Format_RGB888)

        self.image_item.setPixmap(QPixmap.fromImage(q_img))
        self.scene.setSceneRect(0, 0, w, h)

    def set_locked(self, locked: bool):
        self.is_locked = locked
        if locked:
            self.lock_overlay.show()
            self.viewport().unsetCursor()
        else:
            self.lock_overlay.hide()
            self.viewport().setCursor(Qt.OpenHandCursor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.lock_overlay.move(self.width() - self.lock_overlay.width() - 20, 20)

    def wheelEvent(self, event):
        """Control de zoom suave con la rueda del ratón."""
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta == 0:
            return

        zoom = 1.18 if delta > 0 else 0.85
        self.scale(zoom, zoom)
        event.accept()

    def mousePressEvent(self, event):
        # Clic con botón central reinicia la escala al tamaño original (100%)
        if event.button() == Qt.MiddleButton:
            self.resetTransform()
            event.accept()
            return
        super().mousePressEvent(event)