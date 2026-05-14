# -*- coding: utf-8 -*-
"""
캔들 DB 조회 전담 유틸리티 (candle_queries.py)

함수:
  - query_candles(symbol, timeframe, period_opt) → List[Tuple]
  - query_table_counts() → Dict[str, Any]
  - query_symbols_with_stats() → List[Dict]
  - get_save_rate_per_sec() → float
"""
from __future__ import annotations

import logging
import time as _time
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 화이트리스트 — SQL 인젝션 방지용
# ---------------------------------------------------------------------------
_ALLOWED_TABLES = {"candles", "staging_candles", "isolated_candles"}

_ALLOWED_SOURCES = {
    "candles",
    "staging_candles",
    "cagg_candles_5m",
    "cagg_candles_15m",
    "cagg_candles_1h",
    "cagg_candles_1d",
}

# ---------------------------------------------------------------------------
# 저장 속도 계산용 내부 상태
# ---------------------------------------------------------------------------
_rate_snapshot: Dict[str, Any] = {"ts": 0.0, "count": 0}


# ---------------------------------------------------------------------------
# 내부 헬퍼 — 커넥터 획득
# ---------------------------------------------------------------------------

def _get_connector() -> Optional[Any]:
    """TimescaleDB 커넥터를 반환합니다. 없으면 None."""
    try:
        from .db_connectors import get_timescale_connector
        return get_timescale_connector()
    except Exception as exc:
        logger.debug("[candle_queries] 커넥터 획득 실패: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------

def query_candles(
    symbol: str,
    timeframe: str,
    period_opt: dict,
) -> List[Tuple]:
    """TimescaleDB candles 테이블에서 캔들 데이터를 조회합니다.

    Args:
        symbol: 심볼 문자열 (예: 'KRW-BTC')
        timeframe: 타임프레임 문자열 (예: '1m', '1h')
        period_opt: 기간 옵션 dict
            - {"type": "limit", "limit": 100}
            - {"type": "today"}
            - {"type": "days", "days": 7}

    Returns:
        (time, open, high, low, close, volume) 튜플 목록
    """
    connector = _get_connector()
    if connector is None:
        logger.warning("[candle_queries] TimescaleDB 연결 없음")
        return []

    try:
        conn = connector.get_connection(retry=False)
        cur = conn.cursor()
        opt_type = period_opt.get("type", "limit")

        try:
            if opt_type == "limit":
                limit = int(period_opt.get("limit", 100))
                cur.execute(
                    "SELECT time, open, high, low, close, volume "
                    "FROM candles "
                    "WHERE symbol=%s AND timeframe=%s "
                    "ORDER BY time DESC LIMIT %s",
                    (symbol, timeframe, limit),
                )
            elif opt_type == "today":
                today = date.today().isoformat()
                cur.execute(
                    "SELECT time, open, high, low, close, volume "
                    "FROM candles "
                    "WHERE symbol=%s AND timeframe=%s AND time >= %s "
                    "ORDER BY time DESC",
                    (symbol, timeframe, today),
                )
            elif opt_type == "days":
                days = int(period_opt.get("days", 7))
                since = (datetime.utcnow() - timedelta(days=days)).isoformat()
                cur.execute(
                    "SELECT time, open, high, low, close, volume "
                    "FROM candles "
                    "WHERE symbol=%s AND timeframe=%s AND time >= %s "
                    "ORDER BY time DESC",
                    (symbol, timeframe, since),
                )
            else:
                cur.execute(
                    "SELECT time, open, high, low, close, volume "
                    "FROM candles "
                    "WHERE symbol=%s AND timeframe=%s "
                    "ORDER BY time DESC LIMIT 100",
                    (symbol, timeframe),
                )
            rows = cur.fetchall()
        finally:
            cur.close()
            connector.put_connection(conn)

        return rows

    except Exception as exc:
        logger.warning("[candle_queries] candles 조회 실패: %s", exc)
        return []


def query_table_counts() -> Dict[str, Any]:
    """candles / staging_candles / isolated_candles 건수와 최신 시각을 반환합니다.

    Returns:
        {
            "candles": int,
            "staging": int,
            "isolated": int,
            "last_save_time": Optional[datetime],
        }
        TimescaleDB 미연결 시 0 값의 기본 dict 반환 (예외 안전).
    """
    result: Dict[str, Any] = {
        "candles": 0,
        "staging": 0,
        "isolated": 0,
        "last_save_time": None,
    }

    connector = _get_connector()
    if connector is None:
        return result

    table_map = [
        ("candles",          "candles"),
        ("staging_candles",  "staging"),
        ("isolated_candles", "isolated"),
    ]

    try:
        conn = connector.get_connection(retry=False)
        cur = conn.cursor()
        try:
            for tbl, key in table_map:
                if tbl not in _ALLOWED_TABLES:
                    continue
                try:
                    cur.execute("SELECT COUNT(*) FROM " + tbl)  # tbl은 화이트리스트에서 검증됨
                    row = cur.fetchone()
                    if row:
                        result[key] = int(row[0])
                except Exception as tbl_exc:
                    logger.debug("[candle_queries] %s COUNT 실패: %s", tbl, tbl_exc)

            # 최신 저장 시각 (candles 기준)
            try:
                cur.execute("SELECT MAX(time) FROM candles")
                row = cur.fetchone()
                if row and row[0] is not None:
                    result["last_save_time"] = row[0]
            except Exception as time_exc:
                logger.debug("[candle_queries] MAX(time) 조회 실패: %s", time_exc)

        finally:
            cur.close()
            connector.put_connection(conn)

    except Exception as exc:
        logger.debug("[candle_queries] query_table_counts 실패: %s", exc)

    return result


def query_symbols_with_stats() -> List[Dict]:
    """심볼별 통계 정보를 반환합니다.

    Returns:
        [{"symbol": str, "asset_class": str, "exchange": str,
          "candle_count": int, "last_time": Optional[datetime]}, ...]
        TimescaleDB 미연결 시 MongoDB metadata 폴백.
    """
    # config_loader 에서 심볼 조회 LIMIT 읽기 (기본 10000)
    try:
        from .config_loader import get_symbol_query_limit
        _limit = get_symbol_query_limit()
    except Exception:
        _limit = 10_000

    connector = _get_connector()
    if connector is not None:
        try:
            conn = connector.get_connection(retry=False)
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT symbol, COUNT(*) AS cnt, MAX(time) AS last_time "
                    "FROM candles "
                    "GROUP BY symbol "
                    "ORDER BY cnt DESC "
                    "LIMIT %s",
                    (_limit,)
                )
                rows = cur.fetchall()
            finally:
                cur.close()
                connector.put_connection(conn)

            result = []
            for row in rows:
                sym = row[0]
                result.append({
                    "symbol": sym,
                    "asset_class": _infer_asset_class(sym),
                    "exchange": _infer_exchange(sym),
                    "candle_count": int(row[1]),
                    "last_time": row[2],
                })
            return result

        except Exception as exc:
            logger.debug("[candle_queries] symbols_with_stats TimescaleDB 실패: %s", exc)

    # 폴백: MongoDB metadata 컬렉션
    return _query_symbols_from_mongo()


