#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MongoDB 초기화 모듈

기능:
- metadata 컬렉션 인덱스 생성
- priority_settings 기본값 삽입 (upsert)
- Upbit 심볼 목록을 metadata 컬렉션에 저장

DB설계.md 7.2~7.5절 기반

변경사항:
- 동기 호출자가 즉시 DB 객체를 받을 수 있도록 get_db() 동기 헬퍼 추가
- 모듈 전역 캐시(_GLOBAL_CLIENT/_GLOBAL_DB) 지원
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# motor (async MongoDB) 조건부 임포트
try:
    from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore
    _HAS_MOTOR = True
except Exception:
    AsyncIOMotorClient = None  # type: ignore
    _HAS_MOTOR = False

# 전역 캐시: 반복 연결 방지
_GLOBAL_CLIENT: Optional[Any] = None
_GLOBAL_DB: Optional[Any] = None


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


async def init_mongodb(
    uri: Optional[str] = None,
    db_name: str = "upbit_trader",
) -> Optional[Any]:
    """
    MongoDB 초기 데이터 셋업.

    - metadata 컬렉션 인덱스 생성
    - priority_settings 기본값 삽입 (없으면 생성, 있으면 유지)

    Args:
        uri: MongoDB 연결 URI. 미지정 시 환경변수 또는 localhost 기본값 사용.
        db_name: 데이터베이스 이름 (기본값: "upbit_trader")

    Returns:
        성공 시 Motor 데이터베이스 객체, 실패 시 None.
    """
    global _GLOBAL_CLIENT, _GLOBAL_DB

    if not _HAS_MOTOR:
        logger.warning("[init_mongodb] motor 미설치: pip install motor — MongoDB 초기화 건너뜀")
        return None

    import os

    if uri is None:
        uri = _build_default_uri()

    client = None
    db = None

    # MongoDB 연결 시도 (비동기 ping 포함)
    try:
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
        # 비동기 환경에서 ping 시도
        await client.admin.command("ping")
        db = client[db_name]
        _GLOBAL_CLIENT = client
        _GLOBAL_DB = db
        logger.debug("[init_mongodb] MongoDB 연결 성공: %s", _mask_uri(uri))
    except Exception as e:
        logger.error("[init_mongodb] MongoDB 연결 실패: %s", e)
        return None

    # ── metadata 컬렉션 인덱스 ──────────────────────────────────────────────
    _index_count = 0
    try:
        await db.metadata.create_index(
            [("symbol", 1), ("exchange", 1)], unique=True, name="idx_metadata_symbol_exchange"
        )
        await db.metadata.create_index([("active", 1)], name="idx_metadata_active")
        await db.metadata.create_index([("korean_name", 1)], name="idx_metadata_korean_name")
        _index_count += 3
    except Exception as e:
        logger.debug("[init_mongodb] metadata 인덱스 생성 무시: %s", e)

    # ── priority_settings 기본값 ────────────────────────────────────────────
    try:
        await db.priority_settings.update_one(
            {"user_id": "default"},
            {
                "$setOnInsert": {
                    "user_id": "default",
                    "settings": {
                        "volume": False,
                        "market_cap": False,
                        "popularity": False,
                        "favorites": False,
                        "volatility": False,
                        "technical_signals": False,
                    },
                    "logic": "OR",
                    "updated_at": _utcnow(),
                }
            },
            upsert=True,
        )
    except Exception as e:
        logger.debug("[init_mongodb] priority_settings 초기화 무시: %s", e)

    # ── exchange_config 기본값 (DB설계.md 기반) ────────────────────────────
    try:
        await db.exchange_config.update_one(
            {"exchange": "upbit"},
            {
                "$setOnInsert": {
                    "exchange": "upbit",
                    "api_key": "",
                    "secret_key": "",
                    "rest_url": "https://api.upbit.com/v1",
                    "ws_url": "wss://api.upbit.com/websocket/v1",
                    "rate_limit": {"rest": 10, "ws": 5},
                    "enabled": True,
                    "created_at": _utcnow(),
                    "updated_at": _utcnow(),
                }
            },
            upsert=True,
        )
    except Exception as e:
        logger.debug("[init_mongodb] exchange_config 초기화 무시: %s", e)

    # ── latest_snapshot 컬렉션 인덱스 ─────────────────────────────────────
    # MetadataManager.update_snapshot 등은 {symbol, timeframe} 키로 upsert 하므로
    # unique 키는 반드시 (symbol, timeframe) 복합 인덱스여야 한다.
    # 기존 (symbol,) 단일 unique 인덱스(idx_latest_snapshot_symbol / idx_latest_symbol)가
    # 남아있을 경우 timeframe별 신규 도큐먼트 생성이 E11000으로 실패하므로 마이그레이션한다.
    try:
        # 1) 충돌 가능성이 있는 구버전 단일 unique 인덱스 제거 (best-effort)
        try:
            existing = await db.latest_snapshot.index_information()
        except Exception:
            existing = {}
        for legacy_name in ("idx_latest_snapshot_symbol", "idx_latest_symbol"):
            info = existing.get(legacy_name) if isinstance(existing, dict) else None
            if not info:
                continue
            try:
                key = info.get("key") or []
                # key 형태: [('symbol', 1)] 인 경우만 단일 인덱스로 간주하여 제거
                if list(key) == [("symbol", 1)] and info.get("unique"):
                    await db.latest_snapshot.drop_index(legacy_name)
                    logger.info(
                        "[init_mongodb] 구버전 latest_snapshot 단일 unique 인덱스 제거: %s",
                        legacy_name,
                    )
            except Exception as drop_exc:  # 인덱스 제거 실패는 치명적이지 않음
                logger.debug(
                    "[init_mongodb] %s 인덱스 제거 무시: %s", legacy_name, drop_exc
                )

        # 2) (symbol, timeframe) 복합 unique 인덱스 생성 (이미 존재하면 noop)
        await db.latest_snapshot.create_index(
            [("symbol", 1), ("timeframe", 1)],
            unique=True,
            name="idx_latest_snapshot_symbol_tf",
        )
        _index_count += 1
    except Exception as e:
        logger.debug("[init_mongodb] latest_snapshot 인덱스 생성 무시: %s", e)

    # ── gap_settings 기본값 ────────────────────────────────────────────────
    await _init_gap_settings(db)

    logger.info("[init_mongodb] 초기화 완료 (인덱스 %d개, 컬렉션: metadata/priority_settings/exchange_config/gap_settings)", _index_count)
    return db


