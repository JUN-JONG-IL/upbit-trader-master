#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RedisSettingsDialog controller
- redis_settings.ui ???ïÏùò???ÑÏ†Ø?§Í≥º backend ?†Ìã∏(timescale_redis)???∞Í≤∞?©Îãà??
- ÎπÑÏ∞®???§Ìñâ???ÑÌï¥ QThreadPool + QRunnable ???¨Ïö©?©Îãà??
- UI?êÏÑú Pub/Sub, Queue, L1 Ï∫êÏãú ??Ï°∞Ìöå/Ï°∞Ïûë Î≤ÑÌäº???àÏ†Ñ?òÍ≤å Ï≤òÎ¶¨?©Îãà??
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import os
import traceback
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional

from PyQt5 import QtCore, QtWidgets, uic
import logging

logger = logging.getLogger(__name__)

# ---------------------------
# ?àÏ†Ñ Î°úÍπÖ ?òÌçº: logging ?∏Îì§???§Ìä∏Î¶ºÏù¥ ?´Ì????àÏô∏Í∞Ä ?ÑÌåå?òÏ? ?äÎèÑÎ°???
# ---------------------------
def _safe_log(func, *args, **kwargs):
    """
    ?àÏ†Ñ Î°úÍπÖ:
    - logger.handlers??stream ?çÏÑ±???´Ì? ?àÏúºÎ©?logger ?∏Ï∂ú???ºÌïòÍ≥?stderrÎ°?ÏßÅÏ†ë Ï∂úÎ†•?©Îãà??
    - Í∑∏Î†áÏßÄ ?äÏúºÎ©?logger ?∏Ï∂ú???úÎèÑ?òÎêò ?àÏô∏??Î¨¥Ïãú?©Îãà??
    """
    try:
        # Í≤Ä?? ?¥ÔøΩÔø??∏Îì§?¨Îùº???´Ìûå stream???àÎäîÏßÄ ?ïÏù∏
        try:
            handlers = getattr(logger, "handlers", []) or []
            stream_is_closed = False
            for h in handlers:
                # ?ºÎ? ?∏Îì§?¨Îäî stream ?Ä??'stream' ?çÏÑ±??Í∞ñÏ? ?äÏùÑ ???àÏùå
                stream = getattr(h, "stream", None)
                if stream is not None:
                    try:
                        if getattr(stream, "closed", False):
                            stream_is_closed = True
                            break
                    except Exception:
                        # ?àÏ†Ñ?òÍ≤å Î¨¥Ïãú
                        pass
        except Exception:
            handlers = []
            stream_is_closed = False

        if stream_is_closed:
            # ?∏Îì§???§Ìä∏Î¶ºÏù¥ ?´Ì??àÏúºÎ©?logging Î™®Îìà ?∏Ï∂ú???ºÌï®
            try:
                # ?¨Îß∑ ÎßûÏ∂∞ stderr???®Í?. args[0]???¨Îß∑ Î¨∏Ïûê?¥Ïùº Í≤ΩÏö∞ ?¨Îß∑ ?ÅÏö© ?úÎèÑ.
                if args:
                    try:
                        msg = args[0] % args[1:] if isinstance(args[0], str) else str(args)
                    except Exception:
                        msg = str(args)
                else:
                    msg = ""
                print(f"[{__name__}] LOG (fallback): {msg}", file=sys.stderr)
            except Exception:
                try:
                    print(f"[{__name__}] LOG (fallback) - args: {args}", file=sys.stderr)
                except Exception:
                    pass
            return

        # ?ïÏÉÅ Í≤ΩÎ°ú: logger ?∏Ï∂ú (Ï∂îÍ? ?àÏô∏ Î∞©Ï?)
        try:
            func(*args, **kwargs)
        except Exception:
            # logger ?∏Ï∂ú ?ÑÏ§ë Î¨∏Ï†úÍ∞Ä ?ùÍ∏∞Î©?stderrÎ°?ÏµúÏÜå Î©îÏãúÏßÄ Ï∂úÎ†•
            try:
                if args:
                    try:
                        msg = args[0] % args[1:] if isinstance(args[0], str) else str(args)
                    except Exception:
                        msg = str(args)
                else:
                    msg = ""
                print(f"[{__name__}] logging failed during emit: {msg}", file=sys.stderr)
            except Exception:
                pass
    except Exception:
        # ÏµúÌõÑ ?òÎã®: ?ÑÎ¨¥Í≤ÉÎèÑ Î™ªÌï®(Î¨¥Ïãú)
        try:
            print(f"[{__name__}] _safe_log unexpected failure", file=sys.stderr)
        except Exception:
            pass

