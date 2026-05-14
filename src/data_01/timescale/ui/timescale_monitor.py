# -*- coding: utf-8 -*-
"""
TimescaleDB 모니터링 다이얼로그
- timescale_monitor.ui 로드
- tabs/*.py 탭 클래스를 동적으로 로드하여 QTabWidget에 추가
- 독립 실행 또는 메인 앱에서 열기 가능

버그 수정:
- conn_params=None일 때 QSettings에서 저장된 연결 정보 자동 로드
- host가 localhost/빈 값이면 127.0.0.1로 자동 정규화
"""
from __future__ import annotations

import os
import sys
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_UI_FILE = os.path.join(os.path.dirname(__file__), "timescale_monitor.ui")
_TABS_DIR = os.path.join(os.path.dirname(__file__), "tabs")

try:
    from PyQt5 import uic
    from PyQt5.QtWidgets import QDialog, QVBoxLayout, QApplication
    _HAS_QT = True
except Exception:
    _HAS_QT = False

def _load_conn_params_from_settings() -> Dict:
    """QSettings에서 저장된 TimescaleDB 연결 정보를 로드합니다.
    
    timescale_settings.py의 TimescaleSettings().load_connection()을 사용합니다.
    로드 실패 시 빈 dict 반환 (db_worker.py 기본값 사용).
    """
    try:
        # timescale_settings.py 는 ui/ 상위 폴더에 있으므로 경로 추가
        _pkg_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        if _pkg_dir not in sys.path:
            sys.path.insert(0, _pkg_dir)
        from timescale_settings import TimescaleSettings  # type: ignore
        params = TimescaleSettings().load_connection()
        logger.debug("[TimescaleMonitorDialog] QSettings 연결 정보 로드: %s", {
            k: v for k, v in params.items() if k != "pass"
        })
        return params
    except Exception as exc:
        logger.debug("[TimescaleMonitorDialog] QSettings 로드 실패 (기본값 사용): %s", exc)
        return {}

