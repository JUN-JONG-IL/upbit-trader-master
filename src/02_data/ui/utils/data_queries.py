# -*- coding: utf-8 -*-
"""
데이터 조회 함수 전체 (v1.0)

포함된 함수:
    - get_active_symbols     : 활성 WebSocket 심볼 목록
    - get_websocket_stats    : WebSocket 연결 통계
    - get_backfill_progress  : 백필 진행률
    - _get_redis_client      : 단기 Redis 클라이언트 (내부용)
    - get_gap_queue_count_from_redis : Redis gap 큐 건수
    - get_gap_queue_count_realtime   : 실시간 gap 큐 건수
    - get_gaps               : gap fill 작업 목록
    - get_table_stats        : 테이블 통계
    - get_pipeline_stats     : 파이프라인 레코드 수

버그 수정:
    - get_gaps(): Pool 오용 수정 (.cursor() 직접 호출 → .get_connection() 사용)
    - get_gap_queue_count_realtime(): Pool 오용 수정
    - get_table_stats(): Pool 오용 수정
    - get_pipeline_stats(): staging 다중 패턴 조회 + TimescaleDB 폴백 추가
"""
from __future__ import annotations

import json as _json
import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional

from .constants import ALLOWED_TABLES
from .db_connectors import (
    get_mongo_sync_client,
    get_redis_connector,
    get_timescale_connector,
)
from .formatters import format_bytes
from .module_finder import get_auto_backfill_manager, get_realtime_manager

logger = logging.getLogger(__name__)

# MongoDB 클라이언트 임시 캐시 (get_active_symbols 전용)
_mongo_client_cache: Optional[Any] = None
import threading as _threading
_mongo_client_lock = _threading.Lock()


def _get_redis_client() -> Optional[Any]:
    """단기 Redis 클라이언트 반환 (비밀번호 지원).

    Returns:
        redis.Redis 인스턴스 또는 None
    """
    try:
        import redis as _redis_mod  # type: ignore

        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "58530"))
        password = os.getenv("REDIS_PASSWORD") or None
        return _redis_mod.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True,
            socket_connect_timeout=2,
        )
    except Exception as exc:
        logger.debug("[UI Utils] Redis client creation failed: %s", exc)
        return None


def get_active_symbols() -> List[str]:
    """활성 WebSocket 심볼 목록 반환 (최대 20개).

    조회 순서:
        1. RealtimeManager.active_symbols
        2. RealtimeManager._active_symbols
        3. RealtimeManager._ws_tasks
        4. RealtimeManager.codes
        5. MongoDB metadata 컬렉션 폴백

    Returns:
        심볼 문자열 목록 (최대 20개)
    """
    global _mongo_client_cache

    try:
        # RealtimeManager에서 먼저 시도
        mgr = get_realtime_manager()
        if mgr is not None:
            if hasattr(mgr, "active_symbols") and mgr.active_symbols:
                logger.debug("[UI Utils] active_symbols 사용: %d개", len(mgr.active_symbols))
                return list(mgr.active_symbols)[:20]

            if hasattr(mgr, "_active_symbols") and mgr._active_symbols:
                logger.debug(
                    "[UI Utils] _active_symbols 사용: %d개", len(mgr._active_symbols)
                )
                return list(mgr._active_symbols)[:20]

            if hasattr(mgr, "_ws_tasks") and mgr._ws_tasks:
                logger.debug("[UI Utils] _ws_tasks 사용: %d개", len(mgr._ws_tasks))
                return list(mgr._ws_tasks.keys())[:20]

            if hasattr(mgr, "codes"):
                try:
                    codes = mgr.codes() if callable(mgr.codes) else mgr.codes
                    if codes:
                        logger.debug("[UI Utils] codes 사용: %d개", len(codes))
                        return list(codes)[:20]
                except Exception as e:
                    logger.debug("[UI Utils] codes 호출 실패: %s", e)

        # MongoDB 폴백
        logger.warning("[UI Utils] RealtimeManager 없음 - MongoDB 조회 시도")
        try:
            import pymongo  # type: ignore

            uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader")

            with _mongo_client_lock:
                if _mongo_client_cache is None:
                    _mongo_client_cache = pymongo.MongoClient(
                        uri,
                        serverSelectionTimeoutMS=2000,
                        directConnection=True,
                        maxPoolSize=1,
                        minPoolSize=0,
                        maxIdleTimeMS=60000,
                    )
                    logger.info("[UI Utils] MongoDB 싱글톤 연결 생성")

            parsed = urllib.parse.urlparse(uri)
            db_name = parsed.path.lstrip("/") or "upbit_trader"
            db = _mongo_client_cache[db_name]
            cursor = db["metadata"].find({}, {"_id": 1}).limit(20).max_time_ms(1000)
            symbols = list(cursor)
            result = [s["_id"] for s in symbols if "_id" in s]
            logger.info("[UI Utils] MongoDB에서 %d개 심볼 조회 성공", len(result))
            return result
        except Exception as e:
            logger.warning("[UI Utils] MongoDB 조회 실패: %s", e)
    except Exception as e:
        logger.error("[UI Utils] get_active_symbols 실패: %s", e, exc_info=True)

    return []


