#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
AutoBackfill 愿由ш린 (諛⑹뼱??援ы쁽)

二쇱슂 ?먯튃:
- import ???대뼡 ?먮룞 ?ㅽ뻾???섏? ?딆뒿?덈떎.
- ?앹꽦(create_auto_backfill_manager) / ?깅줉(register_auto_backfill_manager) / ?쒖옉(run_once_nonblocking/start_periodic)
  ??紐낇솗??遺꾨━?⑸땲??
- symbols(?щ낵) 以鍮??щ?瑜??뺤씤?섏뿬 遺덊븘?뷀븳 鍮??ㅽ뻾??諛⑹??⑸땲??
- waiter ?ㅻ젅?쒕? ?듯븳 ?ъ떆?꾨뒗 '?湲? ?곹깭濡?痍④툒?섎ŉ, ?ㅼ젣 Gap detection ?ㅽ뻾 ?쒖뿉留?True瑜?諛섑솚?⑸땲??
- 紐⑤뱢 ?섏? ?뚯씪-濡쒕뵫 ?대갚? 媛?ν븳 ???ㅼ엫?ㅽ럹?댁뒪 import瑜??곗꽑?쇰줈 ?섎ŉ, 理쒗썑 ?섎떒?쇰줈留??ъ슜?⑸땲??

