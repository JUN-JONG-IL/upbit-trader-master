# -*- coding: utf-8 -*-
"""
AutoController: PyQt5용 AutoBackfillManager 래퍼
- UI(토글/버튼)와 AutoBackfillManager를 연결하기 위한 QObject 기반 컨트롤러
- QSettings에 자동모드 및 interval을 저장/복원(옵션)
"""
from PyQt5.QtCore import QObject, pyqtSignal, QSettings, QTimer
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import threading

import importlib as _il

# AutoBackfillManager 임포트 — 다양한 실행 환경에 대응하는 폴백 체인
_AutoBackfillManager = None
for _abpath in (
    "app.core.auto_backfill",
    "orchestrator.auto_backfill",
    "src.orchestrator.auto_backfill",
):
    try:
        _abmod = _il.import_module(_abpath)
        _AutoBackfillManager = getattr(_abmod, "AutoBackfillManager", None)
        if _AutoBackfillManager is not None:
            break
    except ImportError:
        continue

if _AutoBackfillManager is None:
    raise ImportError(
        "AutoBackfillManager could not be imported from any known location. "
        "Ensure src/orchestrator/auto_backfill.py exists and is importable."
    )

AutoBackfillManager = _AutoBackfillManager


class AutoController(QObject):
    # 시그널: UI가 연결해서 상태/로그를 갱신하도록 사용
    started = pyqtSignal()
    stopped = pyqtSignal()
    status_updated = pyqtSignal(dict)  # {'automatic': bool, 'queue_length': int, 'last_run_ok': bool, 'last_run_time': str}
    last_run = pyqtSignal(bool, str)  # (success, iso_timestamp_kst)

    def __init__(
        self,
        parent=None,
        use_qsettings: bool = True,
        settings_org: str = "upbit_trader",
        settings_app: str = "upbit_trader",
        status_poll_interval: int = 5000,  # ms
    ):
        """
        use_qsettings: QSettings 사용 여부 (테스트/비GUI 환경에서는 False 권장)
        status_poll_interval: UI에 상태 갱신 알림 주기(ms)
        """
        super().__init__(parent)
        self._mgr = AutoBackfillManager(on_run_complete=self._on_run_complete)
        self._automatic = False
        self._interval_seconds = 300
        self._last_run_ok = False
        self._last_run_time = ""
        self._settings_enabled = bool(use_qsettings)
        self._settings = None
        if self._settings_enabled:
            try:
                self._settings = QSettings(settings_org, settings_app)
                self._automatic = bool(self._settings.value("automatic_backfill", False, type=bool))
                self._interval_seconds = int(self._settings.value("auto_backfill_interval", self._interval_seconds))
            except Exception:
                # QSettings가 동작하지 않으면 무시(테스트 환경)
                self._settings = None
                self._settings_enabled = False

        # UI 폴링 타이머(상태 갱신)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(int(status_poll_interval))
        self._status_timer.timeout.connect(self._emit_status)
        # 타이머는 GUI 루프가 있으면 자동 시작(자동 모드 여부와 상관없이)
        try:
            self._status_timer.start()
        except Exception:
            # non-GUI 환경에서는 타이머 시작 실패 가능 -> 무시
            pass

    # --------------------
    # 내부 콜백
    # --------------------
    def _on_run_complete(self, success: bool):
        """
        AutoBackfillManager에서 호출되는 콜백.
        UI 갱신을 위한 시그널 발생.
        """
        try:
            self._last_run_ok = bool(success)
            # 현재 시간 KST isoformat
            now_kst = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9))).isoformat()
            self._last_run_time = now_kst
            # 시그널
            self.last_run.emit(self._last_run_ok, self._last_run_time)
            # 상태 업데이트 시그널(간단한 dict)
            self.status_updated.emit(self.get_status())
        except Exception:
            # 안전하게 무시
            pass

    # --------------------
    # 제어 메서드 (UI가 호출)
    # --------------------
    def start_background_detection(self, interval_seconds: Optional[int] = None, kickoff: bool = True) -> None:
        """
        주기적 탐지를 시작합니다. interval_seconds를 지정하면 설정으로 저장됩니다.
        자동 ON 시 즉시 1회 kick-off 실행 후 주기 스케줄을 시작합니다.
        """
        if interval_seconds is not None:
            try:
                self._interval_seconds = int(interval_seconds)
            except Exception:
                pass
        if kickoff:
            try:
                self._mgr.run_once_nonblocking(force=True)
            except (RuntimeError, AttributeError) as exc:
                import logging as _log
                _log.getLogger(__name__).warning("[AutoController] kick-off run_once_nonblocking failed: %s", exc)
        # AutoBackfillManager.start_periodic는 non-blocking으로 스레드를 생성하므로 즉시 반환됩니다.
        self._mgr.start_periodic(self._interval_seconds)
        self._automatic = True
        if self._settings_enabled and self._settings is not None:
            try:
                self._settings.setValue("automatic_backfill", True)
                self._settings.setValue("auto_backfill_interval", int(self._interval_seconds))
                self._settings.sync()
            except Exception:
                pass
        self.started.emit()
        # 상태 갱신
        self.status_updated.emit(self.get_status())

    def stop_background_detection(self) -> None:
        """
        주기적 탐지를 중지합니다.
        """
        self._mgr.stop_periodic()
        self._automatic = False
        if self._settings_enabled and self._settings is not None:
            try:
                self._settings.setValue("automatic_backfill", False)
                self._settings.sync()
            except Exception:
                pass
        self.stopped.emit()
        # 상태 갱신
        self.status_updated.emit(self.get_status())

    def run_once(self) -> None:
        """
        한 번만 비동기로 탐지를 실행합니다(스레드).
        force=True 로 심볼 미준비/쿨다운 체크를 우회하여 즉시 실행을 보장합니다.
        """
        self._mgr.run_once_nonblocking(force=True)
        # 상태는 on_run_complete에서 갱신될 것입니다.

    # --------------------
    # 조회 메서드
    # --------------------
    def get_status(self) -> Dict[str, Any]:
        """
        현재 상태 정보를 반환합니다.
        Keys: automatic(bool), interval_seconds(int), queue_length(int),
              processed_count(int), pending_count(int), failed_count(int),
              execution_state(str), last_run_ok(bool), last_run_time(str),
              last_error_reason(str)
        """
        try:
            queue_len = self._mgr.get_queue_length()
        except Exception:
            queue_len = 0
        return {
            "automatic": bool(self._automatic),
            "interval_seconds": int(self._interval_seconds),
            "queue_length": int(queue_len),
            "processed_count": int(getattr(self._mgr, "_processed_count", 0)),
            "pending_count": int(getattr(self._mgr, "_pending_count", queue_len)),
            "failed_count": int(getattr(self._mgr, "_failed_count", 0)),
            "execution_state": str(getattr(self._mgr, "_execution_state", "idle")),
            "last_run_ok": bool(self._last_run_ok),
            "last_run_time": str(self._last_run_time),
            "last_error_reason": str(getattr(self._mgr, "last_error_reason", "")),
        }

    # --------------------
    # 내부 유틸(상태 폴링용)
    # --------------------
    def _emit_status(self):
        """
        주기적으로 UI에 상태를 푸시합니다(QTimer에 바인딩됨).
        """
        try:
            self.status_updated.emit(self.get_status())
        except Exception:
            pass

    # --------------------
    # 유틸리티: UI 연결 예시
    # --------------------
    def connect_to_buttons(self, start_btn, stop_btn, run_once_btn, status_widget_update_fn):
        """
        간단한 UI 연결 헬퍼(예시용). 실제 UI에서는 슬롯/시그널 직접 연결 권장.
        - start_btn/stop_btn/run_once_btn: Qt 버튼 객체 (clicked 시 연결됨)
        - status_widget_update_fn: get_status() 결과를 받아서 UI에 반영하는 콜백(fn(dict)->None)
        """
        try:
            start_btn.clicked.connect(lambda: self.start_background_detection())
            stop_btn.clicked.connect(lambda: self.stop_background_detection())
            run_once_btn.clicked.connect(lambda: self.run_once())
            # 상태 갱신 연결
            self.status_updated.connect(status_widget_update_fn)
        except Exception:
            pass
