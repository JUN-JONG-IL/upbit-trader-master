#!/usr/bin/python
# -*- coding: utf-8 -*-
"""MainWindow 진입점 (v11.4 - pymongo 동기 클라이언트)

변경:
- open_monitoring_dashboard()에서 pymongo.MongoClient 사용 (motor 제거)
- MongoDB 클라이언트를 동기 방식으로 생성하여 StatusWidget에 전달
- "Event loop is closed" 에러 완벽 해결
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from typing import Any, List, Optional
from pathlib import Path

from PyQt5.QtCore import QSettings, QTimer, Qt
from PyQt5.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QTableWidget,
    QVBoxLayout,
)
from PyQt5 import uic

logger = logging.getLogger(__name__)

try:
    import PyQt5.QtCore as _qtc
    _HAS_QT: bool = hasattr(_qtc, "PYQT_VERSION_STR")
except ImportError:
    _HAS_QT = False


UIStateManager: Optional[Any] = None
_HAS_UI_STATE_MANAGER = False
for _uism_path in ("src.app.ui.ui_state_manager", "app.ui.ui_state_manager"):
    try:
        _m = importlib.import_module(_uism_path)
        UIStateManager = getattr(_m, "UIStateManager", None)
        if UIStateManager:
            _HAS_UI_STATE_MANAGER = True
            break
    except Exception:
        pass
if not _HAS_UI_STATE_MANAGER:
    try:
        from .managers.widget_factory import WidgetFactory as _wf
        _cls = _wf._load_widget_class(
            os.path.join("app", "ui", "ui_state_manager.py"), "UIStateManager")
        if _cls:
            UIStateManager, _HAS_UI_STATE_MANAGER = _cls, True
    except Exception:
        pass


class MainWindow(QMainWindow):
    """메인 윈도우 클래스 (v11.4)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui_loaded = False
        self._symbol_table: Optional[Any] = None
        self._chart_widget_inst: Optional[Any] = None
        self._orderbook_widget_inst: Optional[Any] = None
        self._trade_widget_inst: Optional[Any] = None
        self._holding_widget_inst: Optional[Any] = None
        self._search_widget_inst: Optional[Any] = None
        self._pending_symbols: List[str] = []
        self._db_leds: List[Any] = []
        self.ui_state_manager: Optional[Any] = None
        self.vertical_splitter: Optional[Any] = None
        self.home_worker: List[Any] = []
        self.user_worker: List[Any] = []
        self.signal_worker: List[Any] = []
        self._home_workers_started: bool = False
        self._settings_widget_class: Optional[Any] = None
        self._monitoring_dashboard: Optional[Any] = None
        self.settings = QSettings("UpbitTrader", "MainWindow")
        self._setup_ui()
        self._init_managers()

    def _init_managers(self) -> None:
        """매니저 초기화"""
        try:
            from .managers import DBDialogManager, MenuHandler, SymbolLoader, WidgetLoader
            self.widget_loader = WidgetLoader(self)
            self.menu_handler = MenuHandler(self)
            self.db_dialog_manager = DBDialogManager(self)
            self.symbol_loader = SymbolLoader(self)
        except (ImportError, Exception):
            self.widget_loader = None
            self.menu_handler = None
            self.db_dialog_manager = None
            self.symbol_loader = None

    def _ui_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        resources_path = os.path.join(base, "resources", "main.ui")
        if os.path.exists(resources_path):
            return resources_path
        for name in ("main.ui", "window_main.ui", "main_window.ui"):
            p = os.path.join(base, name)
            if os.path.exists(p):
                return p
        parent_resources = os.path.join(os.path.dirname(base), "resources", "main.ui")
        if os.path.exists(parent_resources):
            return parent_resources
        return ""

    def _setup_ui(self) -> None:
        ui_path = self._ui_path()
        if not ui_path:
            logger.error("[MainWindow] main.ui 파일을 찾을 수 없습니다.")
            self._create_minimal_ui()
            return
        try:
            uic.loadUi(ui_path, self)
            self.ui_loaded = True
            logger.info("[MainWindow] UI loaded from %s", ui_path)
        except Exception as e:
            logger.exception("[MainWindow] uic.loadUi 실패", exc_info=e)
            self._create_minimal_ui()

    def _create_minimal_ui(self) -> None:
        from PyQt5.QtWidgets import QWidget
        self.setWindowTitle("Upbit Trader (UI 로드 실패)")
        central = QWidget(self)
        layout = QVBoxLayout()
        label = QLabel(
            "⚠️ main.ui 파일을 찾을 수 없습니다.\n현재는 최소 UI로 동작 중입니다.",
            central,
        )
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        central.setLayout(layout)
        self.setCentralWidget(central)
        self.ui_loaded = False

    def init_data(self) -> None:
        """로그인 성공 후 데이터 초기화"""
        if not self.ui_loaded:
            logger.warning("[MainWindow] init_data 건너뜀 (ui_loaded=False)")
            return

        logger.info("[MainWindow] 데이터 초기화 시작")

        if _HAS_UI_STATE_MANAGER and UIStateManager is not None:
            try:
                self.ui_state_manager = UIStateManager()
            except Exception as e:
                logger.warning("[MainWindow] UIStateManager 생성 실패: %s", e)
                self.ui_state_manager = None

        try:
            from .managers.widget_factory import WidgetFactory
            from .managers.worker_manager import WorkerManager
        except ImportError as e:
            logger.error("[MainWindow] 매니저 로드 실패: %s", e)
            return

        widgets = WidgetFactory.create_all_widgets(self.ui_state_manager)
        WidgetFactory.setup_splitter(self, widgets)
        WidgetFactory.place_remaining_widgets(self, widgets)
        WidgetFactory.connect_legacy_widgets(self)

        self._settings_widget_class = widgets.get("SettingsWidget")

        WorkerManager.setup_worker_lists(self)
        WidgetFactory.apply_default_layout(self)
        self._home_workers_started = False
        WorkerManager.start_home_workers(self, delay_ms=500)

        self._connect_ui_state()
        self._connect_all_menu_actions()
        self._start_symbol_load()
        self._setup_db_status_bar()
        self._setup_monitoring_menu()

        QTimer.singleShot(100, self._restore_splitter_state)

        logger.info("[MainWindow] 데이터 초기화 완료")

    def _connect_ui_state(self) -> None:
        try:
            if self.ui_state_manager is not None and hasattr(self.ui_state_manager, "symbol_changed"):
                self.ui_state_manager.symbol_changed.connect(self._on_symbol_changed)
                return
            from app.ui.ui_state_manager import ui_state_manager
            ui_state_manager.symbol_changed.connect(self._on_symbol_changed)
        except Exception as e:
            logger.warning("[MainWindow] UIStateManager 연결 실패: %s", e)

    def _on_symbol_changed(self, source: str, symbol: str) -> None:
        for widget_attr, name in [
            ("_chart_widget_inst", "차트"),
            ("_orderbook_widget_inst", "호가창"),
        ]:
            widget = getattr(self, widget_attr, None)
            if widget is not None and hasattr(widget, "update_symbol"):
                try:
                    widget.update_symbol(source, symbol)
                except Exception as e:
                    logger.debug("[MainWindow] %s 업데이트 실패: %s", name, e)

    def _on_symbol_item_clicked(self, item) -> None:
        try:
            if not isinstance(self._symbol_table, QTableWidget):
                return
            symbol_item = self._symbol_table.item(item.row(), 0)
            if symbol_item is None:
                return
            symbol = symbol_item.text().strip()
            if symbol:
                from app.ui.ui_state_manager import ui_state_manager
                ui_state_manager.set_symbol("upbit", symbol)
        except Exception as e:
            logger.warning("[MainWindow] 심볼 클릭 처리 실패: %s", e)

    def _setup_db_status_bar(self) -> None:
        """DB 상태 표시등 초기화"""
        try:
            DBStatusLED = None

            try:
                from .widgets.db_status_led import DBStatusLED  # type: ignore
            except Exception:
                DBStatusLED = None

            if DBStatusLED is None:
                for modname in (
                    "src.app.ui.widgets.db_status_led",
                    "app.ui.widgets.db_status_led",
                    "app.widgets.db_status_led",
                    "src.core.auth.ui.widget_login",
                ):
                    try:
                        mod = importlib.import_module(modname)
                        DBStatusLED = getattr(mod, "DBStatusLED", None)
                        if DBStatusLED:
                            logger.debug("[MainWindow] DBStatusLED loaded from module %s", modname)
                            break
                    except Exception:
                        logger.debug("[MainWindow] import %s failed", modname)

            if DBStatusLED is None:
                try:
                    here = os.path.dirname(os.path.abspath(__file__))
                    repo_root = Path(here).parents[1] if len(Path(here).parents) >= 2 else Path(here).parent
                    file_candidates = [
                        os.path.join(here, "widgets", "db_status_led.py"),
                        os.path.join(repo_root, "src", "app", "ui", "widgets", "db_status_led.py"),
                        os.path.join(repo_root, "src", "core", "auth", "ui", "widget_login.py"),
                        os.path.join(repo_root, "src", "app", "ui", "windows", "db_status_led.py"),
                    ]
                    for cand in [os.path.abspath(p) for p in file_candidates]:
                        try:
                            if not os.path.isfile(cand):
                                continue
                            spec = importlib.util.spec_from_file_location("temp_db_status_led_mod", cand)
                            if spec and spec.loader:
                                mod = importlib.util.module_from_spec(spec)
                                spec.loader.exec_module(mod)
                                DBStatusLED = getattr(mod, "DBStatusLED", None)
                                if DBStatusLED:
                                    logger.debug("[MainWindow] DBStatusLED loaded from file %s", cand)
                                    break
                        except Exception as e:
                            logger.debug("[MainWindow] file-load candidate %s failed: %s", cand, e)
                except Exception as e:
                    logger.debug("[MainWindow] File-level DBStatusLED discovery failed: %s", e)

            if DBStatusLED is None:
                logger.warning("[MainWindow] DB 상태 표시등 초기화 실패: DBStatusLED 모듈을 찾을 수 없음")
                return

            status_bar = self.statusBar()
            for display_name, db_key in [
                ("TimescaleDB", "TimescaleDB"), ("MongoDB", "MongoDB"),
                ("Redis", "Redis"), ("Kafka", "Kafka"), ("ClickHouse", "ClickHouse"),
            ]:
                try:
                    status_bar.addPermanentWidget(QLabel(f"  {display_name}: "))
                    led = DBStatusLED(db_key, status_bar)
                    status_bar.addPermanentWidget(led)
                    self._db_leds.append(led)
                except Exception as e:
                    logger.debug("[MainWindow] DB LED widget creation failed for %s: %s", display_name, e)
        except Exception as e:
            logger.warning("[MainWindow] DB 상태 표시등 초기화 실패: %s", e)

    def _restore_splitter_state(self) -> None:
        if not hasattr(self, "settings") or not getattr(self, "vertical_splitter", None):
            return
        try:
            saved = self.settings.value("vertical_splitter_sizes", None)
            if saved:
                if isinstance(saved, str):
                    import json
                    try:
                        saved = json.loads(saved)
                    except (json.JSONDecodeError, ValueError):
                        saved = None
                elif not isinstance(saved, list):
                    saved = list(saved)
                if saved is not None:
                    self.vertical_splitter.setSizes([int(s) for s in saved])
        except Exception as e:
            logger.warning("[MainWindow] QSplitter 상태 복원 실패: %s", e)

    def _switch_page(self, page_index: int) -> None:
        """페이지 전환"""
        _PAGES = {
            0: ("Home",   self.home_worker,   [self.user_worker, self.signal_worker]),
            1: ("User",   self.user_worker,   [self.home_worker, self.signal_worker]),
            2: ("Signal", self.signal_worker, [self.home_worker, self.user_worker]),
        }
        qsw = getattr(self, "qStackedWidget", None)
        if not qsw or qsw.currentIndex() == page_index:
            return
        name, start, stop_lists = _PAGES[page_index]
        logger.info("[MainWindow] %s 페이지 전환", name)
        try:
            from .managers.worker_manager import WorkerManager
            WorkerManager.start_workers([w for w in start if w])
            for workers in stop_lists:
                WorkerManager.stop_workers([w for w in workers if w])
        except ImportError:
            for w in [x for x in start if x]:
                try:
                    if hasattr(w, "isRunning") and not w.isRunning():
                        w.start()
                except Exception:
                    pass
            for workers in stop_lists:
                for w in [x for x in workers if w]:
                    try:
                        if hasattr(w, "close"):
                            w.close()
                        elif hasattr(w, "alive"):
                            w.alive = False
                    except Exception:
                        pass
        qsw.setCurrentIndex(page_index)

    def home_btn_click(self) -> None:
        self._switch_page(0)

    def user_btn_click(self) -> None:
        self._switch_page(1)

    def signal_btn_click(self) -> None:
        self._switch_page(2)

    def settings_btn_click(self) -> None:
        """설정 창 열기"""
        cls = getattr(self, "_settings_widget_class", None)
        if cls is None:
            try:
                from .managers.widget_factory import WidgetFactory
                mapping = getattr(WidgetFactory, "_WIDGET_PATHS", None) or {}
                rel_path, cls_name = mapping.get(
                    "SettingsWidget",
                    (os.path.join("server", "ui", "settings", "widget_server_settings.py"), "SettingsWidget"),
                )
                cls = WidgetFactory._load_widget_class(rel_path, cls_name)
            except Exception:
                cls = None
        if cls is None:
            logger.warning("[MainWindow] SettingsWidget 사용 불가")
            QMessageBox.information(self, "설정", "설정 위젯을 불러올 수 없습니다.")
            return
        try:
            try:
                self.settings_widget = cls(parent=self)
            except TypeError:
                self.settings_widget = cls()
            try:
                from PyQt5.QtWidgets import QDialog
                if isinstance(self.settings_widget, QDialog):
                    self.settings_widget.setModal(False)
            except Exception:
                pass
            self.settings_widget.show()
        except Exception as e:
            logger.error("[MainWindow] settings 열기 실패: %s", e)

    def _embed_widgets(self) -> None:
        if not _HAS_QT:
            return
        if self.widget_loader is not None:
            self.widget_loader.embed_widgets()

    def _connect_all_menu_actions(self) -> None:
        if self.menu_handler is not None:
            self.menu_handler.connect_actions()

    def _connect_db_menu_actions(self) -> None:
        db_action_map = {
            "actionDB_Timescale": self._open_timescale_dialog,
            "actionDB_Mongo": self._open_mongodb_dialog,
            "actionDB_Redis": self._open_redis_dialog,
            "actionDB_Kafka": self._open_kafka_dialog,
            "actionDB_ClickHouse": self._open_clickhouse_dialog,
        }
        for action_name, handler in db_action_map.items():
            action = getattr(self, action_name, None)
            if action is not None:
                action.triggered.connect(handler)

    def _start_symbol_load(self) -> None:
        if self.symbol_loader is not None:
            self.symbol_loader.start_loading()

    def _open_timescale_dialog(self) -> None:
        if self.db_dialog_manager is not None:
            self.db_dialog_manager._open_timescale_dialog()

    def _open_mongodb_dialog(self) -> None:
        if self.db_dialog_manager is not None:
            self.db_dialog_manager._open_mongodb_dialog()

    def _open_redis_dialog(self) -> None:
        if self.db_dialog_manager is not None:
            self.db_dialog_manager._open_redis_dialog()

    def _open_kafka_dialog(self) -> None:
        if self.db_dialog_manager is not None:
            self.db_dialog_manager._open_kafka_dialog()

    def _open_clickhouse_dialog(self) -> None:
        if self.db_dialog_manager is not None:
            self.db_dialog_manager._open_clickhouse_dialog()

    def _open_postgresql_dialog(self) -> None:
        if self.db_dialog_manager is not None:
            self.db_dialog_manager._open_postgresql_dialog()

    def open_monitoring_dashboard(self) -> None:
        """
        실시간 모니터링 대시보드(StatusWidget)를 열거나 앞으로 가져옵니다.
        
        ✅ pymongo.MongoClient (동기) 사용 - Event loop is closed 에러 해결
        """
        try:
            # ✅ MongoDB 동기 클라이언트 생성 (pymongo)
            mongo_client = None
            try:
                import pymongo
                import os
                
                host = os.getenv("MONGO_HOST", "localhost")
                port = int(os.getenv("MONGO_PORT", "27017"))
                uri = os.getenv("MONGO_URI") or f"mongodb://{host}:{port}"
                
                # pymongo.MongoClient 생성 (동기)
                mongo_client = pymongo.MongoClient(
                    uri,
                    serverSelectionTimeoutMS=2000,
                    directConnection=True,
                )
                # 연결 테스트
                mongo_client.admin.command("ping")
                logger.info("[MainWindow] ✅ MongoDB 동기 클라이언트 생성 성공 (pymongo)")
                
            except Exception as exc:
                logger.warning("[MainWindow] MongoDB 클라이언트 생성 실패: %s — 설정 저장 불가", exc)
                mongo_client = None

            # 이미 캐시된 인스턴스가 있으면 재사용
            if self._monitoring_dashboard is not None:
                try:
                    if self._monitoring_dashboard.isVisible():
                        self._monitoring_dashboard.raise_()
                        self._monitoring_dashboard.activateWindow()
                        return
                    else:
                        self._monitoring_dashboard.show()
                        self._monitoring_dashboard.raise_()
                        self._monitoring_dashboard.activateWindow()
                        logger.info("[MainWindow] 시스템 모니터 재열기")
                        return
                except Exception:
                    self._monitoring_dashboard = None

            # StatusWidget 임포트
            StatusWidget = None
            for mod_path in (
                "_data_01.ui.status_widget",
                "data_01.ui.status_widget",
            ):
                try:
                    mod = importlib.import_module(mod_path)
                    StatusWidget = getattr(mod, "StatusWidget", None)
                    if StatusWidget:
                        break
                except Exception:
                    continue

            if StatusWidget is None:
                here = os.path.dirname(os.path.abspath(__file__))
                repo_root = Path(here).parents[1] if len(Path(here).parents) > 1 else Path(here).parent
                candidate = os.path.join(repo_root, "src", "data_01", "ui", "status_widget.py")
                if os.path.isfile(candidate):
                    spec = importlib.util.spec_from_file_location("_status_widget", candidate)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        StatusWidget = getattr(mod, "StatusWidget", None)

            if StatusWidget is None:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(self, "모니터링", "시스템 모니터를 불러올 수 없습니다.")
                return

            # ✅ pymongo 동기 클라이언트 전달
            self._monitoring_dashboard = StatusWidget(parent=None, mongo_client=mongo_client)
            self._monitoring_dashboard.show()
            self._monitoring_dashboard.raise_()
            self._monitoring_dashboard.activateWindow()
            logger.info("[MainWindow] 시스템 모니터(StatusWidget) 열림")
        except Exception as e:
            logger.error("[MainWindow] 시스템 모니터 열기 실패: %s", e)

    def _setup_monitoring_menu(self) -> None:
        """메뉴바에 '모니터링' 메뉴와 '시스템 모니터링' 액션을 추가합니다."""
        try:
            from PyQt5.QtWidgets import QAction, QMenuBar
            menu_bar: Optional[Any] = self.menuBar()
            if menu_bar is None:
                return

            for action in menu_bar.actions():
                if "모니터링" in action.text():
                    return

            monitoring_menu = menu_bar.addMenu("📊 모니터링")
            dashboard_action = QAction("시스템 모니터링", self)
            dashboard_action.setShortcut("Ctrl+Shift+M")
            dashboard_action.triggered.connect(self.open_monitoring_dashboard)
            monitoring_menu.addAction(dashboard_action)
            logger.info("[MainWindow] 모니터링 메뉴 추가 완료")
        except Exception as e:
            logger.warning("[MainWindow] 모니터링 메뉴 추가 실패: %s", e)

    def debug_info(self) -> dict:
        return {
            "ui_loaded": self.ui_loaded,
            "has_qt": _HAS_QT,
            "ui_path": self._ui_path(),
            "symbol_count": len(self._pending_symbols),
        }

    def start(self) -> None:
        logger.info("[MainWindow] 앱 시작")

    def stop(self) -> None:
        logger.info("[MainWindow] 앱 종료")
        try:
            for led in getattr(self, "_db_leds", []) or []:
                try:
                    if hasattr(led, "stop"):
                        led.stop()
                except Exception:
                    pass
        except Exception:
            pass

        for attr in ("refresh_timer", "_symbol_poll_timer"):
            t = getattr(self, attr, None)
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass

        dashboard = getattr(self, "_monitoring_dashboard", None)
        if dashboard is not None:
            try:
                dashboard.close()
            except Exception:
                pass

    def closeEvent(self, event):
        try:
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("windowState", self.saveState())
        except Exception:
            pass
        self.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication

    app = QApplication([])
    win = MainWindow()
    win.show()
    win.init_data()
    win.start()
    app.exec_()