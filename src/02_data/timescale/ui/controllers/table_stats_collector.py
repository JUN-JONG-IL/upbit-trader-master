#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TimescaleDB 테이블 통계 수집기"""

import logging
import threading
from typing import Callable, Optional

try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)


class _CollectorBase:
    """PyQt5 없는 환경을 위한 기반 클래스."""

    def __init__(self):
        self._callbacks: list[Callable] = []

    def stats_updated_connect(self, callback: Callable):
        """통계 갱신 콜백을 등록합니다."""
        self._callbacks.append(callback)

    def _emit_stats(self, stats: list):
        for cb in self._callbacks:
            try:
                cb(stats)
            except Exception as exc:
                logger.debug("통계 콜백 오류: %s", exc)


if _HAS_QT:
    class _QtBase(QObject):
        stats_updated = pyqtSignal(list)

        def _emit_stats(self, stats: list):
            self.stats_updated.emit(stats)

    _Base = _QtBase
else:
    _Base = _CollectorBase


class TableStatsCollector(_Base):
    """TimescaleDB 테이블 통계 수집기.

    하이퍼테이블별 레코드 수, 크기, 최신 시각 등의 통계를
    주기적으로 수집하고 stats_updated 시그널로 전달합니다.

    Example::

        collector = TableStatsCollector(db_conn=conn, interval=30)
        collector.stats_updated.connect(lambda rows: ...)
        collector.start()
        ...
        collector.stop()
    """

    def __init__(self, db_conn=None, interval: int = 30):
        """초기화.

        Args:
            db_conn: TimescaleDB 연결 객체
            interval: 수집 주기 (초)
        """
        if _HAS_QT:
            super().__init__()
        else:
            _CollectorBase.__init__(self)

        self._db_conn = db_conn
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    def start(self):
        """수집 스레드를 시작합니다."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="TableStatsCollector"
        )
        self._thread.start()
        logger.info("TableStatsCollector 시작 (간격: %ds)", self._interval)

    def stop(self):
        """수집 스레드를 중지합니다."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 2)
        logger.info("TableStatsCollector 중지")

    def collect_once(self) -> list:
        """단발 통계 수집을 수행합니다.

        Returns:
            (테이블명, 레코드수, 크기, 최신시각) 튜플 목록
        """
        return self._collect()

    # ------------------------------------------------------------------
    # 내부 로직
    # ------------------------------------------------------------------

    def _run(self):
        """백그라운드 스레드 루프."""
        while not self._stop_event.wait(self._interval):
            stats = self._collect()
            self._emit_stats(stats)

    def _collect(self) -> list:
        """실제 통계 쿼리를 실행합니다.

        Returns:
            (hypertable_name, approx_rows, size_pretty, latest_chunk) 튜플 목록
        """
        if self._db_conn is None:
            return []

        query = """
            SELECT
                h.hypertable_name,
                h.num_chunks::text AS chunks,
                pg_size_pretty(
                    hypertable_size(
                        (h.hypertable_schema || '.' || h.hypertable_name)::regclass
                    )
                ) AS size,
                (
                    SELECT range_end::text
                      FROM timescaledb_information.chunks c
                     WHERE c.hypertable_name = h.hypertable_name
                     ORDER BY range_end DESC
                     LIMIT 1
                ) AS latest_range
            FROM timescaledb_information.hypertables h
            ORDER BY h.hypertable_name;
        """
        try:
            with self._db_conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchall()
        except Exception as exc:
            logger.warning("테이블 통계 수집 실패: %s", exc)
            return []
