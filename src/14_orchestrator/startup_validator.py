# -*- coding: utf-8 -*-
"""
앱 시작 시 DB 연결 및 데이터 검증 모듈 (정석적 구현)

설명:
- bootstrap이 asyncio.run(run_startup_validation())로 호출할 수 있는 비동기 진입점 제공.
- 블로킹 DB 드라이버 호출(psycopg2, redis, pymongo)은 asyncio.to_thread로 별도 스레드에서 실행하여
  메인 이벤트 루프를 블로킹하지 않음.
- Timescale(Postgres), Redis, MongoDB 연결 및 기본 상태를 검사하고 결과를 요약 반환.
- 모든 로그/주석은 한글로 작성되어 있습니다.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Dict, Optional, Tuple, Any
from types import SimpleNamespace

logger = logging.getLogger("app.core.startup_validator")


class ValidationResult:
    """검증 결과 모델"""
    def __init__(self, success: bool, db_name: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.success = success
        self.db_name = db_name
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "db_name": self.db_name,
            "message": self.message,
            "details": self.details,
        }


class StartupValidator:
    """앱 시작 시 DB 연결 및 데이터 검증기"""

    def __init__(self) -> None:
        self.results: Dict[str, ValidationResult] = {}

    async def validate_all(self) -> bool:
        """모든 DB 연결 및 데이터 검증을 병렬로 실행하고 전체 성공여부 반환"""
        logger.info("🔍 DB 연결 검증 시작...")

        tasks = [
            self._validate_timescaledb(),
            self._validate_redis(),
            self._validate_mongodb(),
        ]

        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for res in completed:
            if isinstance(res, ValidationResult):
                self.results[res.db_name] = res
            elif isinstance(res, Exception):
                logger.exception("검증 중 예외 발생:", exc_info=res)

        self._print_summary()
        all_ok = all(r.success for r in self.results.values())

        if all_ok:
            logger.info("🎉 모든 DB 연결 성공")
            # 마이그레이션 자동 실행 (TimescaleDB 연결 성공 시)
            try:
                await asyncio.to_thread(self._run_migrations)
            except Exception as exc:
                logger.warning("마이그레이션 실패 (비치명적): %s", exc)

        return all_ok

    def _run_migrations(self) -> None:
        """TimescaleDB 마이그레이션을 동기 스레드에서 실행합니다."""
        try:
            # src/data_01 경로를 sys.path에 추가하여 timescale 패키지 접근 보장
            _here = os.path.dirname(os.path.abspath(__file__))
            _data_path = os.path.abspath(os.path.join(_here, "..", "data_01"))
            if _data_path not in sys.path:
                sys.path.insert(0, _data_path)
            from timescale.auto_migrate import run_migrations_on_startup  # type: ignore[import]
            run_migrations_on_startup()
        except Exception as exc:
            logger.warning("마이그레이션 모듈 실행 실패: %s", exc)

    # TimescaleDB 검사
    async def _validate_timescaledb(self) -> ValidationResult:
        db_label = "TimescaleDB"

        def sync_check() -> ValidationResult:
            try:
                try:
                    import psycopg2  # type: ignore
                    from psycopg2 import extras  # type: ignore
                except Exception as e:
                    return ValidationResult(False, db_label, "❌ psycopg2 미설치: pip install psycopg2-binary", {"error": str(e)})

                conn = None
                try:
                    # config.yaml 기반 포트 58529 사용
                    conn = psycopg2.connect(
                        host=os.getenv("PGHOST", os.getenv("TIMESCALEDB_HOST", "127.0.0.1")),
                        port=int(os.getenv("PGPORT", os.getenv("TIMESCALEDB_PORT", "58529"))),
                        database=os.getenv("PGDATABASE", os.getenv("TIMESCALEDB_DB", "upbit_trader")),
                        user=os.getenv("PGUSER", os.getenv("TIMESCALEDB_USER", "postgres")),
                        password=os.getenv("PGPASSWORD", os.getenv("TIMESCALEDB_PASSWORD", "postgres")),
                        connect_timeout=5,
                    )
                    cursor = conn.cursor(cursor_factory=extras.RealDictCursor)

                    # PostgreSQL 버전
                    try:
                        cursor.execute("SELECT version();")
                        ver_row = cursor.fetchone()
                        pg_version = ver_row.get("version") if isinstance(ver_row, dict) and "version" in ver_row else str(ver_row)
                    except Exception:
                        pg_version = "unknown"

                    # timescaledb 확장 확인
                    try:
                        cursor.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';")
                        ext = cursor.fetchone()
                        ts_version = ext["extversion"] if ext and isinstance(ext, dict) and "extversion" in ext else None
                    except Exception:
                        ts_version = None

                    hypertables = []
                    if ts_version:
                        try:
                            cursor.execute("""
                                SELECT hypertable_schema, hypertable_name
                                FROM timescaledb_information.hypertables
                                LIMIT 5;
                            """)
                            hypertables = cursor.fetchall()
                        except Exception:
                            hypertables = []

                    recent_count = 0
                    try:
                        cursor.execute("""
                            SELECT COUNT(*) as cnt
                            FROM candles_1m
                            WHERE timestamp > NOW() - INTERVAL '1 hour';
                        """)
                        row = cursor.fetchone()
                        recent_count = int(row["cnt"]) if row and isinstance(row, dict) and "cnt" in row else 0
                    except Exception:
                        recent_count = 0

                    details = {
                        "timescaledb_version": ts_version,
                        "pg_version": str(pg_version)[:120],
                        "hypertables_sample": len(hypertables),
                        "recent_1h_count": recent_count,
                    }

                    if not ts_version:
                        return ValidationResult(False, db_label, "❌ TimescaleDB 확장이 설치되지 않았습니다.", details)

                    return ValidationResult(True, db_label, f"✅ {db_label} (v{ts_version})", details)

                finally:
                    try:
                        if conn:
                            conn.close()
                    except Exception:
                        pass

            except Exception as e:
                return ValidationResult(False, db_label, f"❌ TimescaleDB 검사 실패: {e}", {"error": str(e)})

        return await asyncio.to_thread(sync_check)

    # Redis 검사
    async def _validate_redis(self) -> ValidationResult:
        db_label = "Redis"

        def sync_check() -> ValidationResult:
            try:
                try:
                    import redis  # type: ignore
                except Exception as e:
                    return ValidationResult(False, db_label, "❌ redis 미설치: pip install redis", {"error": str(e)})

                # 1순위: redis_factory (config.yaml 기반 설정)
                redis_url = None
                try:
                    import importlib.util as _sv_ilu
                    import pathlib as _sv_pl
                    _sv_factory_path = _sv_pl.Path(__file__).resolve().parent.parent / "01_core" / "database" / "redis_factory.py"
                    _sv_spec = _sv_ilu.spec_from_file_location("_redis_factory_sv", str(_sv_factory_path))
                    _sv_factory_mod = _sv_ilu.module_from_spec(_sv_spec)  # type: ignore[arg-type]
                    _sv_spec.loader.exec_module(_sv_factory_mod)  # type: ignore[union-attr]
                    redis_url = _sv_factory_mod.get_redis_url()
                    logger.debug("[StartupValidator] redis_factory URL: %s", redis_url)
                except Exception as _sv_e:
                    logger.debug("[StartupValidator] redis_factory 로드 실패 (%s), env fallback 사용", _sv_e)

                # 2순위: 환경변수
                if not redis_url:
                    redis_url = os.getenv("REDIS_URL", "").strip()

                # 3순위: 기본값 (포트 58530)
                if not redis_url:
                    _password = os.getenv("REDIS_PASSWORD", "dummy")
                    _host = os.getenv("REDIS_HOST", "127.0.0.1")
                    _port = os.getenv("REDIS_PORT", "58530")
                    _db = os.getenv("REDIS_DB", "0")
                    redis_url = f"redis://:{_password}@{_host}:{_port}/{_db}"

                try:
                    client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5)
                    client.ping()
                    logger.debug("[StartupValidator] Redis 연결 성공: %s", redis_url)
                except Exception as e:
                    return ValidationResult(False, db_label, f"❌ Redis 연결 실패: {e}", {"error": str(e), "url": redis_url})

                try:
                    info_server = client.info("server")
                except Exception:
                    info_server = {}
                try:
                    info_memory = client.info("memory")
                except Exception:
                    info_memory = {}
                try:
                    info_keyspace = client.info("keyspace")
                except Exception:
                    info_keyspace = {}

                redis_version = info_server.get("redis_version", "unknown")
                used_memory = info_memory.get("used_memory_human", "N/A")
                db0_keys = 0
                if "db0" in info_keyspace and isinstance(info_keyspace["db0"], dict):
                    db0_keys = info_keyspace["db0"].get("keys", 0)

                details = {
                    "redis_version": redis_version,
                    "used_memory": used_memory,
                    "db0_keys": db0_keys,
                }

                return ValidationResult(True, db_label, f"✅ {db_label}", details)

            except Exception as e:
                return ValidationResult(False, db_label, f"❌ Redis 검사 실패: {e}", {"error": str(e)})

        return await asyncio.to_thread(sync_check)

    # MongoDB 검사
    async def _validate_mongodb(self) -> ValidationResult:
        db_label = "MongoDB"

        def sync_check() -> ValidationResult:
            try:
                try:
                    from pymongo import MongoClient  # type: ignore
                except Exception as e:
                    return ValidationResult(False, db_label, "❌ pymongo 미설치: pip install pymongo", {"error": str(e)})

                mongo_uri = os.getenv("MONGO_URI", "").strip()
                try:
                    if mongo_uri:
                        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
                    else:
                        client = MongoClient(
                            host=os.getenv("MONGO_HOST", "localhost"),
                            port=int(os.getenv("MONGO_PORT", 27017)),
                            serverSelectionTimeoutMS=5000,
                        )
                    client.admin.command("ping")
                except Exception as e:
                    return ValidationResult(False, db_label, f"❌ MongoDB 연결 실패: {e}", {"error": str(e)})

                db_name = os.getenv("MONGO_DB", os.getenv("MONGO_INITDB_DATABASE_CONTAINER", "upbit_trader"))
                db = client[db_name]

                try:
                    server_info = client.server_info()
                    mongo_version = server_info.get("version", "unknown")
                except Exception:
                    mongo_version = "unknown"

                try:
                    collections = db.list_collection_names()
                    coll_count = len(collections)
                except Exception:
                    collections = []
                    coll_count = 0

                metadata_count = 0
                if "symbol_metadata" in collections:
                    try:
                        metadata_count = int(db.symbol_metadata.count_documents({}))
                    except Exception:
                        metadata_count = 0

                details = {
                    "mongodb_version": mongo_version,
                    "collections_count": coll_count,
                    "symbol_metadata_count": metadata_count,
                }

                return ValidationResult(True, db_label, f"✅ {db_label} (v{mongo_version})", details)

            except Exception as e:
                return ValidationResult(False, db_label, f"❌ MongoDB 검사 실패: {e}", {"error": str(e)})

        return await asyncio.to_thread(sync_check)

    def _print_summary(self) -> None:
        """검증 결과 요약 출력 (간결한 형식)"""
        parts = []
        for db_name in ["TimescaleDB", "Redis", "MongoDB"]:
            res = self.results.get(db_name)
            if not res:
                continue
            
            icon = "✅" if res.success else "❌"
            
            # 버전 정보 추출
            if db_name == "TimescaleDB":
                ver = res.details.get("timescaledb_version", "?")
            elif db_name == "Redis":
                ver = res.details.get("redis_version", "?")
            elif db_name == "MongoDB":
                ver = res.details.get("mongodb_version", "?")
            else:
                ver = "?"
            
            parts.append(f"{icon} {db_name} (v{ver})" if ver != "?" else f"{icon} {db_name}")
        
        summary = " | ".join(parts)
        logger.info(summary)
        
        if all(r.success for r in self.results.values()):
            pass  # 성공 로그는 validate_all에서 출력
        else:
            failed = [name for name, r in self.results.items() if not r.success]
            logger.warning("⚠️ 일부 DB 연결 실패: %s", ", ".join(failed))

    def get_failed_dbs(self) -> list:
        return [name for name, r in self.results.items() if not r.success]


# 외부 진입점
async def run_startup_validation() -> Tuple[bool, SimpleNamespace]:
    validator = StartupValidator()
    ok = await validator.validate_all()
    ns = SimpleNamespace()
    ns.results = validator.results
    ns.get_failed_dbs = validator.get_failed_dbs
    return ok, ns


# CLI 실행용
if __name__ == "__main__":
    async def _main():
        ok, validator = await run_startup_validation()
        if not ok:
            failed = validator.get_failed_dbs()
            print(f"\n⚠️ 연결 실패한 서비스: {', '.join(failed)}")
            raise SystemExit(1)
        else:
            print("\n✅ 모든 검증 통과!")

    asyncio.run(_main())