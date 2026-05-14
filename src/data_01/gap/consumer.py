# -*- coding: utf-8 -*-
"""
Gap job 소비자(consumer) 워커 - 단일 파일 PoC

기능 요약:
- Redis ZSET (gap_fill_queue)에서 우선순위가 가장 높은 job을 안전하게 추출(ZPOPMAX 시도, 실패 시 fallback)
- job JSON 파싱 및 멱등성/claim 처리:
    - claim 키: gap:claim:{job_id} (SET NX PX 으로 단일 워커 소유)
    - processed 키: gap:processed:{job_id} (중복 처리 방지)
- 처리 로직(백필)은 PoC 수준의 스텁으로 구현되어 있으며,
  실제 환경에��는 Kafka replay / 거래소 REST / S3 재생 중 하나로 대체해야 함.
- 처리 성공 시 processed 키를 설정하고 로그 기록.
- 처리 실패 시 attempts를 증가시켜 재큐(지수적 백오프 점수)하거나 DLQ에 이동.
- 안전 종료, 리소스 정리 지원, 다양한 redis 클라이언트 호환(redis.asyncio / aioredis)

사용법:
- 단발성 실행(한 번만 처리):
    python -m src.data_01.gap.consumer --once --redis-url "redis://:dummy@127.0.0.1:58530/0" --timescale-dsn "<DSN>"
- 데몬 모드:
    python -m src.data_01.gap.consumer --redis-url "redis://:dummy@127.0.0.1:58530/0" --timescale-dsn "<DSN>"

주의:
- 실제 백필 로직은 stub입니다. production 통합 전에 재생(restore) 소스를 구현하세요.
- 모든 주석은 한글입니다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import hashlib
from typing import Any, Dict, Optional

import orjson  # type: ignore

logger = logging.getLogger("gap.consumer")


def _get_default_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530, password=dummy)"""
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parents[3] / "01_core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_gc", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"


# Redis 키/설정
ZSET_KEY = "gap_fill_queue"
CLAIM_KEY_PREFIX = "gap:claim:"       # claim key: gap:claim:{job_id}
PROCESSED_KEY_PREFIX = "gap:processed:"  # processed key: gap:processed:{job_id}
DLQ_LIST = "gap_fill_dlq"             # 실패/영구실패 job 보관 리스트

# Claim 만료(ms)
CLAIM_TTL_MS = 60_000  # 60초 기본

# 재시도 제한
MAX_ATTEMPTS = 5

# 재큐 기본 가중치(우선순위 스케일 보정)
REQUEUE_BASE_DELAY = 30  # 초


class RedisCompat:
    """
    간단한 Redis 호환 레이어(읽기/쓰기/claim/zpop 지원)
    - redis.asyncio 또는 aioredis 둘 다 지원(권장: redis.asyncio)
    """
    def __init__(self, client: Any):
        self._client = client

    # ZPOPMAX wrapper: 반환 형식 통일
    async def zpopmax(self, name: str, count: int = 1):
        """
        시도 순서:
        - redis-py(>=4) / redis.asyncio: await client.zpopmax(name, count)
        - aioredis: await client.zpopmax(name, count)
        - fallback: zrevrange + zrem
        반환: list of tuples [(member_str, score_float), ...]
        """
        try:
            # 표준: redis.asyncio
            res = await self._client.zpopmax(name, count)
            # redis-py returns list of (member, score) where member is bytes or str
            return res
        except Exception:
            # fallback: zrevrange + zrem
            try:
                members = await self._client.zrevrange(name, 0, count - 1, withscores=True)
                if not members:
                    return []
                # 멤버 제거
                # aioredis/redis-py 차이에 대응: zrem accepts *members or single
                keys = [m for (m, s) in members]
                try:
                    await self._client.zrem(name, *keys)
                except TypeError:
                    # some clients expect different signature
                    for k in keys:
                        await self._client.zrem(name, k)
                return members
            except Exception:
                logger.exception("[RedisCompat] zpopmax/fallback 실패")
                return []

    async def set_claim(self, key: str, value: str, px: int) -> bool:
        """
        claim 설정: SET key value NX PX px
        반환 True이면 claim 성공
        """
        try:
            # redis.asyncio / redis-py interface
            res = await self._client.set(key, value, nx=True, px=px)
            return bool(res)
        except TypeError:
            # fallback: older signature may not support keywords
            try:
                res = await self._client.execute_command("SET", key, value, "NX", "PX", str(px))
                return res == b"OK" or res == "OK"
            except Exception:
                logger.exception("[RedisCompat] set_claim 폴백 실패")
                return False
        except Exception:
            logger.exception("[RedisCompat] set_claim 실패")
            return False

    async def get(self, key: str) -> Optional[bytes]:
        try:
            return await self._client.get(key)
        except Exception:
            logger.debug("[RedisCompat] get 실패", exc_info=True)
            return None

    async def set(self, key: str, value: str, ex: Optional[int] = None):
        try:
            await self._client.set(key, value, ex=ex)
        except Exception:
            logger.debug("[RedisCompat] set 실패", exc_info=True)

    async def rpush(self, key: str, value: str):
        try:
            await self._client.rpush(key, value)
        except Exception:
            logger.exception("[RedisCompat] rpush 실패")

    async def zadd(self, name: str, mapping: dict):
        try:
            await self._client.zadd(name, mapping)
        except Exception:
            # 여러 시그니처 대처(라이브러리별 차이)
            try:
                for member, score in mapping.items():
                    await self._client.zadd(name, score, member)  # type: ignore
            except Exception:
                logger.exception("[RedisCompat] zadd 폴백 실패")
                raise

    async def delete(self, key: str):
        try:
            await self._client.delete(key)
        except Exception:
            logger.debug("[RedisCompat] delete 실패", exc_info=True)


