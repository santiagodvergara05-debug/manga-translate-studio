"""
Diagnostic logging core for Manga Translate Studio.

Configures formatted file and console stream logging with custom status prefixes.
"""

import os
import sys
import logging
from datetime import datetime
from src.utils.paths import Paths


class CustomFormatter(logging.Formatter):
    """Custom logging formatter prefixing lines with diagnostic status indicators."""

    def format(self, record: logging.LogRecord) -> str:
        prefix = "[i]"
        if record.levelno == logging.WARNING:
            prefix = "[!]"
        elif record.levelno >= logging.ERROR:
            prefix = "[X]"
        elif "SUCCESS" in str(record.msg):
            prefix = "[+]"

        original_msg = record.msg
        record.msg = f"{prefix} {original_msg}"
        result = super().format(record)
        record.msg = original_msg
        return result


def setup_logger() -> logging.Logger:
    """
    Initializes daily rotation file logger and standard output stream handler.

    Returns:
        logging.Logger: Configured application logger instance.
    """
    Paths.initialize()
    log_file = os.path.join(Paths.LOGS, f"translate_session_{datetime.now().strftime('%Y%m%d')}.log")

    fmt = CustomFormatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S")

    log = logging.getLogger("MangaTranslate")
    log.setLevel(logging.INFO)
    log.propagate = False
    log.handlers.clear()

    # File log handler (UTF-8 encoding)
    handler_file = logging.FileHandler(log_file, encoding="utf-8")
    handler_file.setFormatter(fmt)
    log.addHandler(handler_file)

    # Console stream handler (guarded against missing console handles in windowed executables)
    if sys.stdout is not None and hasattr(sys.stdout, "write"):
        try:
            handler_stream = logging.StreamHandler(sys.stdout)
            handler_stream.setFormatter(fmt)
            log.addHandler(handler_stream)
        except Exception:
            pass

    return log


logger = setup_logger()