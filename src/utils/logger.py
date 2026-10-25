import os
import sys
import logging
from datetime import datetime
from src.utils.paths import Paths

# /////////////////////////////////#
#     DIAGNOSTIC LOGGING CORE      #
# /////////////////////////////////#

class CustomFormatter(logging.Formatter):
    def format(self, record):
        prefix = "[i]"
        if record.levelno == logging.WARNING:
            prefix = "[!]"
        elif record.levelno >= logging.ERROR:
            prefix = "[X]"
        elif "SUCCESS" in record.msg:
            prefix = "[+]"

        original_msg = record.msg
        record.msg = f"{prefix} {original_msg}"
        result = super().format(record)
        record.msg = original_msg
        return result


def setup_logger():
    Paths.initialize()
    log_file = os.path.join(Paths.LOGS, f"translate_session_{datetime.now().strftime('%Y%m%d')}.log")

    handler_file = logging.FileHandler(log_file, encoding='utf-8')
    fmt = CustomFormatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%H:%M:%S')
    handler_file.setFormatter(fmt)

    log = logging.getLogger("MangaTranslate")
    log.setLevel(logging.INFO)
    log.addHandler(handler_file)

    if sys.stdout is not None:
        try:
            handler_stream = logging.StreamHandler(sys.stdout)
            handler_stream.setFormatter(fmt)
            log.addHandler(handler_stream)
        except Exception:
            pass

    return log


logger = setup_logger()