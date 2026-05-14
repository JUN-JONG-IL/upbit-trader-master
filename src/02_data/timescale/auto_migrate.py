# -*- coding: utf-8 -*-
"""
TimescaleDB 마이그레이션 자동 실행

sql/migrations/*.sql 파일을 정렬 순서대로 실행합니다.
각 SQL 파일은 멱등성(idempotent)을 보장해야 합니다 (IF NOT EXISTS 등).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def run_migrations_on_startup(dsn: Optional[str] = None) -> None:
    """앱 시작 시 sql/migrations/*.sql 을 자동 실행합니다.

    Args:
        dsn: TimescaleDB DSN 문자열. None이면 환경 변수에서 자동 빌드.
    """
    try:
        try:
            from .timescale_db import TimescaleConnector  # type: ignore
        except Exception:
            import importlib.util
            _db_path = os.path.join(os.path.dirname(__file__), "timescale_db.py")
            _spec = importlib.util.spec_from_file_location("timescale_db", _db_path)
            if _spec and _spec.loader:
                _mod = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)  # type: ignore
                TimescaleConnector = getattr(_mod, "TimescaleConnector")
            else:
                logger.error("[AutoMigrate] timescale_db 모듈 로드 실패")
                return

        base_dir = Path(__file__).parent
        migrations_dir = base_dir / "sql" / "migrations"

        if not migrations_dir.exists():
            logger.debug("[AutoMigrate] 마이그레이션 폴더 없음: %s", migrations_dir)
            return

        sql_files = sorted(migrations_dir.glob("*.sql"))
        if not sql_files:
            logger.debug("[AutoMigrate] 실행할 마이그레이션 없음")
            return

        logger.info("[AutoMigrate] %d개 마이그레이션 실행 시작", len(sql_files))

        conn = TimescaleConnector(dsn=dsn) if dsn else TimescaleConnector()
        if not conn.connect():
            logger.error("[AutoMigrate] DB 연결 실패 — 마이그레이션 건너뜀")
            return

        try:
            for sql_file in sql_files:
                try:
                    sql = sql_file.read_text(encoding="utf-8")
                    # Migration SQL files are developer-controlled DDL scripts (idempotent IF NOT EXISTS).
                    # They are not user-supplied input, so direct execution is safe here.
                    with conn.conn.cursor() as cur:  # type: ignore[union-attr]
                        cur.execute(sql)
                    conn.conn.commit()  # type: ignore[union-attr]
                    logger.info("[AutoMigrate] ✅ %s", sql_file.name)
                except Exception as exc:
                    logger.error("[AutoMigrate] ❌ %s 실패: %s", sql_file.name, exc)
                    try:
                        conn.conn.rollback()  # type: ignore[union-attr]
                    except Exception:
                        pass
        finally:
            # 직접 연결만 종료 — 전역 풀은 다른 컴포넌트가 계속 사용 중이므로 유지
            try:
                if hasattr(conn, "conn") and conn.conn is not None and not conn.conn.closed:
                    conn.conn.close()  # type: ignore[union-attr]
                if hasattr(conn, "conn"):
                    conn.conn = None  # type: ignore[union-attr]
                logger.debug("[AutoMigrate] 연결 종료 완료 (전역 풀 유지)")
            except Exception:
                pass

        logger.info("[AutoMigrate] 🎉 마이그레이션 완료")

    except Exception as exc:
        logger.error("[AutoMigrate] 예외 발생: %s", exc)
