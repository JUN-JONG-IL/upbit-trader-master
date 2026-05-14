#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ClickHouse 테이블 관리 컨트롤러"""

import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)


class TableManager(QObject if _HAS_QT else object):
    """ClickHouse 테이블 목록 조회, 통계 수집, OPTIMIZE 실행을 담당하는 컨트롤러.

    ClickHouse HTTP 클라이언트를 주입받아 사용하며,
    Qt 환경에서는 작업 완료 시 시그널로 결과를 전달합니다.

    Signals:
        tables_loaded(list): 테이블 목록 로드 완료 시 방출
        stats_loaded(list): 테이블 통계 로드 완료 시 방출
        optimize_done(str, bool): OPTIMIZE 완료 시 방출 (테이블명, 성공 여부)
        error_occurred(str): 오류 발생 시 방출
    """

    if _HAS_QT:
        tables_loaded = pyqtSignal(list)
        stats_loaded = pyqtSignal(list)
        optimize_done = pyqtSignal(str, bool)
        error_occurred = pyqtSignal(str)

    def __init__(self, client=None, database: str = "default", parent=None):
        """초기화.

        Args:
            client: ClickHouse HTTP 클라이언트 인스턴스 (선택)
            database: 대상 데이터베이스 이름 (기본값: "default")
            parent: 부모 QObject (선택)
        """
        if _HAS_QT:
            super().__init__(parent)
        self._client = client
        self._database = database

    def set_client(self, client) -> None:
        """ClickHouse 클라이언트를 교체합니다.

        Args:
            client: 새로운 ClickHouse HTTP 클라이언트 인스턴스
        """
        self._client = client

    def set_database(self, database: str) -> None:
        """대상 데이터베이스를 변경합니다.

        Args:
            database: 새로운 데이터베이스 이름
        """
        self._database = database

    def list_tables(self) -> List[str]:
        """현재 데이터베이스의 테이블 목록을 반환합니다.

        Returns:
            테이블 이름 문자열 목록. 오류 시 빈 목록.
        """
        if self._client is None:
            return []
        try:
            query = (
                f"SELECT name FROM system.tables "
                f"WHERE database = '{self._database}' "
                f"ORDER BY name"
            )
            rows = self._client.execute(query)
            tables = [row[0] for row in rows]
            if _HAS_QT:
                self.tables_loaded.emit(tables)
            return tables
        except Exception as exc:
            msg = f"테이블 목록 조회 실패: {exc}"
            logger.error(msg)
            self._emit_error(msg)
            return []

    def get_table_stats(self) -> List[Tuple]:
        """테이블별 레코드 수 및 디스크 사용량 통계를 반환합니다.

        Returns:
            (table, rows, compressed_bytes, uncompressed_bytes) 튜플 목록.
            오류 시 빈 목록.
        """
        if self._client is None:
            return []
        try:
            query = (
                f"SELECT table, sum(rows) AS rows, "
                f"sum(data_compressed_bytes) AS compressed, "
                f"sum(data_uncompressed_bytes) AS uncompressed "
                f"FROM system.parts "
                f"WHERE database = '{self._database}' AND active = 1 "
                f"GROUP BY table ORDER BY rows DESC"
            )
            rows = self._client.execute(query)
            if _HAS_QT:
                self.stats_loaded.emit(list(rows))
            return list(rows)
        except Exception as exc:
            msg = f"테이블 통계 조회 실패: {exc}"
            logger.error(msg)
            self._emit_error(msg)
            return []

    def get_table_ddl(self, table: str) -> Optional[str]:
        """지정한 테이블의 CREATE TABLE DDL 문을 반환합니다.

        Args:
            table: DDL을 조회할 테이블 이름

        Returns:
            DDL 문자열. 오류 시 None.
        """
        if self._client is None:
            return None
        try:
            query = f"SHOW CREATE TABLE {self._database}.{table}"
            rows = self._client.execute(query)
            return rows[0][0] if rows else None
        except Exception as exc:
            msg = f"DDL 조회 실패 ({table}): {exc}"
            logger.error(msg)
            self._emit_error(msg)
            return None

    def optimize_table(self, table: str, final: bool = False) -> bool:
        """지정한 테이블에 OPTIMIZE TABLE 명령을 실행합니다.

        Args:
            table: OPTIMIZE 대상 테이블 이름
            final: True이면 OPTIMIZE TABLE … FINAL 실행

        Returns:
            성공 여부 (bool)
        """
        if self._client is None:
            return False
        suffix = " FINAL" if final else ""
        query = f"OPTIMIZE TABLE {self._database}.{table}{suffix}"
        try:
            self._client.execute(query)
            logger.info("OPTIMIZE 완료: %s.%s", self._database, table)
            if _HAS_QT:
                self.optimize_done.emit(table, True)
            return True
        except Exception as exc:
            msg = f"OPTIMIZE 실패 ({table}): {exc}"
            logger.error(msg)
            self._emit_error(msg)
            if _HAS_QT:
                self.optimize_done.emit(table, False)
            return False

    def drop_table(self, table: str) -> bool:
        """지정한 테이블을 삭제합니다 (비가역적 작업).

        Args:
            table: 삭제할 테이블 이름

        Returns:
            성공 여부 (bool)
        """
        if self._client is None:
            return False
        try:
            self._client.execute(f"DROP TABLE IF EXISTS {self._database}.{table}")
            logger.warning("테이블 삭제됨: %s.%s", self._database, table)
            return True
        except Exception as exc:
            msg = f"테이블 삭제 실패 ({table}): {exc}"
            logger.error(msg)
            self._emit_error(msg)
            return False

    def _emit_error(self, message: str) -> None:
        """오류 메시지를 시그널 또는 로그로 전달합니다.

        Args:
            message: 오류 설명 문자열
        """
        if _HAS_QT:
            try:
                self.error_occurred.emit(message)
            except RuntimeError:
                pass