def _debug(*a, **k):
    _safe_log(logger.debug, *a, **k)

def _info(*a, **k):
    _safe_log(logger.info, *a, **k)

def _warning(*a, **k):
    _safe_log(logger.warning, *a, **k)

def _exception(*a, **k):
    _safe_log(logger.exception, *a, **k)

# ---------------------------
# Robust loader for timescale_redis module
# ---------------------------
def _load_module_from_path(path: Path, mod_name: str) -> Optional[ModuleType]:
    """
    Load a module from a given file path using importlib, return module or None.
    """
    try:
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        # execute module
        spec.loader.exec_module(mod)  # type: ignore
        _debug("Loaded module %s from %s", mod_name, path)
        return mod
    except Exception:
        _debug("Failed to load module %s from %s", mod_name, path, exc_info=True)
        return None

def _find_timescale_redis() -> Optional[ModuleType]:
    """
    Try multiple strategies to obtain timescale_redis module:
    1) try common import names
    2) normal import (if PYTHONPATH is set)
    3) search for timescale_redis.py in likely repo locations relative to this file
    4) environment override via TIMESCALE_REDIS_PATH
    5) fallback: find any loaded module whose name endswith 'timescale_redis'
    Returns loaded module or None.
    """
    tried = []

    # 1) try a set of common import names
    candidates_import_names = [
        "timescale_redis",
        "src.data_01.timescale.timescale_redis",
        "src._data_01.timescale.timescale_redis",
        "src.data_01.timescale",
        "src._data_01.timescale",
    ]
    for name in candidates_import_names:
        try:
            mod = importlib.import_module(name)
            _debug("Imported timescale_redis via import name: %s", name)
            return mod
        except Exception:
            tried.append(f"import:{name}")

    # 2) search upward from current file location for common candidate paths
    here = Path(__file__).resolve()
    for base in here.parents:
        # candidate 1: <repo-root>/src/data_01/timescale/timescale_redis.py
        c1 = base / "src" / "data_01" / "timescale" / "timescale_redis.py"
        # candidate 2: <repo-root>/src/data_01/timescale_redis.py
        c2 = base / "src" / "data_01" / "timescale_redis.py"
        # candidate 3: <repo-root>/data_01/timescale/timescale_redis.py
        c3 = base / "data_01" / "timescale" / "timescale_redis.py"
        # candidate 4: <repo-root>/src/_data_01/timescale/timescale_redis.py
        c4 = base / "src" / "_data_01" / "timescale" / "timescale_redis.py"
        # candidate 5: near this UI file (src/data_01/redis/ui/ -> ../timescale/timescale_redis.py)
        try:
            c5 = here.parents[2] / "timescale" / "timescale_redis.py"
        except Exception:
            c5 = Path()

        for cand in (c1, c2, c3, c4, c5):
            tried.append(str(cand))
            if cand.exists():
                mod = _load_module_from_path(cand, "timescale_redis")
                if mod:
                    return mod

    # 3) environment override: allow explicit path via env var
    env = os.getenv("TIMESCALE_REDIS_PATH")
    if env:
        p = Path(env).expanduser().resolve()
        tried.append(str(p))
        if p.exists():
            mod = _load_module_from_path(p, "timescale_redis")
            if mod:
                return mod

    # 4) fallback: if a module is already loaded whose name endswith timescale_redis, use it
    for name, mod in list(sys.modules.items()):
        if name.endswith("timescale_redis"):
            _debug("Found timescale_redis in sys.modules: %s", name)
            return mod

    _debug("timescale_redis not found; tried: %s", tried)
    return None

# attempt to load raw module
_raw_tsr = _find_timescale_redis()

