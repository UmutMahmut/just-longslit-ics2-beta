"""Persistent bounded diagnostic logs, including requests and SDK faults."""
from pathlib import Path
from logging.handlers import RotatingFileHandler
import logging
import os
import time


def configure_logging() -> Path:
    directory = Path(os.environ.get("ICS_BETA_LOG_ROOT", "var/logs")).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "ics-beta.log"
    logger = logging.getLogger("justls.ics")
    logger.setLevel(logging.INFO)
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and handler.baseFilename == str(target):
            return target
    handler = RotatingFileHandler(target, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(name)s %(message)s")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info("Diagnostic log initialized: %s", target)
    return target