def get_websocket_stats() -> List[Dict]:
    """WebSocket 연결 상태, 수신 건수, 지연 ms 목록 반환.

    Returns:
        각 심볼별 {"symbol", "status", "count", "latency"} 딕셔너리 목록
    """
    try:
        mgr = get_realtime_manager()
        if mgr is None:
            logger.warning("[UI Utils] get_websocket_stats: RealtimeManager 없음")
            return []

        symbols = get_active_symbols()
        if not symbols:
            logger.warning("[UI Utils] get_websocket_stats: 활성 심볼 없음")
            return []

        stats: List[Dict] = []
        for symbol in symbols:
            try:
                # 연결 상태
                if hasattr(mgr, "is_connected"):
                    is_connected = mgr.is_connected(symbol)
                elif hasattr(mgr, "_ws_tasks") and symbol in mgr._ws_tasks:
                    task = mgr._ws_tasks[symbol]
                    is_connected = not task.done()
                else:
                    is_connected = True

                # 수신 건수
                if hasattr(mgr, "get_message_count"):
                    count = mgr.get_message_count(symbol)
                elif hasattr(mgr, "_message_counts"):
                    count = mgr._message_counts.get(symbol, 0)
                else:
                    count = 0

                # 지연 시간
                if hasattr(mgr, "get_latency_ms"):
                    latency = mgr.get_latency_ms(symbol)
                elif hasattr(mgr, "_latencies"):
                    latency = mgr._latencies.get(symbol, 0)
                else:
                    latency = 0

                stats.append(
                    {
                        "symbol": symbol,
                        "status": "🟢 연결됨" if is_connected else "🔴 끊김",
                        "count": count,
                        "latency": f"{latency:.1f}" if latency > 0 else "-",
                    }
                )
            except Exception as e:
                logger.debug("[UI Utils] 심볼 %s 상태 조회 실패: %s", symbol, e)

        logger.info("[UI Utils] WebSocket 통계 조회 성공: %d개", len(stats))
        return stats
    except Exception as e:
        logger.error("[UI Utils] get_websocket_stats 실패: %s", e, exc_info=True)
    return []


def get_backfill_progress() -> List[Dict]:
    """백필 진행률 목록 반환.

    Returns:
        각 작업별 {"symbol", "progress", "completed_total", "status"} 딕셔너리 목록
    """
    try:
        mgr = get_auto_backfill_manager()
        if mgr is None:
            return []

        progress_list: List[Any] = []
        if hasattr(mgr, "get_progress"):
            try:
                progress_list = mgr.get_progress() or []
            except Exception as e:
                logger.debug("[UI Utils] get_progress 호출 실패: %s", e)

        if not progress_list and hasattr(mgr, "_manager"):
            inner = mgr._manager
            if hasattr(inner, "workers"):
                for worker in inner.workers:
                    if hasattr(worker, "current_task") and worker.current_task:
                        progress_list.append(worker.current_task)

        result: List[Dict] = []
        for item in progress_list[:20]:
            try:
                symbol = item.get("symbol", "")
                total = item.get("total", 0)
                completed = item.get("completed", 0)
                progress_pct = int((completed / total * 100) if total > 0 else 0)
                status = item.get("status", "대기")
                result.append(
                    {
                        "symbol": symbol,
                        "progress": progress_pct,
                        "completed_total": f"{completed}/{total}",
                        "status": status,
                    }
                )
            except Exception as item_exc:
                logger.debug("[UI Utils] backfill progress 항목 처리 실패: %s", item_exc)
                continue
        return result
    except Exception as e:
        logger.debug("[UI Utils] get_backfill_progress 실패: %s", e)
    return []


