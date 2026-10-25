import sys
import os
import ctypes
import multiprocessing

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon
from PySide6.QtCore import Qt, qInstallMessageHandler

from src.frontend.main_window import MainWindow
from src.utils.logger import logger
from src.utils.paths import Paths
from src.utils.config import Config


# /////////////////////////////////#
#       QT MESSAGE FILTER          #
# /////////////////////////////////#

def qt_message_handler(mode, context, message):
    """Suppresses harmless Qt warnings and font metric noise."""
    noise_patterns = ["setPointSize", "Point size <= 0", "setPointSizeF"]
    if any(pattern in message for pattern in noise_patterns):
        return
    if "Warning" in str(mode):
        return


# /////////////////////////////////#
#       APPLICATION ENTRY POINT    #
# /////////////////////////////////#

def main():
    # 1. Register explicit AppUserModelID on Windows to decouple taskbar icon from python.exe
    if os.name == "nt":
        app_id = "mangacleaner.mangatranslatestudio"
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass

    # 2. Redirect standard streams when running in windowed/no-console mode
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    # 3. Ensure all project and storage directories exist
    Paths.initialize()

    # 4. Install Qt message filter
    qInstallMessageHandler(qt_message_handler)

    # 5. Initialize QApplication
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))
    app.setApplicationName(Config.APP_NAME)

    logger.info(f"--- {Config.APP_NAME.upper()} STARTUP ---")

    # 6. Load application icon (.ico prioritized, .png fallback)
    icon_ico = os.path.join(Paths.BUNDLE_DIR, "assets", "icon.ico")
    icon_png = os.path.join(Paths.BUNDLE_DIR, "assets", "icon.png")

    app_icon = None
    if os.path.exists(icon_ico):
        app_icon = QIcon(icon_ico)
    elif os.path.exists(icon_png):
        app_icon = QIcon(icon_png)

    if app_icon:
        app.setWindowIcon(app_icon)
    else:
        logger.warning("Application icon not found in assets directory.")

    # 7. Inject visual stylesheet (QSS)
    qss_path = os.path.join(Paths.BUNDLE_DIR, "src", "frontend", "styles.qss")
    if os.path.exists(qss_path):
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
            logger.info("[+] Stylesheet loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load stylesheet: {e}")
    else:
        logger.warning(f"Stylesheet missing at: {qss_path}")

    # 8. Launch main window
    try:
        window = MainWindow()
        if app_icon:
            window.setWindowIcon(app_icon)
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"FATAL SYSTEM CRASH: {e}", exc_info=True)
    finally:
        logger.info(f"--- {Config.APP_NAME.upper()} SHUTDOWN ---")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()