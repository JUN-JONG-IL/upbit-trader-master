# -*- coding: utf-8 -*-
"""
Gap Backfill Worker

목적:
- Redis ZSET(gap_fill_queue)에서 gap_event를 pop(zpopmax)하거나 peek(zrange)하여
  작업을 클레임(SETNX)하고 처리합니다.
- 처리 방법: gap_event.start ~ gap_event.end 범위에서 업비트 REST API로 1분봉 데이터 조회 후
  candles 테이블에 idempotent(ON CONFLICT DO NOTHING)하게 삽입합니다.
- 실패/예외 시 DLQ에 적재하고 재시도 카운트(increment)를 관리합니다.
- 워커 상태를 Redis에 저장하여 UI에서 모니터링 가능합니다.

사용법(비동기 CLI):
    python -m src.02_data.gap.worker --once --redis-url "redis://:dummy@127.0.0.1:58530/0" --timescale-dsn "postgresql://postgres:postgres@localhost:58529/upbit_trader"

구성(환경변수 또는 인자):
- --redis-url
- --timescale-dsn
- --zset-key (기본 gap_fill_queue)
- --dlq-key (기본 gap_dlq)
- --claim-ttl (초, 기본 300)
- --max-candles-per-page (페이지당 최대 캔들 수, 기본 200)
- --max-pages (최대 페이지 수, 기본 100: 약 3.3일)

모든 주석은 한글입니다.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

try:
    import orjson  # type: ignore
    def _json_dumps(obj: Any) -> str:
        return orjson.dumps(obj).decode("utf-8")
    def _json_loads(s: Any) -> Any:
        return orjson.loads(s)
except ImportError:
    def _json_dumps(obj: Any) -> str:  # type: ignore[misc]
        return json.dumps(obj, ensure_ascii=False, default=str)
    def _json_loads(s: Any) -> Any:  # type: ignore[misc]
        if isinstance(s, (bytes, bytearray)):
            s = s.decode("utf-8")
        return json.loads(s)

logger = logging.getLogger("gap.worker")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(h)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# 기본 키
DEFAULT_ZSET_KEY = os.environ.get("GAP_ZSET_KEY", "gap_fill_queue")
DEFAULT_DLQ_KEY = os.environ.get("GAP_DLQ_KEY", "gap_dlq")
DEFAULT_CLAIM_TTL = int(os.environ.get("GAP_CLAIM_TTL", "300"))  # seconds
DEFAULT_MAX_CANDLES_PER_PAGE = int(os.environ.get("GAP_MAX_CANDLES_PER_PAGE", "200"))
DEFAULT_MAX_PAGES = int(os.environ.get("GAP_MAX_PAGES", "100"))  # 최대 페이지(안전 차단)

# 업비트 REST API 엔드포인트
UPBIT_CANDLE_API_URL = "https://api.upbit.com/v1/candles/minutes/{unit}"

# 업비트 API 속도 제한 준수 (최대 10req/s → 0.12초 간격)
UPBIT_API_DELAY_SECONDS = 0.12

# Redis 상태 키
REDIS_KEY_WORKER_STATUS = "gap:worker:status"
REDIS_KEY_WORKER_GRACE_PERIOD = "gap:worker:grace_period"
REDIS_KEY_WORKER_COUNT = "gap:worker:count"
WORKER_GRACE_PERIOD_SECONDS = 30


def _get_default_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530, password=dummy)"""
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parents[3] / "01_core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_gw", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"


# ---------------------------
# 클라이언트 생성 헬퍼
# ---------------------------
async def _create_redis(redis_url: str) -> Optional[Any]:
    """비동기 Redis 클라이언트 생성."""
    try:
        mod = importlib.import_module("redis.asyncio")
        Redis = getattr(mod, "Redis")
        client = Redis.from_url(redis_url, decode_responses=False)
        await client.ping()
        logger.debug("[worker] redis.asyncio 연결 성공")
        return client
    except Exception:
        try:
            mod = importlib.import_module("aioredis")
            client = getattr(mod, "from_url")(redis_url)
            await client.ping()
            logger.debug("[worker] aioredis 연결 성공")
            return client
        except Exception:
            logger.exception("[worker] Redis 연결 실패")
            return None