# ---------------------------
# Proxy wrapper: ?àÏ†Ñ???∏Ï∂ú(Î™®Îìà???ÜÍ±∞???®Ïàò ?ºÎ?Í∞Ä ?ÜÏùÑ ??Í∏∞Î≥∏Í∞?Î∞òÌôò)
# ---------------------------
class TimescaleRedisProxy:
    """
    timescale_redis Î™®Îìà???Ä???àÏ†Ñ???ÑÎ°ù??
    - Î™®Îìà???ÜÍ±∞???®ÏàòÍ∞Ä ?ÜÏúºÎ©??àÏô∏Î•??òÎ¶¨ÏßÄ ?äÍ≥† ?àÏ†Ñ??Í∏∞Î≥∏Í∞íÏùÑ Î∞òÌôò?©Îãà??
    - UI??proxy.get_client(), proxy.list_pubsub_channels() ?±ÏúºÎ°??∏Ï∂ú?òÎ©¥ ??
    """
    def __init__(self, module: Optional[ModuleType]):
        self._mod = module

    def _call(self, name: str, *args, default=None, **kwargs):
        if not self._mod:
            _debug("TimescaleRedisProxy: module missing, call %s -> default", name)
            return default
        fn = getattr(self._mod, name, None)
        if not callable(fn):
            _debug("TimescaleRedisProxy: function %s missing in module -> default", name)
            return default
        try:
            return fn(*args, **kwargs)
        except Exception:
            _exception("TimescaleRedisProxy: call to %s failed", name)
            return default

    def get_client(self, timeout: int = 5):
        return self._call("get_client", timeout)

    def close_client(self):
        return self._call("close_client")

    def publish_status(self, client, channel: str, message: Dict[str, Any]) -> bool:
        return bool(self._call("publish_status", client, channel, message, default=False))

    def list_pubsub_channels(self, client=None) -> List[str]:
        return self._call("list_pubsub_channels", client, default=[])

    def get_sortedset_top(self, client, zset: str, n: int = 100) -> List[tuple]:
        return self._call("get_sortedset_top", client, zset, n, default=[])

    def get_l1_expiring_keys(self, client, prefix: str = "l1:") -> List[tuple]:
        return self._call("get_l1_expiring_keys", client, prefix, default=[])

    def get_gap_queue_preview(self, queue: str = "gap_fill_queue", n: int = 200) -> List[str]:
        return self._call("get_gap_queue_preview", queue, n, default=[])

    def clear_queue(self, client, queue: str, backup: bool = True):
        return self._call("clear_queue", client, queue, backup, default={"result": "error", "error": "no_module"})

    def clear_keys_by_prefix(self, client, prefix: str, limit: int = 1000, dry_run: bool = True):
        return self._call("clear_keys_by_prefix", client, prefix, limit, dry_run, default={"keys_checked": 0, "to_delete": 0, "deleted": 0, "sample": []})

    def get_status(self, timeout: int = 2) -> Dict[str, Any]:
        return self._call("get_status", timeout=timeout, default={"client": False, "ping": False, "info": {}, "error": "no_module"})

# create proxy instance (UI uses 'tsr' variable)
tsr = TimescaleRedisProxy(_raw_tsr)

# ---------------------------
# Worker helper (QRunnable)
# ---------------------------
class WorkerSignals(QtCore.QObject):
    finished = QtCore.pyqtSignal(object)  # emits (exc, result)
    progress = QtCore.pyqtSignal(object)  # optional

