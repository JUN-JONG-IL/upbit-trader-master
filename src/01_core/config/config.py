#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Config helper for upbit-trader (safe defaults + headless friendly)

This version:
- Provides common logging-related defaults so static.py and other modules
  can read config.log_format, config.log_save, config.log_path, etc.
- Exposes to_dict/from_dict/load/save as before.
- Implements __getattr__ to return None for unknown attributes (safe fallback).
"""
from __future__ import annotations

import os
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Try to import QSettings; fall back to qt_stub.QtCore if available
try:
    from PyQt5.QtCore import QSettings  # type: ignore
    _HAS_QT_SETTINGS = True
except Exception:
    _HAS_QT_SETTINGS = False
    try:
        from utils.qt_stub import QtCore as _QtCore  # type: ignore
        class QSettings:
            def __init__(self, *args, **kwargs):
                self._store = {}
            def value(self, key, default=None):
                return self._store.get(key, default)
            def setValue(self, key, value):
                self._store[key] = value
    except Exception:
        class QSettings:
            def __init__(self, *args, **kwargs):
                self._store = {}
            def value(self, key, default=None):
                return self._store.get(key, default)
            def setValue(self, key, value):
                self._store[key] = value


def find_config_path(provided: Optional[str] = None) -> Path:
    if provided:
        p = Path(provided).expanduser()
        if p.exists():
            return p
    candidates = [
        Path.cwd() / "config.yaml",
        Path.cwd() / "config.yml",
        Path.cwd() / "src" / "config.yaml",
        Path.cwd() / "src" / "config.yml",
        Path(__file__).resolve().parent / "config.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path.cwd() / "config.yaml"


class Config:
    """
    Application configuration container with safe defaults for logging and I/O.
    """

    def __init__(self) -> None:
        # API / DB defaults
        self.upbit_access_key: str = ""
        self.upbit_secret_key: str = ""
        self.mongo_ip: str = "localhost"
        self.mongo_port: int = 27017
        self.mongo_id: Optional[str] = None
        self.mongo_password: Optional[str] = None
        self.redis_host: str = "localhost"
        self.redis_port: int = 58530
        self.timescale_port: int = 58529
        self.sql_connection: str = "sqlite:///trade.db"
        self.max_individual_trade_price: float = 10000.0

        # Logging defaults (static.py expects these)
        self.log_level: str = "DEBUG"
        # format string used by logging configuration
        self.log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        # whether to persist logs to file (True/False)
        self.log_save: bool = True
        # default log file path/name
        self.log_path: str = "upbit-trader.log"
        # whether to also output to console
        self.log_console: bool = True
        # other optional logging flags
        self.log_rotate: bool = False
        self.log_max_bytes: int = 10 * 1024 * 1024
        self.log_backup_count: int = 5

        # GUI mode flag (True = show login window and main UI, False = headless/background only)
        self.gui: bool = True

        # Internal
        self.config_path: Optional[Path] = None
        self._qsettings: Optional[QSettings] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "upbit_access_key": self.upbit_access_key,
            "upbit_secret_key": self.upbit_secret_key,
            "mongo_ip": self.mongo_ip,
            "mongo_port": self.mongo_port,
            "mongo_id": self.mongo_id,
            "mongo_password": self.mongo_password,
            "redis_host": self.redis_host,
            "redis_port": self.redis_port,
            "sql_connection": self.sql_connection,
            "max_individual_trade_price": self.max_individual_trade_price,
            "log_level": self.log_level,
            "log_format": self.log_format,
            "log_save": self.log_save,
            "log_path": self.log_path,
            "log_console": self.log_console,
            "log_rotate": self.log_rotate,
            "log_max_bytes": self.log_max_bytes,
            "log_backup_count": self.log_backup_count,
            "gui": self.gui,
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        for k, v in data.items():
            if hasattr(self, k):
                try:
                    setattr(self, k, v)
                except Exception:
                    logger.exception("Failed to set config attribute %s", k)

    def load(self, path: Optional[str] = None) -> None:
        try:
            cfg_path = find_config_path(path)
            self.config_path = cfg_path
            if cfg_path.exists():
                with cfg_path.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                    if isinstance(data, dict):
                        self.from_dict(data)
                        logger.info("Loaded config from %s", str(cfg_path))
            else:
                logger.info("Config file not found at %s; using defaults", str(cfg_path))
            if _HAS_QT_SETTINGS:
                try:
                    if self._qsettings is None:
                        self._qsettings = QSettings("upbit-trader", "upbit-trader")
                    val = self._qsettings.value("max_individual_trade_price", None)
                    if val is not None:
                        try:
                            self.max_individual_trade_price = float(val)
                        except Exception:
                            pass
                except Exception:
                    logger.exception("QSettings read failed")
        except Exception:
            logger.exception("Failed to load config")

    def save(self, path: Optional[str] = None) -> None:
        try:
            if path:
                cfg_path = Path(path)
            elif self.config_path:
                cfg_path = self.config_path
            else:
                cfg_path = find_config_path(None)
            if not cfg_path.parent.exists():
                try:
                    cfg_path.parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
            with cfg_path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(self.to_dict(), fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
            logger.info("Saved config to %s", str(cfg_path))
            if _HAS_QT_SETTINGS:
                try:
                    if self._qsettings is None:
                        self._qsettings = QSettings("upbit-trader", "upbit-trader")
                    self._qsettings.setValue("max_individual_trade_price", self.max_individual_trade_price)
                except Exception:
                    logger.exception("QSettings write failed")
        except Exception:
            logger.exception("Failed to save config")

    def __getattr__(self, name: str) -> Any:
        """
        Fallback for attributes not explicitly defined.
        Return None to avoid AttributeError during imports; this is safer than
        raising errors when code checks optional config flags.
        """
        return None