if _HAS_QT:
    from PyQt5.QtWidgets import QTabWidget, QWidget

    class TimescaleMonitorDialog(QDialog):
        """
        TimescaleDB 모니터링 다이얼로그.
        timescale_monitor.ui 파일을 로드하고 tabs/*.py 탭 클래스를 QTabWidget에 동적 추가.
        
        conn_params=None이면 QSettings에서 저장된 연결 정보를 자동으로 로드합니다.
        """

        def __init__(self, parent=None, conn_params: Optional[Dict] = None, refresh_ms: int = 10_000):
            super().__init__(parent)
            # conn_params가 제공되면 사용, 없으면 QSettings에서 로드
            if conn_params:
                self._conn_params = conn_params
            else:
                self._conn_params = _load_conn_params_from_settings()
            self._refresh_ms = refresh_ms
            self._load_ui()
            self._load_tabs()
            self._connect_signals()

        def _load_ui(self):
            """UI 파일 로드. 실패 시 최소 레이아웃으로 폴백."""
            try:
                if os.path.isfile(_UI_FILE):
                    uic.loadUi(_UI_FILE, self)
                    return
            except Exception as e:
                logger.debug("[TimescaleMonitorDialog] UI 파일 로드 실패: %s", e)
            # 폴백 레이아웃
            from PyQt5.QtWidgets import (
                QPushButton, QHBoxLayout, QSpacerItem, QSizePolicy
            )
            self.setWindowTitle("TimescaleDB 모니터링")
            self.resize(1100, 720)
            layout = QVBoxLayout(self)
            self.tabWidget = QTabWidget()
            layout.addWidget(self.tabWidget, stretch=1)
            hl = QHBoxLayout()
            hl.addItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
            self.btnClose = QPushButton("닫기")
            hl.addWidget(self.btnClose)
            layout.addLayout(hl)

        def _load_tabs(self):
            """Python 탭 클래스를 우선 로드하고, 실패 시 .ui 파일로 폴백."""
            import importlib.util

            # tabs/ 폴더를 sys.path에 영구 추가합니다.
            # 이유: spec_from_file_location으로 로드된 모듈은 패키지 컨텍스트가 없어
            #       상대 임포트(from .db_worker import)가 실패하므로, 절대 임포트
            #       (from db_worker import)가 성공하도록 해당 디렉토리를 경로에 추가합니다.
            # 부작용: 동일 이름 모듈이 다른 경로에 있으면 충돌 가능.
            #         _TABS_DIR 내 모듈명(db_worker 등)은 고유하게 관리하십시오.
            if _TABS_DIR not in sys.path:
                sys.path.insert(0, _TABS_DIR)

            tab_widget = getattr(self, "tabWidget", None)
            if tab_widget is None:
                logger.warning("[TimescaleMonitorDialog] tabWidget을 찾을 수 없습니다.")
                return

            # 탭 정의: (모듈명, 클래스명, 탭 제목)
            tab_defs = [
                ("db_role_tab",     "DbRoleTab",     "📋 DB 역할 안내"),
                ("overview_db_tab",  "OverviewDbTab",  "📊 DB 개요"),
                ("connection_tab",  "ConnectionTab",  "🔗 연결 상태"),
                ("realtime_tab",    "RealtimeTab",    "📡 실시간 유입"),
                ("performance_tab", "PerformanceTab", "⚡ 성능 지표"),
                ("hypertable_tab",  "HypertableTab",  "🗂️ Hypertable"),
                ("compression_tab", "CompressionTab", "🗜️ 압축 현황"),
                ("cagg_tab",        "CaggTab",        "📐 연속 집계(CAGG)"),
                ("storage_tab",     "StorageTab",     "💾 스토리지"),
                ("data_view_tab",   "DataViewTab",    "🔍 저장 데이터 조회"),
                ("delete_tab",      "DeleteTab",      "🗑️ 데이터 삭제"),
                ("alert_tab",       "AlertTab",       "🔔 알림"),
            ]

            for module_name, class_name, tab_title in tab_defs:
                widget = None

                # 1) Python 탭 클래스 로드 시도
                mod_path = os.path.join(_TABS_DIR, f"{module_name}.py")
                if os.path.exists(mod_path):
                    try:
                        spec = importlib.util.spec_from_file_location(module_name, mod_path)
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        cls = getattr(mod, class_name, None)
                        if cls is not None:
                            import inspect as _inspect
                            sig = _inspect.signature(cls.__init__)
                            if "conn_params" in sig.parameters:
                                widget = cls(conn_params=self._conn_params)
                            else:
                                widget = cls()
                    except Exception as exc:
                        logger.warning(
                            "[TimescaleMonitorDialog] 탭 클래스 로드 실패 (%s.%s): %s",
                            module_name, class_name, exc,
                        )

                # 2) 폴백: .ui 파일을 빈 QWidget에 로드
                if widget is None:
                    ui_path = os.path.join(_TABS_DIR, f"{module_name}.ui")
                    if os.path.exists(ui_path):
                        try:
                            widget = QWidget()
                            uic.loadUi(ui_path, widget)
                        except Exception as exc:
                            logger.warning(
                                "[TimescaleMonitorDialog] 탭 UI 로드 실패 (%s.ui): %s",
                                module_name, exc,
                            )

                if widget is not None:
                    tab_widget.addTab(widget, tab_title)
                    setattr(self, module_name, widget)
                    # 탭이 start_updates() 메서드를 가지고 있으면 호출
                    if hasattr(widget, "start_updates"):
                        try:
                            widget.start_updates()
                        except Exception as exc:
                            logger.debug(
                                "[TimescaleMonitorDialog] start_updates 호출 실패 (%s): %s",
                                module_name, exc,
                            )
                else:
                    logger.debug(
                        "[TimescaleMonitorDialog] 탭 로드 불가 (%s) - 건너뜀", module_name
                    )

        def _connect_signals(self):
            """버튼 시그널 연결."""
            btn = getattr(self, "btnClose", None)
            if btn is not None:
                try:
                    btn.clicked.connect(self.close)
                except Exception:
                    pass

        def set_conn_params(self, params: Dict):
            """연결 파라미터 변경."""
            self._conn_params = params or {}

        def closeEvent(self, event):
            """다이얼로그 닫힘 시 모든 탭의 타이머와 Worker를 정리합니다."""
            tab_widget = getattr(self, "tabWidget", None)
            if tab_widget is not None:
                for i in range(tab_widget.count()):
                    widget = tab_widget.widget(i)
                    if widget and hasattr(widget, "stop_updates"):
                        try:
                            widget.stop_updates()
                        except Exception:
                            pass
            super().closeEvent(event)

else:
    class TimescaleMonitorDialog:  # type: ignore
        """PyQt5 미설치 시 폴백 스텁"""
        def __init__(self, *args, **kwargs):
            logger.warning("[TimescaleMonitorDialog] PyQt5 미설치 - 폴백 스텁")

        def set_conn_params(self, params):
            pass

        def exec_(self):
            return 0

        def show(self):
            pass
