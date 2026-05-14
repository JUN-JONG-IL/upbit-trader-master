# -*- coding: utf-8 -*-
"""
실시간 로그 스트리밍 Mixin (log_streaming.py)

QtLogHandler, MonitoringWorker 클래스와
실시간 로그 스트리밍 설정/시작/수신 메서드를 포함합니다.

CHANGELOG:
    v6.0 (2026-04-28) | Copilot | status_widget.py → 패키지 완전 모듈화

수정 (2026-05-10):
- UI 정책에 따라 통신 관련 INFO/DEBUG 로그는 UI에 표시되도록 핸들러 레벨을 INFO로 설정.
- WARNING/ERROR/CRITICAL 로그는 콘솔 전용으로 취급하여 UI에는 표시하지 않음.
- _should_show_log을 조정하여 combo가 없을 때 INFO/DEBUG 표시 허용.
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QObject, QThread, Qt, QMetaObject, Q_ARG, pyqtSignal, pyqtSlot
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if TYPE_CHECKING:
    pass

if _HAS_QT:
    class QtLogHandler(logging.Handler, QObject):
        """로그를 Qt 시그널로 emit하는 핸들러.

        logging.Handler와 QObject를 다중 상속하여
        Python 로그 레코드를 Qt 시그널로 변환합니다.
        """

        log_signal = pyqtSignal(str, str)

        def __init__(self) -> None:
            logging.Handler.__init__(self)
            QObject.__init__(self)

        def emit(self, record: logging.LogRecord) -> None:
            """로그 레코드를 Qt 시그널로 발행.

            Args:
                record: Python 로그 레코드
            """
            try:
                msg = self.format(record)
                self.log_signal.emit(record.levelname, msg)
            except Exception as exc:
                logger.debug("[QtLogHandler] 로그 emit 실패: %s", exc)

    class MonitoringWorker(QThread):
        """백그라운드 시스템 모니터링 스레드.

        psutil을 사용하여 CPU, 메모리, 디스크 사용률을 수집하고
        stats_updated 시그널로 메인 스레드에 전달합니다.
        """

        stats_updated = pyqtSignal(dict)

        def __init__(self, parent: object = None) -> None:
            super().__init__(parent)
            self._running = True
            self._stop_event = threading.Event()

        def run(self) -> None:
            """모니터링 루프 실행."""
            while self._running:
                try:
                    stats = self._collect_stats()
                    self.stats_updated.emit(stats)
                except Exception as exc:
                    logger.error("[MonitoringWorker] 오류: %s", exc)
                    self._stop_event.wait(timeout=5)
                    if not self._running:
                        break
                    continue
                self._stop_event.wait(timeout=1)

        def _collect_stats(self) -> dict:
            """시스템 통계 수집.

            Returns:
                cpu_percent, mem_percent, mem_used_gb, disk_percent를 담은 dict
            """
            stats: dict = {}
            try:
                import psutil  # type: ignore
                stats["cpu_percent"] = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory()
                stats["mem_percent"] = mem.percent
                stats["mem_used_gb"] = mem.used / (1024 ** 3)
                disk = psutil.disk_usage("/")
                stats["disk_percent"] = disk.percent
            except ImportError:
                pass
            except Exception as exc:
                logger.debug("[MonitoringWorker] 상태 수집 실패: %s", exc)
            return stats

        def stop(self) -> None:
            """모니터링 루프를 정지하고 스레드를 종료합니다."""
            self._running = False
            self._stop_event.set()
            self.wait()

    class LogStreamingMixin:
        """실시간 로그 스트리밍 Mixin.

        QtLogHandler, MonitoringWorker 기반의 실시간 로그 스트리밍
        설정과 메시지 수신 슬롯을 포함합니다.
        """

        def _setup_realtime_log_streaming(self) -> None:
            """실시간 로그 스트리밍 설정.

            Statistics 탭의 text_log 위젯에 WebSocket/Pipeline 로거를 연결하여
            실시간으로 로그를 표시합니다.
            """
            try:
                if self._tab_statistics is None:
                    logger.debug("[StatusWidget] Statistics 탭 없음 — 로그 스트리밍 스킵")
                    return

                log_widget = getattr(self._tab_statistics, "text_log", None)
                if log_widget is None:
                    logger.debug("[StatusWidget] text_log 위젯 없음 — 로그 스트리밍 스킵")
                    return

                class RealtimeLogStreamHandler(logging.Handler):
                    """text_log 위젯에 로그를 스트리밍하는 핸들러."""

                    def __init__(self, text_widget: object) -> None:
                        super().__init__()
                        self.text_widget = text_widget
                        # We want communication logs (INFO/DEBUG) streamed
                        self.setLevel(logging.DEBUG)
                        self.setFormatter(logging.Formatter(
                            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%H:%M:%S"
                        ))

                    def emit(self, record: logging.LogRecord) -> None:
                        """로그를 메인 스레드 append로 위젯에 표시."""
                        try:
                            msg = self.format(record)
                            QMetaObject.invokeMethod(
                                self.text_widget,
                                "append",
                                Qt.QueuedConnection,
                                Q_ARG(str, msg)
                            )
                        except Exception:
                            pass

                # Register handlers for key loggers (WebSocket + Pipeline)
                try:
                    ws_logger = logging.getLogger("data_01.collectors.websocket_manager")
                    ws_handler = RealtimeLogStreamHandler(log_widget)
                    ws_logger.addHandler(ws_handler)
                    self._realtime_log_handlers.append(
                        ("data_01.collectors.websocket_manager", ws_handler)
                    )
                except Exception:
                    logger.debug("[LogStreaming] ws realtime handler registration failed", exc_info=True)

                try:
                    pipeline_logger = logging.getLogger("data_01.pipeline")
                    pipeline_handler = RealtimeLogStreamHandler(log_widget)
                    pipeline_logger.addHandler(pipeline_handler)
                    self._realtime_log_handlers.append(("data_01.pipeline", pipeline_handler))
                except Exception:
                    logger.debug("[LogStreaming] pipeline realtime handler registration failed", exc_info=True)

                logger.info("[StatusWidget] ✅ 실시간 로그 스트리밍 등록 완료 (WebSocket + Pipeline)")

            except Exception as exc:
                logger.error("[StatusWidget] ❌ 실시간 로그 스트리밍 설정 실패: %s", exc)

        def _start_monitoring_worker(self) -> None:
            """모니터링 워커 시작.

            MonitoringWorker 스레드와 QtLogHandler를 초기화하고 시작합니다.

            변경: INFO 레벨부터 UI용 핸들러가 이벤트를 받도록 설정합니다.
            WARNING/ERROR/CRITICAL 은 UI에 표시되지 않도록 _on_log_message에서 차단합니다.
            """
            try:
                self._monitoring_worker = MonitoringWorker(self)
                self._monitoring_worker.stats_updated.connect(self._on_monitoring_stats)
                self._monitoring_worker.start()

                self._qt_log_handler = QtLogHandler()
                # 변경: INFO 이상을 UI 전송 대상으로 하여 통신 로그(INFO)도 UI에 도달하도록 함
                self._qt_log_handler.setLevel(logging.INFO)
                self._qt_log_handler.log_signal.connect(self._on_log_message)
                logging.getLogger().addHandler(self._qt_log_handler)
                logger.debug("[StatusWidget] QtLogHandler added (level=INFO)")
            except Exception as exc:
                logger.warning("[StatusWidget] 모니터링 워커 시작 실패: %s", exc)

        @pyqtSlot(dict)
        def _on_monitoring_stats(self, stats: dict) -> None:
            """모니터링 통계 수신 슬롯.

            Args:
                stats: cpu_percent, mem_percent 등 시스템 통계 dict
            """
            # 통계는 다른 믹스인(예: UIUpdaters)에서 활용하도록 시그널로 전달됨
            pass

        @pyqtSlot(str, str)
        def _on_log_message(self, level: str, msg: str) -> None:
            """로그 메시지 수신 슬롯.

            Args:
                level: 로그 레벨 문자열 ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
                msg: 포맷된 로그 메시지 문자열

            정책:
            - WARNING/ERROR/CRITICAL 메시지는 콘솔 전용 (UI에 표시하지 않음)
            - INFO/DEBUG 메시지는 UI의 text_log에 append (단, _should_show_log를 통과해야 함)
            """
            try:
                # 1) 레벨 기반 차단: WARNING 이상은 UI에 표시하지 않음 (콘솔 전용)
                try:
                    lvl = (level or "").upper()
                except Exception:
                    lvl = ""

                if lvl in ("WARNING", "ERROR", "CRITICAL"):
                    # Do not display warnings/errors in the UI - they remain in console logs.
                    return

                # 2) 사용자 설정(콤보 박스)이 허용하는지 확인
                if not self._should_show_log(level):
                    return

                # 3) 안전하게 UI에 append
                if self._tab_statistics is not None and hasattr(self._tab_statistics, "text_log"):
                    try:
                        self._tab_statistics.text_log.append(f"[{level}] {msg}")
                    except Exception:
                        logger.debug("[StatusWidget] text_log append failed", exc_info=True)
            except Exception as exc:
                logger.debug("[StatusWidget] 로그 메시지 처리 실패: %s", exc)

        def _should_show_log(self, level: str) -> bool:
            """로그 레벨 필터.

            Args:
                level: 로그 레벨 문자열

            Returns:
                True이면 표시, False이면 숨김

            동작:
            - combo_log_level 위젯이 없으면 기본적으로 INFO/DEBUG를 표시.
            - combo_log_level이 있으면 사용자가 선택한 값에 따라 결정하되,
              WARNING/ERROR/CRITICAL은 UI 정책상 표시하지 않음(위에서 이미 차단).
            """
            try:
                combo = getattr(self, "combo_log_level", None)
            except Exception:
                combo = None

            lvl = (level or "").upper()
            # If combo not present, allow INFO/DEBUG
            if combo is None:
                return lvl in ("DEBUG", "INFO")

            # If combo present, respect selection.
            try:
                filter_text = combo.currentText()
            except Exception:
                filter_text = "전체"

            if filter_text == "전체":
                # Even when "전체" selected, WARNING+ are blocked earlier.
                return True
            elif filter_text == "에러만":
                return lvl in ("ERROR", "CRITICAL")
            elif filter_text == "경고 이상":
                return lvl in ("WARNING", "ERROR", "CRITICAL")
            return False

else:
    class QtLogHandler(logging.Handler):  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 QtLogHandler."""

        def emit(self, record: logging.LogRecord) -> None:
            """더미 emit."""
            pass

    class MonitoringWorker:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 MonitoringWorker."""

        def __init__(self, parent: object = None) -> None:
            pass

        def start(self) -> None:
            """더미 start."""
            pass

        def stop(self) -> None:
            """더미 stop."""
            pass

    class LogStreamingMixin:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 LogStreamingMixin."""

        def _setup_realtime_log_streaming(self) -> None:
            """더미 로그 스트리밍 설정."""
            pass

        def _start_monitoring_worker(self) -> None:
            """더미 모니터링 워커 시작."""
            pass

        def _on_monitoring_stats(self, stats: dict) -> None:
            """더미 모니터링 통계 수신."""
            pass

        def _on_log_message(self, level: str, msg: str) -> None:
            """더미 로그 메시지 수신."""
            pass

        def _should_show_log(self, level: str) -> bool:
            """더미 로그 필터."""
            return False