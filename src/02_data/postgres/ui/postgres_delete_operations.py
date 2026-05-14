# -*- coding: utf-8 -*-
"""
postgres_delete_operations.py — PostgreSQL CQRS Event Store 데이터 삭제 로직 (SRP 분리)

PostgresDeleteMixin 클래스를 제공합니다.
PostgresEventStoreDialog 에서 다중 상속으로 사용합니다.

지원 작업:
  - events 테이블 전체 삭제
  - audit_log 테이블 전체 삭제
  - 이벤트 타입별 삭제
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QMessageBox
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class PostgresDeleteMixin:
    """PostgreSQL 데이터 삭제 기능 믹스인.

    사용법:
        class PostgresEventStoreDialog(QDialog, PostgresDeleteMixin):
            def __init__(self, ...):
                ...
                self._bind_pg_delete_signals()
    """

    # ------------------------------------------------------------------
    # 시그널 바인딩
    # ------------------------------------------------------------------

    def _bind_pg_delete_signals(self) -> None:
        """삭제 탭 버튼들을 슬롯에 연결합니다."""
        btn_map = {
            "btn_delete_pg_events_all": self._on_delete_pg_events_all,
            "btn_delete_pg_audit_all": self._on_delete_pg_audit_all,
            "btn_delete_pg_by_type": self._on_delete_pg_by_type,
        }
        for btn_name, slot in btn_map.items():
            btn = getattr(self, btn_name, None)
            if btn is not None:
                btn.clicked.connect(slot)

    # ------------------------------------------------------------------
    # 삭제 핸들러
    # ------------------------------------------------------------------

    def _on_delete_pg_events_all(self) -> None:
        """events 테이블 전체 삭제"""
        if self._confirm_pg_delete("events 테이블", "모든 이벤트 데이터"):
            threading.Thread(
                target=self._exec_pg_delete,
                args=("DELETE FROM events", ()),
                daemon=True,
            ).start()

    def _on_delete_pg_audit_all(self) -> None:
        """audit_log 테이블 전체 삭제"""
        if self._confirm_pg_delete("audit_log 테이블", "모든 감사 로그"):
            threading.Thread(
                target=self._exec_pg_delete,
                args=("DELETE FROM audit_log", ()),
                daemon=True,
            ).start()

    def _on_delete_pg_by_type(self) -> None:
        """이벤트 타입별 삭제"""
        edit = getattr(self, "edit_delete_event_type", None)
        event_type = edit.text().strip() if edit is not None else ""
        if not event_type:
            QMessageBox.warning(self, "입력 오류", "삭제할 이벤트 타입을 입력하세요.")
            return
        if event_type.upper() == "ALL":
            sql = "DELETE FROM events"
            params: tuple = ()
            desc = "모든 이벤트 데이터"
        else:
            sql = "DELETE FROM events WHERE event_type = %s"
            params = (event_type,)
            desc = f"event_type={event_type} 이벤트"
        if self._confirm_pg_delete("events 테이블", desc):
            threading.Thread(
                target=self._exec_pg_delete,
                args=(sql, params),
                daemon=True,
            ).start()

    # ------------------------------------------------------------------
    # PostgreSQL 실행 (백그라운드)
    # ------------------------------------------------------------------

    def _exec_pg_delete(self, sql: str, params: tuple = ()) -> None:
        """SQL DELETE 실행"""
        try:
            conn = self._get_pg_conn()
            if conn is None:
                return
            cur = conn.cursor()
            try:
                cur.execute(sql, params)
                conn.commit()
                logger.info("[PostgresDeleteMixin] 삭제 완료 (%d건): %s", cur.rowcount, sql[:60])
            finally:
                cur.close()
                conn.close()
        except Exception as exc:
            logger.error("[PostgresDeleteMixin] 삭제 실패 (%s): %s", sql[:60], exc)

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    def _confirm_pg_delete(self, target: str, description: str) -> bool:
        """삭제 확인 팝업"""
        ret = QMessageBox.warning(
            self,
            "⚠️ 삭제 확인",
            f"정말로 [{target}] 의 [{description}] 을 삭제하시겠습니까?\n\n삭제된 데이터는 복구할 수 없습니다!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return ret == QMessageBox.Yes

    def _get_pg_conn(self):
        """PostgreSQL 연결을 반환합니다. 실패 시 None."""
        try:
            import psycopg2  # type: ignore[import]
            import os
            return psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                dbname=os.getenv("POSTGRES_DB", "upbit_trader"),
                user=os.getenv("POSTGRES_USER", "admin"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
                connect_timeout=5,
            )
        except Exception as exc:
            logger.debug("[PostgresDeleteMixin] DB 연결 실패: %s", exc)
            return None