異붽? 媛쒖꽑:
- graceful shutdown API 異붽?: stop_once(), stop_periodic(), stop_waiter(), stop_all()/shutdown(timeout)
- thread join/timeout 泥섎━ 異붽?
- BackfillStartResult ?닿굅??異붽?: run_once_nonblocking() 諛섑솚 ?댁쑀瑜??곹깭肄붾뱶濡?遺꾨쪟
- last_start_result ?띿꽦: ?몄텧?먭? False 諛섑솚 ?먯씤??利됱떆 ?뚯븙 媛??
- 荑⑤떎??湲곌컙(cooldown_seconds) 吏?? ?숈씪 ?몄텧 諛섎났 ?듭젣
"""
from __future__ import annotations

import enum
import importlib
import importlib.util
import threading
import os
import sys
import logging
import time
from typing import Optional, Callable, Dict, Any, List

DEFAULT_LOGGER_NAME = "auto_backfill"

__all__ = [
    "AutoBackfillManager",
    "BackfillStartResult",
    "create_auto_backfill_manager",
    "register_auto_backfill_manager",
    "get_registered_auto_backfill_manager",
]


class BackfillStartResult(enum.Enum):
    """run_once_nonblocking() ?몄텧 寃곌낵瑜??섑??대뒗 ?곹깭 肄붾뱶.

    媛?硫ㅻ쾭???ㅼ쓬 異붽? ?띿꽦??媛吏묐땲??(``__new__`` ?먯꽌 ?숈쟻 ?ㅼ젙):

    Attributes:
        value (str): 怨좎쑀 肄붾뱶 臾몄옄??(?? "STARTED", "ALREADY_RUNNING")
        success (bool): True?대㈃ ?ㅼ젣 Gap ?먯? ?뚯빱媛 ?쒖옉??寃껋쓣 ?섎?
        description (str): ?щ엺???쎌쓣 ???덈뒗 ?곹깭 ?ㅻ챸 (?쒓?)

    ?ъ슜踰?
        mgr.run_once_nonblocking()
        reason = mgr.last_start_result
        if reason != BackfillStartResult.STARTED:
            print(reason.description)
    """

    STARTED = ("STARTED", True, "Gap ?먯? ?뚯빱 ?ㅻ젅???쒖옉 ?깃났")
    ALREADY_RUNNING = ("ALREADY_RUNNING", False, "?대? ?ㅽ뻾 以???以묐났 ?몄텧 臾댁떆")
    SYMBOLS_NOT_READY_WAITING = (
        "SYMBOLS_NOT_READY_WAITING",
        False,
        "?щ낵 紐⑸줉 誘몄?鍮????湲??ㅻ젅??waiter) ?좉퇋 ?쒖옉?섏뿬 ?щ낵 ?섏떊 ???먮룞 ?ъ떎???덉젙",
    )
    SYMBOLS_NOT_READY_WAITER_RUNNING = (
        "SYMBOLS_NOT_READY_WAITER_RUNNING",
        False,
        "?щ낵 紐⑸줉 誘몄?鍮????湲??ㅻ젅??waiter)媛 ?대? ?숈옉 以묒씠誘濡?異붽? ?몄텧 臾댁떆",
    )
    SYMBOLS_NOT_READY_WAITER_ALREADY_WAITING = (
        "SYMBOLS_NOT_READY_WAITER_ALREADY_WAITING",
        False,
        "?щ낵 紐⑸줉 誘몄?鍮???_waiting ?뚮옒洹??쒖꽦 以묒쑝濡?以묐났 ?湲?諛⑹?",
    )
    WAITER_START_FAILED = (
        "WAITER_START_FAILED",
        False,
        "?湲??ㅻ젅??waiter) ?쒖옉 ?ㅽ뙣 ???ㅻ젅???앹꽦 ?덉쇅 諛쒖깮",
    )
    THREAD_START_FAILED = (
        "THREAD_START_FAILED",
        False,
        "Gap ?먯? ?뚯빱 ?ㅻ젅???쒖옉 ?ㅽ뙣 ??OS ?ㅻ젅???앹꽦 ?덉쇅 諛쒖깮",
    )
    COOLDOWN_ACTIVE = (
        "COOLDOWN_ACTIVE",
        False,
        "荑⑤떎??湲곌컙 以???理쒓렐 False 諛섑솚 ???湲??쒓컙??吏?섏? ?딆븯??,
    )
    NOT_INITIALIZED = (
        "NOT_INITIALIZED",
        False,
        "?꾩쭅 run_once_nonblocking() ?몄텧 ??(珥덇린 ?곹깭)",
    )

    def __new__(cls, code: str, success: bool, description: str) -> "BackfillStartResult":
        obj = object.__new__(cls)
        obj._value_ = code
        obj.success = success          # type: ignore[attr-defined]
        obj.description = description  # type: ignore[attr-defined]
        return obj

    def __bool__(self) -> bool:
        return self.success  # type: ignore[attr-defined]


class AutoBackfillManager:
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        on_run_complete: Optional[Callable[[bool], None]] = None,
        ready_wait_seconds: int = 15,
        ready_poll_interval: float = 1.0,
        cooldown_seconds: float = 30.0,
    ):
        """
        logger: 濡쒓굅 媛앹껜
        on_run_complete: gap ?먯? ?????ㅽ뻾 ?꾨즺 ???몄텧?섎뒗 肄쒕갚(success: bool)
        ready_wait_seconds: ?щ낵 ?湲??ъ떆?? 理쒕? ?쒓컙 (珥?
        ready_poll_interval: ?щ낵 議댁옱 ?щ? ?뺤씤 二쇨린 (珥?
        cooldown_seconds: False 諛섑솚 ???ы샇異쒓퉴吏 ?湲??쒓컙(珥?. 0?대㈃ 荑⑤떎???놁쓬.
        """
        self.log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

        self.on_run_complete = on_run_complete
        self._periodic_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._periodic_interval = 60
        self._lock = threading.Lock()
        self._running = False
        self._waiting = False  # waiter(?щ낵 ?湲? ?곹깭 ?쒖떆

        # readiness 愿???뚮씪誘명꽣
        self._ready_wait_seconds = int(ready_wait_seconds)
        self._ready_poll_interval = float(ready_poll_interval)

        # 荑⑤떎??湲곌컙 (False 諛섑솚 ???ы샇異??듭젣)
        self._cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._last_false_time: float = 0.0

        # ?대? ?곹깭: 留덉?留됱쑝濡??앹꽦??waiter/once ?ㅻ젅??媛앹껜
        self._delayed_wait_thread: Optional[threading.Thread] = None
        self._once_thread: Optional[threading.Thread] = None

        # 留덉?留?run_once_nonblocking ?몄텧 寃곌낵 (?몄텧?먭? ?먯씤 ?뚯븙???쒖슜)
        self.last_start_result: BackfillStartResult = BackfillStartResult.NOT_INITIALIZED

        # 留덉?留??ㅻ쪟 ?ъ쑀 ??UI ?곹깭李??쒖텧??(?쒓? 援ъ껜 ?ㅻ챸)
        self.last_error_reason: str = ""

        # 諛깊븘 ?듦퀎 移댁슫??(UI ?쒖떆??
        self._processed_count: int = 0   # ?대쾲 ?몄뀡?먯꽌 ?깃났?곸쑝濡?諛깊븘??Gap ??
        self._failed_count: int = 0      # ?ㅽ뙣??Gap ??
        self._pending_count: int = 0     # 留덉?留?泥섎━ ???⑥? Gap ??
        self._execution_state: str = "idle"  # idle / detecting / processing / completed / error

        self.log.debug("[AutoBackfill] Manager initialized (ready_wait=%ss, poll=%ss, cooldown=%ss)",
                       self._ready_wait_seconds, self._ready_poll_interval, self._cooldown_seconds)
    # --------------------------
    # ?꾩뿭 static 紐⑤뱢 ?먯깋 ?좏떥
    # --------------------------
    def _get_static_module(self) -> Optional[Any]:
        candidates = (
            "src.11_server.app.static",
            "11_server.app.static",
            "app.static",
            "src.app.static",
            "static",
        )
        for nm in candidates:
            try:
                mod = importlib.import_module(nm)
                return mod
            except Exception:
                continue
        return None

    # --------------------------
    # ?щ낵 以鍮??щ? ?먮떒
    # --------------------------
    def _has_symbols_available(self) -> bool:
        try:
            mod = self._get_static_module()
            if mod is None:
                return False
            # 1) static.available_symbols
            avail = getattr(mod, "available_symbols", None)
            if avail:
                if isinstance(avail, (list, tuple)) and len(avail) > 0:
                    return True
            # 2) static.chart.codes
            chart = getattr(mod, "chart", None)
            if chart is not None:
                try:
                    codes = getattr(chart, "codes", None)
                    if callable(codes):
                        c = codes()
                        if isinstance(c, (list, tuple)) and len(c) > 0:
                            return True
                    else:
                        if isinstance(codes, (list, tuple)) and len(codes) > 0:
                            return True
                except Exception:
                    pass
            # 3) available_symbols_count
            cnt = getattr(mod, "available_symbols_count", None)
            if isinstance(cnt, int) and cnt > 0:
                return True

            # 4) Bootstrap-style namespaces: check already-imported bootstrap modules
            #    for a .static attribute (SimpleNamespace) that holds available_symbols.
            #    The 11_server.app.static module is a package whose module-level chart/
            #    available_symbols attributes stay None even after bootstrap populates its
            #    own SimpleNamespace, so we scan sys.modules for bootstrap variants.
            try:
                bootstrap_candidates = (
                    "app.bootstrap",
                    "src.app.bootstrap",
                )
                for bname in bootstrap_candidates:
                    bmod = sys.modules.get(bname)
                    if bmod is None:
                        continue
                    ns = getattr(bmod, "static", None)
                    if ns is None:
                        continue
                    # check available_symbols on the namespace
                    b_avail = getattr(ns, "available_symbols", None)
                    if isinstance(b_avail, (list, tuple)) and len(b_avail) > 0:
                        return True
                    # check chart.codes on the namespace
                    b_chart = getattr(ns, "chart", None)
                    if b_chart is not None:
                        b_codes = getattr(b_chart, "codes", None)
                        if callable(b_codes):
                            available_codes = b_codes()
                            if isinstance(available_codes, (list, tuple)) and len(available_codes) > 0:
                                return True
                        elif isinstance(b_codes, (list, tuple)) and len(b_codes) > 0:
                            return True
            except Exception:
                pass

            return False
        except Exception:
            try:
                self.log.debug("[AutoBackfill] _has_symbols_available check failed", exc_info=True)
            except Exception:
                pass
            return False

    # --------------------------
    # symbols 以鍮??湲???run
    # --------------------------
    def _wait_for_symbols_then_run(self, timeout: Optional[int] = None) -> None:
        if timeout is None:
            timeout = self._ready_wait_seconds
        waited = 0.0
        interval = max(0.1, float(self._ready_poll_interval))
        self.log.debug("[AutoBackfill] waiting up to %ss for symbols (poll=%ss)", timeout, interval)
        try:
            self._waiting = True
            while waited < timeout and not self._stop_event.is_set():
                try:
                    if self._has_symbols_available():
                        self.log.debug("[AutoBackfill] symbols detected after waited=%.1fs; starting detection", waited)
                        # Force run_once_nonblocking to bypass readiness checks now that symbols exist.
                        # This internal call will respect _running flag.
                        try:
                            self.run_once_nonblocking(force=True)
                        except Exception:
                            self.log.exception("[AutoBackfill] run_once_nonblocking(force=True) failed inside waiter")
                        return
                except Exception:
                    try:
                        self.log.debug("[AutoBackfill] wait_for_symbols check exception", exc_info=True)
                    except Exception:
                        pass
                time.sleep(interval)
                waited += interval
            self.log.info("[AutoBackfill] symbols not available within wait window (%ss); skipping initial run", timeout)
        finally:
            self._waiting = False

    # --------------------------
    # repo ?뚯씪 寃??(蹂댁“)
    # --------------------------
    def _search_repo_for_gap_finder(self, repo_root: str, max_results: int = 20) -> List[str]:
        matches: List[str] = []
        for root, dirs, files in os.walk(repo_root):
            if any(skip in root for skip in (os.path.join(repo_root, ".git"), "venv", "env", "__pycache__", "node_modules")):
                continue
            for f in files:
                if "gap_finder" in f.lower() and f.lower().endswith(".py"):
                    matches.append(os.path.join(root, f))
                    if len(matches) >= max_results:
                        return matches
        return matches

    # --------------------------
    # gap_finder 紐⑤뱢 ?먯깋/濡쒕뵫
    # --------------------------
    def _find_gap_finder_module(self):
        candidates = (
            "app.core.gap_finder",
            "app.core.auto_backfill_gap_finder",
            "data_01.timescale.operations.gap_finder",
            "src.data_01.timescale.operations.gap_finder",
            "data_01.timescale.timescale_gap_finder",
            "src.data_01.timescale.timescale_gap_finder",
            "timescale.operations.gap_finder",
            "timescale_gap_finder",
            "src.timescale_gap_finder",
            "src.timescale.operations.gap_finder",
        )

        attempted: List[str] = []
        for p in candidates:
            try:
                attempted.append(f"module:{p}")
                mod = importlib.import_module(p)
                self.log.debug("[AutoBackfill] Imported gap finder module: %s -> %s", p, getattr(mod, "__file__", None))
                return mod
            except Exception as e:
                self.log.debug("[AutoBackfill] import %s failed: %s", p, f"{type(e).__name__}: {e}")

        # ?뚯씪 寃??理쒗썑 ?섎떒)
        try:
            here = os.path.dirname(os.path.abspath(__file__))

            def find_ancestor_named(start: str, name: str, max_up: int = 6) -> Optional[str]:
                p = start
                for _ in range(max_up):
                    if os.path.basename(p) == name:
                        return p
                    parent = os.path.dirname(p)
                    if parent == p:
                        break
                    p = parent
                return None

            repo_src = find_ancestor_named(here, "src") or os.path.abspath(os.path.join(here, "..", ".."))
            repo_root_guess = find_ancestor_named(here, ".git") or os.path.abspath(os.path.join(here, "..", "..", ".."))
            repo_root = repo_root_guess if os.path.isdir(repo_root_guess) else os.path.abspath(os.path.join(here, "..", "..", ".."))
        except Exception:
            repo_src = os.path.abspath(os.path.join(os.getcwd(), "src"))
            repo_root = os.path.abspath(os.getcwd())

        self.log.debug("[AutoBackfill] repo_src=%s, repo_root=%s, starting file search for gap_finder", repo_src, repo_root)

        for root_candidate in (repo_src, repo_root, os.getcwd()):
            try:
                if not os.path.isdir(root_candidate):
                    continue
                candidates_files = self._search_repo_for_gap_finder(root_candidate, max_results=20)
                if candidates_files:
                    self.log.debug("[AutoBackfill] repo search found gap_finder candidates under %s: %s", root_candidate, candidates_files)
                    for f in candidates_files:
                        try:
                            alias = f"gap_finder_repo_{os.path.basename(f)}"
                            spec = importlib.util.spec_from_file_location(alias, f)
                            if spec and spec.loader:
                                mod = importlib.util.module_from_spec(spec)
                                try:
                                    sys.modules[alias] = mod
                                except Exception:
                                    pass
                                spec.loader.exec_module(mod)
                                self.log.info("[AutoBackfill] Loaded gap finder from file: %s", f)
                                return mod
                        except Exception as e:
                            self.log.debug("[AutoBackfill] file-level load attempt failed for %s: %s", f, f"{type(e).__name__}: {e}")
            except Exception:
                self.log.debug("[AutoBackfill] repo file search exception", exc_info=True)

        self.log.warning("[AutoBackfill] gap finder module not found in known locations (attempted: %s)", attempted)
        return None

    # --------------------------
    # 諛깊븘 泥섎━ ?ы띁 硫붿꽌??
    # --------------------------

    def _load_backfill_manager_class(self):
        """backfill.auto_backfill_manager.AutoBackfillManager ?대옒???숈쟻 濡쒕뱶."""
        try:
            from .backfill.auto_backfill_manager import AutoBackfillManager as _BfMgr
            return _BfMgr
        except Exception:
            pass
        try:
            import importlib.util as _ilu
            import pathlib as _pl
            _base = _pl.Path(__file__).resolve().parent
            _path = _base / "backfill" / "auto_backfill_manager.py"
            if _path.exists():
                alias = "src._14_orchestrator.backfill.auto_backfill_manager"
                _mod = sys.modules.get(alias)
                if _mod is None:
                    _spec = _ilu.spec_from_file_location(alias, str(_path))
                    if _spec and _spec.loader:
                        _mod = _ilu.module_from_spec(_spec)
                        sys.modules[alias] = _mod
                        _spec.loader.exec_module(_mod)
                if _mod is not None:
                    return getattr(_mod, "AutoBackfillManager", None)
        except Exception:
            self.log.debug("[AutoBackfill] BackfillManager ?대옒??濡쒕뱶 ?ㅽ뙣", exc_info=True)
        return None

    def _load_timescale_connector_class(self):
        """TimescaleConnector ?대옒?ㅻ? ?숈쟻?쇰줈 濡쒕뱶?⑸땲??(怨듯넻 ?ы띁)."""
        _ts_db_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data_01", "timescale", "timescale_db.py")
        )
        alias = "_timescale_db"
        _mod = sys.modules.get(alias)
        if _mod is None and os.path.isfile(_ts_db_path):
            try:
                import importlib.util as _ilu
                _spec = _ilu.spec_from_file_location(alias, _ts_db_path)
                if _spec and _spec.loader:
                    _mod = _ilu.module_from_spec(_spec)
                    sys.modules[alias] = _mod
                    _spec.loader.exec_module(_mod)
            except Exception as e:
                self.log.debug("[AutoBackfill] TimescaleConnector 濡쒕뱶 ?ㅽ뙣: %s", e)
                return None
        return getattr(_mod, "TimescaleConnector", None) if _mod else None

    def _get_pending_gaps_from_db(self, max_items: int = 50) -> list:
        """TimescaleDB gap_fill_queue ?뚯씠釉붿뿉??pending ?곹깭 Gap 議고쉶 (Redis ZSET ?대갚??."""
        try:
            TimescaleConnector = self._load_timescale_connector_class()
            if TimescaleConnector is None:
                return []
            conn = TimescaleConnector()
            if not conn.connect() or not conn.conn or conn.conn.closed:
                return []
            with conn.conn.cursor() as cur:
                cur.execute(
                    "SELECT symbol, timeframe, gap_start, gap_end FROM gap_fill_queue "
                    "WHERE status = 'pending' ORDER BY priority DESC, created_at ASC LIMIT %s",
                    (max_items,),
                )
                rows = cur.fetchall()
            return [
                {"symbol": r[0], "timeframe": r[1], "gap_start": r[2], "gap_end": r[3]}
                for r in rows
            ]
        except Exception as e:
            self.log.debug("[AutoBackfill] DB pending gaps 議고쉶 ?ㅽ뙣: %s", e)
            return []

    def _get_pending_count_from_db(self) -> int:
        """TimescaleDB gap_fill_queue ?뚯씠釉붿뿉??pending ?곹깭 Gap ??議고쉶."""
        try:
            TimescaleConnector = self._load_timescale_connector_class()
            if TimescaleConnector is None:
                return -1
            conn = TimescaleConnector()
            if not conn.connect() or not conn.conn or conn.conn.closed:
                return -1
            with conn.conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM gap_fill_queue WHERE status = 'pending'")
                row = cur.fetchone()
            return int(row[0]) if row else 0
        except Exception as e:
            self.log.debug("[AutoBackfill] DB pending count 議고쉶 ?ㅽ뙣: %s", e)
            return -1

    def _process_queue_sync(self, max_gaps: Optional[int] = None) -> tuple:
        """Queue?먯꽌 Gap??爰쇰궡 諛깊븘 泥섎━?⑸땲??

        ?먮쫫:
          1) in-memory deque?먯꽌 pop_next() 濡?理쒕? max_gaps 嫄댁쓣 媛?몄샂
          2) in-memory媛 鍮꾩뼱?덉쑝硫?TimescaleDB gap_fill_queue(pending) 議고쉶
          3) backfill/auto_backfill_manager.AutoBackfillManager濡?媛?gap 諛깊븘
          4) 泥섎━ 寃곌낵(processed, failed, remaining) 諛섑솚

        Returns:
            (processed: int, failed: int, remaining: int)
        """
        import asyncio as _asyncio

        processed = 0
        failed = 0

        try:
            prev_state = self._execution_state
            self._execution_state = "processing"

            # ?? ?깅뒫 ?ㅼ젙 SSOT 濡쒕뱶 (UI ?ㅼ씠?쇰줈洹몄뿉??蹂寃?媛?? ??
            #   None ?대㈃ UI ?ㅼ젙媛??ъ슜. 紐낆떆??媛믪씠 ?덉쑝硫?洹몃?濡??ъ슜.
            try:
                from .backfill.performance_settings import (
                    get_max_concurrency,
                    get_max_gaps_per_cycle,
                )
                _perf_max_gaps = int(get_max_gaps_per_cycle())
                _perf_max_concurrency = int(get_max_concurrency())
            except Exception as _exc:
                self.log.debug(
                    "[AutoBackfill] performance_settings 濡쒕뱶 ?ㅽ뙣(湲곕낯媛??ъ슜): %s", _exc,
                )
                _perf_max_gaps = 200
                _perf_max_concurrency = 12
            if max_gaps is None:
                max_gaps = _perf_max_gaps
            else:
                max_gaps = max(1, int(max_gaps))

            # gap_finder 紐⑤뱢?먯꽌 pop/len ?⑥닔 媛?몄삤湲?
            mod = self._find_gap_finder_module()
            pop_fn = getattr(mod, "pop_next", None) if mod else None
            get_len_fn = getattr(mod, "get_queue_length", None) if mod else None

            # BackfillManager ?대옒??濡쒕뱶 (?ㅼ젣 泥섎━湲?
            BfMgr = self._load_backfill_manager_class()
            if BfMgr is None:
                self.log.warning("[AutoBackfill] BackfillManager ?놁쓬 - ??泥섎━ 遺덇?")
                # pending count 媛깆떊 ?쒕룄
                remaining = 0
                if get_len_fn:
                    try:
                        remaining = int(get_len_fn())
                    except Exception:
                        remaining = 0
                db_pending = self._get_pending_count_from_db()
                if db_pending > remaining:
                    remaining = db_pending
                self._pending_count = remaining
                return (0, 0, self._pending_count)

            bf_mgr = BfMgr(logger=self.log)
            # ?ъ씠?대퀎 遺꾨쪟 移댁슫??珥덇린??(UI 硫붿떆吏 紐낇솗?붿슜)
            try:
                if hasattr(bf_mgr, "reset_classification"):
                    bf_mgr.reset_classification()
            except Exception:
                pass

            # 泥섎━??gap 紐⑸줉 ?섏쭛
            gaps_to_process: list = []

            # 1李? in-memory deque?먯꽌 pop
            if pop_fn and callable(pop_fn):
                for _ in range(max_gaps):
                    gap = pop_fn()
                    if gap is None:
                        break
                    gaps_to_process.append({
                        "symbol": getattr(gap, "symbol", ""),
                        "timeframe": getattr(gap, "timeframe", "1m"),
                        "gap_start": getattr(gap, "gap_start", None),
                        "gap_end": getattr(gap, "gap_end", None),
                    })

            # 2李? in-memory媛 鍮꾩뼱?덉쑝硫?DB pending 議고쉶
            if not gaps_to_process:
                gaps_to_process = self._get_pending_gaps_from_db(max_items=max_gaps)

            if not gaps_to_process:
                self.log.debug("[AutoBackfill] 泥섎━??Gap ?놁쓬 (??鍮꾩뼱?덉쓬)")
                remaining = 0
                if get_len_fn:
                    try:
                        remaining = int(get_len_fn())
                    except Exception:
                        remaining = 0
                db_pending = self._get_pending_count_from_db()
                if db_pending > remaining:
                    remaining = db_pending
                self._pending_count = remaining
                return (0, 0, self._pending_count)

            self.log.info("[AutoBackfill] 諛깊븘 泥섎━ ?쒖옉: %d嫄????, len(gaps_to_process))

            # 鍮꾨룞湲?泥섎━ ?⑥닔
            async def _process_all_async(gap_list: list):
                # ?숈떆?? SSOT(`backfill_scheduler.performance.max_concurrency`)
                # ???섍꼍蹂??`AUTO_BACKFILL_MAX_CONCURRENCY` ??湲곕낯 12.
                # 湲濡쒕쾶 AsyncRateLimiter(9 req/s 쨌 550 req/min)媛 ?ㅼ젣 ?몃? ?몄텧
                # ?띾룄瑜??덉쟾?섍쾶 吏곷젹?뷀븯誘濡????숈떆??媛믩룄 ?덉쟾.
                max_concurrency = max(1, min(int(_perf_max_concurrency), 32))
                sem = _asyncio.Semaphore(max_concurrency)

                async def _run_one(gap_dict: dict) -> bool:
                    async with sem:
                        try:
                            return bool(await bf_mgr._process_one_gap(gap_dict))
                        except Exception as _e:
                            self.log.error(
                                "[AutoBackfill] Gap 泥섎━ ?덉쇅 (symbol=%s): %s",
                                gap_dict.get("symbol", "?"),
                                _e,
                            )
                            return False

                results = await _asyncio.gather(*[_run_one(g) for g in gap_list])
                p = sum(1 for ok in results if ok)
                f = len(results) - p
                return p, f

            # asyncio.run?쇰줈 ?숆린 ?ㅽ뻾 (?ㅻ젅???대? ???대깽??猷⑦봽 ?놁쓬)
            try:
                processed, failed = _asyncio.run(_process_all_async(gaps_to_process))
            except Exception as e:
                self.log.error("[AutoBackfill] asyncio.run ?ㅽ뙣: %s", e)
                processed = 0
                failed = len(gaps_to_process)

            self._processed_count += processed
            self._failed_count += failed

            # 遺꾨쪟 ?붿빟 罹먯떆 (UI 硫붿떆吏 紐낇솗?붿슜)
            try:
                summary_fn = getattr(bf_mgr, "classification_summary", None)
                if callable(summary_fn):
                    self._last_classification_summary = summary_fn()
                else:
                    self._last_classification_summary = ""
            except Exception:
                self._last_classification_summary = ""

            # remaining count 媛깆떊
            # gap_finder ??湲몄씠 ?곗꽑 (pop_next濡?in-memory deque ?뚮퉬??
            # DB pending count???뺤씤 (Redis 紐⑤뱶??DB-湲곕컲 泥섎━?먯꽌 ???뺥솗)
            remaining = 0
            if get_len_fn:
                try:
                    remaining = int(get_len_fn())
                except Exception:
                    remaining = 0
            db_pending = self._get_pending_count_from_db()
            if db_pending > remaining:
                remaining = db_pending
            self._pending_count = remaining

            self.log.info(
                "[AutoBackfill] 諛깊븘 泥섎━ ?꾨즺: ?깃났=%d, ?ㅽ뙣=%d, ?붿뿬=%d",
                processed, failed, self._pending_count,
            )
            return (processed, failed, self._pending_count)

        except Exception as e:
            self.log.error("[AutoBackfill] _process_queue_sync ?ㅻ쪟: %s", e, exc_info=True)
            return (0, 0, self._pending_count)
        finally:
            # 泥섎━ ?곹깭 蹂듭썝 (detecting?댁뿀?쇰㈃ ?좎?, ?꾨땲硫?idle)
            if self._execution_state == "processing":
                self._execution_state = "idle"

    # --------------------------
    # gap ?먯? ?숆린 ?ㅽ뻾
    # --------------------------
    def _run_gap_detection_sync(self) -> bool:
        success = False
        try:
            self._execution_state = "detecting"
            mod = self._find_gap_finder_module()
            if mod is None:
                reason = "Gap Finder 紐⑤뱢??李얠쓣 ???놁쓬 (?ㅼ튂/寃쎈줈 ?뺤씤 ?꾩슂)"
                self.last_error_reason = reason
                self._execution_state = "error"
                self.log.warning("[AutoBackfill] Gap finder module not found; skipping run")
                return False

            fn_candidates = (
                "detect_all_and_enqueue",
                "detect_gaps_and_enqueue_all",
                "detect_gaps_for_all",
                "detect_and_enqueue",
                "run",
                "main",
            )
            fn = None
            for name in fn_candidates:
                if hasattr(mod, name) and callable(getattr(mod, name)):
                    fn = getattr(mod, name)
                    self.log.debug("[AutoBackfill] Using gap finder entrypoint: %s", name)
                    break

            if fn is None:
                reason = "Gap Finder 紐⑤뱢???명솚 吏꾩엯???놁쓬 (detect_all_and_enqueue ???꾩슂)"
                self.last_error_reason = reason
                self._execution_state = "error"
                self.log.warning("[AutoBackfill] Gap finder module has no compatible entrypoint")
                return False

            self.log.debug("[AutoBackfill] Running gap detection (sync)...")

            called = False
            try_patterns = [
                (),
                ([],),
                (None,),
            ]
            for args in try_patterns:
                try:
                    if args:
                        fn(*args)
                    else:
                        fn()
                    called = True
                    break
                except TypeError as e:
                    self.log.debug("[AutoBackfill] gap finder call with args=%s TypeError: %s", args, e)
                    continue
                except Exception as e:
                    reason = f"Gap ?먯? ?ㅽ뻾 ?덉쇅: {type(e).__name__}: {e}"
                    self.last_error_reason = reason
                    self.log.exception("[AutoBackfill] gap finder function raised an exception")
                    called = True
                    break

            if not called:
                try:
                    fn([])
                    called = True
                except Exception as e:
                    reason = f"Gap ?먯? 理쒖쥌 ?몄텧 ?ㅽ뙣: {type(e).__name__}: {e}"
                    self.last_error_reason = reason
                    self.log.exception("[AutoBackfill] final gap finder invocation attempts failed")

            if called:
                self.log.debug("[AutoBackfill] Gap detection finished (called=%s)", called)
                # ??????????????????????????????????????????????????????????????
                # Gap ?먯? ?꾨즺 ????泥섎━ (諛깊븘 ?ㅽ뻾): ?먯???Gap???ㅼ젣濡?DB??諛섏쁺
                # ?깃났 湲곗?: API ?몄텧 ?깃났???꾨땶 DB 諛섏쁺 ?됱닔 > 0 ?먮뒗 Gap ?곹깭 closed
                # ??????????????????????????????????????????????????????????????
                try:
                    # ?ъ씠???쒖옉 ??bf_mgr ?ъ깮?깆? _process_queue_sync ?대??먯꽌.
                    processed_in_batch, failed_in_batch, remaining_count = self._process_queue_sync()
                    # ?ㅼ젣 DB 諛섏쁺???덉뿀嫄곕굹 ?먭? 鍮꾩뼱?덉쑝硫??먯? ?④퀎?먯꽌 媛??놁쓬) ?깃났
                    success = (processed_in_batch > 0) or (remaining_count == 0)
                    if not success and failed_in_batch > 0:
                        # 遺꾨쪟 移댁슫???붿빟 ?곗꽑 ???놁쑝硫?湲곗〈 ?⑥닚 硫붿떆吏濡??대갚.
                        # _process_queue_sync 媛 ?ъ씠???앹뿉 _last_classification_summary
                        # ?띿꽦????ν븳 ?붿빟???ъ슜?쒕떎.
                        f_summary = getattr(self, "_last_classification_summary", "")
                        if f_summary:
                            self.last_error_reason = (
                                f"諛깊븘 泥섎━ 寃곌낵 ??{f_summary} (?붿뿬 {remaining_count}嫄?"
                            )
                        else:
                            self.last_error_reason = (
                                f"諛깊븘 泥섎━ ?ㅽ뙣 {failed_in_batch}嫄?"
                                f"(?깃났 {processed_in_batch}嫄? ?붿뿬 {remaining_count}嫄?"
                            )
                    elif not success and processed_in_batch == 0 and remaining_count == 0:
                        # 泥섎━??Gap ?놁쓬 ??gap detection ?먯껜???깃났
                        success = True
                except Exception as e:
                    reason = f"諛깊븘 泥섎━ 以??ㅻ쪟: {type(e).__name__}: {e}"
                    self.last_error_reason = reason
                    self.log.exception("[AutoBackfill] _process_queue_sync raised an exception")
                    success = False
            else:
                reason = "Gap ?먯? ?몄텧 遺덇? (?명솚 ?쒓렇?덉쿂 ?놁쓬)"
                self.last_error_reason = reason
                success = False
                self._execution_state = "error"
                self.log.warning("[AutoBackfill] Gap detection was not invoked (no compatible signature)")

            if success:
                self._execution_state = "completed"
            elif self._execution_state not in ("error",):
                self._execution_state = "idle"

            return success
        except Exception as e:
            reason = f"Gap ?먯? ?덇린移??딆? ?ㅻ쪟: {type(e).__name__}: {e}"
            self.last_error_reason = reason
            self._execution_state = "error"
            self.log.exception("[AutoBackfill] Unexpected error in _run_gap_detection_sync")
            return False
        finally:
            try:
                if self.on_run_complete:
                    try:
                        self.on_run_complete(bool(success))
                    except Exception:
                        self.log.exception("[AutoBackfill] on_run_complete callback raised an exception")
            except Exception:
                self.log.debug("[AutoBackfill] on_run_complete invocation failed", exc_info=True)

    # --------------------------
    # ??踰?鍮꾨룞湲??ㅽ뻾 (諛⑹뼱??
    # --------------------------
    def run_once_nonblocking(self, force: bool = False) -> bool:
        """
        gap ?먯?瑜???踰?鍮꾨룞湲??ㅽ뻾.

        諛섑솚媛? ?ㅼ젣 Gap detection worker(諛깊븘 ?묒뾽)媛 ?쒖옉?섏뿀???뚮쭔 True瑜?諛섑솚?⑸땲??
          ?щ낵 誘몄?鍮꾨줈 'waiter' ?ㅻ젅?쒕? ?쒖옉??寃쎌슦?먮뒗 False瑜?諛섑솚(?湲?以?.
          force=True?대㈃ symbols 以鍮?泥댄겕瑜??고쉶?섏뿬 諛붾줈 worker瑜??쒖옉(?? ?대? _running?대㈃ False).

        self.last_start_result ??援ъ껜?곸씤 BackfillStartResult ?곹깭肄붾뱶媛 ?ㅼ젙?⑸땲??
        ?몄텧?먮뒗 ???띿꽦?쇰줈 False 諛섑솚 ?먯씤??利됱떆 ?뚯븙?????덉뒿?덈떎.

        荑⑤떎??cooldown_seconds):
          吏곸쟾 False 諛섑솚 ?댄썑 cooldown_seconds 媛 吏?섏? ?딆븯?쇰㈃ COOLDOWN_ACTIVE 諛섑솚.
          ?대? ?ㅽ뻾 以?ALREADY_RUNNING) 諛?force=True ?몄텧? 荑⑤떎?댁쓣 臾댁떆?⑸땲??
        """
        def _set(result: BackfillStartResult) -> bool:
            self.last_start_result = result
            if not result.success:  # type: ignore[attr-defined]
                self._last_false_time = time.monotonic()
                # ?ㅽ뙣 ?먯씤??last_error_reason ??湲곕줉 (UI ?곹깭李??쒖텧??
                if not self.last_error_reason:
                    self.last_error_reason = result.description  # type: ignore[attr-defined]
            else:
                # ?깃났 ???ㅻ쪟 ?ъ쑀 珥덇린??
                self.last_error_reason = ""
            return bool(result)

        with self._lock:
            if self._running:
                self.log.info(
                    "[AutoBackfill] run_once_nonblocking ???곹깭: %s | %s",
                    BackfillStartResult.ALREADY_RUNNING.value,
                    BackfillStartResult.ALREADY_RUNNING.description,
                )
                return _set(BackfillStartResult.ALREADY_RUNNING)

            # 荑⑤떎??泥댄겕 (force 諛?ALREADY_RUNNING ?댄썑???쒖쇅)
            if not force and self._cooldown_seconds > 0 and self._last_false_time > 0:
                elapsed = time.monotonic() - self._last_false_time
                if (
                    self.last_start_result not in (BackfillStartResult.NOT_INITIALIZED, BackfillStartResult.STARTED)
                    and elapsed < self._cooldown_seconds
                ):
                    remaining = self._cooldown_seconds - elapsed
                    self.log.info(
                        "[AutoBackfill] run_once_nonblocking ???곹깭: %s | %s (?⑥? 荑⑤떎?? %.0fs)",
                        BackfillStartResult.COOLDOWN_ACTIVE.value,
                        BackfillStartResult.COOLDOWN_ACTIVE.description,
                        remaining,
                    )
                    return _set(BackfillStartResult.COOLDOWN_ACTIVE)

            # If not forced and symbols not ready -> start waiter (if not already) and return False (not started)
            if not force and not self._has_symbols_available():
                if self._delayed_wait_thread and self._delayed_wait_thread.is_alive():
                    self.log.info(
                        "[AutoBackfill] run_once_nonblocking ???곹깭: %s | %s",
                        BackfillStartResult.SYMBOLS_NOT_READY_WAITER_RUNNING.value,
                        BackfillStartResult.SYMBOLS_NOT_READY_WAITER_RUNNING.description,
                    )
                    return _set(BackfillStartResult.SYMBOLS_NOT_READY_WAITER_RUNNING)
                if self._waiting:
                    self.log.info(
                        "[AutoBackfill] run_once_nonblocking ???곹깭: %s | %s",
                        BackfillStartResult.SYMBOLS_NOT_READY_WAITER_ALREADY_WAITING.value,
                        BackfillStartResult.SYMBOLS_NOT_READY_WAITER_ALREADY_WAITING.description,
                    )
                    return _set(BackfillStartResult.SYMBOLS_NOT_READY_WAITER_ALREADY_WAITING)

                def _delayed():
                    try:
                        self._wait_for_symbols_then_run(timeout=self._ready_wait_seconds)
                    except Exception:
                        self.log.exception("[AutoBackfill] delayed wait thread failed")

                self._delayed_wait_thread = threading.Thread(target=_delayed, daemon=True, name="auto_backfill_waiter")
                try:
                    self._delayed_wait_thread.start()
                    self.log.info(
                        "[AutoBackfill] run_once_nonblocking ???곹깭: %s | %s (理쒕? %ss ?湲?",
                        BackfillStartResult.SYMBOLS_NOT_READY_WAITING.value,
                        BackfillStartResult.SYMBOLS_NOT_READY_WAITING.description,
                        self._ready_wait_seconds,
                    )
                    return _set(BackfillStartResult.SYMBOLS_NOT_READY_WAITING)
                except Exception as e:
                    self.last_error_reason = f"?щ낵 ?湲??ㅻ젅???쒖옉 ?ㅽ뙣: {type(e).__name__}: {e}"
                    self.log.exception("[AutoBackfill] Failed to start delayed waiter thread")
                    return _set(BackfillStartResult.WAITER_START_FAILED)

            # proceed to start worker immediately
            self._running = True

        def _worker():
            try:
                self._run_gap_detection_sync()
            except Exception as e:
                self.last_error_reason = f"?뚯빱 ?ㅽ뻾 以??덉쇅: {type(e).__name__}: {e}"
                self.log.exception("[AutoBackfill] error in non-blocking worker")
            finally:
                with self._lock:
                    self._running = False
                self.log.debug("[AutoBackfill] non-blocking worker finished; running flag cleared")

        t = threading.Thread(target=_worker, daemon=True, name="auto_backfill_once")
        try:
            t.start()
            # store reference so we can join/stop later
            self._once_thread = t
            self.last_start_result = BackfillStartResult.STARTED
            self.last_error_reason = ""
            self.log.info(
                "[AutoBackfill] run_once_nonblocking ???곹깭: %s | %s",
                BackfillStartResult.STARTED.value,
                BackfillStartResult.STARTED.description,
            )
            return True
        except Exception as e:
            with self._lock:
                self._running = False
            self.last_error_reason = f"Gap ?먯? ?뚯빱 ?ㅻ젅???쒖옉 ?ㅽ뙣: {type(e).__name__}: {e}"
            self.log.exception("[AutoBackfill] Failed to start non-blocking backfill thread")
            return _set(BackfillStartResult.THREAD_START_FAILED)

    def is_running(self) -> bool:
        with self._lock:
            return bool(self._running)

    def is_waiting(self) -> bool:
        return bool(self._waiting)

    # --------------------------
    # 二쇨린 ?ㅽ뻾 (二쇨린 ?쒖옉 ??readiness 泥댄겕)
    # --------------------------
    def _periodic_loop(self, interval_seconds: int):
        self.log.debug("[AutoBackfill] Periodic loop started (interval=%ss)", interval_seconds)
        while not self._stop_event.wait(interval_seconds):
            try:
                # ?щ낵 泥댄겕 ?놁씠 ??긽 gap ?먯? ?ㅽ뻾 ??gap_finder 媛 DB 湲곗? ?щ낵??吏곸젒 議고쉶?⑸땲??
                # static 紐⑤뱢???щ낵???깅줉?섏? ?딆? UI ?꾩슜 ?ㅽ뻾 ?섍꼍?먯꽌???숈옉?⑸땲??
                self._run_gap_detection_sync()
            except Exception:
                self.log.exception("[AutoBackfill] exception in periodic loop")
        self.log.debug("[AutoBackfill] Periodic loop stopped")

    def start_periodic(self, interval_seconds: int = 60) -> None:
        with self._lock:
            self._periodic_interval = int(interval_seconds)
            if self._periodic_thread and self._periodic_thread.is_alive():
                self.log.debug("[AutoBackfill] Periodic thread already running; interval updated")
                return
            self._stop_event.clear()
            self._periodic_thread = threading.Thread(target=self._periodic_loop, args=(self._periodic_interval,), daemon=True, name="auto_backfill_periodic")
            self._periodic_thread.start()
            self.log.info("[AutoBackfill] Periodic thread started (interval=%ss)", self._periodic_interval)

    def stop_periodic(self, timeout: float = 2.0) -> None:
        with self._lock:
            if self._periodic_thread and self._periodic_thread.is_alive():
                self._stop_event.set()
                try:
                    self._periodic_thread.join(timeout=timeout)
                except Exception:
                    pass
            self._periodic_thread = None
            self._stop_event.clear()

    # --------------------------
    # stop / shutdown helpers for threads started by this manager
    # --------------------------
    def stop_once(self, timeout: float = 5.0) -> None:
        """Request stop for the once worker and join it (best-effort)."""
        try:
            with self._lock:
                t = self._once_thread
            if t and t.is_alive():
                # setting _running False will not instantly stop the worker if it is inside blocking calls,
                # but _run_gap_detection_sync is synchronous; we rely on its own exception handling.
                with self._lock:
                    self._running = False
                try:
                    t.join(timeout)
                except Exception:
                    pass
            # clear reference
            with self._lock:
                self._once_thread = None
        except Exception:
            self.log.debug("[AutoBackfill] stop_once failed", exc_info=True)

    def stop_waiter(self, timeout: float = 2.0) -> None:
        """Stop delayed waiter thread if running."""
        try:
            with self._lock:
                t = self._delayed_wait_thread
            if t and t.is_alive():
                # signal stop via stop_event so waiter loop can exit earlier
                self._stop_event.set()
                try:
                    t.join(timeout)
                except Exception:
                    pass
                with self._lock:
                    self._delayed_wait_thread = None
                self._stop_event.clear()
        except Exception:
            self.log.debug("[AutoBackfill] stop_waiter failed", exc_info=True)

    def stop_all(self, timeout: float = 5.0) -> None:
        """
        Stop any running once/periodic/waiter threads started by this manager.
        - timeout: maximum time in seconds to wait for joins (per-thread best-effort)
        """
        try:
            # stop periodic first
            try:
                self.stop_periodic(timeout= min(2.0, timeout))
            except Exception:
                self.log.debug("[AutoBackfill] stop_periodic failed during stop_all", exc_info=True)

            # stop waiter
            try:
                self.stop_waiter(timeout=min(2.0, timeout))
            except Exception:
                self.log.debug("[AutoBackfill] stop_waiter failed during stop_all", exc_info=True)

            # stop once worker
            try:
                self.stop_once(timeout=max(0.5, timeout))
            except Exception:
                self.log.debug("[AutoBackfill] stop_once failed during stop_all", exc_info=True)
        except Exception:
            self.log.debug("[AutoBackfill] stop_all unexpected error", exc_info=True)

    def shutdown(self, timeout: float = 5.0) -> None:
        """
        Graceful shutdown helper to be called by application exit routines.
        Attempts to stop waiter, periodic, and once workers and waits up to `timeout` seconds.
        """
        self.log.info("[AutoBackfill] shutdown requested (timeout=%ss)", timeout)
        try:
            # set global stop flag to prompt waiter/periodic to exit early
            self._stop_event.set()
            self.stop_all(timeout=timeout)
        except Exception:
            self.log.exception("[AutoBackfill] shutdown encountered errors")
        finally:
            # clear stop_event for potential reuse (or leave set if you prefer)
            try:
                self._stop_event.clear()
            except Exception:
                pass
            self.log.info("[AutoBackfill] shutdown completed")

    # --------------------------
    # 蹂댁“ API: ??湲몄씠 諛??ㅻ깄??議고쉶
    # --------------------------
    def get_queue_length(self) -> int:
        try:
            mod = self._find_gap_finder_module()
            if mod:
                fn = getattr(mod, "get_queue_length", None)
                if fn and callable(fn):
                    try:
                        return int(fn())
                    except Exception:
                        self.log.exception("[AutoBackfill] module.get_queue_length failed")
            qpath = os.path.expanduser("~/.timescale_gap_queue.jsonl")
            if os.path.isfile(qpath):
                try:
                    with open(qpath, "r", encoding="utf-8") as fh:
                        return sum(1 for _ in fh)
                except Exception:
                    self.log.exception("[AutoBackfill] counting local queue file failed")
            return 0
        except Exception:
            self.log.exception("[AutoBackfill] get_queue_length unexpected error")
            return 0

    def get_last_snapshot(self, symbol: str, timeframe: str) -> str:
        try:
            connector_cls = None
            candidates = (
                "src.data.timescale.timescale_db",
                "data.timescale.timescale_db",
                "src.data_01.timescale.timescale_db",
                "data_01.timescale.timescale_db",
            )
            for p in candidates:
                try:
                    mod = importlib.import_module(p)
                    connector_cls = getattr(mod, "TimescaleConnector", None)
                    if connector_cls:
                        break
                except Exception:
                    continue
            if connector_cls is None:
                try:
                    here = os.path.dirname(os.path.abspath(__file__))
                    candidate = os.path.join(here, "..", "data", "timescale", "timescale_db.py")
                    candidate = os.path.abspath(candidate)
                    if os.path.isfile(candidate):
                        spec = importlib.util.spec_from_file_location("timescale_db_file", candidate)
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            sys.modules["timescale_db_file"] = mod
                            spec.loader.exec_module(mod)
                            connector_cls = getattr(mod, "TimescaleConnector", None)
                except Exception:
                    self.log.debug("[AutoBackfill] timescale_db file-load fallback failed", exc_info=True)

            if connector_cls is None:
                self.log.warning("[AutoBackfill] TimescaleConnector not found for get_last_snapshot")
                return ""
            conn = connector_cls()
            if not conn.connect():
                self.log.warning("[AutoBackfill] TimescaleConnector.connect failed in get_last_snapshot")
                try:
                    conn.close()
                except Exception:
                    pass
                return ""
            ts = conn.get_last_timestamp(symbol, timeframe)
            try:
                conn.close()
            except Exception:
                pass
            return ts or ""
        except Exception:
            self.log.exception("[AutoBackfill] get_last_snapshot failed")
            return ""


# --------------------------
# ?⑺넗由?諛??깅줉 ?ы띁 (紐⑤뱢 ?덈꺼 ?⑥닔)
# - import ???대뼡 ?몄뒪?댁뒪???앹꽦/?쒖옉?섏? ?딆뒿?덈떎.
# --------------------------
def create_auto_backfill_manager(
    static: Optional[Any] = None,
    logger: Optional[logging.Logger] = None,
    on_run_complete: Optional[Callable[[bool], None]] = None,
    ready_wait_seconds: int = 15,
    ready_poll_interval: float = 1.0,
) -> Optional[AutoBackfillManager]:
    """
    AutoBackfillManager ?몄뒪?댁뒪瑜??앹꽦?섏뿬 諛섑솚?⑸땲??
    - static???쒓났?섎㈃ register_auto_backfill_manager瑜??쒕룄?⑸땲??
    - ?몄뒪?댁뒪???앹꽦留??섎ŉ ?먮룞 ?쒖옉?섏? ?딆뒿?덈떎.
    """
    try:
        mgr = AutoBackfillManager(
            logger=logger,
            on_run_complete=on_run_complete,
            ready_wait_seconds=ready_wait_seconds,
            ready_poll_interval=ready_poll_interval,
        )
    except Exception:
        logging.getLogger(DEFAULT_LOGGER_NAME).exception("[AutoBackfill] Failed to instantiate AutoBackfillManager")
        return None

    # optional register
    if static is not None:
        try:
            register_auto_backfill_manager(mgr, static=static)
        except Exception:
            logging.getLogger(DEFAULT_LOGGER_NAME).debug("[AutoBackfill] register_auto_backfill_manager failed (non-fatal)", exc_info=True)
    return mgr


def register_auto_backfill_manager(mgr: AutoBackfillManager, static: Optional[Any] = None) -> bool:
    """
    mgr瑜?static???덉쟾???깅줉?⑸땲??
    諛섑솚媛? ?깅줉?덉쑝硫?True, ?대? ?깅줉?섏뼱 ?덇굅???ㅽ뙣?섎㈃ False.
    """
    if mgr is None:
        return False
    target_static = static
    if target_static is None:
        # ?먯깋
        candidates = ("src.11_server.app.static", "11_server.app.static", "app.static", "static", "src.app.static")
        for name in candidates:
            try:
                mod = importlib.import_module(name)
                target_static = mod
                break
            except Exception:
                continue
    if target_static is None:
        logging.getLogger(DEFAULT_LOGGER_NAME).debug("[AutoBackfill] No static module available to register AutoBackfillManager")
        return False

    existing = getattr(target_static, "auto_backfill_manager", None) or getattr(target_static, "AutoBackfillManager", None)
    if existing:
        logging.getLogger(DEFAULT_LOGGER_NAME).debug("[AutoBackfill] AutoBackfillManager already registered on static ??skipping duplicate registration")
        return False

    try:
        try:
            setattr(target_static, "auto_backfill_manager", mgr)
        except Exception:
            pass
        try:
            setattr(target_static, "AutoBackfillManager", mgr)
        except Exception:
            pass
        logging.getLogger(DEFAULT_LOGGER_NAME).info("[AutoBackfill] AutoBackfillManager registered to static successfully")
        return True
    except Exception:
        logging.getLogger(DEFAULT_LOGGER_NAME).exception("[AutoBackfill] Failed to register AutoBackfillManager to static")
        return False


def get_registered_auto_backfill_manager(static: Optional[Any] = None) -> Optional[AutoBackfillManager]:
    """
    static?먯꽌 ?깅줉??AutoBackfillManager瑜?諛섑솚?⑸땲???놁쑝硫?None).
    """
    target_static = static
    if target_static is None:
        candidates = ("src.11_server.app.static", "11_server.app.static", "app.static", "static", "src.app.static")
        for name in candidates:
            try:
                mod = importlib.import_module(name)
                target_static = mod
                break
            except Exception:
                continue
    if target_static is None:
        return None
    return getattr(target_static, "auto_backfill_manager", None) or getattr(target_static, "AutoBackfillManager", None)