class TaskRunnable(QtCore.QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @QtCore.pyqtSlot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit((None, result))
        except Exception as exc:
            tb = traceback.format_exc()
            self.signals.finished.emit((exc, tb))

# ---------------------------
# Dialog controller
# ---------------------------
# ??†ú Í∏∞Îä• ÎØπÏä§??Î°úÎìú (?åÏùº Í≤ΩÎ°ú Í∏∞Î∞ò)
def _load_redis_delete_mixin():
    """RedisDeleteMixin ???åÏùº Í≤ΩÎ°úÎ°?Î°úÎìú?©Îãà?? ?§Ìå® ??Îπ??¥Îûò??Î∞òÌôò."""
    try:
        _p = Path(__file__).parent / "redis_delete_operations.py"
        if _p.exists():
            _m = _load_module_from_path(_p, "redis_delete_operations")
            if _m:
                return getattr(_m, "RedisDeleteMixin", None)
    except Exception:
        pass
    return None

_RedisDeleteMixin = _load_redis_delete_mixin()
if _RedisDeleteMixin is None:
    class _RedisDeleteMixin:  # type: ignore[no-redef]
        """RedisDeleteMixin Î°úÎìú ?§Ìå® ???¨Ïö©?òÎäî Îπ?ÎØπÏä§??""
        def _bind_redis_delete_signals(self): pass
        def _refresh_redis_key_count(self): pass


class RedisSettingsDialog(QtWidgets.QDialog, _RedisDeleteMixin):
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent / "redis_settings.ui"
        if not ui_path.exists():
            raise FileNotFoundError(f"UI ?åÏùº??Ï∞æÏùÑ ???ÜÏäµ?àÎã§: {ui_path}")
        uic.loadUi(str(ui_path), self)

        # thread pool
        self.threadpool = QtCore.QThreadPool.globalInstance()

        # connect buttons -> handlers
        # ?ÅÌÉú
        if hasattr(self, "btnRefreshStatus"):
            self.btnRefreshStatus.clicked.connect(self.on_refresh_status)
        # Pub/Sub
        if hasattr(self, "btnRefreshPubSub"):
            # Î≤ÑÌäº??Ï°¥Ïû¨?òÎ©¥ ?àÏ†Ñ?òÍ≤å ?∞Í≤∞ (Î©îÏÑú?úÍ? ?¥Îûò?§Ïóê Î∞òÎìú???àÏñ¥????
            try:
                self.btnRefreshPubSub.clicked.connect(self.on_refresh_pubsub)
            except Exception:
                # ?àÏô∏ Î∞úÏÉù ??Î°úÍ∑∏Îß??®Í∏∞Í≥?ÏßÑÌñâ
                _warning("Failed to connect btnRefreshPubSub to on_refresh_pubsub")
        # Gap queue
        if hasattr(self, "btnRefreshQueue"):
            self.btnRefreshQueue.clicked.connect(self.on_refresh_queue)
        if hasattr(self, "btnClearQueue"):
            self.btnClearQueue.clicked.connect(self.on_clear_queue)
        # L1 cache
        if hasattr(self, "btnRefreshL1Cache"):
            self.btnRefreshL1Cache.clicked.connect(self.on_refresh_l1cache)
        if hasattr(self, "btnClearCache"):
            self.btnClearCache.clicked.connect(self.on_clear_cache)
        # Cluster / Sentinel
        if hasattr(self, "btnRefreshCluster"):
            self.btnRefreshCluster.clicked.connect(self.on_refresh_cluster)
        if hasattr(self, "btnRefreshSentinel"):
            self.btnRefreshSentinel.clicked.connect(self.on_refresh_sentinel)
        # ????Î≤ÑÌäº ?∞Í≤∞
        if hasattr(self, "btnSearch"):
            self.btnSearch.clicked.connect(self.on_search_data)
        if hasattr(self, "btnPrevPage"):
            self.btnPrevPage.clicked.connect(self.on_prev_page)
        if hasattr(self, "btnNextPage"):
            self.btnNextPage.clicked.connect(self.on_next_page)
        if hasattr(self, "btnExportCSV"):
            self.btnExportCSV.clicked.connect(self.on_export_csv)

        # ??†ú ??Î≤ÑÌäº Î∞îÏù∏??(RedisDeleteMixin)
        self._bind_redis_delete_signals()
        self._refresh_redis_key_count()

        # initialize UI placeholders
        try:
            if hasattr(self, "labelRedisEndpoint"):
                self.labelRedisEndpoint.setText("-")
            if hasattr(self, "labelRedisVersion"):
                self.labelRedisVersion.setText("-")
            if hasattr(self, "labelLastUpdated"):
                self.labelLastUpdated.setText("ÎßàÏ?Îß?Í∞±Ïã†: -")
        except Exception:
            pass

        # ÎπÑÎ™®???ùÏóÖ ?§Ï†ï
        self.setWindowModality(QtCore.Qt.NonModal)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)

        # ?òÏù¥ÏßÄ?§Ïù¥???ÅÌÉú
        self._current_page: int = 1
        self._total_pages: int = 1

        # ?§ÏãúÍ∞?Í∞±Ïã† ?Ä?¥Î®∏ (1Ï¥?
        self._realtime_timer = QtCore.QTimer(self)
        self._realtime_timer.setInterval(1000)
        self._realtime_timer.timeout.connect(self.on_refresh_realtime)
        self._realtime_timer.start()

        # PyQtGraph Ï∞®Ìä∏ Ï¥àÍ∏∞??
        try:
            import pyqtgraph as pg
            if hasattr(self, "chartContainer"):
                if self.chartContainer.layout() is None:
                    from PyQt5.QtWidgets import QVBoxLayout as _QVL
                    self.chartContainer.setLayout(_QVL())
                self._chart_widget = pg.PlotWidget()
                self.chartContainer.layout().addWidget(self._chart_widget)
                self._chart_widget.setBackground("k")
                self._chart_widget.setLabel("left", "QPS")
                self._chart_widget.setLabel("bottom", "?úÍ∞Ñ (Ï¥?")
        except ImportError:
            pass

        # Ï∞??ÑÏπò Î≥µÏõê
        try:
            from PyQt5.QtCore import QSettings
            _settings = QSettings("UpbitTrader", "DBMonitor")
            _geometry = _settings.value("redis_geometry")
            if _geometry:
                self.restoreGeometry(_geometry)
        except Exception:
            pass

        # ?§ÌÅ¨ Î™®Îìú ?§Ì???
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #ffffff; }
            QTableWidget { background-color: #1e1e1e; gridline-color: #444; color: #ffffff; }
            QTableWidget QHeaderView::section { background-color: #3c3c3c; color: #ffffff; }
            QPushButton { background-color: #0078d4; color: white; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #1084d8; }
            QGroupBox { color: #ffffff; border: 1px solid #555; margin-top: 6px; }
            QGroupBox::title { color: #aaaaaa; }
            QLabel { color: #ffffff; }
            QComboBox { background-color: #3c3c3c; color: #ffffff; }
            QLineEdit { background-color: #3c3c3c; color: #ffffff; }
            QTabWidget::pane { border: 1px solid #555; }
            QTabBar::tab { background-color: #3c3c3c; color: #ffffff; padding: 6px 12px; }
            QTabBar::tab:selected { background-color: #0078d4; }
        """)

    # -----------------------
    # Helper to run in thread
    # -----------------------
    def _run_task(self, fn, on_done=None):
        task = TaskRunnable(fn)
        if on_done:
            task.signals.finished.connect(on_done)
        self.threadpool.start(task)

    # -----------------------
    # Status
    # -----------------------
    def on_refresh_status(self):
        # tsr??TimescaleRedisProxy ?∏Ïä§?¥Ïä§???àÏ†Ñ ?∏Ï∂ú Î≥¥Ïû•)
        def _task():
            client = tsr.get_client()
            if client is None:
                return {"connected": False}
            try:
                if hasattr(tsr, "get_status"):
                    try:
                        s = tsr.get_status()
                        return {"connected": s.get("client", False), "info": s.get("info", {}), "endpoint": "-"}
                    except Exception:
                        pass
                try:
                    client.ping()
                except Exception:
                    pass
                info = {}
                try:
                    info = client.info()
                except Exception:
                    info = {}
                endpoint = "-"
                try:
                    endpoint_pool = getattr(client, "connection_pool", None)
                    if endpoint_pool:
                        kwargs = getattr(endpoint_pool, "connection_kwargs", {}) or {}
                        host = kwargs.get("host")
                        port = kwargs.get("port")
                        if host:
                            endpoint = f"{host}:{port or ''}"
                except Exception:
                    endpoint = "-"
                return {"connected": True, "info": info, "endpoint": endpoint}
            except Exception as exc:
                return {"connected": False, "error": str(exc)}

        def _done(res_tuple):
            exc, result = res_tuple
            if exc:
                QtWidgets.QMessageBox.warning(self, "?ÅÌÉú Ï°∞Ìöå ?§Ìå®", str(exc))
                return
            data = result
            if not data or not data.get("connected"):
                if hasattr(self, "labelStatusText"):
                    self.labelStatusText.setText("?∞Í≤∞ ?§Ìå®")
                if hasattr(self, "labelStatusDot"):
                    self.labelStatusDot.setStyleSheet("color: #AA0000; font-size: 20px;")
                return
            info = data.get("info", {})
            endpoint = data.get("endpoint", "-")
            ver = info.get("redis_version") or info.get("server_version") or "-"
            if hasattr(self, "labelRedisEndpoint"):
                self.labelRedisEndpoint.setText(endpoint)
            if hasattr(self, "labelRedisVersion"):
                self.labelRedisVersion.setText(str(ver))
            if hasattr(self, "labelLastUpdated"):
                from datetime import datetime
                self.labelLastUpdated.setText(f"ÎßàÏ?Îß?Í∞±Ïã†: {datetime.utcnow().isoformat()}Z")
            if hasattr(self, "labelStatusText"):
                self.labelStatusText.setText("?∞Í≤∞??)
            if hasattr(self, "labelStatusDot"):
                self.labelStatusDot.setStyleSheet("color: #00AA00; font-size: 20px;")

        self._run_task(_task, on_done=_done)

    # -----------------------
    # Pub/Sub
    # -----------------------
    def on_refresh_pubsub(self):
        """
        Pub/Sub ??ùÑ Í∞±Ïã†?©Îãà??
        - tsr.list_pubsub_channels() Í≤∞Í≥ºÎ•??¨Ïö©???åÏù¥Î∏îÏùÑ Ï±ÑÏõÅ?àÎã§.
        - clientÍ∞Ä ?ÜÍ±∞??Î™®Îìà???ÜÏùÑ Í≤ΩÏö∞ ?àÏ†Ñ?òÍ≤å Îπ?Î¶¨Ïä§?∏Î? ?¨Ïö©?©Îãà??
        """
        def _task():
            client = tsr.get_client()
            channels = tsr.list_pubsub_channels(client)
            # channels??list[str] ?àÏÉÅ
            result = []
            try:
                if channels:
                    # ?úÎèÑ: pubsub_numsubÎ°?Íµ¨ÎèÖ????Ï°∞Ìöå (?àÏúºÎ©?, ?§Ìå®?òÎ©¥ -1Î°??úÏãú
                    try:
                        if client and hasattr(client, "pubsub_numsub"):
                            raw = client.pubsub_numsub(*channels)
                            if isinstance(raw, dict):
                                for ch, cnt in raw.items():
                                    result.append((str(ch), int(cnt)))
                            else:
                                for item in raw:
                                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                                        result.append((str(item[0]), int(item[1])))
                        else:
                            result = [(ch, -1) for ch in channels]
                    except Exception:
                        # ?§Ìå®??Í∞?Ï±ÑÎÑê??-1
                        for ch in channels:
                            result.append((ch, -1))
                else:
                    result = []
            except Exception:
                result = []
            return result

        def _done(res_tuple):
            exc, rows = res_tuple
            if exc:
                QtWidgets.QMessageBox.warning(self, "Pub/Sub Ï°∞Ìöå ?§Ìå®", str(exc))
                return
            rows = rows or []
            tbl = getattr(self, "tablePubSub", None)
            if tbl is None:
                # ?åÏù¥Î∏??ÑÏ†Ø???ÜÏúºÎ©?Í∞ÑÎã®??Î©îÏãúÏßÄ Î∞ïÏä§Î°??ïÎ≥¥ ?úÏãú
                QtWidgets.QMessageBox.information(self, "Pub/Sub", f"Ï±ÑÎÑê ?? {len(rows)}")
                return
            tbl.setRowCount(0)
            for i, (ch, cnt) in enumerate(rows):
                tbl.insertRow(i)
                tbl.setItem(i, 0, QtWidgets.QTableWidgetItem(str(ch)))
                tbl.setItem(i, 1, QtWidgets.QTableWidgetItem(str(cnt)))
            if hasattr(self, "labelPubSubSummary"):
                self.labelPubSubSummary.setText(f"Ï¥?{len(rows)}Í∞?Ï±ÑÎÑê")

        self._run_task(_task, on_done=_done)

    # -----------------------
    # Gap queue
    # -----------------------
    def on_refresh_queue(self):
        def _task():
            client = tsr.get_client()
            items = tsr.get_sortedset_top(client, "gap_fill_queue", n=500)
            out = []
            try:
                for it in items:
                    if isinstance(it, (list, tuple)) and len(it) >= 2:
                        out.append((str(it[0]), it[1]))
                    else:
                        out.append((str(it), -1))
            except Exception:
                try:
                    raw = client.lrange("gap_fill_queue", 0, 499) if client else []
                    out = [(str(r), -1) for r in raw]
                except Exception:
                    out = []
            return out

        def _done(res_tuple):
            exc, rows = res_tuple
            if exc:
                QtWidgets.QMessageBox.warning(self, "??Ï°∞Ìöå ?§Ìå®", str(exc))
                return
            tbl = getattr(self, "tableGapQueue", None)
            if tbl is None:
                return
            tbl.setRowCount(0)
            for i, item in enumerate(rows):
                symbol = str(item[0])
                priority = str(item[1])
                tbl.insertRow(i)
                tbl.setItem(i, 0, QtWidgets.QTableWidgetItem(symbol))
                tbl.setItem(i, 1, QtWidgets.QTableWidgetItem(priority))
                tbl.setItem(i, 2, QtWidgets.QTableWidgetItem("-"))
            if hasattr(self, "labelQueueLength"):
                self.labelQueueLength.setText(f"??Í∏∏Ïù¥: {len(rows)}Í∞?)

        self._run_task(_task, on_done=_done)

    def on_clear_queue(self):
        reply = QtWidgets.QMessageBox.question(self, "??ÎπÑÏö∞Í∏?, "?ïÎßêÎ°?gap_fill_queueÎ•?ÎπÑÏö∞?úÍ≤†?µÎãàÍπ? (Î≥µÍµ¨ Î∂àÍ?)", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return

        def _task():
            client = tsr.get_client()
            if not client:
                raise RuntimeError("Redis client ?ÜÏùå")
            import time
            backup = f"gap_fill_queue:backup:{int(time.time())}"
            try:
                # try rename if exists
                try:
                    if client.exists("gap_fill_queue"):
                        client.rename("gap_fill_queue", backup)
                        return {"backup": backup}
                except Exception:
                    # rename may fail if keys absent or cross-slot; fallback to copy/delete
                    items = client.lrange("gap_fill_queue", 0, -1)
                    if items:
                        client.rpush(backup, *items)
                    client.delete("gap_fill_queue")
                    return {"backup": backup if items else None}
                return {"backup": None}
            except Exception:
                # ensure no raising out of worker
                return {"backup": None}

        def _done(res_tuple):
            exc, res = res_tuple
            if exc:
                QtWidgets.QMessageBox.warning(self, "??ÎπÑÏö∞Í∏??§Ìå®", str(exc))
                return
            backup = res.get("backup")
            if backup:
                QtWidgets.QMessageBox.information(self, "?ÑÎ£å", f"?êÎ? Î∞±ÏóÖ({backup})????ÎπÑÏõ†?µÎãà??")
            else:
                QtWidgets.QMessageBox.information(self, "?ÑÎ£å", "?êÎ? ??†ú?àÏäµ?àÎã§.")
            self.on_refresh_queue()

        self._run_task(_task, on_done=_done)

    # -----------------------
    # L1 Ï∫êÏãú
    # -----------------------
    def on_refresh_l1cache(self):
        def _task():
            client = tsr.get_client()
            items = tsr.get_l1_expiring_keys(client, prefix="l1:")
            return items or []

        def _done(res_tuple):
            exc, rows = res_tuple
            if exc:
                QtWidgets.QMessageBox.warning(self, "L1 Ï°∞Ìöå ?§Ìå®", str(exc))
                return
            tbl = getattr(self, "tableExpiringKeys", None)
            if tbl is None:
                return
            tbl.setRowCount(0)
            for i, (key, ttl) in enumerate(rows):
                tbl.insertRow(i)
                tbl.setItem(i, 0, QtWidgets.QTableWidgetItem(str(key)))
                tbl.setItem(i, 1, QtWidgets.QTableWidgetItem(str(ttl)))

        self._run_task(_task, on_done=_done)

    def on_clear_cache(self):
        reply = QtWidgets.QMessageBox.question(self, "Ï∫êÏãú ?¥Î¶¨??, "Î≤îÏúÑ(l1:*)Î•???†ú?òÏãúÍ≤†Ïäµ?àÍπå? (Í∂åÌïú ?ÑÏöî)", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return

        def _task():
            client = tsr.get_client()
            if not client:
                raise RuntimeError("Redis client ?ÜÏùå")
            count = 0
            try:
                for k in client.scan_iter(match="l1:*", count=200):
                    try:
                        client.unlink(k)
                        count += 1
                    except Exception:
                        try:
                            client.delete(k)
                            count += 1
                        except Exception:
                            pass
            except Exception:
                # ensure worker returns gracefully
                pass
            return {"deleted": count}

        def _done(res_tuple):
            exc, res = res_tuple
            if exc:
                QtWidgets.QMessageBox.warning(self, "Ï∫êÏãú ??†ú ?§Ìå®", str(exc))
                return
            cnt = res.get("deleted", 0)
            QtWidgets.QMessageBox.information(self, "?ÑÎ£å", f"??†ú?????? {cnt}")
            self.on_refresh_l1cache()

        self._run_task(_task, on_done=_done)

    # -----------------------
    # Cluster / Sentinel (Í∞ÑÎã® placeholder)
    # -----------------------
    def on_refresh_cluster(self):
        def _task():
            client = tsr.get_client()
            if not client:
                return {"error": "No client"}
            try:
                nodes = client.execute_command("CLUSTER", "NODES")
                return {"nodes": str(nodes)}
            except Exception as exc:
                return {"error": str(exc)}

        def _done(res_tuple):
            exc, res = res_tuple
            if exc:
                QtWidgets.QMessageBox.warning(self, "?¥Îü¨?§ÌÑ∞ Ï°∞Ìöå ?§Ìå®", str(exc))
                return
            if res.get("error"):
                if hasattr(self, "labelClusterStatus"):
                    self.labelClusterStatus.setText(f"?¥Îü¨?§ÌÑ∞ ?∏Ï∂ú ?§Ìå®: {res.get('error')}")
                return
            if hasattr(self, "labelClusterStatus"):
                self.labelClusterStatus.setText("?¥Îü¨?§ÌÑ∞ ?ïÎ≥¥ ?òÏã†")

        self._run_task(_task, on_done=_done)

    def on_refresh_sentinel(self):
        def _task():
            client = tsr.get_client()
            if not client:
                return {"error": "No client"}
            try:
                masters = client.execute_command("SENTINEL", "masters")
                return {"masters": str(masters)}
            except Exception as exc:
                return {"error": str(exc)}

        def _done(res_tuple):
            exc, res = res_tuple
            if exc:
                QtWidgets.QMessageBox.warning(self, "Sentinel Ï°∞Ìöå ?§Ìå®", str(exc))
                return
            if res.get("error"):
                if hasattr(self, "labelSentinelsTitle"):
                    self.labelSentinelsTitle.setText(f"Sentinel ?∏Ï∂ú ?§Ìå®: {res.get('error')}")
                return
            if hasattr(self, "labelSentinelsTitle"):
                self.labelSentinelsTitle.setText("Sentinel ?ïÎ≥¥ ?òÏã†")

        self._run_task(_task, on_done=_done)

    # -----------------------
    # ?§ÏãúÍ∞??µÏã† Î™®Îãà??
    # -----------------------
    def on_refresh_realtime(self) -> None:
        """?§ÏãúÍ∞??µÏã† Î°úÍ∑∏ Í∞±Ïã† (1Ï¥àÎßà???∏Ï∂ú)."""
        try:
            if not hasattr(self, "tableRealtimeQueries"):
                return
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            row = self.tableRealtimeQueries.rowCount()
            if row >= 100:
                self.tableRealtimeQueries.removeRow(0)
                row = self.tableRealtimeQueries.rowCount()
            self.tableRealtimeQueries.insertRow(row)
            self.tableRealtimeQueries.setItem(row, 0, QtWidgets.QTableWidgetItem(ts))
            self.tableRealtimeQueries.setItem(row, 1, QtWidgets.QTableWidgetItem("heartbeat"))
            self.tableRealtimeQueries.setItem(row, 2, QtWidgets.QTableWidgetItem("-"))
            self.tableRealtimeQueries.setItem(row, 3, QtWidgets.QTableWidgetItem("-"))
            self.tableRealtimeQueries.setItem(row, 4, QtWidgets.QTableWidgetItem("OK"))
            self.tableRealtimeQueries.scrollToBottom()
        except Exception:
            pass

    # -----------------------
    # ?Ä???∞Ïù¥??Í≤Ä??
    # -----------------------
    def on_search_data(self) -> None:
        """?Ä?•Îêú ?∞Ïù¥??Í≤Ä??"""
        try:
            table_name = self.comboTable.currentText().strip() if hasattr(self, "comboTable") else ""
            keyword = self.lineFilter.text().strip() if hasattr(self, "lineFilter") else ""
            logger.debug("[RedisSettingsDialog] Í≤Ä?? table=%s keyword=%s", table_name, keyword)
        except Exception:
            pass

    def on_prev_page(self) -> None:
        """?¥Ï†Ñ ?òÏù¥ÏßÄÎ°??¥Îèô."""
        try:
            if self._current_page > 1:
                self._current_page -= 1
                if hasattr(self, "labelPage"):
                    self.labelPage.setText(f"?òÏù¥ÏßÄ: {self._current_page} / {self._total_pages}")
        except Exception:
            pass

    def on_next_page(self) -> None:
        """?§Ïùå ?òÏù¥ÏßÄÎ°??¥Îèô."""
        try:
            if self._current_page < self._total_pages:
                self._current_page += 1
                if hasattr(self, "labelPage"):
                    self.labelPage.setText(f"?òÏù¥ÏßÄ: {self._current_page} / {self._total_pages}")
        except Exception:
            pass

    def on_export_csv(self) -> None:
        """?Ä?•Îêú ?∞Ïù¥??CSV ?¥Î≥¥?¥Í∏∞."""
        try:
            if not hasattr(self, "tableData"):
                return
            import csv
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, "CSV ?Ä??, "", "CSV Files (*.csv)")
            if not filename:
                return
            with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = []
                for col in range(self.tableData.columnCount()):
                    item = self.tableData.horizontalHeaderItem(col)
                    headers.append(item.text() if item else str(col))
                writer.writerow(headers)
                for row in range(self.tableData.rowCount()):
                    row_data = []
                    for col in range(self.tableData.columnCount()):
                        item = self.tableData.item(row, col)
                        row_data.append(item.text() if item else "")
                    writer.writerow(row_data)
            QtWidgets.QMessageBox.information(self, "CSV ?Ä??, f"?Ä???ÑÎ£å: {filename}")
        except Exception as e:
            logger.debug("[RedisSettingsDialog] CSV ?¥Î≥¥?¥Í∏∞ ?àÏô∏: %s", e, exc_info=True)
            QtWidgets.QMessageBox.warning(self, "?§Î•ò", f"CSV ?Ä???§Ìå®: {e}")

    def closeEvent(self, event) -> None:
        try:
            from PyQt5.QtCore import QSettings
            _settings = QSettings("UpbitTrader", "DBMonitor")
            _settings.setValue("redis_geometry", self.saveGeometry())
        except Exception:
            pass
        try:
            if getattr(self, "_realtime_timer", None) and self._realtime_timer.isActive():
                self._realtime_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)


# quick manual run (for local testing)
# ---------------------------
def _run_standalone():
    app = QtWidgets.QApplication(sys.argv)
    dlg = RedisSettingsDialog()
    dlg.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    _run_standalone()
