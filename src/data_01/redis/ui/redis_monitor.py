# -*- coding: utf-8 -*-
"""
Redis 모니터링 다이얼로그
- redis_monitor.ui 로드
- tabs/*.ui 파일을 동적으로 로드하여 QTabWidget에 추가
- 독립 실행 또는 메인 앱에서 열기 가능
"""
from __future__ import annotations

import importlib.util
import os
import sys
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_UI_FILE = os.path.join(os.path.dirname(__file__), "redis_monitor.ui")
_TABS_DIR = os.path.join(os.path.dirname(__file__), "tabs")


def _load_tab_class(tabs_dir: str, module_name: str, class_name: str):
    """Python 탭 클래스를 동적으로 로드. 실패 시 None 반환."""
    mod_path = os.path.join(tabs_dir, f"{module_name}.py")
    if not os.path.exists(mod_path):
        return None
    try:
        spec = importlib.util.spec_from_file_location(module_name, mod_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, class_name, None)
    except Exception as exc:
        logger.debug("탭 클래스 로드 실패 (%s.%s): %s", module_name, class_name, exc)
        return None


try:
    from PyQt5 import uic
    from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QWidget, QApplication
    _HAS_QT = True
except Exception:
    _HAS_QT = False


if _HAS_QT:
    class RedisMonitorDialog(QDialog):
        """
        Redis 모니터링 다이얼로그.
        redis_monitor.ui 파일을 로드하고 tabs/*.ui 파일을 QTabWidget에 동적 추가.
        Python 탭 클래스가 있으면 우선 사용하고, 없으면 .ui 파일 폴백.
        """

        def __init__(self, parent=None, conn_params: Optional[Dict] = None, refresh_ms: int = 10_000):
            super().__init__(parent)
            self._conn_params = conn_params or {}
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
                logger.debug("[RedisMonitorDialog] UI 파일 로드 실패: %s", e)
            # 폴백 레이아웃
            from PyQt5.QtWidgets import (
                QPushButton, QHBoxLayout, QSpacerItem, QSizePolicy
            )
            self.setWindowTitle("Redis 모니터링")
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
            """Python 탭 클래스를 우선 로드. 없으면 .ui 파일로 폴백."""
            # tabs/ 폴더를 sys.path에 추가 (절대 임포트를 위해)
            if _TABS_DIR not in sys.path:
                sys.path.insert(0, _TABS_DIR)

            tab_widget = getattr(self, "tabWidget", None)
            if tab_widget is None:
                logger.warning("[RedisMonitorDialog] tabWidget을 찾을 수 없습니다.")
                return

            # 탭 정의: (모듈명, 클래스명, UI 파일명, 탭 제목, 속성명)
            tab_defs = [
                ("db_role_tab",    "DbRoleTab",     "db_role_tab.ui",    "📋 DB 역할 안내",    "db_role_tab"),
                ("connection_tab", "ConnectionTab", "connection_tab.ui", "📊 연결 상태",       "connection_tab"),
                ("realtime_tab",   "RealtimeTab",   "realtime_tab.ui",   "📡 실시간 통신",     "realtime_tab"),
                ("status_tab",     "StatusTab",     "status_tab.ui",     "📈 성능 모니터링",   "status_tab"),
                ("l1_cache_tab",   "L1CacheTab",    "l1_cache_tab.ui",   "💾 L1 캐시",        "l1_cache_tab"),
                ("gap_queue_tab",  "GapQueueTab",   "gap_queue_tab.ui",  "🔍 Gap 큐",         "gap_queue_tab"),
                ("pubsub_tab",     "PubSubTab",     "pubsub_tab.ui",     "📢 Pub/Sub",        "pubsub_tab"),
                ("sentinel_tab",   "SentinelTab",   "sentinel_tab.ui",   "🛡️ Sentinel",       "sentinel_tab"),
                ("alert_tab",      "AlertTab",      "alert_tab.ui",      "🔔 알림 설정",      "alert_tab"),
                ("data_view_tab",  "DataViewTab",   "data_view_tab.ui",  "🔍 저장 데이터 조회", "data_view_tab"),
                ("delete_tab",     "DeleteTab",     "delete_tab.ui",     "🗑️ 데이터 삭제",    "delete_tab"),
            ]

            for mod_name, cls_name, ui_file, tab_title, attr_name in tab_defs:
                widget = self._try_load_python_tab(mod_name, cls_name)
                if widget is None:
                    widget = self._try_load_ui_tab(ui_file)
                if widget is not None:
                    tab_widget.addTab(widget, tab_title)
                    setattr(self, attr_name, widget)
                    if hasattr(widget, "start_updates"):
                        try:
                            widget.start_updates()
                        except Exception as exc:
                            logger.debug("[RedisMonitorDialog] start_updates 실패 (%s): %s", mod_name, exc)

        def _try_load_python_tab(self, mod_name: str, cls_name: str) -> Optional[QWidget]:
            """Python 탭 클래스 인스턴스화 시도."""
            import inspect
            cls = _load_tab_class(_TABS_DIR, mod_name, cls_name)
            if cls is None:
                return None
            try:
                # inspect로 conn_params 인자 지원 여부 확인 후 전달
                sig = inspect.signature(cls.__init__)
                if "conn_params" in sig.parameters:
                    widget = cls(conn_params=self._conn_params)
                else:
                    widget = cls()
                return widget
            except Exception as exc:
                logger.warning("[RedisMonitorDialog] 탭 클래스 인스턴스화 실패 (%s): %s", cls_name, exc)
                return None

        def _try_load_ui_tab(self, ui_file: str) -> Optional[QWidget]:
            """UI 파일로 QWidget 폴백 로드."""
            ui_path = os.path.join(_TABS_DIR, ui_file)
            if not os.path.exists(ui_path):
                logger.debug("[RedisMonitorDialog] 탭 UI 파일 없음: %s", ui_path)
                return None
            try:
                widget = QWidget()
                uic.loadUi(ui_path, widget)
                return widget
            except Exception as e:
                logger.warning("[RedisMonitorDialog] 탭 UI 로드 실패 (%s): %s", ui_file, e)
                return None

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
    class RedisMonitorDialog:  # type: ignore
        """PyQt5 미설치 시 폴백 스텁"""
        def __init__(self, *args, **kwargs):
            logger.warning("[RedisMonitorDialog] PyQt5 미설치 - 폴백 스텁")

        def set_conn_params(self, params):
            pass

        def exec_(self):
            return 0

        def show(self):
            pass