def get_save_rate_per_sec() -> float:
    """이전 호출 이후 staging_candles 증가 속도를 반환합니다 (건/초).

    최초 호출 시에는 0.0을 반환하고, 이후 호출 시 이전 호출과의 elapsed/delta로 계산합니다.

    Returns:
        저장 속도 (건/초). 계산 불가 시 0.0.
    """
    global _rate_snapshot

    connector = _get_connector()
    if connector is None:
        return 0.0

    try:
        conn = connector.get_connection(retry=False)
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM staging_candles")
            row = cur.fetchone()
            current_count = int(row[0]) if row else 0
        finally:
            cur.close()
            connector.put_connection(conn)

        now = _time.monotonic()
        prev_ts = _rate_snapshot["ts"]
        prev_count = _rate_snapshot["count"]

        _rate_snapshot["ts"] = now
        _rate_snapshot["count"] = current_count

        if prev_ts > 0:
            elapsed = now - prev_ts
            if elapsed > 0:
                delta = current_count - prev_count
                return max(0.0, delta / elapsed)

        return 0.0

    except Exception as exc:
        logger.debug("[candle_queries] get_save_rate_per_sec 실패: %s", exc)
        return 0.0


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _infer_asset_class(symbol: str) -> str:
    """심볼에서 자산군을 추론합니다."""
    s = symbol.upper()
    if s.startswith(("KRW-", "BTC-", "USDT-", "ETH-")):
        return "암호화폐"
    if s.endswith(("=F",)):
        return "파생상품/선물"
    if s.isdigit() or (len(s) == 6 and s.isdigit()):
        return "국내주식"
    if s.isalpha() and len(s) <= 5:
        return "해외주식"
    return "암호화폐"