# ---------------------------
# 백필(처리) 관련 유틸/스텁
# ---------------------------
async def perform_backfill(job: Dict[str, Any], timescale_pool: Any) -> bool:
    """
    실제 백필 작업을 수행하는 자리(현재는 PoC stub).
    - job: job_dict (파싱된 JSON)
    - timescale_pool: asyncpg pool 같은 DB 커넥션 풀
    반환: 성공 True/False

    실제 환경에서는 다음 작업 중 하나 이상을 구현:
    1) Kafka replay (symbol/time range)
    2) 거래소 REST historical fetch
    3) S3/Parquet 아카이브 복구
    그리고 Timescale에 idempotent insert 수행.
    """
    try:
        symbol = job.get("symbol")
        start = job.get("start")
        end = job.get("end")
        job_id = job.get("job_id")
        logger.info("[Backfill] 시작: symbol=%s start=%s end=%s job_id=%s", symbol, start, end, job_id)

        # PoC: 실제 재생 대신 short sleep로 작업을 시뮬레이트
        await asyncio.sleep(0.5)

        # PoC에서는 Timescale에 간단한 로그 인서트(선택 사항) 또는 확인 쿼리만 수행
        # 실제환경: idempotent insert 구현 필요 (INSERT ... ON CONFLICT)
        try:
            if timescale_pool is not None:
                # 예: 로그 테이블에 삽입(테스트용)
                async with timescale_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO IF NOT EXISTS gap_backfill_log (job_id, symbol, start_ts, end_ts, created_at) VALUES ($1, $2, $3, $4, NOW())",
                        job_id, symbol, start, end
                    )
        except Exception:
            # 위 DDL이 없을 수 있으므로 무시(선택)
            pass

        logger.info("[Backfill] 성공: job_id=%s", job_id)
        return True
    except Exception:
        logger.exception("[Backfill] 예외 발생")
        return False


