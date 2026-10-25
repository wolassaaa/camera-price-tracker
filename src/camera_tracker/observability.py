"""Small local-only logging setup for worker diagnostics."""

import logging
from pathlib import Path


def configure_worker_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("camera_tracker")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    resolved = str(log_path.resolve())
    if not any(isinstance(handler, logging.FileHandler) and handler.baseFilename == resolved for handler in logger.handlers):
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    return logger