def _infer_exchange(symbol: str) -> str:
    """심볼에서 거래소를 추론합니다."""
    s = symbol.upper()
    if s.startswith(("KRW-", "BTC-")):
        return "업비트"
    if s.endswith("=F"):
        return "CME"
    if s.isdigit():
        return "KRX/코스피"
    return "전체"


def _query_symbols_from_mongo() -> List[Dict]:
    """MongoDB metadata 컬렉션에서 심볼 목록을 가져옵니다 (폴백)."""
    try:
        from .db_connectors import get_mongo_sync_client
        client = get_mongo_sync_client()
        if client is None:
            return []
        db = client.get_database()
        symbols = db["metadata"].distinct("symbol")
        result = []
        for sym in sorted(symbols):
            result.append({
                "symbol": sym,
                "asset_class": _infer_asset_class(sym),
                "exchange": _infer_exchange(sym),
                "candle_count": 0,
                "last_time": None,
            })
        return result
    except Exception as exc:
        logger.debug("[candle_queries] MongoDB 심볼 조회 실패: %s", exc)
        return []


def query_candles_extended(
    symbol: str,
    timeframe: str,
    period_opt: dict,
    data_source: str = "candles",
) -> List[Tuple]:
    """데이터 소스를 선택하여 캔들 데이터를 조회합니다 (9컬럼 반환).

    Args:
        symbol: 심볼 문자열 (예: 'KRW-BTC')
        timeframe: 타임프레임 문자열 (예: '1m', '1h')
        period_opt: 기간 옵션 dict
        data_source: 데이터 소스 ('candles', 'staging_candles', 'cagg_candles_5m', ...)

    Returns:
        (time, open, high, low, close, volume, quote_volume, trade_count, is_complete) 튜플 목록
        CAGG 뷰는 quote_volume/trade_count/is_complete = None
    """
    if data_source not in _ALLOWED_SOURCES:
        logger.warning("[candle_queries] 허용되지 않은 데이터소스: %s", data_source)
        data_source = "candles"

    connector = _get_connector()
    if connector is None:
        logger.warning("[candle_queries] TimescaleDB 연결 없음")
        return []

    is_cagg = data_source.startswith("cagg_")
    # SELECT 결과에서 trade_count 컬럼 인덱스 (0-based)
    _TRADE_COUNT_IDX = 7

    try:
        conn = connector.get_connection(retry=False)
        cur = conn.cursor()
        opt_type = period_opt.get("type", "limit")

        # CAGG 뷰는 symbol 컬럼만 있고 timeframe 없음
        if is_cagg:
            select_cols = "time, open, high, low, close, volume, NULL, NULL, NULL"
            where_sym = "WHERE symbol=%s"
            params_base: tuple = (symbol,)
        else:
            select_cols = "time, open, high, low, close, volume, quote_volume, trade_count, is_complete"
            where_sym = "WHERE symbol=%s AND timeframe=%s"
            params_base = (symbol, timeframe)

        try:
            if opt_type == "limit":
                limit = int(period_opt.get("limit", 100))
                sql = (
                    f"SELECT {select_cols} FROM {data_source} "
                    f"{where_sym} ORDER BY time DESC LIMIT %s"
                )
                cur.execute(sql, params_base + (limit,))
            elif opt_type == "today":
                today = date.today().isoformat()
                sql = (
                    f"SELECT {select_cols} FROM {data_source} "
                    f"{where_sym} AND time >= %s ORDER BY time DESC"
                )
                cur.execute(sql, params_base + (today,))
            elif opt_type == "days":
                days = int(period_opt.get("days", 7))
                since = (datetime.utcnow() - timedelta(days=days)).isoformat()
                sql = (
                    f"SELECT {select_cols} FROM {data_source} "
                    f"{where_sym} AND time >= %s ORDER BY time DESC"
                )
                cur.execute(sql, params_base + (since,))
            else:
                sql = (
                    f"SELECT {select_cols} FROM {data_source} "
                    f"{where_sym} ORDER BY time DESC LIMIT 100"
                )
                cur.execute(sql, params_base)
            rows = cur.fetchall()

            # 사용자가 candles + 5m/1h 등을 선택했지만 원본 candles에는 1m만 있는 설치도 있다.
            # 이 경우 동일 데이터베이스의 연속 집계(CAGG)에서 자동 조회해 "다른 TF가 비어 보이는" 문제를 완화한다.
            fallback_cagg = {
                "5m": "cagg_candles_5m",
                "15m": "cagg_candles_15m",
                "1h": "cagg_candles_1h",
                "1d": "cagg_candles_1d",
            }.get(timeframe)
            if fallback_cagg not in _ALLOWED_SOURCES:
                fallback_cagg = None
            if not rows and data_source == "candles" and fallback_cagg:
                # CAGG에는 quote_volume/trade_count/is_complete 컬럼이 없어 UI 표 형식에 맞춰 NULL로 채운다.
                select_cols_cagg = "time, open, high, low, close, volume, NULL, NULL, NULL"
                if opt_type == "limit":
                    limit = int(period_opt.get("limit", 100))
                    cur.execute(
                        f"SELECT {select_cols_cagg} FROM {fallback_cagg} "
                        "WHERE symbol=%s ORDER BY time DESC LIMIT %s",
                        (symbol, limit),
                    )
                elif opt_type == "today":
                    today = date.today().isoformat()
                    cur.execute(
                        f"SELECT {select_cols_cagg} FROM {fallback_cagg} "
                        "WHERE symbol=%s AND time >= %s ORDER BY time DESC",
                        (symbol, today),
                    )
                elif opt_type == "days":
                    days = int(period_opt.get("days", 7))
                    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
                    cur.execute(
                        f"SELECT {select_cols_cagg} FROM {fallback_cagg} "
                        "WHERE symbol=%s AND time >= %s ORDER BY time DESC",
                        (symbol, since),
                    )
                else:
                    cur.execute(
                        f"SELECT {select_cols_cagg} FROM {fallback_cagg} "
                        "WHERE symbol=%s ORDER BY time DESC LIMIT 100",
                        (symbol,),
                    )
                rows = cur.fetchall()
        finally:
            cur.close()
            connector.put_connection(conn)

        # trade_count 전체 NULL 여부 로깅 (캔들 테이블 한정)
        if rows and not is_cagg:
            null_tc = sum(1 for r in rows if len(r) > _TRADE_COUNT_IDX and r[_TRADE_COUNT_IDX] is None)
            if null_tc > 0:
                logger.debug(
                    "[candle_queries] %s/%s: trade_count NULL %d/%d행 — DB 미수집 가능성",
                    symbol, data_source, null_tc, len(rows),
                )

        return rows

    except Exception as exc:
        logger.warning("[candle_queries] %s 조회 실패: %s", data_source, exc)
        return []


