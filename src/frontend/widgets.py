"""
Reusable interface widgets, file navigation list, and dynamic SVG icon provider.

Loads application icons directly from the assets/ directory with fallback handling,
and provides telemetry and asset list management.
"""

import os
from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QHBoxLayout, 
    QLabel, QProgressBar
)
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt, QSize
from src.utils.paths import Paths
from src.utils.logger import logger

# Mapping between application state keys and actual filenames inside assets/
ASSET_ICON_MAP = {
    "unmodified": "icon_unassigned_1.svg",
    "waiting": "icon_busy.svg",
    "ready": "icon_ready.svg",
    "empty": "icon_empty.svg",
    "busy": "icon_busy.svg",
    "safety": "icon_safety.svg",
    "modified": "icon_modified.svg",
    "error": "icon_error.svg",
    "lock": "icon_lock.svg"
}


class IconProvider:
    """
    Loads, renders, and caches vector icons from the assets/ directory.
    Uses QSvgRenderer to produce crisp antialiased pixmaps at any requested size.
    """
    _cache: dict[tuple[str, int], QIcon] = {}

    @classmethod
    def get(cls, state_key: str, size: int = 18) -> QIcon:
        """
        Retrieves a cached QIcon for the given state key and pixel size.

        Args:
            state_key (str): State identifier (e.g., 'ready', 'unmodified', 'error').
            size (int): Target bounding square dimension in pixels.

        Returns:
            QIcon: Rendered icon instance.
        """
        clean_key = state_key.lower().strip()
        cache_lookup = (clean_key, size)
        
        if cache_lookup in cls._cache:
            return cls._cache[cache_lookup]

        filename = ASSET_ICON_MAP.get(clean_key, "icon_unassigned_1.svg")
        icon_path = os.path.join(Paths.BUNDLE_DIR, "assets", filename)

        if os.path.exists(icon_path):
            renderer = QSvgRenderer(icon_path)
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            renderer.render(painter)
            painter.end()

            icon = QIcon(pixmap)
        else:
            logger.warning(f"[ICON_PROVIDER] Vector asset not found: {icon_path}")
            icon = QIcon()

        cls._cache[cache_lookup] = icon
        return icon


# ==============================================================================
# PROJECT ASSET LIST WIDGET
# ==============================================================================
class FileListWidget(QListWidget):
    """
    Project assets explorer displaying image queues, processing status icons,
    and user check boxes for selective batch processing.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QListWidget {
                background-color: #121218;
                border: 1px solid #1e1e28;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 4px 6px;
                border-bottom: 1px solid #181822;
            }
            QListWidget::item:hover {
                background-color: #1a1a24;
            }
            QListWidget::item:selected {
                background-color: #20202e;
                color: #00d2ff;
                font-weight: bold;
            }
        """)
        self.setIconSize(QSize(16, 16))

    def add_file(self, full_path: str):
        """
        Appends an image file to the asset list with default unmodified state.

        Args:
            full_path (str): Absolute file system path to the image.
        """
        fname = os.path.basename(full_path)
        item = QListWidgetItem(IconProvider.get("unmodified"), fname)
        item.setData(Qt.UserRole, full_path)
        item.setToolTip(f"{fname}\nStatus: Unmodified")
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)
        self.addItem(item)

    def update_item_state(self, full_path: str, state_str: str, tooltip_msg: str = ""):
        """
        Updates the status icon and tooltip metadata for a target image item.

        Args:
            full_path (str): Target image path identifier.
            state_str (str): Canonical state string (e.g. 'ready', 'error', 'waiting').
            tooltip_msg (str, optional): Custom status text for hover tooltip.
        """
        clean_state = state_str.lower().strip()
        icon = IconProvider.get(clean_state)
        fname = os.path.basename(full_path)

        for i in range(self.count()):
            it = self.item(i)
            if it.data(Qt.UserRole) == full_path:
                it.setIcon(icon)
                status_desc = tooltip_msg if tooltip_msg else clean_state.capitalize()
                it.setToolTip(f"{fname}\nStatus: {status_desc}")
                break


# ==============================================================================
# HARDWARE TELEMETRY MONITOR (RAM USAGE)
# ==============================================================================
class HardwareMonitor(QWidget):
    """Compact navbar widget providing real-time process RAM usage telemetry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.lbl = QLabel("RAM: --MB")
        self.lbl.setStyleSheet("color: #888899; font-size: 10px; font-weight: bold;")

        self.bar = QProgressBar()
        self.bar.setFixedSize(65, 8)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #2a2a35;
                border-radius: 4px;
                background-color: #14141c;
            }
            QProgressBar::chunk {
                background-color: #00d2ff;
                border-radius: 3px;
            }
        """)

        lay.addWidget(self.lbl)
        lay.addWidget(self.bar)