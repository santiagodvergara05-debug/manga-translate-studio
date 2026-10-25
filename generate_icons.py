import os
from PySide6.QtGui import QPixmap, QPainter, QIcon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QByteArray

app = QApplication([])

assets_dir = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(assets_dir, exist_ok=True)
svg_path = os.path.join(assets_dir, "icon.svg")

if os.path.exists(svg_path):
    renderer = QSvgRenderer(svg_path)
    
    # Generar PNG en alta resolución (256x256)
    pix = QPixmap(256, 256)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    
    png_path = os.path.join(assets_dir, "icon.png")
    ico_path = os.path.join(assets_dir, "icon.ico")
    
    pix.save(png_path, "PNG")
    pix.save(ico_path, "ICO")
    print(f"Iconos generados exitosamente en:\n - {png_path}\n - {ico_path}")
else:
    print(f"No se encontró {svg_path}")