"""
Optimized interactive graphics viewport for comic page inspection and navigation.

Provides hardware-accelerated panning, mouse-wheel zooming with boundary clamping,
middle-click zoom resets, and responsive overlay indicators.
"""

import os

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QLabel
from PySide6.QtGui import QPixmap, QImage, QPainter, QBrush, QColor, QIcon
from PySide6.QtCore import Qt
from src.utils.paths import Paths


class MangaCanvas(QGraphicsView):
    """Interactive viewport widget supporting high-resolution manga and manhwa navigation."""

    MIN_ZOOM = 0.05
    MAX_ZOOM = 25.0

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # Enable smooth scaling and antialiasing for crisp text rendering
        self.setRenderHints(
            QPainter.Antialiasing | 
            QPainter.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        # Neutral dark workspace canvas background
        self.setBackgroundBrush(QBrush(QColor(14, 14, 18)))

        # Container item holding the active raster page
        self.image_item = QGraphicsPixmapItem()
        self.scene.addItem(self.image_item)

        self.cv_img = None
        self.is_locked = False

        # Visual indicator overlay displayed during active background processing
        self.lock_overlay = QLabel(self)
        self.lock_overlay.setFixedSize(48, 48)
        lock_path = os.path.join(Paths.BUNDLE_DIR, "assets", "icon_lock.svg")
        if os.path.exists(lock_path):
            self.lock_overlay.setPixmap(QIcon(lock_path).pixmap(48, 48))
        self.lock_overlay.setStyleSheet("background: transparent;")
        self.lock_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lock_overlay.hide()

        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

    def set_image(self, cv_img):
        """
        Loads an RGB/RGBA image matrix into the canvas and adjusts scene bounding geometry.

        Args:
            cv_img (numpy.ndarray or None): NumPy image buffer formatted in RGB or RGBA.
        """
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

        # Use an explicit copy to guarantee memory stability across Qt threads
        self.image_item.setPixmap(QPixmap.fromImage(q_img.copy()))
        self.scene.setSceneRect(0, 0, w, h)

    def set_locked(self, locked: bool):
        """
        Toggles viewport interaction lock and visibility of the lock overlay indicator.

        Args:
            locked (bool): True to lock viewport navigation, False to restore interaction.
        """
        self.is_locked = locked
        if locked:
            self.lock_overlay.show()
            self.viewport().unsetCursor()
        else:
            self.lock_overlay.hide()
            self.viewport().setCursor(Qt.OpenHandCursor)

    def resizeEvent(self, event):
        """Maintains the lock indicator positioned at the top-right corner on viewport resize."""
        super().resizeEvent(event)
        self.lock_overlay.move(self.width() - self.lock_overlay.width() - 20, 20)

    def wheelEvent(self, event):
        """
        Handles smooth incremental zooming centered under the cursor with boundary clamping.
        """
        if self.is_locked:
            event.ignore()
            return

        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta == 0:
            return

        factor = 1.18 if delta > 0 else 0.85
        current_scale = self.transform().m11()

        # Enforce minimum and maximum zoom boundaries
        if factor < 1.0 and current_scale * factor < self.MIN_ZOOM:
            return
        if factor > 1.0 and current_scale * factor > self.MAX_ZOOM:
            return

        self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):
        """
        Catches middle-click to reset viewport scale to 1:1 original size.
        """
        if event.button() == Qt.MiddleButton and not self.is_locked:
            self.resetTransform()
            event.accept()
            return
        super().mousePressEvent(event)