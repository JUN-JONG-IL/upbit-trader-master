# -*- coding: utf-8 -*-
"""
candle_writer — CandleWriterMixin (v2.0 - symbol_full 제거)

캔들 데이터 삽입/스테이징/플러시 담당 믹스인.

✅ 변경사항 v2.0 (2026-04-26):
- symbol_full 컬럼 완전 제거
- 12열 형식으로 통일
- 중복 제거 로직 개선 (DISTINCT ON)

실제 DB 스키마 (12열):
  candles:
    - PRIMARY KEY: (symbol, timeframe, time)
    - 컬럼: exchange, symbol, timeframe, time, open, high, low, close,
            volume, quote_volume, trade_count, is_complete, seq

  staging_candles:
    - id BIGSERIAL PRIMARY KEY
    - 컬럼: exchange, symbol, timeframe, time, open, high, low, close,
            volume, quote_volume, trade_count, is_complete, seq, inserted_at

데이터 형식:
  (exchange, symbol, timeframe, time, open, high, low, close,
   volume, quote_volume, trade_count, is_complete, seq)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("timescale_db")

# psycopg2.extras.execute_values 지연 임포트
try:
    from psycopg2.extras import execute_values as _execute_values  # type: ignore
except ImportError:
    _execute_values = None


class CandleWriterMixin:
    """캔들 데이터 삽입/스테이징/플러시 담당 믹스인."""

    # ------------------------------------------------------------------
    # 벌크 삽입
    # ------------------------------------------------------------------
    def insert_candles_bulk(
        self,
        rows_iterable: Iterable[Tuple[Any, ...]],
        target_table: str = "candles",
    ) -> int:
        """
        캔들 데이터 벌크 upsert (12열 형식).
        
        입력 형식:
            (exchange, symbol, timeframe, time, open, high, low, close,
             volume, quote_volume, trade_count, is_complete, seq)
        
        Returns:
            삽입/업데이트된 행 수
        """
        rows = list(rows_iterable)
        if not rows:
            return 0
        
        if _execute_values is None:
            raise RuntimeError("psycopg2.extras.execute_values 필요")
        
        try:
            # 행 길이 검증
            normalized: List[Tuple[Any, ...]] = []
            for r in rows:
                try:
                    rlen = len(r)
                except Exception:
                    raise RuntimeError("insert_candles_bulk: 행 타입 오류")
                
                if rlen != 12:
                    raise RuntimeError(
                        f"insert_candles_bulk: 잘못된 행 길이 {rlen} (12 필요)\n"
                        f"형식: (exchange, symbol, timeframe, time, open, high, low, close, "
                        f"volume, quote_volume, trade_count, is_complete, seq)"
                    )
                
                normalized.append(tuple(r[:12]))
            
            if not self.conn and not self.connect():
                raise RuntimeError("DB 연결 실패")
            
            # 컬럼 정의 (symbol_full 제거!)
            cols = (
                "exchange", "symbol", "timeframe", "time",
                "open", "high", "low", "close",
                "volume", "quote_volume", "trade_count", "is_complete", "seq"
            )
            col_list = ",".join(cols)
            
            # ON CONFLICT 처리
            on_conflict = f"""
            ON CONFLICT (symbol, timeframe, time) DO UPDATE SET
              exchange     = COALESCE(EXCLUDED.exchange, {target_table}.exchange),
              open         = COALESCE(EXCLUDED.open, {target_table}.open),
              high         = GREATEST(
                               COALESCE({target_table}.high, EXCLUDED.high),
                               COALESCE(EXCLUDED.high, {target_table}.high)
                             ),
              low          = LEAST(
                               COALESCE({target_table}.low, EXCLUDED.low),
                               COALESCE(EXCLUDED.low, {target_table}.low)
                             ),
              close        = EXCLUDED.close,
              volume       = COALESCE({target_table}.volume, 0) + COALESCE(EXCLUDED.volume, 0),
              quote_volume = COALESCE({target_table}.quote_volume, 0) + COALESCE(EXCLUDED.quote_volume, 0),
              trade_count  = COALESCE(EXCLUDED.trade_count, {target_table}.trade_count),
              is_complete  = EXCLUDED.is_complete,
              seq          = EXCLUDED.seq
            """
            
            sql = f"INSERT INTO public.{target_table} ({col_list}) VALUES %s {on_conflict};"
            template = "(" + ",".join(["%s"] * len(cols)) + ")"
            
            with self.conn.cursor() as cur:
                _execute_values(cur, sql, normalized, template=template, page_size=1000)
                self.conn.commit()
            
            logger.info(
                "insert_candles_bulk: %s에 %d행 삽입/업서트 완료",
                target_table, len(normalized)
            )
            return len(normalized)
        
        except Exception:
            logger.exception("insert_candles_bulk 실패")
            try:
                if self.conn:
                    self.conn.rollback()
            except Exception:
                pass
            raise

    # ------------------------------------------------------------------
    # 스테이징 삽입
    # ------------------------------------------------------------------
    def insert_into_staging(
        self,
        rows_iterable: Iterable[Tuple[Any, ...]],
        staging_table: str = "staging_candles",
    ) -> int:
        """
        스테이징 테이블에 데이터 삽입 (12열 형식).
        
        입력 형식:
            (exchange, symbol, timeframe, time, open, high, low, close,
             volume, quote_volume, trade_count, is_complete, seq)
        
        Returns:
            삽입된 행 수
        """
        rows = list(rows_iterable)
        if not rows:
            return 0
        
        if _execute_values is None:
            raise RuntimeError("psycopg2.extras.execute_values 필요")
        
        try:
            # 행 길이 검증
            normalized: List[Tuple[Any, ...]] = []
            for r in rows:
                try:
                    rlen = len(r)
                except Exception:
                    raise RuntimeError("insert_into_staging: 행 타입 오류")
                
                if rlen != 12:
                    raise RuntimeError(f"insert_into_staging: 잘못된 행 길이 {rlen} (12 필요)")
                
                normalized.append(tuple(r[:12]))
            
            if not self.conn and not self.connect():
                raise RuntimeError("DB 연결 실패")
            
            # 스테이징 테이블 생성 (symbol_full 제거!)
            create_sql = f"""
            CREATE TABLE IF NOT EXISTS public.{staging_table} (
                id           BIGSERIAL PRIMARY KEY,
                exchange     VARCHAR(32),
                symbol       VARCHAR(64) NOT NULL,
                timeframe    VARCHAR(16) NOT NULL,
                time         TIMESTAMPTZ NOT NULL,
                open         NUMERIC,
                high         NUMERIC,
                low          NUMERIC,
                close        NUMERIC,
                volume       NUMERIC,
                quote_volume NUMERIC,
                trade_count  INTEGER,
                is_complete  BOOLEAN,
                seq          BIGINT,
                inserted_at  TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_staging_time ON public.{staging_table} (time DESC);
            CREATE INDEX IF NOT EXISTS idx_staging_symbol_time ON public.{staging_table} (symbol, timeframe, time);
            """
            
            cols = (
                "exchange", "symbol", "timeframe", "time",
                "open", "high", "low", "close",
                "volume", "quote_volume", "trade_count", "is_complete", "seq"
            )
            col_list = ",".join(cols)
            template = "(" + ",".join(["%s"] * len(cols)) + ")"
            
            with self.conn.cursor() as cur:
                cur.execute(create_sql)
                insert_sql = f"INSERT INTO public.{staging_table} ({col_list}) VALUES %s;"
                _execute_values(cur, insert_sql, normalized, template=template, page_size=1000)
                self.conn.commit()
            
            logger.info("insert_into_staging: %s에 %d행 추가", staging_table, len(normalized))
            return len(normalized)
        
        except Exception:
            logger.exception("insert_into_staging 실패")
            try:
                if self.conn:
                    self.conn.rollback()
            except Exception:
                pass
            raise

    # ------------------------------------------------------------------
    # 스테이징 → 캔들 플러시 (핵심 수정!)
    # ------------------------------------------------------------------
    def flush_staging_to_candles(
        self,
        staging_table: str = "staging_candles",
        target_table: str = "candles",
        batch_size: int = 1000,
    ) -> int:
        """
        staging_candles → candles 이동 (중복 제거).
        
        프로세스:
          1. DISTINCT ON (symbol, timeframe, time)으로 중복 제거
          2. 최신 데이터 우선 (inserted_at DESC)
          3. ON CONFLICT로 upsert
          4. 이동된 행 staging에서 삭제
        
        Returns:
            이동된 총 행 수
        """
        if not self.conn and not self.connect():
            raise RuntimeError("DB 연결 실패")
        
        # Staging 건수 확인
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM public.{staging_table}")
                row = cur.fetchone()
                staging_count = int(row[0]) if row else 0
            
            logger.info("[Finalizer] staging_candles 현재 행 수: %d", staging_count)
            
            if staging_count == 0:
                logger.info("[Finalizer] staging_candles 비어있음 — flush 스킵")
                return 0
        
        except Exception as e:
            logger.warning("[Finalizer] staging 건수 확인 실패: %s", e)
            staging_count = None
        
        total_moved = 0
        
        try:
            while True:
                with self.conn.cursor() as cur:
                    # ✅ symbol_full 완전 제거!
                    move_sql = f"""
                    WITH uniqued AS (
                      SELECT DISTINCT ON (symbol, timeframe, time)
                        id, exchange, symbol, timeframe, time,
                        open, high, low, close,
                        volume, quote_volume, trade_count, is_complete, seq
                      FROM public.{staging_table}
                      ORDER BY symbol, timeframe, time, inserted_at DESC
                      LIMIT %s
                    ),
                    ins AS (
                      INSERT INTO public.{target_table} (
                        exchange, symbol, timeframe, time,
                        open, high, low, close,
                        volume, quote_volume, trade_count, is_complete, seq
                      )
                      SELECT
                        exchange, symbol, timeframe, time,
                        open, high, low, close,
                        volume, quote_volume, trade_count, is_complete, seq
                      FROM uniqued
                      ON CONFLICT (symbol, timeframe, time) DO UPDATE SET
                        exchange     = COALESCE(EXCLUDED.exchange, {target_table}.exchange),
                        open         = COALESCE(EXCLUDED.open, {target_table}.open),
                        high         = GREATEST(
                                         COALESCE({target_table}.high, EXCLUDED.high),
                                         COALESCE(EXCLUDED.high, {target_table}.high)
                                       ),
                        low          = LEAST(
                                         COALESCE({target_table}.low, EXCLUDED.low),
                                         COALESCE(EXCLUDED.low, {target_table}.low)
                                       ),
                        close        = EXCLUDED.close,
                        volume       = COALESCE({target_table}.volume, 0) + COALESCE(EXCLUDED.volume, 0),
                        quote_volume = COALESCE({target_table}.quote_volume, 0) + COALESCE(EXCLUDED.quote_volume, 0),
                        trade_count  = COALESCE(EXCLUDED.trade_count, {target_table}.trade_count),
                        is_complete  = EXCLUDED.is_complete,
                        seq          = EXCLUDED.seq
                      RETURNING 1
                    )
                    DELETE FROM public.{staging_table}
                    WHERE id IN (SELECT id FROM uniqued)
                    RETURNING 1;
                    """
                    
                    cur.execute(move_sql, (batch_size,))
                    moved = cur.rowcount if cur.rowcount is not None else 0
                    self.conn.commit()
                
                if moved <= 0:
                    break
                
                total_moved += moved
                logger.debug("[Finalizer] 배치 이동: %d건", moved)
            
            logger.info(
                "[Finalizer] ✅ flush 완료: %d건 이동 (staging: %s → 0)",
                total_moved,
                str(staging_count) if staging_count is not None else "?"
            )
            return total_moved
        
        except Exception:
            logger.exception("[Finalizer] ❌ flush_staging_to_candles 실패")
            try:
                if self.conn:
                    self.conn.rollback()
            except Exception:
                pass
            raise

    # ------------------------------------------------------------------
    # 호환 래퍼
    # ------------------------------------------------------------------
    def insert_candles(
        self,
        rows_iterable: Iterable[Tuple[Any, ...]],
        target_table: str = "candles",
    ) -> int:
        """insert_candles_bulk 래퍼 — 외부 코드 호환용."""
        return self.insert_candles_bulk(rows_iterable, target_table=target_table)

    def write_candles(
        self,
        symbol: str,
        timeframe: str,
        candles: Iterable[Dict[str, Any]],
        exchange: str = "upbit",
    ) -> int:
        """
        CandleWriter 인터페이스 호환 메서드.
        
        캔들 dict 목록을 12열 형식으로 변환 후 insert_candles_bulk 호출.
        
        입력 dict 형식:
            {
                "time": datetime,
                "open": float,
                "high": float,
                "low": float,
                "close": float,
                "volume": float,
                "quote_volume": float,
                "trade_count": int,
                "is_complete": bool,
                "seq": int
            }
        
        Returns:
            삽입/업데이트된 행 수
        """
        try:
            normalized_rows: List[Tuple[Any, ...]] = []
            
            for c in candles:
                t = c.get("time") or c.get("timestamp") or c.get("start_ts")
                open_p       = c.get("open")
                high_p       = c.get("high")
                low_p        = c.get("low")
                close_p      = c.get("close")
                volume_p     = c.get("volume", 0)
                quote_volume = c.get("quote_volume", 0)
                trade_count  = c.get("trade_count", 0)
                is_complete  = c.get("is_complete", c.get("is_closed", True))
                seq          = c.get("seq", 0)
                
                # ✅ 12열 형식 (symbol_full 제거!)
                row = (
                    exchange, symbol, timeframe, t,
                    open_p, high_p, low_p, close_p,
                    volume_p, quote_volume, trade_count, is_complete, seq
                )
                normalized_rows.append(row)
            
            if not normalized_rows:
                return 0
            
            return int(self.insert_candles_bulk(normalized_rows, target_table="candles"))
        
        except Exception:
            logger.exception("write_candles 실패 (symbol=%s, timeframe=%s)", symbol, timeframe)
            raise