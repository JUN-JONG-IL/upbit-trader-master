# -*- coding: utf-8 -*-
"""
???쒖옉 ??DB ?곌껐 諛??곗씠??寃利?紐⑤뱢 (?뺤꽍??援ы쁽)

?ㅻ챸:
- bootstrap??asyncio.run(run_startup_validation())濡??몄텧?????덈뒗 鍮꾨룞湲?吏꾩엯???쒓났.
- 釉붾줈??DB ?쒕씪?대쾭 ?몄텧(psycopg2, redis, pymongo)? asyncio.to_thread濡?蹂꾨룄 ?ㅻ젅?쒖뿉???ㅽ뻾?섏뿬
  硫붿씤 ?대깽??猷⑦봽瑜?釉붾줈?뱁븯吏 ?딆쓬.
- Timescale(Postgres), Redis, MongoDB ?곌껐 諛?湲곕낯 ?곹깭瑜?寃?ы븯怨?寃곌낵瑜??붿빟 諛섑솚.
- 紐⑤뱺 濡쒓렇/二쇱꽍? ?쒓?濡??묒꽦?섏뼱 ?덉뒿?덈떎.
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
    """寃利?寃곌낵 紐⑤뜽"""
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
    """???쒖옉 ??DB ?곌껐 諛??곗씠??寃利앷린"""

    def __init__(self) -> None:
        self.results: Dict[str, ValidationResult] = {}

    async def validate_all(self) -> bool:
        """紐⑤뱺 DB ?곌껐 諛??곗씠??寃利앹쓣 蹂묐젹濡??ㅽ뻾?섍퀬 ?꾩껜 ?깃났?щ? 諛섑솚"""
        logger.info("?뵇 DB ?곌껐 寃利??쒖옉...")

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
                logger.exception("寃利?以??덉쇅 諛쒖깮:", exc_info=res)

        self._print_summary()
        all_ok = all(r.success for r in self.results.values())

        if all_ok:
            logger.info("?럦 紐⑤뱺 DB ?곌껐 ?깃났")
            # 留덉씠洹몃젅?댁뀡 ?먮룞 ?ㅽ뻾 (TimescaleDB ?곌껐 ?깃났 ??
            try:
                await asyncio.to_thread(self._run_migrations)
            except Exception as exc:
                logger.warning("留덉씠洹몃젅?댁뀡 ?ㅽ뙣 (鍮꾩튂紐낆쟻): %s", exc)

        return all_ok

    def _run_migrations(self) -> None:
        """TimescaleDB 留덉씠洹몃젅?댁뀡???숆린 ?ㅻ젅?쒖뿉???ㅽ뻾?⑸땲??"""
        try:
            # src/data_01 寃쎈줈瑜?sys.path??異붽??섏뿬 timescale ?⑦궎吏 ?묎렐 蹂댁옣
            _here = os.path.dirname(os.path.abspath(__file__))
            _data_path = os.path.abspath(os.path.join(_here, "..", "data_01"))
            if _data_path not in sys.path:
                sys.path.insert(0, _data_path)
            from timescale.auto_migrate import run_migrations_on_startup  # type: ignore[import]
            run_migrations_on_startup()
        except Exception as exc:
            logger.warning("留덉씠洹몃젅?댁뀡 紐⑤뱢 ?ㅽ뻾 ?ㅽ뙣: %s", exc)

    # TimescaleDB 寃??
    async def _validate_timescaledb(self) -> ValidationResult:
        db_label = "TimescaleDB"

        def sync_check() -> ValidationResult:
            try:
                try:
                    import psycopg2  # type: ignore
                    from psycopg2 import extras  # type: ignore
                except Exception as e:
                    return ValidationResult(False, db_label, "??psycopg2 誘몄꽕移? pip install psycopg2-binary", {"error": str(e)})

                conn = None
                try:
                    # config.yaml 湲곕컲 ?ы듃 58529 ?ъ슜
                    conn = psycopg2.connect(
                        host=os.getenv("PGHOST", os.getenv("TIMESCALEDB_HOST", "127.0.0.1")),
                        port=int(os.getenv("PGPORT", os.getenv("TIMESCALEDB_PORT", "58529"))),
                        database=os.getenv("PGDATABASE", os.getenv("TIMESCALEDB_DB", "upbit_trader")),
                        user=os.getenv("PGUSER", os.getenv("TIMESCALEDB_USER", "postgres")),
                        password=os.getenv("PGPASSWORD", os.getenv("TIMESCALEDB_PASSWORD", "postgres")),
                        connect_timeout=5,
                    )
                    cursor = conn.cursor(cursor_factory=extras.RealDictCursor)

                    # PostgreSQL 踰꾩쟾
                    try:
                        cursor.execute("SELECT version();")
                        ver_row = cursor.fetchone()
                        pg_version = ver_row.get("version") if isinstance(ver_row, dict) and "version" in ver_row else str(ver_row)
                    except Exception:
                        pg_version = "unknown"

                    # timescaledb ?뺤옣 ?뺤씤
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
                        return ValidationResult(False, db_label, "??TimescaleDB ?뺤옣???ㅼ튂?섏? ?딆븯?듬땲??", details)

                    return ValidationResult(True, db_label, f"??{db_label} (v{ts_version})", details)

                finally:
                    try:
                        if conn:
                            conn.close()
                    except Exception:
                        pass

            except Exception as e:
                return ValidationResult(False, db_label, f"??TimescaleDB 寃???ㅽ뙣: {e}", {"error": str(e)})

        return await asyncio.to_thread(sync_check)

    # Redis 寃??
    async def _validate_redis(self) -> ValidationResult:
        db_label = "Redis"

        def sync_check() -> ValidationResult:
            try:
                try:
                    import redis  # type: ignore
                except Exception as e:
                    return ValidationResult(False, db_label, "??redis 誘몄꽕移? pip install redis", {"error": str(e)})

                # 1?쒖쐞: redis_factory (config.yaml 湲곕컲 ?ㅼ젙)
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
                    logger.debug("[StartupValidator] redis_factory 濡쒕뱶 ?ㅽ뙣 (%s), env fallback ?ъ슜", _sv_e)

                # 2?쒖쐞: ?섍꼍蹂??
                if not redis_url:
                    redis_url = os.getenv("REDIS_URL", "").strip()

                # 3?쒖쐞: 湲곕낯媛?(?ы듃 58530)
                if not redis_url:
                    _password = os.getenv("REDIS_PASSWORD", "dummy")
                    _host = os.getenv("REDIS_HOST", "127.0.0.1")
                    _port = os.getenv("REDIS_PORT", "58530")
                    _db = os.getenv("REDIS_DB", "0")
                    redis_url = f"redis://:{_password}@{_host}:{_port}/{_db}"

                try:
                    client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5)
                    client.ping()
                    logger.debug("[StartupValidator] Redis ?곌껐 ?깃났: %s", redis_url)
                except Exception as e:
                    return ValidationResult(False, db_label, f"??Redis ?곌껐 ?ㅽ뙣: {e}", {"error": str(e), "url": redis_url})

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

                return ValidationResult(True, db_label, f"??{db_label}", details)

            except Exception as e:
                return ValidationResult(False, db_label, f"??Redis 寃???ㅽ뙣: {e}", {"error": str(e)})

        return await asyncio.to_thread(sync_check)

    # MongoDB 寃??
    async def _validate_mongodb(self) -> ValidationResult:
        db_label = "MongoDB"

        def sync_check() -> ValidationResult:
            try:
                try:
                    from pymongo import MongoClient  # type: ignore
                except Exception as e:
                    return ValidationResult(False, db_label, "??pymongo 誘몄꽕移? pip install pymongo", {"error": str(e)})

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
                    return ValidationResult(False, db_label, f"??MongoDB ?곌껐 ?ㅽ뙣: {e}", {"error": str(e)})

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

                return ValidationResult(True, db_label, f"??{db_label} (v{mongo_version})", details)

            except Exception as e:
                return ValidationResult(False, db_label, f"??MongoDB 寃???ㅽ뙣: {e}", {"error": str(e)})

        return await asyncio.to_thread(sync_check)

    def _print_summary(self) -> None:
        """寃利?寃곌낵 ?붿빟 異쒕젰 (媛꾧껐???뺤떇)"""
        parts = []
        for db_name in ["TimescaleDB", "Redis", "MongoDB"]:
            res = self.results.get(db_name)
            if not res:
                continue
            
            icon = "?? if res.success else "??
            
            # 踰꾩쟾 ?뺣낫 異붿텧
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
            pass  # ?깃났 濡쒓렇??validate_all?먯꽌 異쒕젰
        else:
            failed = [name for name, r in self.results.items() if not r.success]
            logger.warning("?좑툘 ?쇰? DB ?곌껐 ?ㅽ뙣: %s", ", ".join(failed))

    def get_failed_dbs(self) -> list:
        return [name for name, r in self.results.items() if not r.success]


# ?몃? 吏꾩엯??
async def run_startup_validation() -> Tuple[bool, SimpleNamespace]:
    validator = StartupValidator()
    ok = await validator.validate_all()
    ns = SimpleNamespace()
    ns.results = validator.results
    ns.get_failed_dbs = validator.get_failed_dbs
    return ok, ns


# CLI ?ㅽ뻾??
if __name__ == "__main__":
    async def _main():
        ok, validator = await run_startup_validation()
        if not ok:
            failed = validator.get_failed_dbs()
            print(f"\n?좑툘 ?곌껐 ?ㅽ뙣???쒕퉬?? {', '.join(failed)}")
            raise SystemExit(1)
        else:
            print("\n??紐⑤뱺 寃利??듦낵!")

    asyncio.run(_main())
