"""Local rotating application diagnostics."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from excelclone.util.paths import log_dir


def configure_logging(directory: str | Path | None = None) -> logging.Logger:
    """Configure the application logger without duplicating file handlers."""
    destination = Path(directory) if directory is not None else log_dir()
    destination.mkdir(parents=True, exist_ok=True)
    log_path = (destination / "opengrid.log").resolve()
    logger = logging.getLogger("excelclone")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in tuple(logger.handlers):
        if isinstance(handler, RotatingFileHandler):
            if Path(handler.baseFilename).resolve() == log_path:
                return logger
            logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger
