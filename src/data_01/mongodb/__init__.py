#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MongoDB 서브모듈

임포트 예시:
    from mongodb.operations.symbol_manager import SymbolManager
    from mongodb.operations.settings_manager import SettingsManager
    from mongodb.core import get_db
    from mongodb.core.handler import DBHandler
    from mongodb.init_mongodb import init_mongodb, save_symbols_to_mongodb
"""
from .core import MongoConfig, get_config, get_db, create_connection, close_connection
from .models import SymbolMetadata, PrioritySettings, UserFavorite, ExchangeConfig
from .operations import SymbolManager, SettingsManager
from .init_mongodb import init_mongodb, save_symbols_to_mongodb

try:
    from .core.handler import DBHandler
except Exception:
    pass

try:
    from .core.lite_storage import LiteStorage
except Exception:
    pass

__all__ = [
    "MongoConfig", "get_config", "get_db", "create_connection", "close_connection",
    "SymbolMetadata", "PrioritySettings", "UserFavorite", "ExchangeConfig",
    "SymbolManager", "SettingsManager",
    "DBHandler",
    "LiteStorage",
    "init_mongodb",
    "save_symbols_to_mongodb",
]

