# -*- coding: utf-8 -*-
"""
Kafka 모니터링 다이얼로그
- kafka_monitor.ui 로드
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

_UI_FILE = os.path.join(os.path.dirname(__file__), "kafka_monitor.ui")
_TABS_DIR = os.path.join(os.path.dirname(__file__), "tabs")

try:
    from PyQt5 import uic
    from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QWidget, QApplication
    _HAS_QT = True
except Exception:
    _HAS_QT = False


def _load_tab_class(tabs_dir, module_name, class_name):
    """탭 Python 클래스를 동적으로 로드한다."""
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


if _HAS_QT:
    class KafkaMonitorDialog(QDialog):
        """
        Kafka 모니터링 다이얼로그.
        kafka_monitor.ui 파일을 로드하고 tabs/*.ui 파일을 QTabWidget에 동적 추가.
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
                logger.debug("[KafkaMonitorDialog] UI 파일 로드 실패: %s", e)
            # 폴백 레이아웃
            from PyQt5.QtWidgets import (
                QPushButton, QHBoxLayout, QSpacerItem, QSizePolicy
            )
            self.setWindowTitle("Kafka 모니터링")
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
            """각 탭 클래스를 동적으로 로드하여 QTabWidget에 추가. Python 클래스 우선, .ui 파일 폴백."""
            import inspect as _inspect

            # tabs/ 폴더를 sys.path에 추가 (절대 임포트를 위해)
            if _TABS_DIR not in sys.path:
                sys.path.insert(0, _TABS_DIR)

            tab_widget = getattr(self, "tabWidget", None)
            if tab_widget is None:
                logger.warning("[KafkaMonitorDialog] tabWidget을 찾을 수 없습니다.")
                return

            tab_defs = [
                ("db_role_tab",    "DbRoleTab",    "📋 DB 역할 안내"),
                ("connection_tab", "ConnectionTab","📊 연결 상태"),
                ("realtime_tab",   "RealtimeTab",  "📡 실시간 통신"),
                ("overview_tab",   "OverviewTab",  "📈 성능 모니터링"),
                ("topic_tab",      "TopicTab",     "📂 토픽 관리"),
                ("consumer_tab",   "ConsumerTab",  "📥 Consumer Lag"),
                ("message_tab",    "MessageTab",   "📧 Message 뷰어"),
                ("data_view_tab",  "DataViewTab",  "🔍 저장 데이터 조회"),
                ("delete_tab",     "DeleteTab",    "🗑️ 데이터 삭제"),
            ]

            for module_name, class_name, tab_title in tab_defs:
                cls = _load_tab_class(_TABS_DIR, module_name, class_name)
                if cls is not None:
                    try:
                        sig = _inspect.signature(cls.__init__)
                        if "conn_params" in sig.parameters:
                            widget = cls(conn_params=self._conn_params)
                        else:
                            widget = cls()
                        tab_widget.addTab(widget, tab_title)
                        setattr(self, module_name, widget)
                        if hasattr(widget, "start_updates"):
                            try:
                                widget.start_updates()
                            except Exception as exc:
                                logger.debug("[KafkaMonitorDialog] start_updates 실패 (%s): %s", module_name, exc)
                        continue
                    except Exception as exc:
                        logger.warning("탭 클래스 인스턴스화 실패 (%s): %s", class_name, exc)

                # 폴백: .ui 파일 로드
                ui_path = os.path.join(_TABS_DIR, f"{module_name}.ui")
                if os.path.exists(ui_path):
                    try:
                        widget = QWidget()
                        uic.loadUi(ui_path, widget)
                        tab_widget.addTab(widget, tab_title)
                        setattr(self, module_name, widget)
                    except Exception as e:
                        logger.warning("탭 UI 로드 실패 (%s.ui): %s", module_name, e)

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
    class KafkaMonitorDialog:  # type: ignore
        """PyQt5 미설치 시 폴백 스텁"""
        def __init__(self, *args, **kwargs):
            logger.warning("[KafkaMonitorDialog] PyQt5 미설치 - 폴백 스텁")

        def set_conn_params(self, params):
            pass

        def exec_(self):
            return 0

        def show(self):
            pass
