# -*- coding: utf-8 -*-
"""
7개 DB 서비스 체크 함수 통합 (v3.0 - Timescale psycopg2 동기 연결 추가)

변경사항 v3.0:
- ✅ TimescaleDB: psycopg2 동기 연결을 2단계로 추가 (asyncpg 비동기 풀 한계 보완)
- ✅ psycopg(v3) → psycopg2 순차 시도
- ✅ 포트·사용자·패스워드·DB명 환경변수 우선 적용
"""
from __future__ import annotations
import importlib.util
import logging
import os
import types
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# constants.py 로드 (01_core 패키지명이 Python 식별자 규칙 위반으로 직접 import 불가)
# ---------------------------------------------------------------------------
_CONST_PATH = Path(__file__).parents[3] / "01_core" / "config" / "constants.py"

def _load_constants() -> Optional[types.ModuleType]:
    """constants.py 모듈을 경로 기반으로 로드합니다."""
    try:
        spec = importlib.util.spec_from_file_location("_svc_checker_consts", str(_CONST_PATH))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
    except Exception as exc:
        logger.debug("[ServiceChecker] constants 로드 실패: %s", exc)
    return None

_CONSTS = _load_constants()
_DEFAULT_TIMESCALE_PORT: int = getattr(_CONSTS, "DEFAULT_TIMESCALE_PORT", 58529)
_DEFAULT_TIMESCALE_HOST: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_HOST", "127.0.0.1")
_DEFAULT_TIMESCALE_USER: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_USER", "postgres")
_DEFAULT_TIMESCALE_DB: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_DB", "upbit_trader")
_DEFAULT_POSTGRES_PRIMARY_PORT: int = getattr(_CONSTS, "DEFAULT_POSTGRES_PRIMARY_PORT", 5433)

try:
    from ..utils.network_helpers import tcp_probe, http_probe
except ImportError:
    import socket
    import urllib.request
    import urllib.error
    from typing import Tuple, Optional

    def tcp_probe(host: str, port: int, timeout: float = 2.0) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    def http_probe(host: str, port: int, path: str = "/", timeout: float = 2.0):
        url = f"http://{host}:{port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return True, getattr(resp, "status", None)
        except urllib.error.HTTPError as he:
            return True, getattr(he, "code", None)
        except Exception:
            return False, None


def _get_timescale_dsn() -> dict:
    """환경변수에서 TimescaleDB 접속 정보를 읽어 반환."""
    host = (
        os.getenv("TIMESCALE_HOST")
        or os.getenv("PGHOST")
        or _DEFAULT_TIMESCALE_HOST
    )
    port_str = (
        os.getenv("TIMESCALE_PORT")
        or os.getenv("TIMESCALEDB_PORT")
        or os.getenv("PGPORT")
        or str(_DEFAULT_TIMESCALE_PORT)
    )
    try:
        port = int(port_str)
    except ValueError:
        logger.debug(
            "[ServiceChecker] TimescaleDB 포트 파싱 실패('%s') — 기본값 %d 사용",
            port_str, _DEFAULT_TIMESCALE_PORT,
        )
        port = _DEFAULT_TIMESCALE_PORT
    return {
        "host": host,
        "port": port,
        "user": os.getenv("TIMESCALE_USER", os.getenv("PGUSER", _DEFAULT_TIMESCALE_USER)),
        "password": os.getenv("TIMESCALE_PASSWORD", os.getenv("PGPASSWORD", "")),
        "dbname": os.getenv("TIMESCALE_DB", os.getenv("PGDATABASE", _DEFAULT_TIMESCALE_DB)),
    }


