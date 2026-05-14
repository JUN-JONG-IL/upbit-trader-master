# -*- coding: utf-8 -*-
"""
격리 데이터 재처리 유틸리티 (isolated_reprocessor.py)

isolated_candles 테이블에 쌓인 tick 관련 격리 데이터를
normalize_tick_to_candle()로 정규화하여 staging_candles로 이동합니다.

단일 책임 원칙(SRP): 재처리 로직만 담당합니다.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 재처리 가능한 격리 사유 패턴
_TICK_REASON_PATTERNS: Tuple[str, ...] = (
    "open 필드 누락",
    "time 필드 누락",
    "symbol 누락",
)


def _get_db_conn():
    """TimescaleDB/PostgreSQL 연결 반환 (없으면 None)."""
    try:
        import psycopg2  # type: ignore
        host = os.getenv("TIMESCALE_HOST", os.getenv("POSTGRES_HOST", "localhost"))
        port = int(os.getenv("TIMESCALE_PORT", os.getenv("POSTGRES_PORT", "5432")))
        dbname = os.getenv("TIMESCALE_DB", os.getenv("POSTGRES_DB", "upbit_trader"))
        user = os.getenv("TIMESCALE_USER", os.getenv("POSTGRES_USER", "postgres"))
        password = os.getenv("TIMESCALE_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
        return psycopg2.connect(
            host=host, port=port, dbname=dbname,
            user=user, password=password,
            connect_timeout=5,
        )
    except Exception as exc:
        logger.debug("[IsolatedReprocessor] DB 연결 실패: %s", exc)
        return None


def _build_reason_where_clause() -> str:
    """재처리 가능한 격리 사유 패턴에 해당하는 WHERE 절 반환."""
    like_clauses = " OR ".join(
        f"isolation_reason LIKE '%{p}%'" for p in _TICK_REASON_PATTERNS
    )
    return f"({like_clauses})"


def get_tick_isolated_count() -> int:
    """재처리 가능한 tick 격리 건수 반환.

    isolation_reason에 'open 필드 누락', 'time 필드 누락' 등
    tick 관련 오류 패턴이 포함된 레코드 수를 반환합니다.

    Returns:
        재처리 가능한 격리 건수 (DB 오류 시 0 반환)
    """
    conn = _get_db_conn()
    if conn is None:
        return 0
    try:
        where = _build_reason_where_clause()
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM isolated_candles WHERE {where}")
            row = cur.fetchone()
            return int(row[0]) if row else 0
    except Exception as exc:
        logger.warning("[IsolatedReprocessor] tick 격리 건수 조회 실패: %s", exc)
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_isolated_stats() -> Dict[str, int]:
    """격리 건수 통계 반환.

    Returns:
        {"total": N, "reprocessable": M, "non_reprocessable": K}
    """
    conn = _get_db_conn()
    if conn is None:
        return {"total": 0, "reprocessable": 0, "non_reprocessable": 0}
    try:
        where = _build_reason_where_clause()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM isolated_candles")
            total = int((cur.fetchone() or (0,))[0])
            cur.execute(f"SELECT COUNT(*) FROM isolated_candles WHERE {where}")
            reprocessable = int((cur.fetchone() or (0,))[0])
        return {
            "total": total,
            "reprocessable": reprocessable,
            "non_reprocessable": max(0, total - reprocessable),
        }
    except Exception as exc:
        logger.warning("[IsolatedReprocessor] 통계 조회 실패: %s", exc)
        return {"total": 0, "reprocessable": 0, "non_reprocessable": 0}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def reprocess_tick_isolated(batch_size: int = 1000) -> Dict:
    """
    isolated_candles에서 tick 관련 격리 레코드를 재처리합니다.

    처리 흐름:
    1. isolation_reason에 tick 관련 패턴이 포함된 레코드 조회
    2. normalize_tick_to_candle()로 정규화
    3. staging_candles INSERT (ON CONFLICT DO NOTHING)
    4. isolated_candles에서 해당 레코드 DELETE

    Args:
        batch_size: 한 번에 처리할 최대 레코드 수 (기본값 1000)

    Returns:
        {"reprocessed": N, "failed": M, "errors": [...]}
    """
    try:
        from ...pipeline.validator import normalize_tick_to_candle  # type: ignore
    except Exception:
        try:
            import importlib
            import os as _os
            _vpath = _os.path.join(
                _os.path.dirname(_os.path.abspath(__file__)),
                "..", "..", "pipeline", "validator.py",
            )
            spec = importlib.util.spec_from_file_location("_validator_reprocess", _vpath)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                normalize_tick_to_candle = getattr(mod, "normalize_tick_to_candle", None)
            else:
                normalize_tick_to_candle = None
        except Exception:
            normalize_tick_to_candle = None

    if normalize_tick_to_candle is None:
        return {
            "reprocessed": 0,
            "failed": 0,
            "errors": ["normalize_tick_to_candle 함수를 로드할 수 없습니다."],
        }

    conn = _get_db_conn()
    if conn is None:
        return {
            "reprocessed": 0,
            "failed": 0,
            "errors": ["DB 연결 실패"],
        }

    reprocessed = 0
    failed = 0
    errors: List[str] = []

    try:
        where = _build_reason_where_clause()
        with conn.cursor() as cur:
            # 재처리 대상 조회 (raw_data 포함)
            cur.execute(
                f"""
                SELECT symbol, time, isolation_reason,
                       open, high, low, close, volume, raw_data
                FROM isolated_candles
                WHERE {where}
                ORDER BY COALESCE(isolated_at, received_at) DESC
                LIMIT %s
                """,
                (batch_size,),
            )
            rows = cur.fetchall()

        logger.info("[IsolatedReprocessor] 재처리 대상: %d 건", len(rows))

        delete_targets: List[Tuple] = []

        with conn.cursor() as cur:
            for row in rows:
                symbol = row[0]
                time_val = row[1]
                isolation_reason = row[2]
                open_val = row[3]
                high_val = row[4]
                low_val = row[5]
                close_val = row[6]
                volume_val = row[7]
                raw_data = row[8]

                try:
                    # raw_data가 있으면 원본으로 정규화 시도
                    tick_source: dict = {}
                    if isinstance(raw_data, dict):
                        tick_source = raw_data
                    elif isinstance(raw_data, str) and raw_data:
                        import json
                        try:
                            tick_source = json.loads(raw_data)
                        except Exception:
                            tick_source = {}

                    # raw_data 없으면 현재 필드로 재구성
                    if not tick_source:
                        tick_source = {
                            "symbol": symbol,
                            "close": close_val,
                            "trade_price": close_val,
                            "volume": volume_val,
                            "trade_volume": volume_val,
                            "timestamp": (
                                int(time_val.timestamp() * 1000)
                                if hasattr(time_val, "timestamp")
                                else None
                            ),
                        }

                    # tick → OHLCV 정규화
                    normalized = normalize_tick_to_candle(tick_source)

                    # symbol이 없으면 원본 symbol 사용
                    if not normalized.get("symbol") and symbol:
                        normalized["symbol"] = symbol

                    # time이 없으면 원본 time 사용
                    if not normalized.get("time") and time_val is not None:
                        normalized["time"] = time_val

                    # close가 없으면 원본 close 사용
                    if normalized.get("close") is None and close_val is not None:
                        normalized["close"] = close_val
                        normalized["open"] = close_val
                        normalized["high"] = close_val
                        normalized["low"] = close_val

                    # staging_candles INSERT
                    cur.execute(
                        """
                        INSERT INTO staging_candles
                            (symbol, time, open, high, low, close, volume)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, time) DO NOTHING
                        """,
                        (
                            normalized.get("symbol", symbol),
                            normalized.get("time", time_val),
                            normalized.get("open"),
                            normalized.get("high"),
                            normalized.get("low"),
                            normalized.get("close"),
                            normalized.get("volume"),
                        ),
                    )
                    delete_targets.append((symbol, time_val))
                    reprocessed += 1

                except Exception as exc:
                    failed += 1
                    err_msg = f"{symbol}@{time_val}: {exc}"
                    errors.append(err_msg)
                    logger.warning("[IsolatedReprocessor] 재처리 실패: %s", err_msg)

            # 성공한 레코드 isolated_candles에서 삭제
            if delete_targets:
                cur.executemany(
                    "DELETE FROM isolated_candles WHERE symbol = %s AND time = %s",
                    delete_targets,
                )

        conn.commit()
        logger.info(
            "[IsolatedReprocessor] 재처리 완료: 성공=%d, 실패=%d",
            reprocessed, failed,
        )

    except Exception as exc:
        logger.error("[IsolatedReprocessor] 재처리 중 치명적 오류: %s", exc)
        errors.append(f"치명적 오류: {exc}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return {"reprocessed": reprocessed, "failed": failed, "errors": errors}
