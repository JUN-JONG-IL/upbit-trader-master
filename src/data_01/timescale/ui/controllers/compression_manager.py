#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TimescaleDB 압축 정책 관리자"""

import logging
import threading
from typing import Callable, Optional

try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)


class _ManagerBase:
    """PyQt5 없는 환경을 위한 기반 클래스."""

    def __init__(self):
        self._callbacks: list[Callable] = []

    def compression_updated_connect(self, callback: Callable):
        """압축 정보 갱신 콜백을 등록합니다."""
        self._callbacks.append(callback)

    def _emit_compression(self, data: list):
        for cb in self._callbacks:
            try:
                cb(data)
            except Exception as exc:
                logger.debug("압축 콜백 오류: %s", exc)


if _HAS_QT:
    class _QtBase(QObject):
        compression_updated = pyqtSignal(list)

        def _emit_compression(self, data: list):
            self.compression_updated.emit(data)

    _Base = _QtBase
else:
    _Base = _ManagerBase


class CompressionManager(_Base):
    """TimescaleDB 압축 정책 관리자.

    각 하이퍼테이블의 압축 정책 적용 여부, 압축 청크 수,
    미압축 청크 수를 주기적으로 수집하고 시그널/콜백으로 전달합니다.

    압축 정책 적용 및 해제 메서드도 제공합니다.

    Example::

        manager = CompressionManager(db_conn=conn)
        manager.compression_updated.connect(lambda rows: ...)
        manager.start()
        manager.enable_compression("ohlcv", compress_after="7 days")
        ...
        manager.stop()
    """

    def __init__(self, db_conn=None, interval: int = 60):
        """초기화.

        Args:
            db_conn: TimescaleDB 연결 객체
            interval: 수집 주기 (초)
        """
        if _HAS_QT:
            super().__init__()
        else:
            _ManagerBase.__init__(self)

        self._db_conn = db_conn
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    def start(self):
        """모니터링 스레드를 시작합니다."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="CompressionManager"
        )
        self._thread.start()
        logger.info("CompressionManager 시작 (간격: %ds)", self._interval)

    def stop(self):
        """모니터링 스레드를 중지합니다."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 2)
        logger.info("CompressionManager 중지")

    def collect_once(self) -> list:
        """단발 압축 정보 수집을 수행합니다.

        Returns:
            (테이블명, 정책, 압축 청크 수, 미압축 청크 수) 튜플 목록
        """
        return self._collect()

    def enable_compression(self, table_name: str, compress_after: str = "7 days") -> bool:
        """지정 테이블에 압축 정책을 설정합니다.

        Args:
            table_name: 하이퍼테이블 이름
            compress_after: 압축 기준 기간 (예: '7 days')

        Returns:
            성공 여부
        """
        if self._db_conn is None:
            logger.warning("DB 연결이 없습니다.")
            return False
        try:
            with self._db_conn.cursor() as cur:
                cur.execute(
                    "SELECT add_compression_policy(%s, INTERVAL %s);",
                    (table_name, compress_after),
                )
            self._db_conn.commit()
            logger.info("압축 정책 설정: %s (after %s)", table_name, compress_after)
            return True
        except Exception as exc:
            logger.error("압축 정책 설정 실패: %s", exc)
            return False

    def disable_compression(self, table_name: str) -> bool:
        """지정 테이블의 압축 정책을 해제합니다.

        Args:
            table_name: 하이퍼테이블 이름

        Returns:
            성공 여부
        """
        if self._db_conn is None:
            return False
        try:
            with self._db_conn.cursor() as cur:
                cur.execute(
                    "SELECT remove_compression_policy(%s);",
                    (table_name,),
                )
            self._db_conn.commit()
            logger.info("압축 정책 해제: %s", table_name)
            return True
        except Exception as exc:
            logger.error("압축 정책 해제 실패: %s", exc)
            return False

    # ------------------------------------------------------------------
    # 내부 로직
    # ------------------------------------------------------------------

    def _run(self):
        """백그라운드 스레드 루프."""
        while not self._stop_event.wait(self._interval):
            data = self._collect()
            self._emit_compression(data)

    def _collect(self) -> list:
        """압축 정책 및 청크 통계를 조회합니다.

        Returns:
            (테이블명, 정책, 압축청크수, 미압축청크수) 튜플 목록
        """
        if self._db_conn is None:
            return []

        query = """
            SELECT
                h.hypertable_name,
                COALESCE(p.config->>'compress_after', '정책 없음') AS policy,
                COUNT(c.chunk_name) FILTER (WHERE c.is_compressed)::text  AS compressed,
                COUNT(c.chunk_name) FILTER (WHERE NOT c.is_compressed)::text AS uncompressed
            FROM timescaledb_information.hypertables h
            LEFT JOIN timescaledb_information.chunks c
                   ON c.hypertable_name = h.hypertable_name
            LEFT JOIN (
                SELECT hypertable_name, config
                  FROM timescaledb_information.jobs
                 WHERE proc_name = 'policy_compression'
            ) p ON p.hypertable_name = h.hypertable_name
            GROUP BY h.hypertable_name, p.config
            ORDER BY h.hypertable_name;
        """
        try:
            with self._db_conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchall()
        except Exception as exc:
            logger.warning("압축 정보 수집 실패: %s", exc)
            return []
