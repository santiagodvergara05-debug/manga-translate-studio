import os
from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QHBoxLayout, 
    QLabel, QProgressBar, QFrame
)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt, QSize, QByteArray


# ==============================================================================
# SVGs EN CÓDIGO (IDÉNTICOS AL REPOSITORIO DE MANGA CLEANER)
# ==============================================================================
SVG_ICONS = {
    "unmodified": """<svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="18" fill="#32323e" stroke="#1f1f26" stroke-width="4"/>
    </svg>""",

    "waiting": """<svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="#ffd600" stroke="#1a1a20" stroke-width="6"/>
        <path d="M50 22 V50 L68 62" fill="none" stroke="#ffffff" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>""",

    "ready": """<svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="#00e676" stroke="#1a1a20" stroke-width="6"/>
        <path d="M28 52 L44 68 L74 34" fill="none" stroke="#ffffff" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>""",

    "modified": """<svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="#e000d0" stroke="#1a1a20" stroke-width="6"/>
        <polygon points="50,26 74,50 50,74 26,50" fill="#ffffff"/>
    </svg>""",

    "error": """<svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="#ff3d00" stroke="#1a1a20" stroke-width="6"/>
        <path d="M32 32 L68 68 M68 32 L32 68" fill="none" stroke="#ffffff" stroke-width="12" stroke-linecap="round"/>
    </svg>""",

    "lock": """<svg viewBox="0 0 100 100">
        <rect x="20" y="40" width="60" height="48" rx="6" fill="#00d2ff" stroke="#1a1a20" stroke-width="4"/>
        <path d="M32 40 V26 A18 18 0 0 1 68 26 V40" fill="none" stroke="#00d2ff" stroke-width="10" stroke-linecap="round"/>
        <circle cx="50" cy="60" r="6" fill="#ffffff"/>
        <path d="M50 60 V74" stroke="#ffffff" stroke-width="6" stroke-linecap="round"/>
    </svg>"""
}


class IconProvider:
    """Genera y cachea QIcons limpios a partir de los vectores SVG."""
    _cache = {}

    @classmethod
    def get(cls, state_key: str, size: int = 18) -> QIcon:
        key = (state_key, size)
        if key in cls._cache:
            return cls._cache[key]

        svg_str = SVG_ICONS.get(state_key, SVG_ICONS["unmodified"])
        byte_array = QByteArray(svg_str.encode("utf-8"))
        renderer = QSvgRenderer(byte_array)

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.end()

        icon = QIcon(pixmap)
        cls._cache[key] = icon
        return icon


# ==============================================================================
# LISTA DE ARCHIVOS (PROJECT ASSETS)
# ==============================================================================
class FileListWidget(QListWidget):
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
        fname = os.path.basename(full_path)
        item = QListWidgetItem(IconProvider.get("unmodified"), fname)
        item.setData(Qt.UserRole, full_path)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)
        self.addItem(item)

    def update_item_state(self, full_path: str, state_str: str):
        """Actualiza el icono según el estado (waiting, ready, modified, error, lock, unmodified)."""
        clean_state = state_str.lower()
        icon = IconProvider.get(clean_state)

        for i in range(self.count()):
            it = self.item(i)
            if it.data(Qt.UserRole) == full_path:
                it.setIcon(icon)
                break


# ==============================================================================
# MONITOR DE HARDWARE (RAM / TELEMETRÍA)
# ==============================================================================
class HardwareMonitor(QWidget):
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