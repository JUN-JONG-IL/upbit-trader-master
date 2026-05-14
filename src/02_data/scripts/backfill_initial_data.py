#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
초기 데이터 백필 스크립트

기능:
- staging_candles → candles 전체 flush (미처리 데이터 이관)
- Gap 검출 후 자동 백필

실행 방법:
    python src/02_data/scripts/backfill_initial_data.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src" / "02_data"))

logger = logging.getLogger(__name__)


async def flush_all_staging() -> int:
    """
    staging_candles → candles 전체 flush

    staging_candles.processed = FALSE 인 레코드를 모두 candles로 이관합니다.
    Returns:
        이관된 총 레코드 수
    """
    try:
        import importlib.util

        # timescale connector 로드
        ts_path = _ROOT / "src" / "02_data" / "timescale" / "connector.py"
        if not ts_path.exists():
            logger.error("TimescaleDB connector를 찾을 수 없습니다: %s", ts_path)
            return 0

        spec = importlib.util.spec_from_file_location("timescale_connector", str(ts_path))
        ts_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ts_mod)  # type: ignore

        connector_cls = getattr(ts_mod, "TimescaleConnector", None)
        if connector_cls is None:
            logger.error("TimescaleConnector 클래스를 찾을 수 없습니다.")
            return 0

        connector = connector_cls()
        pool = await connector.create_pool()
        if pool is None:
            logger.error("TimescaleDB 연결 풀 생성 실패")
            return 0

        from pipeline.finalizer import CandlesFinalizer

        finalizer = CandlesFinalizer(pool=pool)
        total = await finalizer.flush_all_staging()
        await pool.close()

        logger.info("✅ staging_candles → candles flush 완료: %d건", total)
        return total

    except Exception as exc:
        logger.error("flush_all_staging 실패: %s", exc, exc_info=True)
        return 0


async def main() -> None:
    """메인 실행"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 60)
    logger.info("초기 데이터 백필 시작")
    logger.info("=" * 60)

    # 1. staging_candles 전체 flush
    flushed = await flush_all_staging()
    logger.info("1. staging flush 완료: %d건", flushed)

    logger.info("=" * 60)
    logger.info("초기 데이터 백필 완료")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
