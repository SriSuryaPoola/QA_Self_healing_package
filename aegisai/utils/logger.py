"""Logging helpers."""

from __future__ import annotations

import logging


LOGGER_NAME = "aegisai"


def get_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger
