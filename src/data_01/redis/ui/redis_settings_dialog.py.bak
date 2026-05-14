#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RedisSettingsDialog controller
- redis_settings.ui 에 정의된 위젯들과 backend 유틸(timescale_redis)을 연결합니다.
- 비차단 실행을 위해 QThreadPool + QRunnable 을 사용합니다.
- UI에서 Pub/Sub, Queue, L1 캐시 등 조회/조작 버튼을 안전하게 처리합니다.
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
# 안전 로깅 래퍼: logging 핸들러/스트림이 닫혀도 예외가 전파되지 않도록 함
# ---------------------------
def _safe_log(func, *args, **kwargs):
    """
    안전 로깅:
    - logger.handlers의 stream 속성이 닫혀 있으면 logger 호출을 피하고 stderr로 직접 출력합니다.
    - 그렇지 않으면 logger 호출을 시도하되 예외는 무시합니다.
    """
    try:
        # 검사: 어�� 핸들러라도 닫힌 stream이 있는지 확인
        try:
            handlers = getattr(logger, "handlers", []) or []
            stream_is_closed = False
            for h in handlers:
                # 일부 핸들러는 stream 대신 'stream' 속성을 갖지 않을 수 있음
                stream = getattr(h, "stream", None)
                if stream is not None:
                    try:
                        if getattr(stream, "closed", False):
                            stream_is_closed = True
                            break
                    except Exception:
                        # 안전하게 무시
                        pass
        except Exception:
            handlers = []
            stream_is_closed = False

        if stream_is_closed:
            # 핸들러 스트림이 닫혀있으면 logging 모듈 호출을 피함
            try:
                # 포맷 맞춰 stderr에 남김. args[0]이 포맷 문자열일 경우 포맷 적용 시도.
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

        # 정상 경로: logger 호출 (추가 예외 방지)
        try:
            func(*args, **kwargs)
        except Exception:
            # logger 호출 도중 문제가 생기면 stderr로 최소 메시지 출력
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
        # 최후 수단: 아무것도 못함(무시)
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
        "src.02_data.timescale.timescale_redis",
        "src._02_data.timescale.timescale_redis",
        "src.02_data.timescale",
        "src._02_data.timescale",
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
        # candidate 1: <repo-root>/src/02_data/timescale/timescale_redis.py
        c1 = base / "src" / "02_data" / "timescale" / "timescale_redis.py"
        # candidate 2: <repo-root>/src/02_data/timescale_redis.py
        c2 = base / "src" / "02_data" / "timescale_redis.py"
        # candidate 3: <repo-root>/02_data/timescale/timescale_redis.py
        c3 = base / "02_data" / "timescale" / "timescale_redis.py"
        # candidate 4: <repo-root>/src/_02_data/timescale/timescale_redis.py
        c4 = base / "src" / "_02_data" / "timescale" / "timescale_redis.py"
        # candidate 5: near this UI file (src/02_data/redis/ui/ -> ../timescale/timescale_redis.py)
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
# Proxy wrapper: 안전한 호출(모듈이 없거나 함수 일부가 없을 때 기본값 반환)
# ---------------------------
class TimescaleRedisProxy:
    """
    timescale_redis 모듈에 대한 안전한 프록시:
    - 모듈이 없거나 함수가 없으면 예외를 흘리지 않고 안전한 기본값을 반환합니다.
    - UI는 proxy.get_client(), proxy.list_pubsub_channels() 등으로 호출하면 됨.
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
# 삭제 기능 믹스인 로드 (파일 경로 기반)
def _load_redis_delete_mixin():
    """RedisDeleteMixin 을 파일 경로로 로드합니다. 실패 시 빈 클래스 반환."""
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
        """RedisDeleteMixin 로드 실패 시 사용하는 빈 믹스인"""
        def _bind_redis_delete_signals(self): pass
        def _refresh_redis_key_count(self): pass


class RedisSettingsDialog(QtWidgets.QDialog, _RedisDeleteMixin):
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent / "redis_settings.ui"
        if not ui_path.exists():
            raise FileNotFoundError(f"UI 파일을 찾을 수 없습니다: {ui_path}")
        uic.loadUi(str(ui_path), self)

        # thread pool
        self.threadpool = QtCore.QThreadPool.globalInstance()

        # connect buttons -> handlers
        # 상태
        if hasattr(self, "btnRefreshStatus"):
            self.btnRefreshStatus.clicked.connect(self.on_refresh_status)
        # Pub/Sub
        if hasattr(self, "btnRefreshPubSub"):
            # 버튼이 존재하면 안전하게 연결 (메서드가 클래스에 반드시 있어야 함)
            try:
                self.btnRefreshPubSub.clicked.connect(self.on_refresh_pubsub)
            except Exception:
                # 예외 발생 시 로그만 남기고 진행
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
        # 새 탭 버튼 연결
        if hasattr(self, "btnSearch"):
            self.btnSearch.clicked.connect(self.on_search_data)
        if hasattr(self, "btnPrevPage"):
            self.btnPrevPage.clicked.connect(self.on_prev_page)
        if hasattr(self, "btnNextPage"):
            self.btnNextPage.clicked.connect(self.on_next_page)
        if hasattr(self, "btnExportCSV"):
            self.btnExportCSV.clicked.connect(self.on_export_csv)

        # 삭제 탭 버튼 바인딩 (RedisDeleteMixin)
        self._bind_redis_delete_signals()
        self._refresh_redis_key_count()

        # initialize UI placeholders
        try:
            if hasattr(self, "labelRedisEndpoint"):
                self.labelRedisEndpoint.setText("-")
            if hasattr(self, "labelRedisVersion"):
                self.labelRedisVersion.setText("-")
            if hasattr(self, "labelLastUpdated"):
                self.labelLastUpdated.setText("마지막 갱신: -")
        except Exception:
            pass

        # 비모달 팝업 설정
        self.setWindowModality(QtCore.Qt.NonModal)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)

        # 페이지네이션 상태
        self._current_page: int = 1
        self._total_pages: int = 1

        # 실시간 갱신 타이머 (1초)
        self._realtime_timer = QtCore.QTimer(self)
        self._realtime_timer.setInterval(1000)
        self._realtime_timer.timeout.connect(self.on_refresh_realtime)
        self._realtime_timer.start()

        # PyQtGraph 차트 초기화
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
                self._chart_widget.setLabel("bottom", "시간 (초)")
        except ImportError:
            pass

        # 창 위치 복원
        try:
            from PyQt5.QtCore import QSettings
            _settings = QSettings("UpbitTrader", "DBMonitor")
            _geometry = _settings.value("redis_geometry")
            if _geometry:
                self.restoreGeometry(_geometry)
        except Exception:
            pass

        # 다크 모드 스타일
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
        # tsr는 TimescaleRedisProxy 인스턴스임(안전 호출 보장)
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
                QtWidgets.QMessageBox.warning(self, "상태 조회 실패", str(exc))
                return
            data = result
            if not data or not data.get("connected"):
                if hasattr(self, "labelStatusText"):
                    self.labelStatusText.setText("연결 실패")
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
                self.labelLastUpdated.setText(f"마지막 갱신: {datetime.utcnow().isoformat()}Z")
            if hasattr(self, "labelStatusText"):
                self.labelStatusText.setText("연결됨")
            if hasattr(self, "labelStatusDot"):
                self.labelStatusDot.setStyleSheet("color: #00AA00; font-size: 20px;")

        self._run_task(_task, on_done=_done)

    # -----------------------
    # Pub/Sub
    # -----------------------
    def on_refresh_pubsub(self):
        """
        Pub/Sub 탭을 갱신합니다.
        - tsr.list_pubsub_channels() 결과를 사용해 테이블을 채웁니다.
        - client가 없거나 모듈이 없을 경우 안전하게 빈 리스트를 사용합니다.
        """
        def _task():
            client = tsr.get_client()
            channels = tsr.list_pubsub_channels(client)
            # channels는 list[str] 예상
            result = []
            try:
                if channels:
                    # 시도: pubsub_numsub로 구독자 수 조회 (있으면), 실패하면 -1로 표시
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
                        # 실패시 각 채널에 -1
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
                QtWidgets.QMessageBox.warning(self, "Pub/Sub 조회 실패", str(exc))
                return
            rows = rows or []
            tbl = getattr(self, "tablePubSub", None)
            if tbl is None:
                # 테이블 위젯이 없으면 간단히 메시지 박스로 정보 표시
                QtWidgets.QMessageBox.information(self, "Pub/Sub", f"채널 수: {len(rows)}")
                return
            tbl.setRowCount(0)
            for i, (ch, cnt) in enumerate(rows):
                tbl.insertRow(i)
                tbl.setItem(i, 0, QtWidgets.QTableWidgetItem(str(ch)))
                tbl.setItem(i, 1, QtWidgets.QTableWidgetItem(str(cnt)))
            if hasattr(self, "labelPubSubSummary"):
                self.labelPubSubSummary.setText(f"총 {len(rows)}개 채널")

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
                QtWidgets.QMessageBox.warning(self, "큐 조회 실패", str(exc))
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
                self.labelQueueLength.setText(f"큐 길이: {len(rows)}개")

        self._run_task(_task, on_done=_done)

    def on_clear_queue(self):
        reply = QtWidgets.QMessageBox.question(self, "큐 비우기", "정말로 gap_fill_queue를 비우시겠습니까? (복구 불가)", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return

        def _task():
            client = tsr.get_client()
            if not client:
                raise RuntimeError("Redis client 없음")
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
                QtWidgets.QMessageBox.warning(self, "큐 비우기 실패", str(exc))
                return
            backup = res.get("backup")
            if backup:
                QtWidgets.QMessageBox.information(self, "완료", f"큐를 백업({backup})한 뒤 비웠습니다.")
            else:
                QtWidgets.QMessageBox.information(self, "완료", "큐를 삭제했습니다.")
            self.on_refresh_queue()

        self._run_task(_task, on_done=_done)

    # -----------------------
    # L1 캐시
    # -----------------------
    def on_refresh_l1cache(self):
        def _task():
            client = tsr.get_client()
            items = tsr.get_l1_expiring_keys(client, prefix="l1:")
            return items or []

        def _done(res_tuple):
            exc, rows = res_tuple
            if exc:
                QtWidgets.QMessageBox.warning(self, "L1 조회 실패", str(exc))
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
        reply = QtWidgets.QMessageBox.question(self, "캐시 클리어", "범위(l1:*)를 삭제하시겠습니까? (권한 필요)", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return

        def _task():
            client = tsr.get_client()
            if not client:
                raise RuntimeError("Redis client 없음")
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
                QtWidgets.QMessageBox.warning(self, "캐시 삭제 실패", str(exc))
                return
            cnt = res.get("deleted", 0)
            QtWidgets.QMessageBox.information(self, "완료", f"삭제된 키 수: {cnt}")
            self.on_refresh_l1cache()

        self._run_task(_task, on_done=_done)

    # -----------------------
    # Cluster / Sentinel (간단 placeholder)
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
                QtWidgets.QMessageBox.warning(self, "클러스터 조회 실패", str(exc))
                return
            if res.get("error"):
                if hasattr(self, "labelClusterStatus"):
                    self.labelClusterStatus.setText(f"클러스터 호출 실패: {res.get('error')}")
                return
            if hasattr(self, "labelClusterStatus"):
                self.labelClusterStatus.setText("클러스터 정보 수신")

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
                QtWidgets.QMessageBox.warning(self, "Sentinel 조회 실패", str(exc))
                return
            if res.get("error"):
                if hasattr(self, "labelSentinelsTitle"):
                    self.labelSentinelsTitle.setText(f"Sentinel 호출 실패: {res.get('error')}")
                return
            if hasattr(self, "labelSentinelsTitle"):
                self.labelSentinelsTitle.setText("Sentinel 정보 수신")

        self._run_task(_task, on_done=_done)

    # -----------------------
    # 실시간 통신 모니터
    # -----------------------
    def on_refresh_realtime(self) -> None:
        """실시간 통신 로그 갱신 (1초마다 호출)."""
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
    # 저장 데이터 검색
    # -----------------------
    def on_search_data(self) -> None:
        """저장된 데이터 검색."""
        try:
            table_name = self.comboTable.currentText().strip() if hasattr(self, "comboTable") else ""
            keyword = self.lineFilter.text().strip() if hasattr(self, "lineFilter") else ""
            logger.debug("[RedisSettingsDialog] 검색: table=%s keyword=%s", table_name, keyword)
        except Exception:
            pass

    def on_prev_page(self) -> None:
        """이전 페이지로 이동."""
        try:
            if self._current_page > 1:
                self._current_page -= 1
                if hasattr(self, "labelPage"):
                    self.labelPage.setText(f"페이지: {self._current_page} / {self._total_pages}")
        except Exception:
            pass

    def on_next_page(self) -> None:
        """다음 페이지로 이동."""
        try:
            if self._current_page < self._total_pages:
                self._current_page += 1
                if hasattr(self, "labelPage"):
                    self.labelPage.setText(f"페이지: {self._current_page} / {self._total_pages}")
        except Exception:
            pass

    def on_export_csv(self) -> None:
        """저장된 데이터 CSV 내보내기."""
        try:
            if not hasattr(self, "tableData"):
                return
            import csv
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, "CSV 저장", "", "CSV Files (*.csv)")
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
            QtWidgets.QMessageBox.information(self, "CSV 저장", f"저장 완료: {filename}")
        except Exception as e:
            logger.debug("[RedisSettingsDialog] CSV 내보내기 예외: %s", e, exc_info=True)
            QtWidgets.QMessageBox.warning(self, "오류", f"CSV 저장 실패: {e}")

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