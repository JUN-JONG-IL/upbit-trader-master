# -*- coding: utf-8 -*-
"""
StatisticsTab (View ?„ìš©, ê°•í™”??UI ë¡œë“œ/ë°”ì¸??
- ?µì‹¬ ëª©í‘œ: .uiê°€ ë¡œë“œ?˜ì–´???„ì ¯(objectName)???†ì–´???”ë©´??ë¹„ì–´ ë³´ì´??ë¬¸ì œ ë°©ì?.
- ?„ëµ:
  1) load_ui_with_tab_fix ?°ì„  ?œë„ (?ˆìœ¼ë©?.ui enum/xml ë³´ì •)
  2) PyQt uic.loadUi ?´ë°±
  3) uic.loadUiType ?´ë°± (ì½”ë“œ ?ì„±??
  4) ë¡œë“œ ???µì‹¬ ?„ì ¯(tabWidget_main_tabs, table_tab_X ?????†ìœ¼ë©?findChild ê¸°ë°˜?¼ë¡œ ?ë™ ë°”ì¸??
- ???Œì¼?€ ViewÂ·?œê·¸?Â·ê²½???¬í¼ë§??¬í•¨?©ë‹ˆ?? ë¹„ì¦ˆ?ˆìŠ¤ ë¡œì§?€ Controllerë¡??´ë™?˜ì„¸??
"""
from __future__ import annotations
import os
import logging
import importlib
import importlib.util
import threading
import json
import csv
from collections import deque
from datetime import datetime
from typing import Any, Optional, Sequence, Dict, List, Deque, TYPE_CHECKING

logger = logging.getLogger(__name__)

# PyQt import (ê°€?©ì„± ê²€??
try:
    from PyQt5 import uic
    from PyQt5.QtCore import pyqtSignal, QTimer, Qt
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import (
        QWidget, QFileDialog, QTableWidget, QTableWidgetItem, QTextEdit, QPlainTextEdit,
        QTabWidget, QLabel, QVBoxLayout, QHeaderView, QTableView, QAbstractItemView
    )
    _HAS_QT = True
except Exception:
    _HAS_QT = False

# Optional local imports (if your project has these modules)
# Make editors/type-checkers happy while keeping runtime fallback
if TYPE_CHECKING:
    try:
        from ._mixins import TableCopyMixin  # type: ignore
    except Exception:
        TableCopyMixin = object  # type: ignore
else:
    try:
        from ._mixins import TableCopyMixin
    except Exception:
        TableCopyMixin = object

try:
    from .statistics_model import StatisticsModel, LogFilterProxyModel
except Exception:
    StatisticsModel = None
    LogFilterProxyModel = None

# Persistence paths (???”ë ‰?°ë¦¬???¨ê? ?”ë ‰?°ë¦¬)
_LAYOUT_DIR = os.path.join(os.path.expanduser("~"), ".upbit_trader")
_LAYOUT_FILE = os.path.join(_LAYOUT_DIR, "statistics_tab_layout.json")
_SETTINGS_FILE = os.path.join(_LAYOUT_DIR, "statistics_tab_settings.json")

# ê¸°ë³¸ ?¤ì •
_DEF = {
    "num_live_tabs": 3,
    "flush_interval_ms": 200,
    "flush_batch": 200,
    "max_pending": 100000,
    "enable_forwarding": True,
    "autostart_timer": True,
    "auto_load_history_on_start": False,
    "history_max_lines": 1000,
}