def query_table_counts_extended() -> Dict[str, Any]:
    """candles / staging / isolated / CAGG 건수를 모두 반환합니다.

    Returns:
        {
            "candles": int, "staging": int, "isolated": int,
            "cagg_5m": int, "cagg_15m": int, "cagg_1h": int, "cagg_1d": int,
            "last_save_time": Optional[datetime],
        }
    """
    result: Dict[str, Any] = {
        "candles": 0,
        "staging": 0,
        "isolated": 0,
        "cagg_5m": 0,
        "cagg_15m": 0,
        "cagg_1h": 0,
        "cagg_1d": 0,
        "last_save_time": None,
    }

    connector = _get_connector()
    if connector is None:
        return result

    table_map = [
        ("candles",          "candles"),
        ("staging_candles",  "staging"),
        ("isolated_candles", "isolated"),
        ("cagg_candles_5m",  "cagg_5m"),
        ("cagg_candles_15m", "cagg_15m"),
        ("cagg_candles_1h",  "cagg_1h"),
        ("cagg_candles_1d",  "cagg_1d"),
    ]

    try:
        conn = connector.get_connection(retry=False)
        cur = conn.cursor()
        try:
            for tbl, key in table_map:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                    row = cur.fetchone()
                    if row:
                        result[key] = int(row[0])
                except Exception:
                    pass
            try:
                cur.execute("SELECT MAX(time) FROM candles")
                row = cur.fetchone()
                if row and row[0] is not None:
                    result["last_save_time"] = row[0]
            except Exception:
                pass
        finally:
            cur.close()
            connector.put_connection(conn)
    except Exception as exc:
        logger.debug("[candle_queries] query_table_counts_extended 실패: %s", exc)

    return result


