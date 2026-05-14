# -*- coding: utf-8 -*-
"""
schema_ddl — SchemaDDLMixin
DDL/하이퍼테이블/연속 집계/압축 정책 담당 믹스인.

변경 요지:
- 안전한 커넥션 획득/실행 래퍼 `_execute_with_fresh_conn` 추가:
  - 전역 pool 모듈을 우선 시도(get_connection/release_connection)
  - 실패 시 self.connect()로 재연결 시도
  - psycopg2의 InterfaceError/OperationalError 발생 시 커넥션 정리 후 재시도
- ensure_hypertable 시작부에 환경변수 TIMESCALE_SKIP_SCHEMA 체크 추가(임시 완화용)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional, Union, Callable, Any, Tuple

logger = logging.getLogger("timescale_db")

# --------------------------------------------------------------------------
# 내부 헬퍼: SQL 식별자 정리
# --------------------------------------------------------------------------
import re as _re

_ident_re = _re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_identifier(name: str) -> str:
    if not name:
        return ""
    s = str(name).strip()
    s = _ident_re.sub("_", s)
    s = _re.sub(r"_+", "_", s)
    if s and s[0].isdigit():
        s = "_" + s
    return s


def _qualify_name(qname: str) -> str:
    """'schema.name' 또는 'name'을 안전하게 인용된 식별자로 반환."""
    if not qname:
        return '"public"."unknown"'
    parts = qname.split(".", 1)
    if len(parts) == 2:
        schema = _sanitize_identifier(parts[0])
        name = _sanitize_identifier(parts[1])
    else:
        schema = "public"
        name = _sanitize_identifier(parts[0])
    return f'"{schema}"."{name}"'


def _schema_dot_name(qname: str) -> str:
    """schema.name 문자열(비인용)을 반환 — SQL 리터럴 내 regclass 캐스트 용도."""
    if not qname:
        return "public.unknown"
    parts = qname.split(".", 1)
    if len(parts) == 2:
        schema = _sanitize_identifier(parts[0])
        name = _sanitize_identifier(parts[1])
    else:
        schema = "public"
        name = _sanitize_identifier(parts[0])
    return f"{schema}.{name}"


class SchemaDDLMixin:
    """DDL/하이퍼테이블/연속 집계/압축 정책 담당 믹스인."""

    # ----------------------
    # 내부 유틸: 유연한 커넥션 획득/실행
    # ----------------------
    def _acquire_conn_flex(self) -> Tuple[Optional[Any], Optional[Callable[[Any], None]]]:
        """
        self로부터 안전하게 psycopg2 connection을 얻는 유틸리티.
        반환: (conn, release_fn)
          - conn: 획득한 connection 객체 (또는 None)
          - release_fn: 획득한 connection을 반환/닫을 함수. None이면 호출자(보통 self.conn)를 닫지 않음.
        시도 순서:
          1) 전역 pool 모듈(get_connection/release_connection) 사용
          2) self.connect() 호출 후 self.conn 사용
        """
        # avoid import-time dependency on psycopg2
        try:
            # 1) 전역 pool 모듈 우선 시도
            try:
                from .. import pool as _pool_mod  # type: ignore
                get_conn = getattr(_pool_mod, "get_connection", None)
                release_conn = getattr(_pool_mod, "release_connection", None)
                if callable(get_conn):
                    try:
                        conn = get_conn()
                        if conn:
                            def _release(c):
                                try:
                                    if callable(release_conn):
                                        release_conn(c)
                                    else:
                                        try:
                                            c.close()
                                        except Exception:
                                            pass
                                except Exception:
                                    try:
                                        c.close()
                                    except Exception:
                                        pass
                            logger.debug("[schema_ddl] acquire_conn_flex: obtained conn from global pool id=%s closed=%s", id(conn), getattr(conn, "closed", None))
                            return conn, _release
                    except Exception:
                        # fall through to self.connect
                        logger.debug("[schema_ddl] global pool get_connection failed", exc_info=True)
            except Exception:
                # pool module not available
                pass

            # 2) self.connect() 사용
            if callable(getattr(self, "connect", None)):
                try:
                    ok = self.connect()
                except Exception:
                    ok = False
                conn = getattr(self, "conn", None)
                if conn and not getattr(conn, "closed", 0):
                    # caller should NOT close self.conn
                    logger.debug("[schema_ddl] acquire_conn_flex: using self.conn id=%s closed=%s", id(conn), getattr(conn, "closed", None))
                    return conn, None

        except Exception:
            logger.debug("[schema_ddl] acquire_conn_flex unexpected error", exc_info=True)

        logger.debug("[schema_ddl] acquire_conn_flex: no connection source available")
        return None, None

    def _execute_with_fresh_conn(
        self,
        fn: Callable[[Any], Any],
        max_retries: int = 1,
        retry_backoff: float = 0.5,
        autocommit: Optional[bool] = None,
    ) -> Any:
        """
        주어진 함수 fn(cur 또는 conn)을 안전하게 실행.

        전략:
        - _acquire_conn_flex로 conn을 얻고, 작업 후 release_fn으로 반환/닫음.
        - psycopg2.InterfaceError / OperationalError 계열 예외는 연결을 닫고 재접속하여 재시도.
        - fn에는 cursor를 전달(대부분의 사용처가 cursor 기대).
        """
        try:
            import psycopg2
            DB_EXCEPTIONS = (psycopg2.InterfaceError, psycopg2.OperationalError)
        except Exception:
            DB_EXCEPTIONS = ()

        attempt = 0
        last_exc = None

        while attempt <= max_retries:
            attempt += 1
            conn = None
            release_fn = None
            cur = None
            try:
                conn, release_fn = self._acquire_conn_flex()
                if not conn:
                    raise RuntimeError("DB 연결 불가 (no conn from _acquire_conn_flex)")

                # temporary autocommit toggle
                old_autocommit = getattr(conn, "autocommit", None)
                if autocommit is not None:
                    try:
                        conn.autocommit = bool(autocommit)
                    except Exception:
                        pass

                # create cursor
                cur = conn.cursor()
                try:
                    result = fn(cur)
                    # commit if not autocommit True
                    if autocommit is not True:
                        try:
                            conn.commit()
                        except Exception:
                            logger.debug("[schema_ddl] commit failed (ignored)", exc_info=True)
                    return result
                finally:
                    try:
                        cur.close()
                    except Exception:
                        pass
                    if autocommit is not None:
                        try:
                            if old_autocommit is None:
                                try:
                                    delattr(conn, "autocommit")
                                except Exception:
                                    pass
                            else:
                                conn.autocommit = old_autocommit
                        except Exception:
                            pass

            except DB_EXCEPTIONS as db_e:
                last_exc = db_e
                logger.warning("[schema_ddl] DB 오류 발생 (시도 %d/%d): %s", attempt, max_retries + 1, db_e)
                # cleanup: release or close
                try:
                    if cur:
                        try:
                            cur.close()
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if release_fn and conn:
                        try:
                            release_fn(conn)
                        except Exception:
                            try:
                                conn.close()
                            except Exception:
                                pass
                    else:
                        # if this was self.conn, clear it to force reconnect on next attempt
                        try:
                            if getattr(self, "conn", None) is conn:
                                try:
                                    conn.close()
                                except Exception:
                                    pass
                                try:
                                    self.conn = None
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception:
                    pass

                if attempt > max_retries:
                    logger.exception("[schema_ddl] 재시도 한계 도달, 작업 실패")
                    raise
                time.sleep(retry_backoff * attempt)
                continue

            except Exception as e:
                last_exc = e
                logger.exception("[schema_ddl] 실행 중 예외", exc_info=True)
                try:
                    if cur:
                        try:
                            cur.close()
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if release_fn and conn:
                        try:
                            release_fn(conn)
                        except Exception:
                            try:
                                conn.close()
                            except Exception:
                                pass
                    else:
                        # don't forcibly close self.conn here
                        pass
                except Exception:
                    pass
                raise

        if last_exc:
            raise last_exc
        return None

    # ------------------------------------------------------------------
    # TimescaleDB 확장 활성화 (이제 wrapper 사용)
    # ------------------------------------------------------------------
    def ensure_timescaledb_extension(self) -> bool:
        def _fn(cur):
            cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
            return True

        try:
            self._execute_with_fresh_conn(_fn, max_retries=1, autocommit=False)
            logger.debug("ensure_timescaledb_extension: 완료")
            return True
        except Exception:
            logger.exception("ensure_timescaledb_extension 실패")
            try:
                if getattr(self, "conn", None):
                    try:
                        self.conn.rollback()
                    except Exception:
                        pass
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # 하이퍼테이블 및 보조 테이블 DDL 보장
    # ------------------------------------------------------------------
    def ensure_hypertable(self, table_name: str = "candles", time_column: str = "time") -> bool:
        """
        candles 테이블 및 하이퍼테이블 존재를 보장합니다.
        staging_candles, latest_snapshot, isolated_candles 테이블도 함께 생성합니다.
        """
        # 임시 완화: 환경변수로 스킵 가능
        if os.getenv("TIMESCALE_SKIP_SCHEMA", "") == "1":
            logger.info("ensure_hypertable: SKIPPED by TIMESCALE_SKIP_SCHEMA")
            return False

        def _ddl(cur):
            # candles 테이블 생성
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS public.{table_name} (
                exchange     VARCHAR(32),
                symbol       VARCHAR(64),
                symbol_full  VARCHAR(64),
                timeframe    VARCHAR(16),
                time         TIMESTAMPTZ NOT NULL,
                open         NUMERIC,
                high         NUMERIC,
                low          NUMERIC,
                close        NUMERIC,
                volume       NUMERIC DEFAULT 0,
                trade_count  BIGINT,
                is_closed    BOOLEAN DEFAULT TRUE,
                ts           BIGINT,
                raw_data     JSONB
            );
            """)

            # 유니크 제약 (upsert용, 멱등성)
            cur.execute(f"""
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'candles_unique_time_symbol_tf'
              ) THEN
                BEGIN
                  ALTER TABLE public.{table_name}
                    ADD CONSTRAINT candles_unique_time_symbol_tf UNIQUE (time, symbol, timeframe);
                EXCEPTION WHEN duplicate_object THEN
                  NULL;
                END;
              END IF;
            END
            $$;
            """)

            # 확장 존재 여부 확인 및 하이퍼테이블 생성 시도
            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'timescaledb';")
            ext = cur.fetchone()
            if ext:
                try:
                    cur.execute(f"SELECT create_hypertable('public.{table_name}', '{time_column}', if_not_exists => TRUE);")
                except Exception:
                    try:
                        cur.execute(f"SELECT create_hypertable('public.{table_name}', '{time_column}');")
                    except Exception:
                        logger.debug("하이퍼테이블 생성 스킵 (이미 존재하거나 실패함)")

            # staging_candles 테이블 생성
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS public.staging_candles (
                id           BIGSERIAL PRIMARY KEY,
                exchange     VARCHAR(32),
                symbol       VARCHAR(64),
                symbol_full  VARCHAR(64),
                timeframe    VARCHAR(16),
                time         TIMESTAMPTZ,
                open         NUMERIC,
                high         NUMERIC,
                low          NUMERIC,
                close        NUMERIC,
                volume       NUMERIC,
                trade_count  BIGINT,
                is_closed    BOOLEAN,
                ts           BIGINT
            );
            """)

            # latest_snapshot 테이블 생성
            cur.execute("""
            CREATE TABLE IF NOT EXISTS public.latest_snapshot (
              symbol           VARCHAR(64),
              timeframe        VARCHAR(16) DEFAULT '1m',
              last_candle_time TIMESTAMPTZ,
              last_seq         BIGINT,
              candle_count     BIGINT DEFAULT 0,
              updated_at       TIMESTAMPTZ DEFAULT NOW(),
              time             TIMESTAMPTZ
            );
            """)

            # latest_snapshot 복합 PK 보장
            cur.execute("""
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'latest_snapshot_pkey'
              ) THEN
                BEGIN
                  ALTER TABLE public.latest_snapshot
                    ADD CONSTRAINT latest_snapshot_pkey PRIMARY KEY (symbol, timeframe);
                EXCEPTION WHEN duplicate_object THEN
                  NULL;
                END;
              END IF;
            END
            $$;
            """)

            # latest_snapshot 인덱스 생성 (있으면 무시)
            try:
                cur.execute("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'latest_snapshot'
                      AND column_name = 'last_candle_time';
                """)
                if cur.fetchone():
                    try:
                        cur.execute("CREATE INDEX IF NOT EXISTS idx_latest_snapshot_time ON public.latest_snapshot(last_candle_time);")
                    except Exception:
                        logger.exception("idx_latest_snapshot_time 인덱스 생성 실패")
            except Exception:
                logger.exception("latest_snapshot 스키마 조정 실패")

            # isolated_candles 테이블 생성 및 인덱스
            cur.execute("""
            CREATE TABLE IF NOT EXISTS public.isolated_candles (
                id               BIGSERIAL PRIMARY KEY,
                time             TIMESTAMPTZ NOT NULL,
                symbol           VARCHAR(64) NOT NULL,
                timeframe        VARCHAR(16) NOT NULL,
                exchange         VARCHAR(32) NOT NULL,
                open             NUMERIC,
                high             NUMERIC,
                low              NUMERIC,
                close            NUMERIC,
                volume           NUMERIC,
                quote_volume     NUMERIC,
                raw_data         JSONB,
                isolation_reason TEXT NOT NULL,
                received_at      TIMESTAMPTZ DEFAULT NOW(),
                isolated_at      TIMESTAMPTZ DEFAULT NOW(),
                retry_count      INT DEFAULT 0,
                last_retry_at    TIMESTAMPTZ,
                resolved_at      TIMESTAMPTZ
            );
            """)
            try:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_isolated_symbol_time ON public.isolated_candles(symbol, time DESC);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_isolated_reason ON public.isolated_candles(isolation_reason);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_isolated_at ON public.isolated_candles(isolated_at DESC);")
            except Exception:
                logger.exception("isolated_candles 인덱스 생��� 실패")

            return True

        try:
            # 안전한 실행 래퍼 사용
            self._execute_with_fresh_conn(_ddl, max_retries=2, retry_backoff=0.5, autocommit=False)
            logger.debug("ensure_hypertable (isolated_candles 포함) 완료")
            return True
        except Exception:
            logger.exception("ensure_hypertable 실패")
            try:
                # 보수적으로 self.conn rollback
                if getattr(self, "conn", None):
                    try:
                        self.conn.rollback()
                    except Exception:
                        pass
            except Exception:
                pass
            return False

    def ensure_candles_hypertable(self) -> bool:
        """candles 테이블 하이퍼테이블 보장 (기본 진입점)."""
        return self.ensure_hypertable("candles", "time")

    # ------------------------------------------------------------------
    # 연속 집계
    # ------------------------------------------------------------------
    def create_continuous_aggregate(
        self,
        view_name: str,
        bucket_interval: str,
        source_table: str = "public.candles",
        where_clause: Optional[str] = None,
        with_no_data: bool = True,
    ) -> bool:
        """연속 집계 구체화 뷰 생성."""
        def _fn(cur):
            qualified_view = _qualify_name(view_name)
            qualified_src = _qualify_name(source_table) if "." in source_table else _qualify_name(f"public.{source_table}")
            where_sql = f"WHERE {where_clause}" if where_clause else ""
            no_data = "WITH NO DATA" if with_no_data else ""
            sql = f"""
            CREATE MATERIALIZED VIEW IF NOT EXISTS {qualified_view}
            WITH (timescaledb.continuous) AS
            SELECT time_bucket('{bucket_interval}', time) AS bucket, symbol, timeframe,
                   first(open, time) AS open, max(high) AS high, min(low) AS low,
                   last(close, time) AS close, sum(volume) AS volume
            FROM {qualified_src}
            {where_sql}
            GROUP BY bucket, symbol, timeframe
            {no_data};
            """
            cur.execute(sql)
            return True

        try:
            self._execute_with_fresh_conn(_fn, max_retries=1, autocommit=False)
            logger.info("create_continuous_aggregate: %s", view_name)
            return True
        except Exception:
            logger.exception("create_continuous_aggregate 실패")
            try:
                if getattr(self, "conn", None):
                    try:
                        self.conn.rollback()
                    except Exception:
                        pass
            except Exception:
                pass
            return False

    def refresh_materialized_view(self, view_name: str, concurrently: bool = True) -> bool:
        """구체화 뷰 갱신."""
        def _fn(cur):
            qualified_view = _qualify_name(view_name)
            if concurrently:
                try:
                    cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {qualified_view};")
                except Exception:
                    cur.execute(f"REFRESH MATERIALIZED VIEW {qualified_view};")
            else:
                cur.execute(f"REFRESH MATERIALIZED VIEW {qualified_view};")
            return True

        try:
            self._execute_with_fresh_conn(_fn, max_retries=1, autocommit=False)
            logger.info("refresh_materialized_view: %s 갱신 완료", view_name)
            return True
        except Exception:
            logger.exception("refresh_materialized_view 실패")
            try:
                if getattr(self, "conn", None):
                    try:
                        self.conn.rollback()
                    except Exception:
                        pass
            except Exception:
                pass
            return False

    def refresh_continuous_aggregate(
        self,
        view_name: str,
        start_ts: Union[str, None],
        end_ts: Union[str, None],
    ) -> bool:
        """TimescaleDB refresh_continuous_aggregate 프로시저 래퍼."""
        def _fn(cur):
            view_regclass = f"'{_schema_dot_name(view_name)}'::regclass"
            start_sql = f"'{start_ts}'::timestamptz" if start_ts is not None else "NULL"
            end_sql = f"'{end_ts}'::timestamptz" if end_ts is not None else "NULL"
            sql = f"CALL refresh_continuous_aggregate({view_regclass}, {start_sql}, {end_sql});"
            cur.execute(sql)
            return True

        try:
            self._execute_with_fresh_conn(_fn, max_retries=1, autocommit=True)
            logger.info("refresh_continuous_aggregate: %s %s -> %s", view_name, start_ts, end_ts)
            return True
        except Exception:
            logger.exception("refresh_continuous_aggregate 실패")
            return False

    def refresh_continuous_aggregate_progressive(
        self,
        view_name: str,
        start_ts: str,
        end_ts: str,
        window_seconds: int = 600,
        pause_seconds: float = 0.05,
    ) -> bool:
        """연속 집계 점진적 갱신: start_ts → end_ts를 작은 윈도우로 분할."""
        try:
            from datetime import datetime, timezone, timedelta

            def _parse_to_dt(s: str) -> datetime:
                try:
                    dt = datetime.fromisoformat(s)
                except Exception:
                    try:
                        from dateutil import parser as _p  # type: ignore
                        dt = _p.parse(s)
                    except Exception:
                        raise
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)

            start_dt = _parse_to_dt(start_ts)
            end_dt = _parse_to_dt(end_ts)
            cur_start = start_dt
            view_regclass = f"'{_schema_dot_name(view_name)}'::regclass"
            while cur_start < end_dt:
                cur_end = min(cur_start + timedelta(seconds=window_seconds), end_dt)
                s_iso = cur_start.isoformat()
                e_iso = cur_end.isoformat()

                def _call_window(cur):
                    sql = f"CALL refresh_continuous_aggregate({view_regclass}, '{s_iso}'::timestamptz, '{e_iso}'::timestamptz);"
                    cur.execute(sql)
                    return True

                try:
                    self._execute_with_fresh_conn(_call_window, max_retries=1, autocommit=True)
                    logger.info("점진적 갱신: %s %s -> %s", view_name, s_iso, e_iso)
                except Exception:
                    logger.exception("점진적 윈도우 갱신 실패, 계속 진행")
                    try:
                        if getattr(self, "conn", None):
                            try:
                                self.conn.rollback()
                            except Exception:
                                pass
                    except Exception:
                        pass

                cur_start = cur_end
                if pause_seconds:
                    time.sleep(pause_seconds)
            return True
        except Exception:
            logger.exception("refresh_continuous_aggregate_progressive 실패")
            try:
                if getattr(self, "conn", None):
                    try:
                        self.conn.rollback()
                    except Exception:
                        pass
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # 압축 정책
    # ------------------------------------------------------------------
    def add_compression_policy(self, table_name: str, older_than: str = "7 days") -> bool:
        """압축 정책 추가."""
        def _fn(cur):
            cur.execute("SELECT 1 FROM pg_proc WHERE proname = 'add_compression_policy';")
            if cur.fetchone():
                try:
                    cur.execute(f"SELECT add_compression_policy('{table_name}', INTERVAL '{older_than}');")
                except Exception:
                    logger.exception("add_compression_policy 호출 실패; 계속 진행")
                    try:
                        cur.connection.rollback()
                    except Exception:
                        pass
            else:
                logger.warning("add_compression_policy 미지원")
            return True

        try:
            self._execute_with_fresh_conn(_fn, max_retries=1, autocommit=False)
            return True
        except Exception:
            logger.exception("add_compression_policy 실패")
            try:
                if getattr(self, "conn", None):
                    try:
                        self.conn.rollback()
                    except Exception:
                        pass
            except Exception:
                pass
            return False