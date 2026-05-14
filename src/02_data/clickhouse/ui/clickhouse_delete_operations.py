# -*- coding: utf-8 -*-
"""
clickhouse_delete_operations.py — ClickHouse 데이터 삭제 로직 (SRP 분리)

ClickHouseDeleteMixin 클래스를 제공합니다.
ClickHouseSettingsDialog 에서 다중 상속으로 사용합니다.

지원 작업:
  - candles 테이블 전체 삭제 (DELETE FROM)
  - candles 테이블 TRUNCATE
  - 파티션 DROP
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QMessageBox, QInputDialog, QLineEdit
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class ClickHouseDeleteMixin:
    """ClickHouse 데이터 삭제 기능 믹스인.

    사용법:
        class ClickHouseSettingsDialog(QDialog, ClickHouseDeleteMixin):
            def __init__(self, ...):
                ...
                self._bind_ch_delete_signals()
    """

    # ------------------------------------------------------------------
    # 시그널 바인딩
    # ------------------------------------------------------------------

    def _bind_ch_delete_signals(self) -> None:
        """삭제 탭 버튼들을 슬롯에 연결합니다."""
        btn_map = {
            "btn_delete_ch_candles_all": self._on_delete_ch_candles_all,
            "btn_truncate_ch_candles": self._on_truncate_ch_candles,
            "btn_drop_ch_partition": self._on_drop_ch_partition,
        }
        for btn_name, slot in btn_map.items():
            btn = getattr(self, btn_name, None)
            if btn is not None:
                btn.clicked.connect(slot)

    # ------------------------------------------------------------------
    # 삭제 핸들러
    # ------------------------------------------------------------------

    def _on_delete_ch_candles_all(self) -> None:
        """candles 테이블 전체 삭제"""
        if self._confirm_ch_delete("candles 테이블 전체 데이터"):
            threading.Thread(
                target=self._exec_ch_query,
                args=("ALTER TABLE candles DELETE WHERE 1=1",),
                daemon=True,
            ).start()

    def _on_truncate_ch_candles(self) -> None:
        """candles 테이블 TRUNCATE"""
        if self._confirm_ch_delete("candles 테이블 TRUNCATE (즉시 삭제)"):
            threading.Thread(
                target=self._exec_ch_query,
                args=("TRUNCATE TABLE candles",),
                daemon=True,
            ).start()

    def _on_drop_ch_partition(self) -> None:
        """입력된 파티션 DROP"""
        import re
        edit = getattr(self, "edit_delete_partition", None)
        partition = edit.text().strip() if edit is not None else ""
        if not partition:
            QMessageBox.warning(self, "입력 오류", "삭제할 파티션 ID를 입력하세요 (예: 202501).")
            return
        # 파티션 ID 형식 검증 (숫자/영문/하이픈만 허용)
        if not re.match(r'^[A-Za-z0-9_\-]+$', partition):
            QMessageBox.warning(self, "입력 오류", "파티션 ID에 허용되지 않는 문자가 포함되어 있습니다.")
            return
        if self._confirm_ch_delete(f"파티션 {partition} 삭제"):
            threading.Thread(
                target=self._exec_ch_query,
                args=(f"ALTER TABLE candles DROP PARTITION '{partition}'",),
                daemon=True,
            ).start()

    # ------------------------------------------------------------------
    # ClickHouse 실행 (백그라운드)
    # ------------------------------------------------------------------

    def _exec_ch_query(self, sql: str) -> None:
        """ClickHouse 쿼리 실행"""
        try:
            client = self._get_ch_client()
            if client is None:
                return
            client.command(sql)
            logger.info("[ClickHouseDeleteMixin] 쿼리 실행 완료: %s", sql[:60])
        except Exception as exc:
            logger.error("[ClickHouseDeleteMixin] 쿼리 실패 (%s): %s", sql[:60], exc)

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    def _confirm_ch_delete(self, target: str) -> bool:
        """삭제 확인 팝업"""
        ret = QMessageBox.warning(
            self,
            "⚠️ 삭제 확인",
            f"[{target}] 을 삭제하시겠습니까?\n\n삭제된 데이터는 복구할 수 없습니다!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return ret == QMessageBox.Yes

    def _get_ch_client(self):
        """ClickHouse 클라이언트를 반환합니다. 실패 시 None."""
        try:
            import clickhouse_connect  # type: ignore[import]
            import os
            host = os.getenv("CLICKHOUSE_HOST", "localhost")
            port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
            user = os.getenv("CLICKHOUSE_USER", "default")
            password = os.getenv("CLICKHOUSE_PASSWORD", "")
            db = os.getenv("CLICKHOUSE_DB", "upbit_trader")
            return clickhouse_connect.get_client(
                host=host, port=port, username=user, password=password, database=db,
                connect_timeout=5,
            )
        except ImportError:
            logger.debug("[ClickHouseDeleteMixin] clickhouse-connect 미설치")
            return None
        except Exception as exc:
            logger.debug("[ClickHouseDeleteMixin] ClickHouse 연결 실패: %s", exc)
            return None
