# -*- coding: utf-8 -*-
"""
StatusWidget 메인 클래스 (widget.py)

변경:
- 실시간 로그 팝업을 StatisticsTab 인스턴스로 임베드하여 로그가 보이도록 개선.
- StatisticsTab 임포트 실패 시 기존 QPlainTextEdit fallback 유지.
- StatusWidget._on_ui_log_received가 팝업(StatisticsTab)에 레코드와 함께 로그를 전달하도록 보강.

추가 변경(핵심):
- 파일-경로 폴백으로 statistics_tab.py를 로드할 때, 모듈을 '무작정 exec' 하지 않고
  적절한 __package__ 값 설정과 sys.modules에 패키지 엔트리를 등록하여 내부의 상대 import가
  정상 동작하도록 보강했습니다.
  (문제 원인: 숫자로 시작하는 폴더명 때문에 dotted import가 실패하면 file-path fallback이 동작,
   이때 package context가 없으면 'from ._mixins' 같은 상대 import가 실패하여 빈 UI가 표시됨)
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
import threading
import types
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5.QtWidgets import (
        QWidget,
        QApplication,
        QDialog,
        QVBoxLayout,
        QPlainTextEdit,
        QPushButton,
        QHBoxLayout,
        QSizePolicy,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

# Mixins: tab_manager 등은 로딩/초기화만 사용
from .tab_manager import TabManagerMixin
from .controller_manager import ControllerManagerMixin
from .signal_handlers import SignalHandlersMixin
from .ui_updaters import UIUpdatersMixin
from .log_streaming import LogStreamingMixin
from .settings_handler import SettingsHandlerMixin
from .tf_safe_panel import TFSafePanelMixin


if _HAS_QT:
    class LogPopup(QDialog):
        """실시간 로그 전용 팝업창.

        동작 방식:
        - 우선 src/02_data/ui/tabs/statistics_tab.py의 StatisticsTab 클래스를 동적 임포트하여 임베드합니다.
        - 임포트 실패 시 QPlainTextEdit 기반의 fallback 뷰를 사용합니다.
        - append_log(formatted_message, record=None) 를 통해 로그를 전달받아 StatisticsTab.add_log_entry 또는 텍스트뷰에 쌓습니다.

        주의(핵심):
        - 파일-경로로 모듈을 로드할 때 모듈 내부에서 상대 import를 사용하면 패키지 컨텍스트가 필요합니다.
          여기서는 안전하게 패키지 이름을 유추하고 sys.modules에 패키지 엔트리를 등록한 뒤 모듈을 exec 합니다.
        """
        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("실시간 로그")
            self.setWindowModality(Qt.NonModal)
            self._has_stats_tab = False
            self._stats_tab = None
            self._text = None
            self._init_ui()

        def _init_ui(self) -> None:
            layout = QVBoxLayout(self)

            # === Robust StatisticsTab import: try relative/package import first, then file-path fallback ===
            _stats_tab_cls = None
            try:
                # Try relative/package import first (preferred)
                from ..tabs.statistics_tab import StatisticsTab  # type: ignore
                _stats_tab_cls = StatisticsTab
            except Exception as e_rel:
                logger.debug("[LogPopup] relative import of StatisticsTab failed: %s", e_rel)
                # File-path fallback: load statistics_tab.py by filesystem path
                try:
                    here = os.path.dirname(os.path.abspath(__file__))
                    candidate = os.path.abspath(os.path.join(here, "..", "tabs", "statistics_tab.py"))
                    if os.path.isfile(candidate):
                        try:
                            # -------------------------
                            # 안전한 파일-경로 로드 로직
                            #  - module_name과 package_name을 유추
                            #  - 패키지 모듈을 sys.modules에 등록(간단한 __path__ 설정 포함)
                            #  - 모듈.__package__를 설정한 뒤 exec_module 호출
                            #  - 이렇게 하면 statistics_tab 내부의 상대 import(from ._mixins 등)가 동작함
                            # -------------------------
                            # 유추: candidate 경로에서 'src' 디렉터리 이후의 경로를 패키지 네임으로 사용 시도
                            candidate_norm = os.path.normpath(candidate)
                            parts = candidate_norm.split(os.sep)
                            package_name = None
                            try:
                                # 'src' 루트가 있으면 그 이후를 패키지 이름으로 사용
                                idx = next(i for i, p in enumerate(parts) if p == "src")
                                # exclude the filename at the end
                                pkg_parts = parts[idx:-1]
                                package_name = ".".join(pkg_parts) if pkg_parts else None
                            except StopIteration:
                                package_name = None

                            # fallback package_name: 디렉터리 이름을 사용 (안전하게)
                            if not package_name:
                                package_name = os.path.basename(os.path.dirname(candidate))

                            # 현실적으로 statistics_tab.py 파일은 '.../src/02_data/ui/tabs/statistics_tab.py' 에 있음.
                            # 이때 package_name은 'src.02_data.ui.tabs' 가 될 가능성이 큼.
                            module_name = package_name + ".statistics_tab_local"

                            spec = importlib.util.spec_from_file_location(module_name, candidate)
                            if spec and spec.loader:
                                mod = importlib.util.module_from_spec(spec)

                                # 부모 패키지(간단 타입) 등록: importlib의 상대 import가 동작하려면
                                # package 엔트리가 sys.modules에 존재하고 __path__가 올바르게 설정되어야 함.
                                try:
                                    # 패키지 파일 시스템 디렉토리 (statistics_tab.py의 상위 디렉토리)
                                    package_dir = os.path.dirname(candidate)
                                    # 등록되지 않은 경우에만 생성
                                    if package_name not in sys.modules:
                                        pkg_mod = types.ModuleType(package_name)
                                        # __path__는 패키지 탐색시 사용됨(상위 디렉토리로 설정)
                                        pkg_mod.__path__ = [package_dir]
                                        sys.modules[package_name] = pkg_mod
                                    # 모듈의 패키지 속성 설정 (상대 import resolution에 사용)
                                    mod.__package__ = package_name
                                except Exception as e_pkg:
                                    logger.debug("[LogPopup] 패키지 등록 중 오류(무시): %s", e_pkg)

                                # sys.modules에 모듈 이름 등록 — 모듈 내부에서 자신의 절대 이름으로 접근 가능
                                try:
                                    sys.modules[module_name] = mod
                                except Exception:
                                    pass

                                # finally exec the module
                                try:
                                    spec.loader.exec_module(mod)
                                    _stats_tab_cls = getattr(mod, "StatisticsTab", None)
                                    if _stats_tab_cls is not None:
                                        logger.debug("[LogPopup] StatisticsTab loaded from file with package context: %s", candidate)
                                    else:
                                        logger.debug("[LogPopup] file loaded but StatisticsTab not found in module: %s", candidate)
                                except Exception as e_file:
                                    logger.debug("[LogPopup] file-path import (with package context) of StatisticsTab failed: %s", e_file, exc_info=True)
                            else:
                                logger.debug("[LogPopup] spec 생성 실패 또는 loader 없음 for candidate: %s", candidate)
                        except Exception as e_file_outer:
                            logger.debug("[LogPopup] file-path import of StatisticsTab failed (outer): %s", e_file_outer, exc_info=True)
                    else:
                        logger.debug("[LogPopup] candidate statistics_tab.py not found at: %s", candidate)
                except Exception as e_fp:
                    logger.debug("[LogPopup] statistics_tab import fallback failed: %s", e_fp, exc_info=True)

            # If we found a StatisticsTab class, instantiate and embed it
            if _stats_tab_cls is not None:
                try:
                    self._stats_tab = _stats_tab_cls(parent=self)
                    layout.addWidget(self._stats_tab)
                    self._has_stats_tab = True
                except Exception as exc:
                    logger.debug("[LogPopup] StatisticsTab instance create failed, fallback used: %s", exc, exc_info=True)
                    self._has_stats_tab = False
            else:
                self._has_stats_tab = False

            # fallback 텍스트 뷰 (StatisticsTab이 없을 때 사용)
            if not self._has_stats_tab:
                try:
                    self._text = QPlainTextEdit(self)
                    self._text.setReadOnly(True)
                    self._text.setLineWrapMode(QPlainTextEdit.NoWrap)
                    self._text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    layout.addWidget(self._text)
                except Exception:
                    # final fallback: try a basic widget-less behavior (rare)
                    logger.debug("[LogPopup] fallback text widget creation failed", exc_info=True)

            # 하단 닫기 버튼
            try:
                btn_layout = QHBoxLayout()
                btn_layout.addStretch(1)
                self.btn_close = QPushButton("닫기", self)
                self.btn_close.clicked.connect(self.close)
                btn_layout.addWidget(self.btn_close)
                layout.addLayout(btn_layout)
            except Exception:
                pass

        def append_log(self, formatted_message: str, record: Optional[logging.LogRecord] = None) -> None:
            """팝업에 로그 추가.

            Args:
                formatted_message: 포맷된 로그 문자열
                record: optional LogRecord — 있으면 level/module/time 정보를 채워 StatisticsTab에 전달
            """
            try:
                if self._has_stats_tab and self._stats_tab is not None:
                    # build entry expected by StatisticsTab.add_log_entry
                    try:
                        if record is not None:
                            ts = datetime.fromtimestamp(getattr(record, "created", datetime.now().timestamp())).strftime("%H:%M:%S")
                            level = getattr(record, "levelname", "INFO")
                            module = getattr(record, "name", "")
                            msg = formatted_message
                            entry = {"time": ts, "level": level, "module": module, "message": msg}
                        else:
                            # record 없으면 포맷 문자열을 메시지로 넣음
                            ts = datetime.now().strftime("%H:%M:%S")
                            entry = {"time": ts, "level": "INFO", "module": "", "message": formatted_message}
                        # 호출 (StatisticsTab 내부에서 스레드 안전 처리함)
                        try:
                            self._stats_tab.add_log_entry(entry)
                        except Exception as exc:
                            logger.debug("[LogPopup] statistics_tab.add_log_entry 실패, fallback: %s", exc)
                            # fallback to text view if present
                            if self._text is not None:
                                try:
                                    self._text.appendPlainText(f"[{entry['level']}] {entry['time']} {entry['module']}: {entry['message']}")
                                except Exception:
                                    pass
                    except Exception:
                        # 안전하게 fallback
                        if self._text is not None:
                            try:
                                self._text.appendPlainText(formatted_message)
                            except Exception:
                                pass
                else:
                    # 단순 텍스트 뷰에 append
                    if self._text is not None:
                        try:
                            self._text.appendPlainText(formatted_message)
                        except Exception:
                            pass
                # autoscroll for plain text view
                try:
                    if self._text is not None:
                        sb = self._text.verticalScrollBar()
                        if sb is not None:
                            sb.setValue(sb.maximum())
                except Exception:
                    pass
            except Exception:
                logger.exception("[LogPopup] append_log 실패")

        def show_fullscreen_safely(self) -> None:
            """최대화로 표시 시도(윈도우 매니저에 위임)."""
            try:
                self.showMaximized()
            except Exception:
                try:
                    self.show()
                except Exception:
                    pass


    class StatusWidget(
        TabManagerMixin,
        ControllerManagerMixin,
        SignalHandlersMixin,
        UIUpdatersMixin,
        LogStreamingMixin,
        SettingsHandlerMixin,
        TFSafePanelMixin,
        QWidget,
    ):
        """통합 시스템 모니터 메인(로더·상단 제어)."""

        def __init__(
            self,
            parent: Optional[QWidget] = None,
            ui_path: Optional[str] = None,
            refresh_ms: int = 3000,
            mongo_client: Optional[object] = None,
        ) -> None:
            super().__init__(parent)
            self._mongo_client = mongo_client

            # .ui 파일 경로 (status_widget.ui를 로드)
            self._ui_file = ui_path or os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "status_widget.ui",
            )

            # 기본 동작 파라미터
            self._refresh_ms = max(1000, int(refresh_ms))
            self._start_time = datetime.now()
            self._thread_lock = threading.Lock()

            # 내부 상태
            self._last_update_time: dict = {}
            self._update_interval_ms: int = 100

            # placeholder for controllers/workers/handlers
            self._monitoring_worker: Optional[object] = None
            self._realtime_log_handlers: list = []
            self._qt_log_handler: Optional[object] = None
            self._last_health: dict = {}

            # throttling timestamps (perf_counter*1000 expected elsewhere)
            self._last_ws_row_ms: float = 0.0
            self._last_pl_row_ms: float = 0.0

            # UI 로그 등록 상태
            self._ui_log_registered = False
            self._ui_log_register_attempts = 0
            self._ui_log_register_max_attempts = 2

            # 타이머 (업타임/주기 갱신)
            self._uptime_timer = QTimer(self)
            self._uptime_timer.setInterval(1000)
            self._uptime_timer.timeout.connect(self._update_uptime)

            self._timer = QTimer(self)
            self._timer.setInterval(self._refresh_ms)
            self._timer.timeout.connect(self._on_timer_tick)

            # 로그 팝업 객체 (초기에는 없음)
            self._log_popup: Optional[LogPopup] = None

            # UI 로드 (중요: UI 구조는 변경하지 않음)
            try:
                uic.loadUi(self._ui_file, self)
            except Exception as exc:
                logger.exception("[StatusWidget] UI 로드 실패: %s", exc)
                # UI가 없으면 더 이상 초기화할 수 없음
                return

            # 시작 시 전체창(최대화)으로 표시 — 사용자가 다시 복원하면 원래 크기로 돌아갑니다.
            try:
                # 표준 최대화 호출 (안정성 위해 예외 처리)
                self.showMaximized()
            except Exception:
                pass

            # --- 최소한의 런타임 보정: UI 구조 안정화 (레이아웃/텍스트 변경 금지) ---
            try:
                self._optimize_layout()
            except Exception as exc:
                logger.debug("[StatusWidget] 초기 레이아웃 최적화 실패: %s", exc)

            # 설정 핸들링 초기화
            try:
                if hasattr(self, "start_settings_handling") and callable(getattr(self, "start_settings_handling")):
                    try:
                        self.start_settings_handling(mongo_client=self._mongo_client, collection_name="ui_status")
                        logger.debug("[StatusWidget] start_settings_handling 호출됨")
                    except Exception:
                        logger.debug("[StatusWidget] start_settings_handling 실패", exc_info=True)
                else:
                    for name in ("restore_settings", "_restore_settings", "load_settings", "_load_settings", "restore_ui_settings"):
                        fn = getattr(self, name, None)
                        if callable(fn):
                            try:
                                fn()
                                logger.debug("[StatusWidget] 설정 복원 호출 (fallback): %s", name)
                                break
                            except Exception:
                                logger.debug("[StatusWidget] 설정 복원(%s) 실패", name, exc_info=True)
            except Exception:
                pass

            # 탭/컨트롤러/시그널/워커 초기화 (각 모듈에 위임된 작업 호출)
            try:
                self._init_tabs()
            except Exception as exc:
                logger.exception("[StatusWidget] _init_tabs 실패: %s", exc)

            # 로그 스트리밍 핸들러 초기화
            try:
                if hasattr(self, "_setup_realtime_log_streaming") and callable(getattr(self, "_setup_realtime_log_streaming")):
                    try:
                        self._setup_realtime_log_streaming()
                        logger.debug("[StatusWidget] _setup_realtime_log_streaming 호출됨")
                    except Exception:
                        logger.debug("[StatusWidget] _setup_realtime_log_streaming 실패", exc_info=True)
            except Exception:
                pass

            try:
                self._init_controllers()
            except Exception as exc:
                logger.exception("[StatusWidget] _init_controllers 실패: %s", exc)

            # ---------- 안전하게 시그널 연결 시도 ----------
            try:
                conn_fn = getattr(self, "_connect_signals", None)
                if callable(conn_fn):
                    try:
                        conn_fn()
                    except Exception as exc:
                        logger.exception("[StatusWidget] _connect_signals 실패: %s", exc)
                else:
                    logger.debug("[StatusWidget] _connect_signals 구현 없음 — 연결 건너뜀")
            except Exception as exc:
                logger.exception("[StatusWidget] _connect_signals 호출 래퍼 실패: %s", exc)

            # --- 중요한 연결: 실시간 로그 버튼 → 팝업 오픈 ---
            try:
                if hasattr(self, "btn_realtime_log") and callable(getattr(self.btn_realtime_log, "clicked", None)):
                    try:
                        # 안전하게 연결
                        self.btn_realtime_log.clicked.connect(self._open_realtime_log_popup)
                    except Exception:
                        logger.debug("[StatusWidget] btn_realtime_log 연결 실패", exc_info=True)
                else:
                    logger.debug("[StatusWidget] btn_realtime_log 위젯이 없습니다 — 팝업 연결 생략")
            except Exception:
                logger.debug("[StatusWidget] btn_realtime_log 연결 시도 중 오류", exc_info=True)

            try:
                self._start_monitoring_worker()
            except Exception as exc:
                logger.exception("[StatusWidget] _start_monitoring_worker 실패: %s", exc)

            try:
                self._init_tf_safe_panel()
            except Exception as exc:
                logger.debug("[StatusWidget] _init_tf_safe_panel 실패: %s", exc)

            try:
                self._attempt_register_ui_log_consumer()
            except Exception:
                logger.debug("[StatusWidget] _attempt_register_ui_log_consumer 초기 시도 실패", exc_info=True)

            try:
                self._uptime_timer.start()
                self._timer.start()
            except Exception as exc:
                logger.debug("[StatusWidget] 타이머 시작 실패: %s", exc)

        # ---------- 로그 팝업 생성/오픈/클로즈 ----------
        def _create_log_popup(self) -> LogPopup:
            """LogPopup을 생성하여 반환. 이미 있으면 기존 인스턴스 반환."""
            if self._log_popup is not None:
                return self._log_popup
            try:
                self._log_popup = LogPopup(parent=self)
            except Exception as exc:
                logger.exception("[StatusWidget] LogPopup 생성 실패: %s", exc)
                raise
            return self._log_popup

        def _open_realtime_log_popup(self) -> None:
            """실시간 로그 팝업을 열고 최대화(안전하게)."""
            try:
                popup = self._create_log_popup()
                popup.show_fullscreen_safely()
                try:
                    popup.raise_()
                    popup.activateWindow()
                except Exception:
                    pass
            except Exception:
                logger.exception("[StatusWidget] _open_realtime_log_popup 실패")

        def _close_realtime_log_popup(self) -> None:
            """팝업을 닫고 참조 해제."""
            try:
                if self._log_popup is not None:
                    try:
                        self._log_popup.close()
                    except Exception:
                        pass
                    self._log_popup = None
            except Exception:
                logger.debug("[StatusWidget] _close_realtime_log_popup 실패", exc_info=True)

        # ---------- UI 로그 콜백 위임 (재귀 방지) ----------
        def _on_ui_log_received(self, formatted_message: str, record: logging.LogRecord) -> None:
            """UI로 전달된 로그를 수신 — UIUpdatersMixin에 위임하고 팝업이 열려 있으면 실시간으로 append."""
            try:
                # 1) 기존 믹스인 위임 (우선)
                mixin_handler = getattr(UIUpdatersMixin, "_on_ui_log_received", None)
                if callable(mixin_handler):
                    try:
                        mixin_handler(self, formatted_message, record)
                    except Exception:
                        logger.debug("[StatusWidget] UIUpdatersMixin._on_ui_log_received 오류", exc_info=True)
                else:
                    logger.debug("[StatusWidget] UIUpdatersMixin._on_ui_log_received 미구현 — 로그: %s", formatted_message)

                # 2) 팝업 창이 열려 있으면 여기에도 출력(사용자 요청)
                try:
                    popup = getattr(self, "_log_popup", None)
                    if popup is not None and popup.isVisible():
                        try:
                            # append_log accepts (formatted_message, record)
                            popup.append_log(formatted_message, record)
                        except RuntimeError:
                            # 스레드 문제시 Qt 이벤트 루프에 큐잉
                            try:
                                QTimer.singleShot(0, lambda m=formatted_message, r=record: popup.append_log(m, r))
                            except Exception:
                                pass
                        except Exception:
                            # fallback 큐잉
                            try:
                                QTimer.singleShot(0, lambda m=formatted_message, r=record: popup.append_log(m, r))
                            except Exception:
                                pass
                except Exception:
                    logger.debug("[StatusWidget] 팝업에 로그 추가 실패", exc_info=True)

            except Exception:
                logger.debug("[StatusWidget] _on_ui_log_received wrapper 실패", exc_info=True)

        # ---------- 종료 시 정리 ----------
        def closeEvent(self, event: object) -> None:
            """위젯 닫힘 시 안전 정리: 로그 소비자 해제, 워커/타이머 종료, 핸들러 제거 등."""
            # 설정 저장 시도
            try:
                for name in ("save_settings", "_save_settings", "persist_settings", "_persist_settings", "store_settings"):
                    fn = getattr(self, name, None)
                    if callable(fn):
                        try:
                            fn()
                            logger.debug("[StatusWidget] 설정 저장 호출: %s", name)
                            break
                        except Exception:
                            logger.debug("[StatusWidget] 설정 저장(%s) 실패", name, exc_info=True)
            except Exception:
                pass

            # UI 로그 소비자 해제
            try:
                self._attempt_unregister_ui_log_consumer()
            except Exception:
                logger.debug("[StatusWidget] UI 로그 소비자 해제 실패", exc_info=True)

            # 모니터링 워커 정지
            try:
                if self._monitoring_worker is not None:
                    try:
                        self._monitoring_worker.stop()
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[StatusWidget] 모니터링 워커 종료 실패: %s", exc)

            # Qt 로그 핸들러 제거
            try:
                if self._qt_log_handler is not None:
                    logging.getLogger().removeHandler(self._qt_log_handler)
            except Exception as exc:
                logger.debug("[StatusWidget] Qt 로그 핸들러 제거 실패: %s", exc)

            # 실시간 로그 핸들러 제거
            try:
                if self._realtime_log_handlers:
                    for logger_name, handler in self._realtime_log_handlers:
                        try:
                            logging.getLogger(logger_name).removeHandler(handler)
                        except Exception:
                            pass
            except Exception as exc:
                logger.debug("[StatusWidget] 실시간 로그 핸들러 제거 실패: %s", exc)

            # 기타 타이머/워커 정리
            try:
                if getattr(self, "_ws_poll_timer", None) is not None:
                    try:
                        self._ws_poll_timer.stop()
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                if getattr(self, "_tf_safe_timer", None) is not None:
                    try:
                        self._tf_safe_timer.stop()
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                w = getattr(self, "_tf_safe_worker", None)
                if w is not None and getattr(w, "isRunning", lambda: False)():
                    try:
                        w.quit()
                        w.wait(1500)
                    except Exception:
                        pass
            except Exception:
                pass

            # 팝업이 열려 있으면 닫음
            try:
                if getattr(self, "_log_popup", None) is not None:
                    try:
                        self._log_popup.close()
                    except Exception:
                        pass
                    self._log_popup = None
            except Exception:
                pass

            # 부모의 closeEvent 호출
            try:
                super().closeEvent(event)
            except Exception:
                try:
                    QWidget.closeEvent(self, event)  # type: ignore[misc]
                except Exception:
                    pass

        # ---------- 간단한 공개 메서드(로더 수준) ----------
        def start_auto_refresh(self) -> None:
            if not self._timer.isActive():
                self._timer.start()

        def stop_auto_refresh(self) -> None:
            if self._timer.isActive():
                self._timer.stop()

        def refresh_now(self, force: bool = False) -> None:
            """외부에서 즉시 갱신 요청 — 탭/컨트롤러의 refresh 메서드를 호출하도록 위임합니다."""
            try:
                if hasattr(self, "_on_refresh_clicked") and callable(getattr(self, "_on_refresh_clicked")):
                    try:
                        self._on_refresh_clicked()
                    except Exception:
                        pass
                if hasattr(self, "_update_status_bar") and callable(getattr(self, "_update_status_bar")):
                    try:
                        self._update_status_bar()
                    except Exception:
                        pass
            except Exception:
                pass

else:
    class StatusWidget:  # type: ignore[no-redef]
        def __init__(self, parent: Optional[object] = None, **kwargs: object) -> None:
            pass

        def start_auto_refresh(self) -> None:
            pass

        def stop_auto_refresh(self) -> None:
            pass

        def refresh_now(self, force: bool = False) -> None:
            pass

        def update_flow_status(self, stage: str, status: str) -> None:
            pass

        def add_comm_row(
            self,
            time_str: str,
            kind: str,
            symbol: str,
            data: str,
            latency_ms: str,
        ) -> None:
            pass