class ServiceChecker:
    """7개 DB 서비스 연결 상태 확인 (v3.0)"""

    # ------------------------------------------------------------------
    # TimescaleDB
    # ------------------------------------------------------------------

    def check_timescale(self) -> bool:
        """
        TimescaleDB 연결 상태 ���인 (3단계 Fallback)

        1단계: utils.get_timescale_connector() — 앱 연결 풀 재사용
        2단계: psycopg / psycopg2 동기 연결 (asyncpg 비동기 풀 한계 보완)
        3단계: TCP probe — 최후 수단
        """
        dsn = _get_timescale_dsn()
        host, port = dsn["host"], dsn["port"]

        # ── 1단계: utils 연결 풀 ──────────────────────────────────────
        try:
            from .. import utils as _ui_utils  # type: ignore
            connector = _ui_utils.get_timescale_connector()
            if connector is not None:
                logger.debug("[ServiceChecker] ✅ TimescaleDB: utils 연결 풀 사용")
                return True
            logger.debug("[ServiceChecker] ⚠️ TimescaleDB: utils 연결 풀 None — 2단계로")
        except Exception as exc:
            logger.debug("[ServiceChecker] ⚠️ TimescaleDB: utils 로드 실패 (%s) — 2단계로", exc)

        # ── 2단계: psycopg(v3) 동기 연결 ─────────────────────────────
        try:
            import psycopg  # type: ignore
            with psycopg.connect(
                host=host, port=port,
                user=dsn["user"], password=dsn["password"],
                dbname=dsn["dbname"],
                connect_timeout=2,
                options="-c statement_timeout=2000",
            ):
                logger.debug("[ServiceChecker] ✅ TimescaleDB: psycopg(v3) 연결 성공 (%s:%d)", host, port)
                return True
        except ImportError:
            pass  # psycopg v3 미설치 → psycopg2 시도
        except Exception as exc:
            logger.debug("[ServiceChecker] ⚠️ TimescaleDB: psycopg(v3) 실패 (%s)", exc)

        # ── 2단계-b: psycopg2 동기 연결 ──────────────────────────────
        try:
            import psycopg2  # type: ignore
            conn = psycopg2.connect(
                host=host, port=port,
                user=dsn["user"], password=dsn["password"],
                dbname=dsn["dbname"],
                connect_timeout=2,
                options="-c statement_timeout=2000",
            )
            conn.close()
            logger.debug("[ServiceChecker] ✅ TimescaleDB: psycopg2 연결 성공 (%s:%d)", host, port)
            return True
        except ImportError:
            logger.debug("[ServiceChecker] psycopg2 미설치 — 3단계 TCP probe로")
        except Exception as exc:
            logger.debug("[ServiceChecker] ⚠️ TimescaleDB: psycopg2 실패 (%s) — 3단계로", exc)

        # ── 3단계: TCP probe ──────────────────────────────────────────
        try:
            result = tcp_probe(host, port, timeout=2.0)
            if result:
                logger.debug("[ServiceChecker] ✅ TimescaleDB: TCP probe 성공 (%s:%d)", host, port)
            else:
                logger.debug("[ServiceChecker] ❌ TimescaleDB: TCP probe 실패 (%s:%d)", host, port)
            return result
        except Exception as exc:
            logger.debug("[ServiceChecker] ❌ TimescaleDB: TCP probe 예외 (%s)", exc)
            return False

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------

    def check_redis(self) -> bool:
        """Redis 연결 상태 확인 (utils → TCP probe)"""
        try:
            from .. import utils as _ui_utils  # type: ignore
            rc = _ui_utils.get_redis_connector()
            if rc is not None:
                logger.debug("[ServiceChecker] ✅ Redis: utils 클라이언트 사용")
                return True
        except Exception as exc:
            logger.debug("[ServiceChecker] ⚠️ Redis: utils 실패 (%s) — TCP probe", exc)

        try:
            host = os.getenv("REDIS_HOST", "127.0.0.1")
            port = int(os.getenv("REDIS_PORT", "58530"))
            result = tcp_probe(host, port, timeout=2.0)
            logger.debug(
                "[ServiceChecker] %s Redis: TCP probe (%s:%d)",
                "✅" if result else "❌", host, port,
            )
            return result
        except Exception as exc:
            logger.debug("[ServiceChecker] ❌ Redis: TCP probe 예외 (%s)", exc)
            return False

    # ------------------------------------------------------------------
    # MongoDB
    # ------------------------------------------------------------------

    def check_mongo(self) -> bool:
        """MongoDB 연결 상태 확인 (utils → TCP probe)"""
        try:
            from .. import utils as _ui_utils  # type: ignore
            client = _ui_utils.get_mongo_sync_client()
            if client is not None:
                logger.debug("[ServiceChecker] ✅ MongoDB: utils 클라이언트 사용")
                return True
        except Exception as exc:
            logger.debug("[ServiceChecker] ⚠️ MongoDB: utils 실패 (%s) — TCP probe", exc)

        try:
            host = os.getenv("MONGO_HOST", "127.0.0.1")
            port = int(os.getenv("MONGO_PORT", "27017"))
            result = tcp_probe(host, port, timeout=2.0)
            logger.debug(
                "[ServiceChecker] %s MongoDB: TCP probe (%s:%d)",
                "✅" if result else "❌", host, port,
            )
            return result
        except Exception as exc:
            logger.debug("[ServiceChecker] ❌ MongoDB: TCP probe 예외 (%s)", exc)
            return False

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------

    def check_postgres(self) -> bool:
        """PostgreSQL 연결 상태 확인 (TCP probe)"""
        try:
            host = os.getenv("POSTGRES_HOST", "127.0.0.1")
            port = int(os.getenv("POSTGRES_PORT", str(_DEFAULT_POSTGRES_PRIMARY_PORT)))
            result = tcp_probe(host, port, timeout=2.0)
            logger.debug(
                "[ServiceChecker] %s PostgreSQL: TCP probe (%s:%d)",
                "✅" if result else "❌", host, port,
            )
            return result
        except Exception as exc:
            logger.debug("[ServiceChecker] ❌ PostgreSQL: TCP probe 예외 (%s)", exc)
            return False

    # ------------------------------------------------------------------
    # Kafka
    # ------------------------------------------------------------------

    def check_kafka(self) -> bool:
        """Kafka 연결 상태 확인 (TCP probe)"""
        try:
            host = os.getenv("KAFKA_HOST", "127.0.0.1")
            port = int(os.getenv("KAFKA_PORT", "9092"))
            result = tcp_probe(host, port, timeout=2.0)
            logger.debug(
                "[ServiceChecker] %s Kafka: TCP probe (%s:%d)",
                "✅" if result else "❌", host, port,
            )
            return result
        except Exception as exc:
            logger.debug("[ServiceChecker] ❌ Kafka: TCP probe 예외 (%s)", exc)
            return False

    # ------------------------------------------------------------------
    # ClickHouse
    # ------------------------------------------------------------------

    def check_clickhouse(self) -> bool:
        """ClickHouse 연결 상태 확인 (HTTP probe)"""
        try:
            host = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
            port = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
            ok, status_code = http_probe(host, port, "/ping", timeout=2.0)
            logger.debug(
                "[ServiceChecker] %s ClickHouse: HTTP probe (%s:%d, status=%s)",
                "✅" if ok else "❌", host, port, status_code,
            )
            return ok
        except Exception as exc:
            logger.debug("[ServiceChecker] ❌ ClickHouse: HTTP probe 예외 (%s)", exc)
            return False

    # ------------------------------------------------------------------
    # MLflow
    # ------------------------------------------------------------------

    def check_mlflow(self) -> bool:
        """MLflow 연결 상태 확인 (HTTP probe)"""
        try:
            host = os.getenv("MLFLOW_HOST", "127.0.0.1")
            port = int(os.getenv("MLFLOW_PORT", "5000"))
            ok, status_code = http_probe(host, port, "/", timeout=2.0)
            logger.debug(
                "[ServiceChecker] %s MLflow: HTTP probe (%s:%d, status=%s)",
                "✅" if ok else "❌", host, port, status_code,
            )
            return ok
        except Exception as exc:
            logger.debug("[ServiceChecker] ❌ MLflow: HTTP probe 예외 (%s)", exc)
            return False

    # ------------------------------------------------------------------
    # 전체 체크
    # ------------------------------------------------------------------

    def check_all(self) -> Dict[str, bool]:
        """모든 DB 서비스 상태 일괄 확인."""
        result = {
            "timescale":  self.check_timescale(),
            "redis":      self.check_redis(),
            "mongo":      self.check_mongo(),
            "postgres":   self.check_postgres(),
            "kafka":      self.check_kafka(),
            "clickhouse": self.check_clickhouse(),
            "mlflow":     self.check_mlflow(),
        }
        ok_count = sum(1 for v in result.values() if v)
        total    = len(result)
        logger.info(
            "[ServiceChecker] 🎉 전체 DB 체크 완료: %d/%d 성공 "
            "(timescale=%s, redis=%s, mongo=%s, postgres=%s, kafka=%s)",
            ok_count, total,
            "✅" if result["timescale"]  else "❌",
            "✅" if result["redis"]      else "❌",
            "✅" if result["mongo"]      else "❌",
            "✅" if result["postgres"]   else "❌",
            "✅" if result["kafka"]      else "❌",
        )
        return result