async def _create_pool(timescale_dsn: Optional[str]) -> Optional[Any]:
    """asyncpg 연결 풀 생성."""
    if not timescale_dsn:
        logger.warning("[worker] timescale_dsn 미지정 - DB 연동 비활성")
        return None
    try:
        mod = importlib.import_module("asyncpg")
        pool = await mod.create_pool(timescale_dsn)
        logger.debug("[worker] asyncpg pool 생성 성공")
        return pool
    except Exception:
        logger.exception("[worker] asyncpg pool 생성 실패")
        return None


# ---------------------------
# 업비트 REST API 호출 헬퍼
# ---------------------------
async def _fetch_upbit_candles(
    symbol: str,
    to: str,
    unit: int = 1,
    count: int = 200,
) -> List[Dict[str, Any]]:
    """업비트 REST API에서 분봉 캔들 데이터를 조회합니다.

    Args:
        symbol:  업비트 마켓 코드 (예: KRW-BTC)
        to:      조회 기준 시각 (ISO 8601, 해당 시각 이전 데이터 반환)
        unit:    분봉 단위 (1, 3, 5, 15, 30, 60, 240)
        count:   조회 건수 (최대 200)

    Returns:
        업비트 API 응답 딕셔너리 목록 (최신 → 과거 순서)
    """
    try:
        import aiohttp  # type: ignore
    except ImportError:
        logger.error("[worker] aiohttp 미설치 — pip install aiohttp")
        return []

    url = UPBIT_CANDLE_API_URL.format(unit=unit)
    params = {"market": symbol, "count": count, "to": to}
    headers = {"Accept": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning("[worker] 업비트 API 응답 이상: status=%d symbol=%s", resp.status, symbol)
                    return []
                data = await resp.json(content_type=None)
                return data if isinstance(data, list) else []
    except Exception as exc:
        logger.error("[worker] 업비트 API 호출 실패: symbol=%s err=%s", symbol, exc)
        return []


# ---------------------------
# DB 삽입 헬퍼 (idempotent)
# ---------------------------
INSERT_CANDLE_SQL = """
INSERT INTO candles
    (time, symbol, timeframe, exchange, open, high, low, close, volume, quote_volume, trade_count)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
ON CONFLICT (time, symbol, timeframe) DO NOTHING;
"""


async def _insert_candles_batch(
    pool: Any,
    rows: List[tuple],
) -> int:
    """candles 테이블에 배치 삽입(idempotent).

    Args:
        pool: asyncpg 연결 풀
        rows: (time, symbol, timeframe, exchange, open, high, low, close, volume, quote_volume, trade_count) 튜플 목록

    Returns:
        삽입된 행 수 (추정)
    """
    if pool is None or not rows:
        return 0
    try:
        async with pool.acquire() as conn:
            await conn.executemany(INSERT_CANDLE_SQL, rows)
        return len(rows)
    except Exception as exc:
        logger.exception("[worker] candles 배치 삽입 실패: %s", exc)
        return 0


def _parse_timeframe_unit(timeframe: str) -> int:
    """타임프레임 문자열을 분 단위로 변환합니다."""
    tf_map = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15,
        "30m": 30, "1h": 60, "4h": 240, "1d": 1440,
    }
    return tf_map.get(timeframe, 1)


