"""
Centralised logging configuration for the application.

Usage in any module:
    from app.logger import get_logger
    logger = get_logger(__name__)

Log level is controlled by the LOG_LEVEL environment variable (default: INFO).
Logs are written to both the console and logs/app.log (rotating, 10 MB / 5 files).
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_DIR = Path("logs")
_LOG_FILE = _LOG_DIR / "app.log"
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _setup() -> None:
    _LOG_DIR.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(_LOG_LEVEL)

    if root.handlers:
        return

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


_setup()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
