#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collector_manager: server-side orchestrator for collectors

- 기존: UpbitWebSocket 우선 사용
- 변경: UpbitWebSocket이 없으면 REST 폴링 기반 UpbitRestCollector를 대신 사용하도록 함.
"""
from __future__ import annotations

import asyncio
import logging
import os
import importlib
from typing import List, Optional

logger = logging.getLogger("collector_manager")

# try to import UpbitWebSocket from data collectors
UpbitWebSocket = None
UpbitRestCollector = None

# 시도 순서: 패키지명 형태로 import 시도 (환경에 따라 달라짐)
_try_names = [
    "src.data_01.collectors.upbit_websocket",
    "data_01.collectors.upbit_websocket",
    "collectors.upbit_websocket",
]

for nm in _try_names:
    try:
        mod = importlib.import_module(nm)
        UpbitWebSocket = getattr(mod, "UpbitWebSocket", None)
        if UpbitWebSocket:
            logger.debug("UpbitWebSocket imported from %s", nm)
            break
    except Exception:
        continue

# UpbitWebSocket이 없으면 REST 폴링 collector 시도
if UpbitWebSocket is None:
    try:
        rc_mod = importlib.import_module("src.data_01.collectors.upbit_rest_collector")
        UpbitRestCollector = getattr(rc_mod, "UpbitRestCollector", None)
        if UpbitRestCollector:
            logger.info("Fallback: UpbitRestCollector 사용(REST 폴링)")
    except Exception:
        try:
            import importlib.util
            from pathlib import Path
            repo_root = Path(__file__).resolve().parents[3]
            candidate = repo_root / "data_01" / "collectors" / "upbit_rest_collector.py"
            if candidate.exists():
                spec = importlib.util.spec_from_file_location("upbit_rest_collector", str(candidate))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore
                UpbitRestCollector = getattr(module, "UpbitRestCollector", None)
                if UpbitRestCollector:
                    logger.info("Fallback file-load: UpbitRestCollector 사용")
        except Exception:
            logger.debug("UpbitRestCollector 파일 로드 실패", exc_info=True)

class CollectorManager:
    def __init__(self):
        self._tasks = {}  # name -> asyncio.Task
        self._clients = {}  # name -> collector instance
        self._loop = asyncio.get_event_loop()

    async def _run_upbit_ws(self, symbols: List[str]) -> None:
        """Run one UpbitWebSocket instance for given symbols (async)."""
        if UpbitWebSocket is not None:
            try:
                ws = UpbitWebSocket(symbols=symbols)
                self._clients["upbit"] = ws
                res = ws.start(symbols=symbols)
                if asyncio.iscoroutine(res):
                    await res
                return
            except asyncio.CancelledError:
                logger.info("UpbitWebSocket cancelled")
                try:
                    await ws.stop()
                except Exception:
                    pass
                raise
            except Exception as exc:
                logger.exception("UpbitWebSocket run failed: %s", exc)

        # Fallback: REST 기반 수집기 실행
        if UpbitRestCollector is not None:
            try:
                rc = UpbitRestCollector()
                self._clients["upbit_rest"] = rc
                # Run blocking start in executor so we don't block the event loop.
                def _start_block():
                    rc.start(symbols)
                await self._loop.run_in_executor(None, _start_block)
            except Exception as exc:
                logger.exception("UpbitRestCollector 실행 실패: %s", exc)
            return

        logger.error("Upbit collector 구현을 찾을 수 없습니다 (UpbitWebSocket/UpbitRestCollector 모두 없음)")
        return

    def start_upbit(self, symbols: Optional[List[str]] = None) -> None:
        """Start Upbit collector as background task. If symbols is None, uses env or default."""
        if symbols is None:
            symbols_env = os.getenv("UPBIT_INITIAL_SYMBOLS")
            if symbols_env:
                symbols = [s.strip() for s in symbols_env.split(",") if s.strip()]
            else:
                symbols = []

        if "upbit" in self._tasks and not self._tasks["upbit"].done():
            logger.info("Upbit collector already running")
            return

        task = self._loop.create_task(self._run_upbit_ws(symbols))
        self._tasks["upbit"] = task
        logger.info("Upbit collector task started (symbols=%d)", len(symbols) if symbols else 0)

    def stop_upbit(self) -> None:
        t = self._tasks.get("upbit")
        client = self._clients.get("upbit_rest") or self._clients.get("upbit")
        try:
            if client and hasattr(client, "stop"):
                try:
                    client.stop()
                except Exception:
                    logger.debug("collector stop() 호출 중 예외", exc_info=True)
        except Exception:
            pass

        if t and not t.done():
            t.cancel()
            logger.info("Requested Upbit collector cancellation")
        else:
            logger.info("No running Upbit collector to stop")

    def status(self) -> dict:
        st = {}
        for name, task in self._tasks.items():
            st[name] = {
                "done": task.done(),
                "cancelled": task.cancelled(),
            }
        return st