# ---------------------------
# Gap 처리 로직(클레임/실행/DLQ)
# ---------------------------
class GapWorker:
    """Gap 백필 워커 — 업비트 REST API 실제 호출 버전."""

    def __init__(
        self,
        redis_url: str,
        timescale_dsn: Optional[str],
        zset_key: str = DEFAULT_ZSET_KEY,
        dlq_key: str = DEFAULT_DLQ_KEY,
        claim_ttl: int = DEFAULT_CLAIM_TTL,
        max_candles_per_page: int = DEFAULT_MAX_CANDLES_PER_PAGE,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        self.redis_url = redis_url
        self.timescale_dsn = timescale_dsn
        self.zset_key = zset_key
        self.dlq_key = dlq_key
        self.claim_ttl = claim_ttl
        self.max_candles_per_page = min(max_candles_per_page, 200)
        self.max_pages = max_pages

        self._redis: Optional[Any] = None
        self._pool: Optional[Any] = None
        self._processed_count = 0

    async def start(self) -> None:
        """Redis 및 DB 연결을 초기화합니다."""
        self._redis = await _create_redis(self.redis_url)
        self._pool = await _create_pool(self.timescale_dsn)
        await self._save_worker_status(running=True)

    async def stop(self) -> None:
        """워커를 종료하고 리소스를 해제합니다."""
        await self._save_worker_status(running=False)
        try:
            if self._redis is not None:
                if hasattr(self._redis, "aclose"):
                    res = self._redis.aclose()
                    if asyncio.iscoroutine(res):
                        await res
                elif hasattr(self._redis, "close"):
                    res = self._redis.close()
                    if asyncio.iscoroutine(res):
                        await res
        except Exception:
            logger.debug("[worker] redis 종료 중 예외", exc_info=True)
        try:
            if self._pool is not None:
                await self._pool.close()
        except Exception:
            logger.debug("[worker] pool 종료 중 예외", exc_info=True)

    async def _save_worker_status(self, running: bool) -> None:
        """워커 상태를 Redis에 저장합니다 (UI 모니터링용).

        저장 키:
            gap:worker:status       — {"running": bool, "processed": int, "last_processed": ISO str}
            gap:worker:grace_period — 유예 기간(초)
            gap:worker:count        — 활성 워커 수
        """
        if self._redis is None:
            return
        try:
            status_obj = {
                "running": running,
                "processed": self._processed_count,
                "last_processed": datetime.now(tz=timezone.utc).isoformat(),
            }
            await self._redis.set(REDIS_KEY_WORKER_STATUS, _json_dumps(status_obj), ex=180)
            await self._redis.set(REDIS_KEY_WORKER_GRACE_PERIOD, str(WORKER_GRACE_PERIOD_SECONDS), ex=180)
            await self._redis.set(REDIS_KEY_WORKER_COUNT, "1" if running else "0", ex=180)
        except Exception as exc:
            logger.debug("[worker] 상태 저장 실패(무시): %s", exc)

    async def _zpopmax_once(self) -> List[Any]:
        """ZPOPMAX로 가장 우선순위 높은 항목 1개를 꺼냅니다."""
        if self._redis is None:
            return []
        try:
            if hasattr(self._redis, "zpopmax"):
                res = await self._redis.zpopmax(self.zset_key, count=1)
                if not res:
                    return []
                return res
            else:
                # fallback: zrange with scores then zrem
                items = await self._redis.zrange(self.zset_key, -1, -1, withscores=True)
                if not items:
                    return []
                member, score = items[-1]
                await self._redis.zrem(self.zset_key, member)
                return [(member, score)]
        except Exception:
            logger.exception("[worker] zpopmax 실패")
            return []

    async def _claim_job(self, job_id: str) -> bool:
        """SETNX로 작업을 클레임합니다. 이미 클레임된 경우 False 반환."""
        if self._redis is None:
            return False
        key = f"gap:claim:{job_id}"
        try:
            res = await self._redis.set(key, b"1", nx=True, ex=self.claim_ttl)
            return bool(res)
        except Exception:
            logger.exception("[worker] claim 실패")
            return False

    async def _release_claim(self, job_id: str) -> None:
        """클레임 키를 삭제합니다."""
        if self._redis is None:
            return
        key = f"gap:claim:{job_id}"
        try:
            await self._redis.delete(key)
        except Exception:
            logger.debug("[worker] claim 삭제 실패", exc_info=True)

    async def _move_to_dlq(self, gap_event: Dict[str, Any], reason: str) -> None:
        """실패 항목을 DLQ에 push합니다."""
        if self._redis is None:
            return
        try:
            gap_event["attempts"] = int(gap_event.get("attempts", 0)) + 1
            gap_event["last_error"] = reason
            member = _json_dumps(gap_event)
            await self._redis.lpush(self.dlq_key, member)
            logger.warning("[worker] 작업 DLQ 이동: job_id=%s reason=%s", gap_event.get("job_id"), reason)
        except Exception:
            logger.exception("[worker] DLQ 적재 실패")

    async def _process_gap_event(self, gap_event: Dict[str, Any]) -> bool:
        """실제 업비트 REST API를 호출하여 Gap 구간의 캔들 데이터를 백필합니다.

        역방향 페이지네이션:
            end → start 방향으로 UPBIT_CANDLE_API_URL 호출,
            candles 테이블에 ON CONFLICT DO NOTHING으로 삽입.

        Args:
            gap_event: Gap 이벤트 딕셔너리 (job_id, symbol, timeframe, start, end 포함)

        Returns:
            성공 여부
        """
        try:
            symbol: str = gap_event["symbol"]
            timeframe: str = gap_event.get("timeframe", "1m")
            start_str: str = gap_event.get("start", "")
            end_str: str = gap_event.get("end", "")
        except KeyError as exc:
            logger.error("[worker] gap_event 필드 누락: %s", exc)
            return False

        # 시간 파싱
        try:
            start_dt = datetime.fromisoformat(start_str) if start_str else None
            end_dt = datetime.fromisoformat(end_str) if end_str else datetime.now(tz=timezone.utc)
        except Exception as exc:
            logger.error("[worker] 시각 파싱 실패: %s", exc)
            return False

        unit = _parse_timeframe_unit(timeframe)
        inserted_total = 0
        page_count = 0
        cursor_to = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

        # 역방향 페이지네이션 (end → start)
        while page_count < self.max_pages:
            candles = await _fetch_upbit_candles(
                symbol=symbol,
                to=cursor_to,
                unit=unit,
                count=self.max_candles_per_page,
            )
            if not candles:
                logger.info("[worker] 업비트 API 응답 없음 — 백필 종료: symbol=%s", symbol)
                break

            rows: List[tuple] = []
            oldest_ts: Optional[datetime] = None

            for c in candles:
                try:
                    # 업비트 API 응답 필드 매핑
                    ts_str = c.get("candle_date_time_utc") or c.get("timestamp", "")
                    if not ts_str:
                        continue
                    # ISO 8601 파싱 (Python 3.7+는 'Z' 미지원 → rstrip 처리)
                    if isinstance(ts_str, str):
                        ts = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                    else:
                        ts = datetime.fromtimestamp(ts_str / 1000, tz=timezone.utc)

                    rows.append((
                        ts,
                        symbol,
                        timeframe,
                        "upbit",
                        float(c.get("opening_price", 0)),
                        float(c.get("high_price", 0)),
                        float(c.get("low_price", 0)),
                        float(c.get("trade_price", 0)),
                        float(c.get("candle_acc_trade_volume", 0)),
                        float(c.get("candle_acc_trade_price", 0)),
                        0,  # Upbit 분봉 API는 trade_count 미제공
                    ))

                    if oldest_ts is None or ts < oldest_ts:
                        oldest_ts = ts
                except Exception as row_exc:
                    logger.debug("[worker] 행 파싱 오류(무시): %s", row_exc)

            if rows:
                n = await _insert_candles_batch(self._pool, rows)
                inserted_total += n
                logger.debug("[worker] 페이지 %d: %d행 삽입 (symbol=%s)", page_count + 1, n, symbol)

            page_count += 1

            # start_dt에 도달했으면 종료
            if start_dt is not None and oldest_ts is not None and oldest_ts <= start_dt:
                break

            # 다음 페이지: 가장 오래된 캔들 시각을 기준으로 재조회
            if oldest_ts is not None:
                cursor_to = oldest_ts.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                break

            # API 속도 제한 준수 (Upbit: 최대 10req/s → UPBIT_API_DELAY_SECONDS 간격)
            await asyncio.sleep(UPBIT_API_DELAY_SECONDS)

        logger.info(
            "[worker] 백필 완료: job_id=%s symbol=%s inserted=%d pages=%d",
            gap_event.get("job_id"), symbol, inserted_total, page_count,
        )
        return True

    async def claim_and_process_once(self) -> bool:
        """큐에서 한 작업을 꺼내 클레임하고 처리합니다.

        Returns:
            작업을 처리했으면 True, 큐가 비었거나 스킵했으면 False
        """
        items = await self._zpopmax_once()
        if not items:
            logger.debug("[worker] 처리할 gap 없음")
            return False

        member, score = items[0]
        try:
            if isinstance(member, (bytes, bytearray)):
                member = member.decode("utf-8")
            gap_event = _json_loads(member)
        except Exception:
            logger.exception("[worker] gap_event 파싱 실패 - 스킵")
            return False

        job_id = gap_event.get("job_id")
        if not job_id:
            logger.warning("[worker] job_id 없음 - 스킵 (isolator.py의 _enqueue_gap() 확인 필요)")
            return False

        # 클레임
        claimed = await self._claim_job(job_id)
        if not claimed:
            logger.info("[worker] 이미 클레임된 작업, 스킵: job_id=%s", job_id)
            return False

        try:
            ok = await self._process_gap_event(gap_event)
            if ok:
                self._processed_count += 1
                await self._save_worker_status(running=True)
                logger.info("[worker] job 처리 성공: job_id=%s", job_id)
            else:
                await self._move_to_dlq(gap_event, "process_failed")
        except Exception as exc:
            logger.exception("[worker] job 처리 중 예외")
            await self._move_to_dlq(gap_event, f"exception:{exc}")
        finally:
            await self._release_claim(job_id)
        return True

    async def run_once(self) -> None:
        """단일 작업을 처리하고 종료합니다."""
        await self.start()
        try:
            await self.claim_and_process_once()
        finally:
            await self.stop()

    async def run_loop(self, poll_interval: float = 5.0) -> None:
        """큐가 빌 때까지 연속 처리합니다."""
        await self.start()
        last_heartbeat = time.monotonic()
        try:
            while True:
                try:
                    has = await self.claim_and_process_once()
                    if not has:
                        await asyncio.sleep(poll_interval)
                    # 60초마다 heartbeat 갱신 (idle 상태에서도 상태 키 만료 방지)
                    now = time.monotonic()
                    if now - last_heartbeat >= 60.0:
                        await self._save_worker_status(running=True)
                        last_heartbeat = now
                except Exception:
                    logger.exception("[worker] 루프 처리 중 예외")
                    await asyncio.sleep(poll_interval)
        finally:
            await self.stop()


# ---------------------------
# PyQt5 연동용 백그라운드 스레드
# ---------------------------
class GapWorkerThread(threading.Thread):
    """GapWorker를 별도 스레드에서 실행하는 래퍼 (PyQt5 앱 연동용).

    사용 예:
        thread = GapWorkerThread(redis_url=..., timescale_dsn=...)
        thread.start()
        # 앱 종료 시:
        thread.stop()
        thread.join(timeout=10)
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        timescale_dsn: Optional[str] = None,
        poll_interval: float = 5.0,
        **worker_kwargs: Any,
    ) -> None:
        super().__init__(name="GapWorkerThread", daemon=True)
        self._redis_url = redis_url or _get_default_redis_url()
        self._timescale_dsn = timescale_dsn or os.environ.get("TIMESCALE_DSN", "")
        self._poll_interval = poll_interval
        self._worker_kwargs = worker_kwargs
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = threading.Event()

    def run(self) -> None:
        """스레드 진입점 — 새 이벤트 루프에서 GapWorker.run_loop() 실행."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        worker = GapWorker(
            redis_url=self._redis_url,
            timescale_dsn=self._timescale_dsn,
            **self._worker_kwargs,
        )
        try:
            self._loop.run_until_complete(worker.run_loop(self._poll_interval))
        except Exception:
            logger.exception("[GapWorkerThread] 루프 종료")
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    def stop(self) -> None:
        """스레드 종료를 요청합니다."""
        self._stop_event.set()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)