# ---------------------------------------------------------------------------
# 백필 검증
# ---------------------------------------------------------------------------

# 타임프레임 → CAGG 뷰 폴백 매핑 (검증/표시 일관성 확보용)
_VERIFY_CAGG_FALLBACK = {
    "5m": "cagg_candles_5m",
    "15m": "cagg_candles_15m",
    "1h": "cagg_candles_1h",
    "1d": "cagg_candles_1d",
}


def query_verify_backfill(
    symbol: str,
    timeframe: str,
    start_dt: Any,
    end_dt: Any,
) -> Tuple[int, int]:
    """TimescaleDB에서 지정 심볼/타임프레임/기간의 실제 봉수와 중복 수를 반환합니다.

    Args:
        symbol: 심볼 (예: KRW-BTC)
        timeframe: 타임프레임 (예: 1m, 5m, 1h)
        start_dt: 조회 시작 시각 (datetime, UTC)
        end_dt: 조회 종료 시각 (datetime, UTC)

    Returns:
        Tuple[actual_count, duplicate_count]

    Note:
        세부 데이터 소스 정보(원본 candles vs CAGG 폴백)가 필요하면
        :func:`query_verify_backfill_ex` 를 사용하세요. 본 함수는 하위
        호환을 위한 2-튜플 래퍼입니다.
    """
    actual, dup, _src, _fb = query_verify_backfill_ex(symbol, timeframe, start_dt, end_dt)
    return actual, dup


