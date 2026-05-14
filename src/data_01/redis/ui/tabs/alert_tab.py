# -*- coding: utf-8 -*-
"""Redis 알림 설정 탭"""
from __future__ import annotations
import os
import logging

try:
    from PyQt5.QtWidgets import QWidget, QMessageBox
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "alert_tab.ui")

# 기본 임계값 상수
_DEFAULT_MEMORY_THRESH = 85   # 메모리 사용률 (%)
_DEFAULT_HITRATE_THRESH = 70  # 캐시 히트율 최소 (%)

if _HAS_QT:
    class AlertTab(QWidget):
        def __init__(self, conn_params: dict = None, parent=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            # 저장된 임계값
            self._memory_thresh = _DEFAULT_MEMORY_THRESH
            self._hitrate_thresh = _DEFAULT_HITRATE_THRESH
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[AlertTab] UI 로드 실패: %s", exc)
            self._timer = QTimer(self)
            self._timer.setInterval(5000)
            self._timer.timeout.connect(self._update)
            self._connect_signals()
            self._load_thresholds()
            self._timer.start()

        def _connect_signals(self) -> None:
            btn_save = getattr(self, "btnSaveAlerts", None)
            if btn_save:
                try:
                    btn_save.clicked.connect(self._save_thresholds)
                except Exception:
                    pass

        def start_updates(self, interval_ms: int = 5000) -> None:
            self._timer.setInterval(max(1000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

        def _load_thresholds(self) -> None:
            """저장된 임계값을 UI에 표시."""
            spin_mem = getattr(self, "spinMemory", None)
            if spin_mem:
                try:
                    spin_mem.setValue(self._memory_thresh)
                except Exception:
                    pass

            spin_hit = getattr(self, "spinHitRate", None)
            if spin_hit:
                try:
                    spin_hit.setValue(self._hitrate_thresh)
                except Exception:
                    pass

        def _save_thresholds(self) -> None:
            """UI의 임계값을 저장."""
            spin_mem = getattr(self, "spinMemory", None)
            if spin_mem:
                try:
                    self._memory_thresh = spin_mem.value()
                except Exception:
                    pass

            spin_hit = getattr(self, "spinHitRate", None)
            if spin_hit:
                try:
                    self._hitrate_thresh = spin_hit.value()
                except Exception:
                    pass

            logger.info("[AlertTab] 임계값 저장: 메모리=%d%%, 히트율=%d%%",
                        self._memory_thresh, self._hitrate_thresh)

        def _update(self) -> None:
            """주기적으로 현재 임계값 상태를 확인. (현재: UI 표시 유지)"""
            self._load_thresholds()

else:
    class AlertTab:  # type: ignore[no-redef]
        def __init__(self, conn_params: dict = None, parent=None): pass
        def start_updates(self, interval_ms: int = 5000) -> None: pass
        def stop_updates(self) -> None: pass
