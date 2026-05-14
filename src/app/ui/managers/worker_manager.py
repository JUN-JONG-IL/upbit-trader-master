#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
WorkerManager: 워커 생명주기 관리 전담 모듈

변경 사항:
- stop_all / shutdown / collect_all_workers / wait_for_workers 기능 추가
- 다양한 워커 타입(QThread, threading.Thread, custom worker)의 안전한 중지/대기 로직 구현
- bootstrap cleanup에서 호출하여 앱 종료시 QThread 경고 최소화 목적

사용법(권장):
- 앱 초기화 시 WorkerManager.setup_worker_lists(main_window)
- 홈 워커 지연 시작: WorkerManager.start_home_workers(main_window)
- 앱 종료 전 안전 정리: WorkerManager.shutdown(main_window, timeout_ms=2000)
"""
from __future__ import annotations

import logging
import time
from typing import Any, List, Iterable, Optional

try:
    from PyQt5.QtCore import QTimer, QThreadPool, QThread
    _HAS_QT = True
except Exception:
    QTimer = None  # type: ignore[assignment]
    QThreadPool = None  # type: ignore[assignment]
    QThread = None  # type: ignore[assignment]
    _HAS_QT = False

logger = logging.getLogger(__name__)

try:
    from PyQt5 import sip as _sip
    _HAS_SIP = True
except Exception:
    _sip = None  # type: ignore[assignment]
    _HAS_SIP = False


class WorkerManager:
    """워커 생명주기 관리"""

    @staticmethod
    def setup_worker_lists(main_window: Any) -> None:
        """워커 리스트 초기화"""
        main_window.home_worker = [
            getattr(getattr(main_window, "orderbook_widget", None), "ow", None),
            getattr(getattr(main_window, "trade_widget", None), "tw", None),
            getattr(getattr(main_window, "holding_list_widget", None), "hw", None),
            getattr(getattr(main_window, "search_frame_widget", None), "sw", None),
        ]

        userinfo = getattr(main_window, "userinfo_widget", None)
        view = getattr(userinfo, "view", None)
        view_widget = getattr(view, "widget", None) if view else None
        main_window.user_worker = [
            getattr(view_widget, "pw", None) if view_widget else None,
            getattr(getattr(main_window, "detailholdinglist_widget", None), "dw", None),
            getattr(userinfo, "uw", None),
        ]

        main_window.signal_worker = [
            getattr(getattr(main_window, "signal_list_widget", None), "sw", None)
        ]

        logger.debug("[WorkerManager] 워커 리스트 설정 완료")

    @staticmethod
    def start_home_workers(main_window: Any, delay_ms: int = 500) -> None:
        """Home 워커 지연 시작 (UI 프리징 방지)"""
        if not _HAS_QT or QTimer is None:
            return

        def _start() -> None:
            if getattr(main_window, "_home_workers_started", False):
                return

            logger.info("[WorkerManager] Home 워커 시작")
            workers: List[Any] = []

            for attr in ("orderbook_widget", "trade_widget", "holding_list_widget", "search_frame_widget"):
                widget = getattr(main_window, attr, None)
                if not widget:
                    continue
                if _HAS_SIP and _sip is not None and _sip.isdeleted(widget):
                    continue

                for worker_attr in ("ow", "tw", "hw", "sw", "worker"):
                    w = getattr(widget, worker_attr, None)
                    if w:
                        workers.append(w)
                        break

            WorkerManager.start_workers(workers)
            main_window._home_workers_started = True
            logger.info("[WorkerManager] Home 워커 시작 완료")

        QTimer.singleShot(delay_ms, _start)

    @staticmethod
    def start_workers(workers: Iterable[Any]) -> None:
        """워커 목록 시작"""
        for w in workers:
            if not w:
                continue
            try:
                # QThread-like: isRunning method
                if hasattr(w, "isRunning") and callable(getattr(w, "isRunning")):
                    try:
                        if not w.isRunning():
                            w.start()
                    except Exception:
                        # some implementations may raise; try start() anyway
                        try:
                            w.start()
                        except Exception as e:
                            logger.warning("[WorkerManager] 워커 시작 실패: %s", e)
                # threading.Thread-like
                elif hasattr(w, "is_alive") and callable(getattr(w, "is_alive")):
                    try:
                        if not w.is_alive():
                            w.start()
                    except Exception as e:
                        logger.warning("[WorkerManager] 워커(start thread) 시작 실패: %s", e)
                # generic start
                else:
                    if hasattr(w, "start") and callable(getattr(w, "start")):
                        try:
                            w.start()
                        except Exception as e:
                            logger.warning("[WorkerManager] 워커(start generic) 시작 실패: %s", e)
            except Exception as e:
                logger.warning("[WorkerManager] 워커 시작 실패: %s", e)

    @staticmethod
    def stop_workers(workers: Iterable[Any]) -> None:
        """워커 목록 중지(비블로킹 요청만 수행)"""
        for w in workers:
            if not w:
                continue
            try:
                # 우선적으로 명시적 인터페이스 호출
                for fn in ("stop", "stop_all", "shutdown", "close", "terminate", "quit"):
                    f = getattr(w, fn, None)
                    if callable(f):
                        try:
                            f()
                        except Exception:
                            # 일부는 인자 필요하거나 blocking일 수 있음; ignore
                            try:
                                f()  # retry once
                            except Exception:
                                pass
                        # 호출 후 다음 워커로
                        break
                else:
                    # alive 플래그 방식
                    if hasattr(w, "alive"):
                        try:
                            setattr(w, "alive", False)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("[WorkerManager] 워커 중지 실패: %s", e)

    # ---------------------------
    # 새로운 API: 워커 수집 / 대기 / 전체 중지/종료
    # ---------------------------
    @staticmethod
    def collect_all_workers(main_window: Any) -> List[Any]:
        """
        main_window에 등록된 알려진 워커 리스트를 수집하여 반환.
        - setup_worker_lists로 사전에 설정된 항목 사용 우선
        - 없을 경우 위젯들을 탐색하여 발견되는 worker 속성(ow, tw, hw, sw, worker 등) 수집
        """
        workers: List[Any] = []
        try:
            for attr in ("home_worker", "user_worker", "signal_worker"):
                lst = getattr(main_window, attr, None)
                if lst and isinstance(lst, (list, tuple)):
                    for w in lst:
                        if w and w not in workers:
                            workers.append(w)
        except Exception:
            logger.debug("[WorkerManager] collect_all_workers: preset lists retrieval failed", exc_info=True)

        # 추가 탐색: 위젯 속성 스캔
        try:
            widget_attrs = ("orderbook_widget", "trade_widget", "holding_list_widget", "search_frame_widget",
                            "userinfo_widget", "detailholdinglist_widget", "signal_list_widget")
            for wa in widget_attrs:
                widget = getattr(main_window, wa, None)
                if not widget:
                    continue
                for worker_attr in ("ow", "tw", "hw", "sw", "pw", "dw", "uw", "worker"):
                    w = getattr(widget, worker_attr, None)
                    if w and w not in workers:
                        workers.append(w)
        except Exception:
            logger.debug("[WorkerManager] collect_all_workers: widget scan failed", exc_info=True)

        return workers

    @staticmethod
    def _is_worker_running(w: Any) -> bool:
        """여러 인터페이스를 통해 워커가 여전히 동작 중인지 확인"""
        try:
            # QThread-like
            if hasattr(w, "isRunning") and callable(getattr(w, "isRunning")):
                try:
                    return bool(w.isRunning())
                except Exception:
                    pass
            # threading.Thread-like
            if hasattr(w, "is_alive") and callable(getattr(w, "is_alive")):
                try:
                    return bool(w.is_alive())
                except Exception:
                    pass
            # alive 플래그
            if hasattr(w, "alive"):
                try:
                    return bool(getattr(w, "alive"))
                except Exception:
                    pass
            # running 속성
            if hasattr(w, "running"):
                try:
                    return bool(getattr(w, "running"))
                except Exception:
                    pass
            # for QThread instances
            if _HAS_QT and QThread is not None and isinstance(w, QThread):
                try:
                    # QThread.isRunning exists, but covered above
                    return bool(w.isRunning())
                except Exception:
                    pass
        except Exception:
            pass
        return False

    @staticmethod
    def wait_for_workers(workers: Iterable[Any], timeout_ms: int = 2000) -> None:
        """
        지정한 워커들이 종료될 때까지 최대 timeout_ms 만큼 대기.
        - 각 워커별로 가능한 대기 함수를 호출하거나 폴링으로 확인함.
        - 예외는 무시하고 로그만 남김.
        """
        if workers is None:
            return
        start = time.time()
        timeout_s = timeout_ms / 1000.0
        remaining = timeout_s
        # First attempt: try direct wait/join APIs on workers
        for w in workers:
            if not w:
                continue
            try:
                # QThread-like wait
                if hasattr(w, "wait") and callable(getattr(w, "wait")):
                    try:
                        # some wait implementations accept msecs or seconds; try both approaches
                        try:
                            w.wait(timeout_ms)
                        except Exception:
                            # fallback: blocking wait without args (dangerous) so we poll instead
                            pass
                    except Exception:
                        pass
                # thread join
                if hasattr(w, "join") and callable(getattr(w, "join")):
                    try:
                        # threading.Thread.join expects seconds
                        rem = max(0.0, timeout_s - (time.time() - start))
                        if rem > 0:
                            try:
                                w.join(rem)
                            except TypeError:
                                # some join implementations may require integer or none
                                w.join()
                    except Exception:
                        pass
            except Exception:
                logger.debug("[WorkerManager] wait_for_workers: individual wait failed", exc_info=True)

        # Polling loop for remaining running workers
        while True:
            alive_any = False
            for w in workers:
                try:
                    if WorkerManager._is_worker_running(w):
                        alive_any = True
                        break
                except Exception:
                    continue
            if not alive_any:
                logger.debug("[WorkerManager] wait_for_workers: all workers appear stopped")
                return
            if (time.time() - start) >= timeout_s:
                logger.debug("[WorkerManager] wait_for_workers: timeout reached, workers may still be running")
                return
            time.sleep(0.05)

    @staticmethod
    def stop_all(main_window: Any) -> None:
        """
        main_window에 연결된 모든 워커에 대해 중지 요청(stop/shutdown/close/플래그 설정)을 수행.
        (비블로킹) 이후 wait_for_workers로 대기 가능.
        """
        try:
            workers = WorkerManager.collect_all_workers(main_window)
            if not workers:
                logger.debug("[WorkerManager] stop_all: no workers found")
                return
            logger.info("[WorkerManager] stop_all: stopping %d workers", len(workers))
            WorkerManager.stop_workers(workers)
        except Exception:
            logger.debug("[WorkerManager] stop_all failed", exc_info=True)

    @staticmethod
    def shutdown(main_window: Any, timeout_ms: int = 2000) -> None:
        """
        안전 종료 시 사용:
        1) 모든 워커에 중지 요청
        2) QThreadPool.waitForDone(timeout_ms) 호출(가능하면)
        3) wait_for_workers로 실제 종료 대기
        """
        try:
            # 1) stop all workers (request)
            WorkerManager.stop_all(main_window)

            # 2) wait for threads/QRunnable in QThreadPool
            try:
                if _HAS_QT and QThreadPool is not None:
                    pool = QThreadPool.globalInstance()
                    if pool is not None:
                        try:
                            pool.waitForDone(timeout_ms)
                            logger.info("[WorkerManager] QThreadPool.waitForDone(%dms) returned", timeout_ms)
                        except Exception:
                            logger.debug("[WorkerManager] QThreadPool.waitForDone failed", exc_info=True)
            except Exception:
                logger.debug("[WorkerManager] QThreadPool wait attempt failed", exc_info=True)

            # 3) wait for remaining workers via polling
            try:
                workers = WorkerManager.collect_all_workers(main_window)
                WorkerManager.wait_for_workers(workers, timeout_ms=timeout_ms)
            except Exception:
                logger.debug("[WorkerManager] wait_for_workers failed", exc_info=True)
        except Exception:
            logger.debug("[WorkerManager] shutdown unexpected error", exc_info=True)


__all__ = ["WorkerManager"]