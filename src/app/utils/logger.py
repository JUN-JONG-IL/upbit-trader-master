# -*- coding: utf-8 -*-
"""
앱 공통 로거
"""
from __future__ import annotations
import logging
import sys
from typing import Optional


def get_logger(name: str = "upbit_trader", level: int = logging.INFO) -> logging.Logger:
    """공통 로거를 반환한다.

    Parameters
    ----------
    name:  로거 이름 (기본값 ``"upbit_trader"``)
    level: 로깅 레벨 (기본값 ``logging.INFO``)

    Returns
    -------
    logging.Logger
        이미 핸들러가 설정된 경우 기존 로거를 그대로 반환하고,
        그렇지 않은 경우 stdout 스트림 핸들러를 붙여 반환한다.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger
