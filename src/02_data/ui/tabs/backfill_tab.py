# -*- coding: utf-8 -*-
"""Tab 5: 백필 작업 제어 로직"""
from __future__ import annotations
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:
    class BackfillTab(QWidget):
        """Tab 5: 백필 작업 — uic.loadUi() 기반 자립형 위젯"""

        def __init__(self, parent=None):
            super().__init__(parent)
            ui_path = os.path.join(os.path.dirname(__file__), "backfill_tab.ui")
            try:
                uic.loadUi(ui_path, self)
            except Exception as exc:
                logger.warning("[BackfillTab] UI 파일 로드 실패: %s", exc)

            self._timer = QTimer(self)
            self._timer.setInterval(3000)
            self._timer.timeout.connect(self._update_ui)

        def start_updates(self, interval_ms: int = 3000) -> None:
            self._timer.setInterval(max(3000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

        def _update_ui(self) -> None:
            pass

        def update_backfill_status(self, db_name: str, status_text: str) -> None:
            """특정 DB 백필 상태 레이블 갱신"""
            label_map = {
                "timescale": "label_db_timescale_placeholder",
                "redis": "label_db_redis_placeholder",
                "mongodb": "label_db_mongodb_placeholder",
                "postgres": "label_db_postgres_placeholder",
                "kafka": "label_db_kafka_placeholder",
                "clickhouse": "label_db_clickhouse_placeholder",
            }
            label_name = label_map.get(db_name)
            if label_name and hasattr(self, label_name):
                lbl = getattr(self, label_name)
                lbl.setText(status_text)

else:
    class BackfillTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""
        def __init__(self, parent=None):
            pass
        def start_updates(self, interval_ms: int = 3000) -> None:
            pass
        def stop_updates(self) -> None:
            pass
        def update_backfill_status(self, db_name: str, status_text: str) -> None:
            pass