# ---------------------------
# 소비자 메인 클래스
# ---------------------------
class GapConsumer:
    """
    Gap job 소비자
    - redis_client: raw redis client (redis.asyncio 또는 aioredis)
    - timescale_pool: asyncpg pool (선택)
    """

    def __init__(self, redis_client: Any, timescale_pool: Any = None, claim_ttl_ms: int = CLAIM_TTL_MS):
        self.redis = RedisCompat(redis_client)
        self._raw_redis = redis_client
        self.timescale_pool = timescale_pool
        self._claim_ttl_ms = claim_ttl_ms
        self._running = False

    async def _pop_job(self) -> Optional[Dict[str, Any]]:
        """
        ZSET에서 최고 우선 job을 꺼냄(zpopmax). 반환: parsed job dict 또는 None
        """
        try:
            items = await self.redis.zpopmax(ZSET_KEY, 1)
            if not items:
                return None
            # items: [(member, score)] - member may be bytes or str
            member, score = items[0]
            if isinstance(member, bytes):
                member = member.decode("utf-8")
            try:
                job = orjson.loads(member)
            except Exception:
                # fallback to str -> eval/json
                import json
                job = json.loads(member)
            # attach raw_member for DLQ/redis requeue if needed
            job["_raw_member"] = member
            job["_score"] = float(score)
            return job
        except Exception:
            logger.exception("[GapConsumer] pop_job 실패")
            return None

    async def _claim_job(self, job_id: str, owner_id: str) -> bool:
        key = CLAIM_KEY_PREFIX + job_id
        return await self.redis.set_claim(key, owner_id, px=self._claim_ttl_ms)

    async def _mark_processed(self, job_id: str, ttl_seconds: int = 86400):
        key = PROCESSED_KEY_PREFIX + job_id
        await self.redis.set(key, "1", ex=ttl_seconds)

    async def _is_processed(self, job_id: str) -> bool:
        key = PROCESSED_KEY_PREFIX + job_id
        res = await self.redis.get(key)
        return bool(res)

    async def _requeue_job(self, job: Dict[str, Any], attempts: int):
        """
        재큐: attempts 증가, score 재계산(지수적 backoff 기반)
        - attempts가 MAX_ATTEMPTS 초과하면 DLQ로 이동
        """
        job["attempts"] = attempts
        raw = orjson.dumps(job).decode("utf-8")
        if attempts > MAX_ATTEMPTS:
            logger.warning("[GapConsumer] 최대 재시도 초과, DLQ로 이동 job_id=%s attempts=%d", job.get("job_id"), attempts)
            await self.redis.rpush(DLQ_LIST, raw)
            return
        # 지수적 지연 기반 우선순위(간단): 기존 score를 줄여서 순위를 낮춤
        base_score = job.get("_score", 1.0)
        delay_seconds = REQUEUE_BASE_DELAY * (2 ** (attempts - 1))
        new_score = base_score / (1 + attempts)  # 간단 스코어 감소
        # 실제 운영에서는 재시도 예약 시스템을 사용하는 것이 더 좋음
        await self.redis.zadd(ZSET_KEY, {raw: new_score})
        logger.info("[GapConsumer] 재큐: job_id=%s attempts=%d new_score=%.4f delay=%ds", job.get("job_id"), attempts, new_score, delay_seconds)

    async def _process_job(self, job: Dict[str, Any], owner_id: str):
        """
        단건 job 처리 플로우:
        - 멱등성 검사
        - claim 시도
        - perform_backfill 호출
        - 성공: mark_processed
        - 실패: 재큐(또는 DLQ)
        """
        job_id = job.get("job_id") or hashlib.sha256(orjson.dumps(job)).hexdigest()
        # 이미 처리되었는지 확인
        if await self._is_processed(job_id):
            logger.info("[GapConsumer] 이미 처리된 job 건너뜀: %s", job_id)
            return

        # claim 시도
        claimed = await self._claim_job(job_id, owner_id)
        if not claimed:
            logger.debug("[GapConsumer] claim 실패 (다른 워커 처리 중): %s", job_id)
            return

        # attempts 카운트 관리
        attempts = int(job.get("attempts", 0))
        try:
            ok = await perform_backfill(job, self.timescale_pool)
            if ok:
                await self._mark_processed(job_id)
                logger.info("[GapConsumer] 처리 성공: %s", job_id)
            else:
                attempts += 1
                await self._requeue_job(job, attempts)
                logger.warning("[GapConsumer] 처리 실패 - 재큐: %s attempts=%d", job_id, attempts)
        except Exception:
            attempts += 1
            await self._requeue_job(job, attempts)
            logger.exception("[GapConsumer] 처리 예외 - 재큐: %s attempts=%d", job_id, attempts)

    async def run_once(self, owner_id: Optional[str] = None) -> int:
        """
        단발성 처리: 하나의 job을 처리(또는 시도)하고 종료.
        반환: 처리(시도)한 job 수(0/1)
        """
        owner = owner_id or f"consumer:{os.getpid()}:{int(time.time())}"
        job = await self._pop_job()
        if not job:
            logger.debug("[GapConsumer] 처리할 job 없음")
            return 0
        await self._process_job(job, owner)
        return 1

    async def run(self, poll_interval: float = 1.0, owner_id: Optional[str] = None):
        """
        데몬 모드: 계속해서 ZSET에서 job을 꺼내 처리.
        안전 종료는 외부에서 loop에 SIGINT/SIGTERM을 전달해야 함.
        """
        owner = owner_id or f"consumer:{os.getpid()}:{int(time.time())}"
        self._running = True
        logger.info("[GapConsumer] 데몬 시작 owner=%s", owner)
        try:
            while self._running:
                try:
                    job = await self._pop_job()
                    if job:
                        await self._process_job(job, owner)
                        # 즉시 다음 job 처리 (��은 재시도 대기 없음)
                        await asyncio.sleep(0.01)
                    else:
                        # 폴링 백오프
                        await asyncio.sleep(poll_interval)
                except Exception:
                    logger.exception("[GapConsumer] 루프 중 예외 발생")
                    await asyncio.sleep(1.0)
        finally:
            self._running = False
            logger.info("[GapConsumer] 데몬 종료")

    def stop(self):
        self._running = False