def _load_ui_loader() -> Optional[callable]:
    """
    Try to locate load_ui_with_tab_fix:
      - prefer package import 'src.data_01.ui_loader' when src is a package root
      - fallback to searching common relative paths from this file
    """
    try:
        try:
            mod = importlib.import_module("src.data_01.ui_loader")
            return getattr(mod, "load_ui_with_tab_fix", None)
        except Exception:
            pass

        candidates = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ui_loader.py")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "ui_loader.py")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src", "data_01", "ui_loader.py")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src", "data", "ui_loader.py")),
            # developer local candidate (optional)
            r"C:\Users\jji24\anaconda3\envs\py311\trade\upbit-trader-master\src\data\ui_loader.py",
        ]
        for p in candidates:
            try:
                if p and os.path.exists(p):
                    spec = importlib.util.spec_from_file_location("ui_loader_local", p)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        return getattr(mod, "load_ui_with_tab_fix", None)
            except Exception:
                continue
    except Exception:
        pass
    return None


_load_ui_with_tab_fix = _load_ui_loader()


if _HAS_QT:
    class StatisticsTab(TableCopyMixin, QWidget):
        _RAW_VIEW_MAX_LINES = 2000

        # View-only signals (Controller should connect)
        load_history_requested = pyqtSignal(str)
        pause_toggled = pyqtSignal()
        manual_refresh_requested = pyqtSignal()
        export_tab_requested = pyqtSignal(int)
        export_all_requested = pyqtSignal()
        clear_tab_requested = pyqtSignal(int)
        clear_all_requested = pyqtSignal()
        active_tab_changed = pyqtSignal(int)
        search_text_changed = pyqtSignal(int, str)

        def __init__(self, parent=None, ui_filename: Optional[str] = None):
            super().__init__(parent)

            if ui_filename is None:
                ui_filename = os.path.join(os.path.dirname(__file__), "statistics_tab.ui")

            loaded = self._robust_load_ui(ui_filename)

            # Quick diagnostic to help find blank-UI problems
            try:
                logger.debug("[StatisticsTab.DEBUG] after load, child count=%d", len(self.findChildren(object)))
            except Exception:
                pass

            if not loaded or not self._has_core_widgets():
                logger.warning("[StatisticsTab] UI ë¡œë“œ ?ëŠ” ë°”ì¸??ë¶ˆì™„?????ë™ ë°”ì¸???œë„")
                self._attempt_find_widgets()
                if not self._has_core_widgets():
                    self._show_ui_warning(f"StatisticsTab UI ë¡œë“œ ?¤íŒ¨ ?ëŠ” ?µì‹¬ ?„ì ¯ ?„ë½: {os.path.basename(ui_filename)}")

            # mixin init (optional)
            try:
                self._setup_table_copy()
            except Exception:
                pass

            # settings
            self._settings: Dict[str, Any] = {}
            self._load_settings_file_or_defaults()

            # buffers and locks
            self._pending_logs: Deque[Dict[str, Any]] = deque()
            self._pending_lock = threading.Lock()

            # per-tab caches (fixed annotations and initialization)
            self._displayed_logs_by_tab: Dict[int, Deque[Dict[str, Any]]] = {i: deque() for i in range(1, 8)}
            self._models: Dict[int, Optional[StatisticsModel]] = {}
            self._proxies: Dict[int, Optional[LogFilterProxyModel]] = {}
            self._views: Dict[int, Optional[object]] = {}

            # widget caches
            self._text_logs: Dict[int, Optional[object]] = {}
            self._search_boxes: Dict[int, Optional[object]] = {}
            self._spin_max_rows: Dict[int, Optional[object]] = {}
            self._chk_autoscrolls: Dict[int, Optional[object]] = {}
            self._chk_ws: Dict[int, Optional[object]] = {}
            self._chk_pipeline: Dict[int, Optional[object]] = {}
            self._chk_gap: Dict[int, Optional[object]] = {}
            self._chk_show_warnings: Dict[int, Optional[object]] = {}
            self._combo_levels: Dict[int, Optional[object]] = {}

            self._column_layouts: Dict[str, List[int]] = {}
            self._load_column_layouts()

            # bind per-tab widgets and connect signals
            for i in range(1, 8):
                tbl_widget = getattr(self, f"table_tab_{i}", None)
                self._orig_tablewidgets[i] = tbl_widget
                self._text_logs[i] = getattr(self, f"text_log_tab_{i}", None) or getattr(self, f"plain_log_tab_{i}", None)
                self._search_boxes[i] = getattr(self, f"le_tab{i}_search", None)
                self._spin_max_rows[i] = getattr(self, f"sb_tab{i}_max_rows", None)
                self._chk_autoscrolls[i] = getattr(self, f"chk_tab{i}_autoscroll", None)
                self._chk_ws[i] = getattr(self, f"chk_tab{i}_ws", None)
                self._chk_pipeline[i] = getattr(self, f"chk_tab{i}_exchange_api", None)
                self._chk_gap[i] = getattr(self, f"chk_tab{i}_quotation_api", None)
                self._chk_show_warnings[i] = getattr(self, f"chk_tab{i}_warning", None)
                self._combo_levels[i] = getattr(self, f"combo_tab{i}_log_level", None) or getattr(self, "combo_log_level", None)

                try:
                    self._replace_table_widget_with_view(i, tbl_widget)
                except Exception as exc:
                    logger.debug("[StatisticsTab] _replace_table_widget_with_view ?¤íŒ¨(tab=%s): %s", i, exc)

                try:
                    if self._search_boxes[i] is not None and hasattr(self._search_boxes[i], "textChanged"):
                        self._search_boxes[i].textChanged.connect(lambda _, tab=i: self._update_proxy_filters(tab))
                except Exception:
                    pass

                try:
                    btn_show_all = getattr(self, f"btn_tab{i}_show_all", None)
                    if btn_show_all is not None and hasattr(btn_show_all, "clicked"):
                        btn_show_all.clicked.connect(lambda _, tab=i: self._on_show_all_tab(tab))
                    btn_export = getattr(self, f"btn_tab{i}_export", None)
                    if btn_export is not None and hasattr(btn_export, "clicked"):
                        btn_export.clicked.connect(lambda _, tab=i: self._on_export_tab(tab))
                    btn_clear = getattr(self, f"btn_tab{i}_clear", None)
                    if btn_clear is not None and hasattr(btn_clear, "clicked"):
                        btn_clear.clicked.connect(lambda _, tab=i: self.clear_tab(tab))
                except Exception:
                    pass

            # toolbar
            try:
                btn_pause = getattr(self, "btn_pause", None)
                if btn_pause is not None:
                    btn_pause.clicked.connect(self._on_toggle_pause)
                btn_refresh = getattr(self, "btn_refresh", None)
                if btn_refresh is not None:
                    btn_refresh.clicked.connect(lambda: self._on_manual_refresh())
                btn_export_all = getattr(self, "btn_export_all", None)
                if btn_export_all is not None:
                    btn_export_all.clicked.connect(lambda: self._on_export_all())
                btn_clear_all = getattr(self, "btn_clear_all", None)
                if btn_clear_all is not None:
                    btn_clear_all.clicked.connect(lambda: self.clear_all_tabs())
                btn_settings = getattr(self, "btn_settings", None)
                if btn_settings is not None:
                    btn_settings.clicked.connect(self._open_settings_dialog)
                btn_load_history = getattr(self, "btn_load_history", None)
                if btn_load_history is not None and hasattr(btn_load_history, "clicked"):
                    btn_load_history.clicked.connect(self._on_load_history)
            except Exception:
                pass

            # timer
            self._timer = QTimer(self)
            self._timer.setInterval(int(self._settings.get("flush_interval_ms", _DEF["flush_interval_ms"])))
            self._timer.timeout.connect(self._on_timer_flush)

            # main tab widget hook
            self._main_tabwidget = getattr(self, "tabWidget_main_tabs", None)
            try:
                if self._main_tabwidget is not None:
                    self._main_tabwidget.currentChanged.connect(lambda idx: self._on_active_tab_changed())
            except Exception:
                pass

            # handlers
            self._log_handler = None
            self._auto_log_handler = None
            self._forwarding_handler = None
            self._setup_auto_log_handler()
            self._add_bootstrap_stream_handler()

            try:
                if bool(self._settings.get("autostart_timer", _DEF["autostart_timer"])) and not self._timer.isActive():
                    self._timer.start()
                    logger.info("[StatisticsTab] ?€?´ë¨¸ ?ë™ ?œì‘")
            except Exception:
                pass

            try:
                if bool(self._settings.get("auto_load_history_on_start", _DEF["auto_load_history_on_start"])):
                    self.load_history(max_lines=int(self._settings.get("history_max_lines", _DEF["history_max_lines"])) )
            except Exception:
                pass

        # -------------------------
        # UI ë¡œë“œ / ë°”ì¸??ë³´ì¡°
        # -------------------------
        def _robust_load_ui(self, ui_path: str) -> bool:
            """Try load_ui_with_tab_fix, then uic.loadUi, then uic.loadUiType as final fallback."""
            try:
                if _load_ui_with_tab_fix is not None:
                    try:
                        _load_ui_with_tab_fix(ui_path, self)
                        logger.info("[StatisticsTab] UI ë¡œë“œ ?±ê³µ (load_ui_with_tab_fix)")
                        return True
                    except Exception as e:
                        logger.debug("[StatisticsTab] load_ui_with_tab_fix ?¤íŒ¨: %s", e)
                # Try uic.loadUi
                try:
                    uic.loadUi(ui_path, self)
                    logger.info("[StatisticsTab] UI ë¡œë“œ ?±ê³µ (uic.loadUi)")
                    return True
                except Exception as e:
                    logger.debug("[StatisticsTab] uic.loadUi ?¤íŒ¨: %s", e)
                # Try loadUiType fallback (generates form class)
                try:
                    form_class, base_class = uic.loadUiType(ui_path)
                    form = form_class()
                    form.setupUi(self)
                    logger.info("[StatisticsTab] UI ë¡œë“œ ?±ê³µ (uic.loadUiType ?´ë°±)")
                    return True
                except Exception as e:
                    logger.warning("[StatisticsTab] uic.loadUiType ?´ë°± ?¤íŒ¨: %s", e)
                    return False
            except Exception as exc:
                logger.exception("[StatisticsTab] UI ë¡œë“œ ì¤??ˆì™¸: %s", exc)
                return False

        def _has_core_widgets(self) -> bool:
            """Check for presence of primary expected widgets."""
            if hasattr(self, "tabWidget_main_tabs") and getattr(self, "tabWidget_main_tabs") is not None:
                return True
            # fallback: any table or text_log present
            for name in ("table_tab_1", "text_log_tab_1"):
                if hasattr(self, name) and getattr(self, name) is not None:
                    return True
            return False

        def _attempt_find_widgets(self) -> None:
            """Try to auto-bind expected widget names via findChild if attributes missing."""
            try:
                if not hasattr(self, "tabWidget_main_tabs") or getattr(self, "tabWidget_main_tabs") is None:
                    tab = self._find_first_child(QTabWidget)
                    if tab is not None:
                        try:
                            setattr(self, "tabWidget_main_tabs", tab)
                            logger.debug("[StatisticsTab] tabWidget_main_tabs ?ë™ ë°”ì¸????(%s)", getattr(tab, "objectName", lambda: "")())
                        except Exception:
                            pass
            except Exception:
                pass

            # For tables/texts: attempt findChild by name patterns
            for i in range(1, 8):
                try:
                    if not hasattr(self, f"table_tab_{i}") or getattr(self, f"table_tab_{i}") is None:
                        w = self._find_widget_by_name(QTableWidget, f"table_tab_{i}")
                        if w is not None:
                            try:
                                setattr(self, f"table_tab_{i}", w)
                                logger.debug("[StatisticsTab] table_tab_%d ?ë™ ë°”ì¸??(%s)", i, w.objectName())
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    if not hasattr(self, f"text_log_tab_{i}") or getattr(self, f"text_log_tab_{i}") is None:
                        w = self._find_widget_by_name((QTextEdit, QPlainTextEdit), f"text_log_tab_{i}")
                        if w is not None:
                            try:
                                setattr(self, f"text_log_tab_{i}", w)
                                logger.debug("[StatisticsTab] text_log_tab_%d ?ë™ ë°”ì¸??(%s)", i, w.objectName())
                            except Exception:
                                pass
                except Exception:
                    pass

        def _find_widget_by_name(self, cls, name: str):
            """Wrapper around findChild with None-safe behavior and fuzzy fallback."""
            try:
                if isinstance(cls, tuple):
                    for c in cls:
                        obj = self.findChild(c, name)
                        if obj is not None:
                            return obj
                else:
                    obj = self.findChild(cls, name)
                    if obj is not None:
                        return obj
                # fuzzy fallback
                for child in self.findChildren(object):
                    try:
                        if name in (child.objectName() or ""):
                            return child
                    except Exception:
                        continue
            except Exception:
                pass
            return None

        def _find_first_child(self, cls):
            try:
                childs = self.findChildren(cls)
                if childs:
                    return childs[0]
            except Exception:
                pass
            return None

        def _show_ui_warning(self, text: str) -> None:
            """If UI hasn't proper widgets, show a small label so user sees something.""" 
            try:
                # don't override if actual UI present
                if self._has_core_widgets():
                    return
                layout = QVBoxLayout(self)
                lbl = QLabel(text, self)
                lbl.setStyleSheet("color: red; font-weight: bold;")
                layout.addWidget(lbl)
                self.setLayout(layout)
            except Exception:
                pass

        # -------------------------
        # ?¤ì • ?Œì¼ ë¡œë“œ/?€??
        # -------------------------
        def _load_settings_file_or_defaults(self) -> None:
            self._settings = dict(_DEF)
            try:
                if os.path.exists(_SETTINGS_FILE):
                    with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._settings.update(data)
            except Exception as exc:
                logger.debug("[StatisticsTab] _load_settings_file_or_defaults ?¤íŒ¨: %s", exc)

        def _save_settings_file(self) -> None:
            try:
                if not os.path.isdir(_LAYOUT_DIR):
                    os.makedirs(_LAYOUT_DIR, exist_ok=True)
                with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._settings, f, ensure_ascii=False, indent=2)
            except Exception as exc:
                logger.debug("[StatisticsTab] _save_settings_file ?¤íŒ¨: %s", exc)

        # (?´í•˜ ë¡œì§ ë°?UI ?¬í¼???ë³¸ ?™ì‘??? ì? ???ëµ??ë¶€ë¶„ì? ?„ìš” ???ë³¸ ê·¸ë?ë¡?ë¶™ì—¬ ?ìš©?˜ì„¸??)
        # ì£¼ìš” ?™ì‘: _replace_table_widget_with_view, _on_section_resized, set_log_handler, _register_forwarding_handler,
        # _setup_auto_log_handler, _add_bootstrap_stream_handler, add_log_entry, _on_timer_flush, _collect_filters_for_tab,
        # _update_proxy_filters, UI ?¡ì…˜?? export/load history, _filter_log_item, _get_max_rows_for_tab, closeEvent ??
        #
        # ?„ì²´ ?ë³¸ ë¡œì§??ë³´ì¡´?˜ë ¤ë©????Œì¼???˜ë¨¸ì§€ ë©”ì„œ???¤ë¦¬ì§€??êµ¬í˜„)ë¥?ê·¸ë?ë¡??©ì³ ?¬ìš©?˜ì‹œë©??©ë‹ˆ??

else:
    class StatisticsTab:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PyQt5 not available; StatisticsTab (View) cannot be created in this environment.")