def get_gap_queue_count_from_redis() -> int:
    """Redis Sorted Set에서 Gap 큐 건수 반환.

    Returns:
        gap_fill_queue 항목 수
    """
    rc = _get_redis_client()
    if rc is None:
        return 0
    try:
        return int(rc.zcard("gap_fill_queue") or 0)
    except Exception as exc:
        logger.debug("[UI Utils] Redis gap queue count failed: %s", exc)
        return 0


def get_gap_queue_count_realtime() -> int:
    """Gap 큐 건수 실시간 조회 (Redis 우선, DB 폴백).

    Returns:
        gap_fill_queue 항목 수
    """
    # Redis 시도
    try:
        rc = _get_redis_client()
        if rc is not None:
            redis_count = rc.zcard("gap_fill_queue")
            if redis_count and redis_count > 0:
                return int(redis_count)
    except Exception as exc:
        logger.debug("[UI Utils] Redis 실시간 조회 실패: %s", exc)

    # TimescaleDB 폴백 — 반드시 get_connection() 사용
    connector = get_timescale_connector()
    if connector is None:
        return 0
    conn = None
    cur = None
    try:
        conn = connector.get_connection(retry=False)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM gap_fill_queue WHERE status = 'pending'")
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception as exc:
        logger.debug("[UI Utils] DB gap queue count 조회 실패: %s", exc)
        return 0
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception as close_exc:
                logger.debug("[UI Utils] cursor close error: %s", close_exc)
        if conn is not None:
            try:
                connector.put_connection(conn)
            except Exception as put_exc:
                logger.debug("[UI Utils] put_connection error: %s", put_exc)