async def _init_gap_settings(db: Any) -> None:
    """
    Gap Detection 설정 컬렉션 초기화.

    - grace_period_seconds: 신규 종목 추가 후 갭 검출 유예 시간 (기본 0초 = 즉시 검출)
    - min_gap_threshold_seconds: 검출 대상 최소 갭 크기 (기본 300초 = 5분)
    - auto_backfill_enabled: 자동 백필 활성화 여부
    - max_backfill_workers: 백필 워커 최대 동시 실행 수
    """
    try:
        await db.gap_settings.update_one(
            {"_id": "default"},
            {
                "$setOnInsert": {
                    "_id": "default",
                    "grace_period_seconds": 0,          # 0초 (즉시 검출)
                    "min_gap_threshold_seconds": 300,   # 5분
                    "auto_backfill_enabled": True,
                    "max_backfill_workers": 4,
                    "updated_at": _utcnow(),
                }
            },
            upsert=True,
        )
        logger.info("[init_mongodb] Gap Detection 설정 초기화 완료")
    except Exception as e:
        logger.debug("[init_mongodb] gap_settings 초기화 무시: %s", e)


async def save_symbols_to_mongodb(
    symbols: List[Any],
    db: Optional[Any] = None,
    uri: Optional[str] = None,
    db_name: str = "upbit_trader",
) -> int:
    """
    Upbit 심볼 목록을 MongoDB metadata 컬렉션에 저장한다.

    Args:
        symbols: aiopyupbit.get_tickers() 반환값 (dict 또는 str 목록)
        db: Motor 데이터베이스 객체 (미지정 시 uri로 연결)
        uri: MongoDB 연결 URI (db가 None일 때 사용)
        db_name: 데이터베이스 이름

    Returns:
        저장된 심볼 수
    """
    if not _HAS_MOTOR:
        return 0

    if db is None:
        db = await init_mongodb(uri=uri, db_name=db_name)
    if db is None:
        return 0

    count = 0
    now = _utcnow()

    for item in symbols:
        try:
            if isinstance(item, dict):
                symbol = item.get("market") or item.get("symbol") or item.get("code") or str(item)
                korean_name = item.get("korean_name") or item.get("name") or ""
                english_name = item.get("english_name") or ""
                market_warning = item.get("market_warning") or "NONE"
            else:
                symbol = str(item)
                korean_name = ""
                english_name = ""
                market_warning = "NONE"

            if not symbol:
                continue

            # symbol 형식: "KRW-BTC" → base/quote 분리
            parts = symbol.split("-", 1)
            quote_currency = parts[0] if len(parts) == 2 else ""
            base_currency = parts[1] if len(parts) == 2 else symbol

            await db.metadata.update_one(
                {"symbol": symbol, "exchange": "upbit"},
                {
                    "$set": {
                        "symbol": symbol,
                        "exchange": "upbit",
                        "korean_name": korean_name,
                        "english_name": english_name,
                        "base_currency": base_currency,
                        "quote_currency": quote_currency,
                        "market_warning": market_warning,
                        "active": True,
                        "updated_at": now,
                    },
                    "$setOnInsert": {
                        "created_at": now - timedelta(days=7),
                    },
                },
                upsert=True,
            )
            count += 1
        except Exception as e:
            logger.debug("[save_symbols_to_mongodb] 심볼 저장 실패 (%s): %s", item, e)

    if count:
        logger.info("[init_mongodb] %d개 심볼 metadata 컬렉션에 저장 완료", count)
    return count