# ---------------------------
# CLI
# ---------------------------
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gap Backfill Worker (업비트 REST API 실제 호출)")
    p.add_argument("--once", action="store_true", help="한 번만 실행")
    p.add_argument("--redis-url", type=str, default=os.environ.get("REDIS_URL") or _get_default_redis_url())
    p.add_argument("--timescale-dsn", type=str, default=os.environ.get("TIMESCALE_DSN", ""))
    p.add_argument("--zset-key", type=str, default=DEFAULT_ZSET_KEY)
    p.add_argument("--dlq-key", type=str, default=DEFAULT_DLQ_KEY)
    p.add_argument("--claim-ttl", type=int, default=DEFAULT_CLAIM_TTL)
    p.add_argument("--max-candles-per-page", type=int, default=DEFAULT_MAX_CANDLES_PER_PAGE)
    p.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    worker = GapWorker(
        redis_url=args.redis_url,
        timescale_dsn=args.timescale_dsn,
        zset_key=args.zset_key,
        dlq_key=args.dlq_key,
        claim_ttl=args.claim_ttl,
        max_candles_per_page=args.max_candles_per_page,
        max_pages=args.max_pages,
    )
    if args.once:
        asyncio.run(worker.run_once())
    else:
        try:
            asyncio.run(worker.run_loop())
        except KeyboardInterrupt:
            logger.info("[worker] 사용자 중단으로 종료")


if __name__ == "__main__":
    main()
