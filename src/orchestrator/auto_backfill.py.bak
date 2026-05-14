#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
AutoBackfill 관리기 (방어적 구현)

주요 원칙:
- import 시 어떤 자동 실행도 하지 않습니다.
- 생성(create_auto_backfill_manager) / 등록(register_auto_backfill_manager) / 시작(run_once_nonblocking/start_periodic)
  을 명확히 분리합니다.
- symbols(심볼) 준비 여부를 확인하여 불필요한 빈 실행을 방지합니다.
- waiter 스레드를 통한 재시도는 '대기' 상태로 취급하며, 실제 Gap detection 실행 시에만 True를 반환합니다.
- 모듈 수준 파일-로딩 폴백은 가능한 한 네임스페이스 import를 우선으로 하며, 최후 수단으로만 사용합니다.

추가 개선:
- graceful shutdown API 추가: stop_once(), stop_periodic(), stop_waiter(), stop_all()/shutdown(timeout)
- thread join/timeout 처리 추가
- BackfillStartResult 열거형 추가: run_once_nonblocking() 반환 이유를 상태코드로 분류
- last_start_result 속성: 호출자가 False 반환 원인을 즉시 파악 가능
- 쿨다운 기간(cooldown_seconds) 지원: 동일 호출 반복 억제
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
    """run_once_nonblocking() 호출 결과를 나타내는 상태 코드.

    각 멤버는 다음 추가 속성을 가집니다 (``__new__`` 에서 동적 설정):

    Attributes:
        value (str): 고유 코드 문자열 (예: "STARTED", "ALREADY_RUNNING")
        success (bool): True이면 실제 Gap 탐지 워커가 시작된 것을 의미
        description (str): 사람이 읽을 수 있는 상태 설명 (한글)

    사용법:
        mgr.run_once_nonblocking()
        reason = mgr.last_start_result
        if reason != BackfillStartResult.STARTED:
            print(reason.description)
    """

    STARTED = ("STARTED", True, "Gap 탐지 워커 스레드 시작 성공")
    ALREADY_RUNNING = ("ALREADY_RUNNING", False, "이미 실행 중 — 중복 호출 무시")
    SYMBOLS_NOT_READY_WAITING = (
        "SYMBOLS_NOT_READY_WAITING",
        False,
        "심볼 목록 미준비 — 대기 스레드(waiter) 신규 시작하여 심볼 수신 후 자동 재실행 예정",
    )
    SYMBOLS_NOT_READY_WAITER_RUNNING = (
        "SYMBOLS_NOT_READY_WAITER_RUNNING",
        False,
        "심볼 목록 미준비 — 대기 스레드(waiter)가 이미 동작 중이므로 추가 호출 무시",
    )
    SYMBOLS_NOT_READY_WAITER_ALREADY_WAITING = (
        "SYMBOLS_NOT_READY_WAITER_ALREADY_WAITING",
        False,
        "심볼 목록 미준비 — _waiting 플래그 활성 중으로 중복 대기 방지",
    )
    WAITER_START_FAILED = (
        "WAITER_START_FAILED",
        False,
        "대기 스레드(waiter) 시작 실패 — 스레드 생성 예외 발생",
    )
    THREAD_START_FAILED = (
        "THREAD_START_FAILED",
        False,
        "Gap 탐지 워커 스레드 시작 실패 — OS 스레드 생성 예외 발생",
    )
    COOLDOWN_ACTIVE = (
        "COOLDOWN_ACTIVE",
        False,
        "쿨다운 기간 중 — 최근 False 반환 후 대기 시간이 지나지 않았음",
    )
    NOT_INITIALIZED = (
        "NOT_INITIALIZED",
        False,
        "아직 run_once_nonblocking() 호출 전 (초기 상태)",
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
        logger: 로거 객체
        on_run_complete: gap 탐지 한 회 실행 완료 시 호출되는 콜백(success: bool)
        ready_wait_seconds: 심볼 대기(재시도) 최대 시간 (초)
        ready_poll_interval: 심볼 존재 여부 확인 주기 (초)
        cooldown_seconds: False 반환 후 재호출까지 대기 시간(초). 0이면 쿨다운 없음.
        """
        self.log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

        self.on_run_complete = on_run_complete
        self._periodic_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._periodic_interval = 60
        self._lock = threading.Lock()
        self._running = False
        self._waiting = False  # waiter(심볼 대기) 상태 표시

        # readiness 관련 파라미터
        self._ready_wait_seconds = int(ready_wait_seconds)
        self._ready_poll_interval = float(ready_poll_interval)

        # 쿨다운 기간 (False 반환 후 재호출 억제)
        self._cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._last_false_time: float = 0.0

        # 내부 상태: 마지막으로 생성한 waiter/once 스레드 객체
        self._delayed_wait_thread: Optional[threading.Thread] = None
        self._once_thread: Optional[threading.Thread] = None

        # 마지막 run_once_nonblocking 호출 결과 (호출자가 원인 파악에 활용)
        self.last_start_result: BackfillStartResult = BackfillStartResult.NOT_INITIALIZED

        # 마지막 오류 사유 — UI 상태창 표출용 (한글 구체 설명)
        self.last_error_reason: str = ""

        # 백필 통계 카운터 (UI 표시용)
        self._processed_count: int = 0   # 이번 세션에서 성공적으로 백필된 Gap 수
        self._failed_count: int = 0      # 실패한 Gap 수
        self._pending_count: int = 0     # 마지막 처리 후 남은 Gap 수
        self._execution_state: str = "idle"  # idle / detecting / processing / completed / error

        self.log.debug("[AutoBackfill] Manager initialized (ready_wait=%ss, poll=%ss, cooldown=%ss)",
                       self._ready_wait_seconds, self._ready_poll_interval, self._cooldown_seconds)
    # --------------------------
    # 전역 static 모듈 탐색 유틸
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
    # 심볼 준비 여부 판단
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
    # symbols 준비 대기 후 run
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
    # repo 파일 검색 (보조)
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
    # gap_finder 모듈 탐색/로딩
    # --------------------------
    def _find_gap_finder_module(self):
        candidates = (
            "app.core.gap_finder",
            "app.core.auto_backfill_gap_finder",
            "02_data.timescale.operations.gap_finder",
            "src.02_data.timescale.operations.gap_finder",
            "02_data.timescale.timescale_gap_finder",
            "src.02_data.timescale.timescale_gap_finder",
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

        # 파일 검색(최후 수단)
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
    # 백필 처리 헬퍼 메서드
    # --------------------------

    def _load_backfill_manager_class(self):
        """backfill.auto_backfill_manager.AutoBackfillManager 클래스 동적 로드."""
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
            self.log.debug("[AutoBackfill] BackfillManager 클래스 로드 실패", exc_info=True)
        return None

    def _load_timescale_connector_class(self):
        """TimescaleConnector 클래스를 동적으로 로드합니다 (공통 헬퍼)."""
        _ts_db_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "02_data", "timescale", "timescale_db.py")
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
                self.log.debug("[AutoBackfill] TimescaleConnector 로드 실패: %s", e)
                return None
        return getattr(_mod, "TimescaleConnector", None) if _mod else None

    def _get_pending_gaps_from_db(self, max_items: int = 50) -> list:
        """TimescaleDB gap_fill_queue 테이블에서 pending 상태 Gap 조회 (Redis ZSET 폴백용)."""
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
            self.log.debug("[AutoBackfill] DB pending gaps 조회 실패: %s", e)
            return []

    def _get_pending_count_from_db(self) -> int:
        """TimescaleDB gap_fill_queue 테이블에서 pending 상태 Gap 수 조회."""
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
            self.log.debug("[AutoBackfill] DB pending count 조회 실패: %s", e)
            return -1

    def _process_queue_sync(self, max_gaps: Optional[int] = None) -> tuple:
        """Queue에서 Gap을 꺼내 백필 처리합니다.

        흐름:
          1) in-memory deque에서 pop_next() 로 최대 max_gaps 건을 가져옴
          2) in-memory가 비어있으면 TimescaleDB gap_fill_queue(pending) 조회
          3) backfill/auto_backfill_manager.AutoBackfillManager로 각 gap 백필
          4) 처리 결과(processed, failed, remaining) 반환

        Returns:
            (processed: int, failed: int, remaining: int)
        """
        import asyncio as _asyncio

        processed = 0
        failed = 0

        try:
            prev_state = self._execution_state
            self._execution_state = "processing"

            # ── 성능 설정 SSOT 로드 (UI 다이얼로그에서 변경 가능) ──
            #   None 이면 UI 설정값 사용. 명시적 값이 있으면 그대로 사용.
            try:
                from .backfill.performance_settings import (
                    get_max_concurrency,
                    get_max_gaps_per_cycle,
                )
                _perf_max_gaps = int(get_max_gaps_per_cycle())
                _perf_max_concurrency = int(get_max_concurrency())
            except Exception as _exc:
                self.log.debug(
                    "[AutoBackfill] performance_settings 로드 실패(기본값 사용): %s", _exc,
                )
                _perf_max_gaps = 200
                _perf_max_concurrency = 12
            if max_gaps is None:
                max_gaps = _perf_max_gaps
            else:
                max_gaps = max(1, int(max_gaps))

            # gap_finder 모듈에서 pop/len 함수 가져오기
            mod = self._find_gap_finder_module()
            pop_fn = getattr(mod, "pop_next", None) if mod else None
            get_len_fn = getattr(mod, "get_queue_length", None) if mod else None

            # BackfillManager 클래스 로드 (실제 처리기)
            BfMgr = self._load_backfill_manager_class()
            if BfMgr is None:
                self.log.warning("[AutoBackfill] BackfillManager 없음 - 큐 처리 불가")
                # pending count 갱신 시도
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
            # 사이클별 분류 카운터 초기화 (UI 메시지 명확화용)
            try:
                if hasattr(bf_mgr, "reset_classification"):
                    bf_mgr.reset_classification()
            except Exception:
                pass

            # 처리할 gap 목록 수집
            gaps_to_process: list = []

            # 1차: in-memory deque에서 pop
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

            # 2차: in-memory가 비어있으면 DB pending 조회
            if not gaps_to_process:
                gaps_to_process = self._get_pending_gaps_from_db(max_items=max_gaps)

            if not gaps_to_process:
                self.log.debug("[AutoBackfill] 처리할 Gap 없음 (큐 비어있음)")
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

            self.log.info("[AutoBackfill] 백필 처리 시작: %d건 대상", len(gaps_to_process))

            # 비동기 처리 함수
            async def _process_all_async(gap_list: list):
                # 동시성: SSOT(`backfill_scheduler.performance.max_concurrency`)
                # → 환경변수 `AUTO_BACKFILL_MAX_CONCURRENCY` → 기본 12.
                # 글로벌 AsyncRateLimiter(9 req/s · 550 req/min)가 실제 외부 호출
                # 속도를 안전하게 직렬화하므로 큰 동시성 값도 안전.
                max_concurrency = max(1, min(int(_perf_max_concurrency), 32))
                sem = _asyncio.Semaphore(max_concurrency)

                async def _run_one(gap_dict: dict) -> bool:
                    async with sem:
                        try:
                            return bool(await bf_mgr._process_one_gap(gap_dict))
                        except Exception as _e:
                            self.log.error(
                                "[AutoBackfill] Gap 처리 예외 (symbol=%s): %s",
                                gap_dict.get("symbol", "?"),
                                _e,
                            )
                            return False

                results = await _asyncio.gather(*[_run_one(g) for g in gap_list])
                p = sum(1 for ok in results if ok)
                f = len(results) - p
                return p, f

            # asyncio.run으로 동기 실행 (스레드 내부 — 이벤트 루프 없음)
            try:
                processed, failed = _asyncio.run(_process_all_async(gaps_to_process))
            except Exception as e:
                self.log.error("[AutoBackfill] asyncio.run 실패: %s", e)
                processed = 0
                failed = len(gaps_to_process)

            self._processed_count += processed
            self._failed_count += failed

            # 분류 요약 캐시 (UI 메시지 명확화용)
            try:
                summary_fn = getattr(bf_mgr, "classification_summary", None)
                if callable(summary_fn):
                    self._last_classification_summary = summary_fn()
                else:
                    self._last_classification_summary = ""
            except Exception:
                self._last_classification_summary = ""

            # remaining count 갱신
            # gap_finder 큐 길이 우선 (pop_next로 in-memory deque 소비됨)
            # DB pending count도 확인 (Redis 모드나 DB-기반 처리에서 더 정확)
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
                "[AutoBackfill] 백필 처리 완료: 성공=%d, 실패=%d, 잔여=%d",
                processed, failed, self._pending_count,
            )
            return (processed, failed, self._pending_count)

        except Exception as e:
            self.log.error("[AutoBackfill] _process_queue_sync 오류: %s", e, exc_info=True)
            return (0, 0, self._pending_count)
        finally:
            # 처리 상태 복원 (detecting이었으면 유지, 아니면 idle)
            if self._execution_state == "processing":
                self._execution_state = "idle"

    # --------------------------
    # gap 탐지 동기 실행
    # --------------------------
    def _run_gap_detection_sync(self) -> bool:
        success = False
        try:
            self._execution_state = "detecting"
            mod = self._find_gap_finder_module()
            if mod is None:
                reason = "Gap Finder 모듈을 찾을 수 없음 (설치/경로 확인 필요)"
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
                reason = "Gap Finder 모듈에 호환 진입점 없음 (detect_all_and_enqueue 등 필요)"
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
                    reason = f"Gap 탐지 실행 예외: {type(e).__name__}: {e}"
                    self.last_error_reason = reason
                    self.log.exception("[AutoBackfill] gap finder function raised an exception")
                    called = True
                    break

            if not called:
                try:
                    fn([])
                    called = True
                except Exception as e:
                    reason = f"Gap 탐지 최종 호출 실패: {type(e).__name__}: {e}"
                    self.last_error_reason = reason
                    self.log.exception("[AutoBackfill] final gap finder invocation attempts failed")

            if called:
                self.log.debug("[AutoBackfill] Gap detection finished (called=%s)", called)
                # ──────────────────────────────────────────────────────────────
                # Gap 탐지 완료 후 큐 처리 (백필 실행): 탐지된 Gap을 실제로 DB에 반영
                # 성공 기준: API 호출 성공이 아닌 DB 반영 행수 > 0 또는 Gap 상태 closed
                # ──────────────────────────────────────────────────────────────
                try:
                    # 사이클 시작 — bf_mgr 재생성은 _process_queue_sync 내부에서.
                    processed_in_batch, failed_in_batch, remaining_count = self._process_queue_sync()
                    # 실제 DB 반영이 있었거나 큐가 비어있으면(탐지 단계에서 갭 없음) 성공
                    success = (processed_in_batch > 0) or (remaining_count == 0)
                    if not success and failed_in_batch > 0:
                        # 분류 카운터 요약 우선 — 없으면 기존 단순 메시지로 폴백.
                        # _process_queue_sync 가 사이클 끝에 _last_classification_summary
                        # 속성에 저장한 요약을 사용한다.
                        f_summary = getattr(self, "_last_classification_summary", "")
                        if f_summary:
                            self.last_error_reason = (
                                f"백필 처리 결과 — {f_summary} (잔여 {remaining_count}건)"
                            )
                        else:
                            self.last_error_reason = (
                                f"백필 처리 실패 {failed_in_batch}건 "
                                f"(성공 {processed_in_batch}건, 잔여 {remaining_count}건)"
                            )
                    elif not success and processed_in_batch == 0 and remaining_count == 0:
                        # 처리할 Gap 없음 → gap detection 자체는 성공
                        success = True
                except Exception as e:
                    reason = f"백필 처리 중 오류: {type(e).__name__}: {e}"
                    self.last_error_reason = reason
                    self.log.exception("[AutoBackfill] _process_queue_sync raised an exception")
                    success = False
            else:
                reason = "Gap 탐지 호출 불가 (호환 시그니처 없음)"
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
            reason = f"Gap 탐지 예기치 않은 오류: {type(e).__name__}: {e}"
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
    # 한 번 비동기 실행 (방어적)
    # --------------------------
    def run_once_nonblocking(self, force: bool = False) -> bool:
        """
        gap 탐지를 한 번 비동기 실행.

        반환값: 실제 Gap detection worker(백필 작업)가 시작되었을 때만 True를 반환합니다.
          심볼 미준비로 'waiter' 스레드를 시작한 경우에는 False를 반환(대기 중).
          force=True이면 symbols 준비 체크를 우회하여 바로 worker를 시작(단, 이미 _running이면 False).

        self.last_start_result 에 구체적인 BackfillStartResult 상태코드가 설정됩니다.
        호출자는 이 속성으로 False 반환 원인을 즉시 파악할 수 있습니다.

        쿨다운(cooldown_seconds):
          직전 False 반환 이후 cooldown_seconds 가 지나지 않았으면 COOLDOWN_ACTIVE 반환.
          이미 실행 중(ALREADY_RUNNING) 및 force=True 호출은 쿨다운을 무시합니다.
        """
        def _set(result: BackfillStartResult) -> bool:
            self.last_start_result = result
            if not result.success:  # type: ignore[attr-defined]
                self._last_false_time = time.monotonic()
                # 실패 원인을 last_error_reason 에 기록 (UI 상태창 표출용)
                if not self.last_error_reason:
                    self.last_error_reason = result.description  # type: ignore[attr-defined]
            else:
                # 성공 시 오류 사유 초기화
                self.last_error_reason = ""
            return bool(result)

        with self._lock:
            if self._running:
                self.log.info(
                    "[AutoBackfill] run_once_nonblocking — 상태: %s | %s",
                    BackfillStartResult.ALREADY_RUNNING.value,
                    BackfillStartResult.ALREADY_RUNNING.description,
                )
                return _set(BackfillStartResult.ALREADY_RUNNING)

            # 쿨다운 체크 (force 및 ALREADY_RUNNING 이후는 제외)
            if not force and self._cooldown_seconds > 0 and self._last_false_time > 0:
                elapsed = time.monotonic() - self._last_false_time
                if (
                    self.last_start_result not in (BackfillStartResult.NOT_INITIALIZED, BackfillStartResult.STARTED)
                    and elapsed < self._cooldown_seconds
                ):
                    remaining = self._cooldown_seconds - elapsed
                    self.log.info(
                        "[AutoBackfill] run_once_nonblocking — 상태: %s | %s (남은 쿨다운: %.0fs)",
                        BackfillStartResult.COOLDOWN_ACTIVE.value,
                        BackfillStartResult.COOLDOWN_ACTIVE.description,
                        remaining,
                    )
                    return _set(BackfillStartResult.COOLDOWN_ACTIVE)

            # If not forced and symbols not ready -> start waiter (if not already) and return False (not started)
            if not force and not self._has_symbols_available():
                if self._delayed_wait_thread and self._delayed_wait_thread.is_alive():
                    self.log.info(
                        "[AutoBackfill] run_once_nonblocking — 상태: %s | %s",
                        BackfillStartResult.SYMBOLS_NOT_READY_WAITER_RUNNING.value,
                        BackfillStartResult.SYMBOLS_NOT_READY_WAITER_RUNNING.description,
                    )
                    return _set(BackfillStartResult.SYMBOLS_NOT_READY_WAITER_RUNNING)
                if self._waiting:
                    self.log.info(
                        "[AutoBackfill] run_once_nonblocking — 상태: %s | %s",
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
                        "[AutoBackfill] run_once_nonblocking — 상태: %s | %s (최대 %ss 대기)",
                        BackfillStartResult.SYMBOLS_NOT_READY_WAITING.value,
                        BackfillStartResult.SYMBOLS_NOT_READY_WAITING.description,
                        self._ready_wait_seconds,
                    )
                    return _set(BackfillStartResult.SYMBOLS_NOT_READY_WAITING)
                except Exception as e:
                    self.last_error_reason = f"심볼 대기 스레드 시작 실패: {type(e).__name__}: {e}"
                    self.log.exception("[AutoBackfill] Failed to start delayed waiter thread")
                    return _set(BackfillStartResult.WAITER_START_FAILED)

            # proceed to start worker immediately
            self._running = True

        def _worker():
            try:
                self._run_gap_detection_sync()
            except Exception as e:
                self.last_error_reason = f"워커 실행 중 예외: {type(e).__name__}: {e}"
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
                "[AutoBackfill] run_once_nonblocking — 상태: %s | %s",
                BackfillStartResult.STARTED.value,
                BackfillStartResult.STARTED.description,
            )
            return True
        except Exception as e:
            with self._lock:
                self._running = False
            self.last_error_reason = f"Gap 탐지 워커 스레드 시작 실패: {type(e).__name__}: {e}"
            self.log.exception("[AutoBackfill] Failed to start non-blocking backfill thread")
            return _set(BackfillStartResult.THREAD_START_FAILED)

    def is_running(self) -> bool:
        with self._lock:
            return bool(self._running)

    def is_waiting(self) -> bool:
        return bool(self._waiting)

    # --------------------------
    # 주기 실행 (주기 시작 전 readiness 체크)
    # --------------------------
    def _periodic_loop(self, interval_seconds: int):
        self.log.debug("[AutoBackfill] Periodic loop started (interval=%ss)", interval_seconds)
        while not self._stop_event.wait(interval_seconds):
            try:
                # 심볼 체크 없이 항상 gap 탐지 실행 — gap_finder 가 DB 기준 심볼을 직접 조회합니다.
                # static 모듈에 심볼이 등록되지 않은 UI 전용 실행 환경에서도 동작합니다.
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
    # 보조 API: 큐 길이 및 스냅샷 조회
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
                "src.02_data.timescale.timescale_db",
                "02_data.timescale.timescale_db",
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
# 팩토리 및 등록 헬퍼 (모듈 레벨 함수)
# - import 시 어떤 인스턴스도 생성/시작하지 않습니다.
# --------------------------
def create_auto_backfill_manager(
    static: Optional[Any] = None,
    logger: Optional[logging.Logger] = None,
    on_run_complete: Optional[Callable[[bool], None]] = None,
    ready_wait_seconds: int = 15,
    ready_poll_interval: float = 1.0,
) -> Optional[AutoBackfillManager]:
    """
    AutoBackfillManager 인스턴스를 생성하여 반환합니다.
    - static이 제공되면 register_auto_backfill_manager를 시도합니다.
    - 인스턴스는 생성만 하며 자동 시작하지 않습니다.
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
    mgr를 static에 안전히 등록합니다.
    반환값: 등록했으면 True, 이미 등록되어 있거나 실패하면 False.
    """
    if mgr is None:
        return False
    target_static = static
    if target_static is None:
        # 탐색
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
        logging.getLogger(DEFAULT_LOGGER_NAME).debug("[AutoBackfill] AutoBackfillManager already registered on static — skipping duplicate registration")
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
    static에서 등록된 AutoBackfillManager를 반환합니다(없으면 None).
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