# ---------------------------
# CLI / 런처
# ---------------------------
async def create_redis_client(url: str):
    """
    redis-clients 초기화: redis.asyncio 를 우선 시도, 없으면 aioredis를 시도.
    """
    try:
        import importlib
        mod = importlib.import_module("redis.asyncio")
        Redis = getattr(mod, "Redis")
        client = Redis.from_url(url, decode_responses=False)
        await client.ping()
        return client
    except Exception:
        # aioredis fallback
        try:
            import importlib
            mod = importlib.import_module("aioredis")
            client = getattr(mod, "from_url")(url)
            await client.ping()
            return client
        except Exception:
            logger.exception("[GapConsumer] Redis 클라이언트 생성 실패")
            raise


async def create_timescale_pool(dsn: Optional[str]):
    """
    asyncpg pool 생성(선택). dsn 없으면 None 반환.
    """
    if not dsn:
        return None
    try:
        import asyncpg  # type: ignore
        pool = await asyncpg.create_pool(dsn)
        return pool
    except Exception:
        logger.exception("[GapConsumer] timescale pool 생성 실패")
        return None


def _setup_logging():
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        root.addHandler(handler)
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


async def _main_async(args):
    _setup_logging()
    redis_client = await create_redis_client(args.redis_url)
    timescale_pool = await create_timescale_pool(args.timescale_dsn)
    consumer = GapConsumer(redis_client, timescale_pool)

    if args.once:
        await consumer.run_once()
        # 안전 종료
        try:
            await _safe_close(redis_client)
        except Exception:
            pass
        if timescale_pool:
            await timescale_pool.close()
    else:
        # 데몬 모드: 시그널 처리
        loop = asyncio.get_running_loop()
        stop_evt = asyncio.Event()

        def _on_stop():
            logger.info("[GapConsumer] 종료 신호 수신")
            consumer.stop()
            stop_evt.set()

        try:
            loop.add_signal_handler(signal.SIGINT, _on_stop)   # type: ignore[name-defined]
            loop.add_signal_handler(signal.SIGTERM, _on_stop)  # type: ignore[name-defined]
        except Exception:
            logger.debug("[GapConsumer] 시그널 핸들러 등록 불가(환경제한)")

        # 백그라운드 실행
        task = asyncio.create_task(consumer.run(poll_interval=args.interval))
        await stop_evt.wait()
        # 정리
        try:
            await _safe_close(redis_client)
        except Exception:
            pass
        if timescale_pool:
            await timescale_pool.close()
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except Exception:
            task.cancel()
            try:
                await task
            except Exception:
                pass


async def _safe_close(obj: Any):
    """
    Redis/DB client 안전 종료: aclose -> close 순으로 시도
    """
    try:
        if hasattr(obj, "aclose"):
            res = obj.aclose()
            if asyncio.iscoroutine(res):
                await res
            return
        if hasattr(obj, "close"):
            res = obj.close()
            if asyncio.iscoroutine(res):
                await res
    except Exception:
        logger.debug("[GapConsumer] 안전 종료 중 예외", exc_info=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Gap consumer worker")
    parser.add_argument("--once", action="store_true", help="한 번만 처리하고 종료")
    parser.add_argument("--redis-url", type=str, default=os.environ.get("REDIS_URL") or _get_default_redis_url())
    parser.add_argument("--timescale-dsn", type=str, default=os.environ.get("TIMESCALE_DSN", ""))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("GAP_CONSUMER_INTERVAL", "1.0")))
    args = parser.parse_args()
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        logger.info("[GapConsumer] 사용자 인터럽트로 종료")
    except Exception:
        logger.exception("[GapConsumer] 예외로 종료")
        sys.exit(1)


if __name__ == "__main__":
    main()