def get_gaps() -> List[Dict]:
    """Gap Fill 작업 목록 반환 (TimescaleDB 우선, Redis 폴백).

    Returns:
        각 gap 항목 딕셔너리 목록
    """
    connector = get_timescale_connector()
    if connector is not None:
        conn = None
        cur = None
        try:
            conn = connector.get_connection(retry=False)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT symbol, gap_start, gap_end,
                       EXTRACT(EPOCH FROM (gap_end - gap_start))::INTEGER AS gap_seconds,
                       priority, status
                FROM gap_fill_queue
                WHERE status = 'pending'
                ORDER BY priority DESC, gap_seconds DESC
                LIMIT 100
                """
            )
            rows = cur.fetchall()
            if rows:
                result = [
                    {
                        "symbol": row[0],
                        "gap_start": row[1],
                        "gap_end": row[2],
                        "gap_seconds": row[3],
                        "priority": row[4],
                        "status": row[5],
                    }
                    for row in rows
                ]
                logger.info("[UI Utils] Gap query success: %d rows", len(result))
                return result
            # 0행이면 Redis ZSET 폴백으로 계속 진행
            logger.debug("[UI Utils] gap_fill_queue 테이블 비어있음 — Redis 폴백 시도")
        except Exception as exc:
            logger.debug("[UI Utils] gap_fill_queue query failed: %s", exc)
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception as close_exc:
                    logger.debug("[UI Utils] cursor close error: %s", close_exc)
            if conn is not None:
                try:
                    connector.put_connection(conn)
                except Exception as put_exc:
                    logger.debug("[UI Utils] put_connection error: %s", put_exc)
    else:
        logger.warning("[UI Utils] get_gaps: TimescaleDB connection unavailable")

    # Redis 폴백: JSON 형식으로 저장된 gap_fill_queue 항목 파싱
    rc = _get_redis_client()
    if rc is None:
        return []
    try:
        items = rc.zrange("gap_fill_queue", 0, 99, withscores=True)
        gaps: List[Dict] = []
        for item, score in items:
            try:
                # isolator.py가 JSON 형식으로 저장하므로 JSON 우선 파싱
                obj = _json.loads(str(item))
                gaps.append(
                    {
                        "symbol": obj.get("symbol", ""),
                        "timeframe": obj.get("timeframe", "1m"),
                        "gap_start": obj.get("start", ""),
                        "gap_end": obj.get("end", ""),
                        "gap_seconds": float(obj.get("gap_seconds", 0)),
                        "priority": float(score),
                        "status": "pending",
                        "job_id": obj.get("job_id", ""),
                    }
                )
            except Exception:
                # 레거시 파이프-구분 형식 폴백
                parts = str(item).split("|")
                if len(parts) >= 2:
                    gaps.append(
                        {
                            "symbol": parts[0],
                            "timeframe": parts[1] if len(parts) > 1 else "1m",
                            "gap_start": parts[2] if len(parts) > 2 else "",
                            "gap_end": parts[3] if len(parts) > 3 else "",
                            "gap_seconds": 0,
                            "priority": float(score),
                            "status": "pending",
                        }
                    )
        logger.info("[UI Utils] Redis fallback success: %d rows", len(gaps))
        return gaps
    except Exception as exc:
        logger.error("[UI Utils] Redis fallback failed: %s", exc)
    return []


def get_gap_worker_status() -> Dict[str, Any]:
    """Redis에서 GapWorker 실행 상태를 조회합니다.

    조회 키:
        gap:worker:status       — {"running": bool, "processed": int, "last_processed": str}
        gap:worker:grace_period — 유예 기간(초)
        gap:worker:count        — 활성 워커 수

    Returns:
        {
            "running": bool,
            "processed": int,
            "last_processed": str,
            "grace_period": int,
            "worker_count": int,
        }
    """
    result: Dict[str, Any] = {
        "running": False,
        "processed": 0,
        "last_processed": "--",
        "grace_period": 0,
        "worker_count": 0,
    }
    rc = _get_redis_client()
    if rc is None:
        return result
    try:
        raw_status = rc.get("gap:worker:status")
        if raw_status:
            try:
                obj = _json.loads(raw_status)
                result["running"] = bool(obj.get("running", False))
                result["processed"] = int(obj.get("processed", 0))
                result["last_processed"] = str(obj.get("last_processed", "--"))
            except Exception as exc:
                logger.debug("[UI Utils] gap:worker:status 파싱 실패: %s", exc)

        grace = rc.get("gap:worker:grace_period")
        if grace:
            try:
                result["grace_period"] = int(grace)
            except Exception:
                pass

        count = rc.get("gap:worker:count")
        if count:
            try:
                result["worker_count"] = int(count)
            except Exception:
                pass
    except Exception as exc:
        logger.debug("[UI Utils] get_gap_worker_status 실패: %s", exc)
    return result


def get_table_stats(table: str) -> Dict:
    """테이블 통계 반환 (행 수, 크기, 최신 시간).

    Args:
        table: 조회할 테이블 이름 (ALLOWED_TABLES에 포함되어야 함)

    Returns:
        {"table", "row_count", "size_bytes", "size_human", "latest_time"} 딕셔너리
        허용되지 않은 테이블이나 연결 실패 시 {}
    """
    if table not in ALLOWED_TABLES:
        logger.warning("[UI Utils] 허용되지 않은 테이블 이름: %s", table)
        return {}

    connector = get_timescale_connector()
    if connector is None:
        return {}

    conn = None
    cur = None
    try:
        conn = connector.get_connection(retry=False)
        cur = conn.cursor()

        # 행 수
        cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        count_row = cur.fetchone()
        row_count = int(count_row[0]) if count_row and count_row[0] is not None else 0

        # 크기 (바이트) — hypertable_size 우선, pg_total_relation_size 폴백
        size_bytes = 0
        try:
            cur.execute(f"SELECT hypertable_size('{table}')")  # noqa: S608
            size_row = cur.fetchone()
            if size_row and size_row[0] is not None:
                size_bytes = int(size_row[0])
        except Exception as e:
            logger.debug("[UI Utils] hypertable_size 실패: %s", e)

        if size_bytes == 0:
            try:
                cur.execute(f"SELECT pg_total_relation_size('{table}')")  # noqa: S608
                size_row = cur.fetchone()
                if size_row and size_row[0] is not None:
                    size_bytes = int(size_row[0])
            except Exception as e:
                logger.debug("[UI Utils] pg_total_relation_size 실패: %s", e)

        # 최신 시간
        latest_time = None
        try:
            cur.execute(f"SELECT MAX(time) FROM {table}")  # noqa: S608
            latest_row = cur.fetchone()
            latest_time = (
                latest_row[0] if latest_row and latest_row[0] is not None else None
            )
        except Exception as e:
            logger.debug("[UI Utils] MAX(time) 조회 실패: %s", e)

        return {
            "table": table,
            "row_count": row_count,
            "size_bytes": size_bytes,
            "size_human": format_bytes(size_bytes),
            "latest_time": latest_time,
        }
    except Exception as e:
        logger.debug("[UI Utils] get_table_stats(%s) 실패: %s", table, e)
        return {}
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception as close_exc:
                logger.debug("[UI Utils] cursor close error: %s", close_exc)
        if conn is not None:
            try:
                connector.put_connection(conn)
            except Exception as put_exc:
                logger.debug("[UI Utils] put_connection error: %s", put_exc)


# processor 탐색 결과 캐시 (60초 TTL — 매 호출마다 sys.modules 전체 탐색 방지)
import time as _time_module
_processor_cache: Optional[Any] = None
_processor_cache_ts: float = 0.0
_PROCESSOR_CACHE_TTL: float = 60.0

_PROC_ATTRS = ("processor", "_processor", "instance", "_instance", "PROCESSOR")
_PROC_MARKERS = frozenset(("_total_received", "stager", "_stager", "_total_processed"))


def _find_processor_in_modules() -> Optional[Any]:
    """sys.modules 전체에서 pipeline processor 인스턴스를 탐색합니다.

    탐색 결과를 _PROCESSOR_CACHE_TTL 초 동안 캐싱하여 반복 탐색 비용을 절감합니다.

    Returns:
        발견된 processor 객체 또는 None
    """
    global _processor_cache, _processor_cache_ts
    import sys

    now = _time_module.monotonic()
    if _processor_cache is not None and now - _processor_cache_ts < _PROCESSOR_CACHE_TTL:
        return _processor_cache

    # list()로 복사하여 이터레이션 중 모듈 추가로 인한 RuntimeError 방지
    for mod_name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        name_lower = mod_name.lower()
        if "pipeline" not in name_lower and "processor" not in name_lower:
            continue
        mod_dict = getattr(mod, "__dict__", {})
        for attr_name in _PROC_ATTRS:
            obj = mod_dict.get(attr_name)
            if obj is None:
                continue
            obj_dict = getattr(obj, "__dict__", {})
            if not _PROC_MARKERS.isdisjoint(obj_dict):
                logger.debug(
                    "[UI Utils] ✅ processor found in %s.%s (%s)",
                    mod_name, attr_name, type(obj).__name__,
                )
                _processor_cache = obj
                _processor_cache_ts = now
                return obj
    return None


def _safe_int(val: Any) -> int:
    """값을 안전하게 int로 변환합니다. 변환 불가 시 0 반환."""
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def get_pipeline_stats() -> Dict[str, int]:
    """파이프라인 테이블 레코드 수 조회 (v2.0).

    반환값:
        {"staging": int, "candles": int, "isolated": int, "isolated_recent": int}

    조회 순서:
        1순위: pipeline processor 인스턴스 직접 접근 (sys.modules 탐색)
        2순위: staging → Redis 다중 패턴 시도 → 0이면 TimescaleDB 폴백
        3순위: candles → TimescaleDB → MongoDB 폴백
        4순위: isolated → TimescaleDB (전체 누적 + 최근 1시간)
    """
    result: Dict[str, int] = {"staging": 0, "candles": 0, "isolated": 0, "isolated_recent": 0}

    # ============================================================
    # 1순위: processor 직접 접근 (DB 조회 불필요 시)
    # ============================================================
    try:
        processor = _find_processor_in_modules()
        if processor is not None:
            # staging 카운트: stager 속성 탐색 (or 대신 명시적 None 체크)
            stager = getattr(processor, "stager", None)
            if stager is None:
                stager = getattr(processor, "_stager", None)
            if stager is not None:
                for attr in ("count", "_count", "staging_count", "_staging_count"):
                    val = _safe_int(getattr(stager, attr, None))
                    if val > 0:
                        result["staging"] = val
                        break
            # candles 카운트: 누적 수신/처리 건수
            for attr in ("_total_received", "_total_processed", "total_received", "total_processed"):
                val = _safe_int(getattr(processor, attr, None))
                if val > 0:
                    result["candles"] = val
                    break
            if result["staging"] > 0 or result["candles"] > 0:
                logger.debug(
                    "[UI Utils] ✅ processor 직접 접근: staging=%d, candles=%d",
                    result["staging"], result["candles"],
                )
    except Exception as exc:
        logger.debug("[UI Utils] processor 직접 접근 실패: %s", exc)

    # ============================================================
    # 2. Staging 카운트 — Redis 다중 패턴 시도 (processor에서 0인 경우)
    # ============================================================
    if result["staging"] == 0:
        try:
            rc = get_redis_connector()
            if rc is not None:
                staging_count = 0
                for pattern in ("staging_candles:*", "staging:*", "candle:staging:*"):
                    keys = rc.keys(pattern)
                    if keys:
                        staging_count = len(keys)
                        break
                result["staging"] = staging_count
                logger.debug("[UI Utils] ✅ Staging 카운트 (Redis): %d", result["staging"])
            else:
                logger.debug("[UI Utils] Redis 커넥터 없음 - Staging=0")
        except Exception as exc:
            logger.debug("[UI Utils] Staging Redis 카운트 실패: %s", exc)

    # Redis에서 0이면 TimescaleDB staging_candles 직접 조회
    if result["staging"] == 0:
        _staging_connector = get_timescale_connector()
        if _staging_connector is not None:
            _staging_conn = None
            _staging_cur = None
            try:
                _staging_conn = _staging_connector.get_connection(retry=False)
                _staging_cur = _staging_conn.cursor()
                _staging_cur.execute("SELECT COUNT(*) FROM staging_candles")
                _staging_row = _staging_cur.fetchone()
                if _staging_row and _staging_row[0] is not None:
                    result["staging"] = int(_staging_row[0])
            except Exception as exc:
                logger.debug("[UI Utils] staging_candles 카운트 실패: %s", exc)
            finally:
                if _staging_cur is not None:
                    try:
                        _staging_cur.close()
                    except Exception as e:
                        logger.debug("[UI Utils] cursor close: %s", e)
                if _staging_conn is not None:
                    try:
                        _staging_connector.put_connection(_staging_conn)
                    except Exception as e:
                        logger.debug("[UI Utils] put_connection: %s", e)

    # ============================================================
    # 2. Candles 카운트 (TimescaleDB → MongoDB fallback)
    # ============================================================
    _candles_conn = None
    _candles_cur = None
    _candles_connector = None
    candles_success = False

    try:
        _candles_connector = get_timescale_connector()
        if _candles_connector is not None:
            _candles_conn = _candles_connector.get_connection(retry=False)
            _candles_cur = _candles_conn.cursor()
            _candles_cur.execute("SELECT COUNT(*) FROM candles")
            row = _candles_cur.fetchone()
            if row and row[0] is not None:
                result["candles"] = int(row[0])
                candles_success = True
                logger.debug(
                    "[UI Utils] ✅ Candles 카운트 (TimescaleDB): %d", result["candles"]
                )
    except Exception as exc:
        logger.debug("[UI Utils] TimescaleDB candles 조회 실패: %s", exc)
    finally:
        if _candles_cur is not None:
            try:
                _candles_cur.close()
            except Exception as e:
                logger.debug("[UI Utils] cursor close: %s", e)
        if _candles_conn is not None and _candles_connector is not None:
            try:
                _candles_connector.put_connection(_candles_conn)
            except Exception as e:
                logger.debug("[UI Utils] put_connection: %s", e)

    # MongoDB fallback
    if not candles_success:
        try:
            client = get_mongo_sync_client()
            if client is not None:
                db = client.get_database("upbit_trader")
                result["candles"] = db.candles.estimated_document_count()
                logger.debug(
                    "[UI Utils] ✅ Candles 카운트 (MongoDB fallback): %d", result["candles"]
                )
        except Exception as exc:
            logger.debug("[UI Utils] MongoDB candles 조회 실패: %s", exc)

    # ============================================================
    # 3. Isolated 카운트 (TimescaleDB)
    # ============================================================
    _iso_conn = None
    _iso_cur = None
    _iso_connector = None
    try:
        _iso_connector = get_timescale_connector()
        if _iso_connector is not None:
            _iso_conn = _iso_connector.get_connection(retry=False)
            _iso_cur = _iso_conn.cursor()
            _iso_cur.execute("SELECT COUNT(*) FROM isolated_candles")
            row = _iso_cur.fetchone()
            if row and row[0] is not None:
                result["isolated"] = int(row[0])
                logger.debug(
                    "[UI Utils] ✅ Isolated 카운트 (TimescaleDB): %d", result["isolated"]
                )
            # 최근 1시간 격리 건수
            try:
                _iso_cur.execute(
                    "SELECT COUNT(*) FROM isolated_candles"
                    " WHERE received_at >= NOW() - INTERVAL '1 hour'"
                )
                row_recent = _iso_cur.fetchone()
                if row_recent and row_recent[0] is not None:
                    result["isolated_recent"] = int(row_recent[0])
                    logger.debug(
                        "[UI Utils] ✅ Isolated 최근 1시간 카운트: %d",
                        result["isolated_recent"],
                    )
            except Exception as exc:
                logger.debug("[UI Utils] Isolated 최근 1시간 카운트 실패: %s", exc)
    except Exception as exc:
        logger.debug("[UI Utils] Isolated 카운트 실패: %s", exc)
    finally:
        if _iso_cur is not None:
            try:
                _iso_cur.close()
            except Exception as e:
                logger.debug("[UI Utils] cursor close: %s", e)
        if _iso_conn is not None and _iso_connector is not None:
            try:
                _iso_connector.put_connection(_iso_conn)
            except Exception as e:
                logger.debug("[UI Utils] put_connection: %s", e)

    logger.info(
        "[UI Utils] 🎉 get_pipeline_stats 완료: staging=%d, candles=%d, isolated=%d, isolated_recent=%d",
        result["staging"],
        result["candles"],
        result["isolated"],
        result["isolated_recent"],
    )

    # processor fallback: candles가 여전히 0이면 static.processor에서 직접 조회
    if result["candles"] == 0:
        _proc_stats = _get_pipeline_stats_from_processor()
        if _proc_stats:
            # staging은 덮어쓰지 않음 (이미 Redis/TimescaleDB 값이 있을 수 있음)
            if result["staging"] == 0:
                result["staging"] = _proc_stats.get("staging", 0)
            result["candles"] = _proc_stats.get("candles", 0)
            logger.debug("[UI Utils] processor fallback 적용: %s", _proc_stats)

    return result


def _get_pipeline_stats_from_processor() -> Optional[Dict[str, int]]:
    """static.processor 객체에서 직접 파이프라인 통계 조회.

    Returns:
        통계 딕셔너리 또는 None
    """
    try:
        from .module_finder import _find_static_module
        static = _find_static_module()
        if static is None:
            return None
        processor = getattr(static, "processor", None)
        if processor is None:
            return None
        stats: Dict[str, int] = {}
        # 누적 수신/처리 건수
        total_received = getattr(processor, "_total_received", None)
        total_processed = getattr(processor, "_total_processed", None)
        if total_received is not None:
            stats["candles"] = int(total_received)
        elif total_processed is not None:
            stats["candles"] = int(total_processed)
        # stager에서 staging 카운트
        stager = getattr(processor, "_stager", None) or getattr(processor, "stager", None)
        if stager is not None:
            stager_count = getattr(stager, "_count", None) or getattr(stager, "count", None)
            if stager_count is not None:
                stats["staging"] = int(stager_count)
        return stats if stats else None
    except Exception as e:
        logger.debug("[UI Utils] processor fallback 실패: %s", e)
        return None


def get_cache_stats() -> Dict[str, Any]:
    """Redis 캐시 상태 조회 (L1 캐시 항목수, Pub/Sub 채널수).

    Returns:
        {"l1_count": int, "pubsub_channels": int}
    """
    result: Dict[str, Any] = {"l1_count": 0, "pubsub_channels": 0}
    try:
        rc = get_redis_connector()
        if rc is None:
            return result
        # L1 캐시 항목 수: candle:*, ticker:*, cache:*, l1:* 패턴 순차 시도
        for pattern in ("candle:*", "ticker:*", "cache:*", "l1:*"):
            try:
                keys = rc.keys(pattern)
                if keys:
                    result["l1_count"] = len(keys)
                    break
            except Exception:
                pass
        # 아무 패턴도 없으면 전체 dbsize
        if result["l1_count"] == 0:
            try:
                result["l1_count"] = int(rc.dbsize() or 0)
            except Exception:
                pass
        # Pub/Sub 채널 수
        try:
            channels = rc.pubsub_channels()
            result["pubsub_channels"] = len(channels) if channels else 0
        except Exception as e:
            logger.debug("[UI Utils] Pub/Sub 채널 조회 실패: %s", e)
    except Exception as e:
        logger.debug("[UI Utils] get_cache_stats 실패: %s", e)
    return result