def query_verify_backfill_ex(
    symbol: str,
    timeframe: str,
    start_dt: Any,
    end_dt: Any,
) -> Tuple[int, int, str, bool]:
    """검증 쿼리 — CAGG 폴백 포함 + 데이터 소스 정보 반환.

    candles 원본이 비어있으면(예: 1h/5m/15m/1d 가 CAGG 만 채워진 환경)
    표시 쿼리(:func:`query_candles_extended`)와 동일한 규칙으로 CAGG 뷰를
    조회한다. 이로써 "표시는 6개, 검증은 0개" 같은 불일치가 사라진다.

    Args:
        symbol: 심볼 (예: KRW-BTC)
        timeframe: 타임프레임 (예: 1m, 5m, 1h)
        start_dt: 조회 시작 시각 (datetime, UTC)
        end_dt: 조회 종료 시각 (datetime, UTC)

    Returns:
        Tuple[actual_count, duplicate_count, source_table, used_fallback]
            * source_table : 실제 카운트를 얻은 테이블/뷰 명. 빈 문자열이면 조회 실패.
            * used_fallback: CAGG 폴백을 사용했는지 여부 (True/False).
    """
    connector = _get_connector()
    if connector is None:
        return 0, 0, "", False

    if not symbol or not timeframe:
        return 0, 0, "", False

    actual = 0
    dup = 0
    source_table = ""
    used_fallback = False

    try:
        conn = connector.get_connection(retry=False)
        cur = conn.cursor()
        try:
            # 1) 원본 candles 조회
            cur.execute(
                """
                SELECT
                    COUNT(*) AS actual_count,
                    COUNT(*) - COUNT(DISTINCT time) AS duplicate_count
                FROM candles
                WHERE symbol = %s
                  AND timeframe = %s
                  AND time >= %s
                  AND time < %s
                """,
                (symbol, timeframe, start_dt, end_dt),
            )
            row = cur.fetchone()
            if row and len(row) >= 2:
                actual = int(row[0] or 0)
                dup = int(row[1] or 0)
                source_table = "candles"

            # 2) candles 가 비어있으면 CAGG 뷰로 폴백 (표시 쿼리와 동일 규칙)
            #    CAGG 는 time 단일 인덱스이므로 중복은 사실상 0.
            #    SQL 인젝션 방지: fb_view 는 정적 매핑(_VERIFY_CAGG_FALLBACK)
            #    에서만 가져오며, 추가로 _ALLOWED_SOURCES 화이트리스트 검사를
            #    이중으로 통과해야 쿼리에 사용된다. 외부 입력은 전혀 사용되지 않는다.
            if actual == 0:
                fb_view = _VERIFY_CAGG_FALLBACK.get(str(timeframe))
                if fb_view and fb_view in _ALLOWED_SOURCES:
                    # 한 번 더 화이트리스트 일치 확인 (방어적 — 시간이 지나며
                    # _VERIFY_CAGG_FALLBACK 가 확장되더라도 안전).
                    assert fb_view in _ALLOWED_SOURCES, (
                        f"비허용 CAGG 뷰: {fb_view}"
                    )
                    try:
                        cur.execute(
                            f"""
                            SELECT
                                COUNT(*) AS actual_count,
                                COUNT(*) - COUNT(DISTINCT time) AS duplicate_count
                            FROM {fb_view}
                            WHERE symbol = %s
                              AND time >= %s
                              AND time < %s
                            """,
                            (symbol, start_dt, end_dt),
                        )
                        row2 = cur.fetchone()
                        if row2 and len(row2) >= 2:
                            cagg_actual = int(row2[0] or 0)
                            cagg_dup = int(row2[1] or 0)
                            if cagg_actual > 0:
                                actual = cagg_actual
                                dup = cagg_dup
                                source_table = fb_view
                                used_fallback = True
                    except Exception as exc_inner:
                        logger.debug(
                            "[candle_queries] CAGG 폴백 실패 (%s): %s",
                            fb_view, exc_inner,
                        )
        finally:
            cur.close()
            connector.put_connection(conn)
    except Exception as exc:
        logger.debug("[candle_queries] query_verify_backfill 실패: %s", exc)
        return 0, 0, "", False

    return actual, dup, source_table, used_fallback