def _build_default_uri() -> str:
    """
    MongoDB 연결 URI를 환경변수에서 구성한다.

    우선순위:
    1. MONGO_URI 환경변수 (완성된 URI — 그대로 반환)
    2. 인증 없는 기본 URI (localhost)

    개발 환경 우선:
    - .env 파일의 MONGO_URI가 명시적으로 설정되어 있으면 사용
    - 그렇지 않으면 인증 없는 localhost URI 사용
    """
    import os

    # 우선순위 1: MONGO_URI 환경변수 (완성된 URI)
    uri = os.getenv("MONGO_URI")
    if uri:
        logger.debug("[_build_default_uri] MONGO_URI 환경변수 사용")
        return uri

    # 우선순위 2: 인증 없는 기본 URI (개발 환경)
    host = os.getenv("MONGO_HOST", "localhost")
    port = os.getenv("MONGO_PORT", "27017")
    db = os.getenv("MONGO_DB", "upbit_trader")
    
    logger.debug("[_build_default_uri] 인증 없는 기본 URI 사용 (localhost)")
    return f"mongodb://{host}:{port}/{db}"


def _mask_uri(uri: str) -> str:
    """
    로그 출���용으로 URI에서 비밀번호를 마스킹한다.
    """
    import re
    # mongodb://user:password@host:port/db → mongodb://user:***@host:port/db
    return re.sub(r"(:\/\/[^:]+:)([^@]+)(@)", r"\1***\3", uri)


# -----------------------------------------------------------------------
# 동기/편의 헬퍼: get_db()
# - pipeline_loader 같은 동기 컨텍스트에서 사용하기 위한 간단한 접근자
# - motor 미설치 시 None 반환
# - 최초 호출 시 AsyncIOMotorClient를 생성하여 모듈 전역에 캐시
# -----------------------------------------------------------------------
def get_db(uri: Optional[str] = None, db_name: str = "upbit_trader") -> Optional[Any]:
    """
    동기적으로 MongoDB DB 객체를 반환합니다.
    - motor 미설치 시 None을 반환합니다.
    - 내부적으로 AsyncIOMotorClient를 생성하고 AsyncIOMotorDatabase 객체를 반환합니다.
    - 초기화(인덱스 등)는 init_mongodb()를 호출해 처리하세요(비동기).
    """
    global _GLOBAL_CLIENT, _GLOBAL_DB

    if not _HAS_MOTOR:
        logger.debug("[get_db] motor 미설치: None 반환")
        return None

    if _GLOBAL_DB is not None:
        return _GLOBAL_DB

    try:
        if uri is None:
            uri = _build_default_uri()
        # AsyncIOMotorClient 생성은 동기적으로 가능(내부적으로 비동기 연결 관리)
        client = AsyncIOMotorClient(uri)
        db = client[db_name]
        _GLOBAL_CLIENT = client
        _GLOBAL_DB = db
        logger.debug("[get_db] AsyncIOMotorClient 생성 및 DB 반환 (uri=%s)", _mask_uri(uri))
        return db
    except Exception as e:
        logger.error("[get_db] 동기 DB 생성 실패: %s", e)
        return None


__all__ = ["init_mongodb", "save_symbols_to_mongodb", "get_db", "_init_gap_settings"]