"""
SymbolLoader - 심볼 데이터 비동기 로딩 (v10.0)

책임:
- start_loading(): 백그라운드 스레드에서 심볼 로딩 시작
- MongoDB / static module / Upbit API 순으로 심볼 데이터 조회
- 로딩 완료 후 종목 테이블 업데이트
"""
from __future__ import annotations

import importlib
import logging
import os
import threading
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# MongoDB metadata 컬렉션에서 조회할 최대 심볼 수
_SYMBOL_FETCH_LIMIT: int = int(os.getenv("MONGO_SYMBOL_LIMIT", "10000"))


class SymbolLoader:
    """심볼 데이터 비동기 로딩 관리"""

    def __init__(self, main_window: Any) -> None:
        self.main_window = main_window

    # ─────────────────────────────────────── 로딩 시작 ──

    def start_loading(self) -> None:
        """백그라운드 스레드에서 심볼 로딩을 시작합니다."""
        from PyQt5.QtCore import QTimer

        self.main_window._pending_symbols = []
        t = threading.Thread(target=self._bg_load_symbols, daemon=True)
        t.start()

        poll = QTimer(self.main_window)
        poll.setInterval(250)
        poll.timeout.connect(lambda: self._check_load_done(t, poll))
        poll.start()
        self.main_window._symbol_poll_timer = poll

    # ─────────────────────────────────────── 백그라운드 작업 ──

    def _bg_load_symbols(self) -> None:
        """백그라운드 스레드: 심볼 목록 조회 (static → MongoDB → Upbit API 순)"""
        symbols: List[str] = []

        # 1. static module (서버/메모리)
        try:
            static_mod = None
            for mod_path in ["static", "app.static", "server.static", "server.app.static.static", "server.server.static.static"]:
                try:
                    static_mod = importlib.import_module(mod_path)
                    break
                except Exception:
                    continue

            if static_mod:
                available_symbols = getattr(static_mod, "available_symbols", None)
                if available_symbols:
                    for s in available_symbols:
                        if isinstance(s, (list, tuple)):
                            symbols.append(str(s[1]) if len(s) >= 2 else str(s[0]))
                        else:
                            symbols.append(str(s))
                    logger.info("[SymbolLoader] static에서 %d개 심볼 로드", len(symbols))
        except Exception as e:
            logger.debug("[SymbolLoader] static 모듈 로드 실패: %s", e)

        # 2. MongoDB metadata 컬렉션
        if not symbols:
            try:
                import asyncio

                loop = asyncio.new_event_loop()
                try:
                    symbols = loop.run_until_complete(self._async_fetch_from_mongodb())
                finally:
                    loop.close()
            except Exception as e:
                logger.debug("[SymbolLoader] MongoDB 심볼 조회 실패: %s", e)

        # 3. Upbit API 직접 호출
        if not symbols:
            symbols = self._fetch_upbit_tickers_with_retry()

        self.main_window._pending_symbols = symbols

    async def _async_fetch_from_mongodb(self) -> List[str]:
        """MongoDB metadata 컬렉션에서 활성 심볼 목록 조회"""
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            host = os.getenv("MONGO_HOST", "localhost")
            port = os.getenv("MONGO_PORT", "27017")
            db_name = os.getenv("MONGO_DB", "upbit_trader")
            uri = os.getenv("MONGO_URI") or f"mongodb://{host}:{port}/{db_name}"

            client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
            db = client[db_name]
            docs = await db.metadata.find({"active": True}, {"symbol": 1}).to_list(
                length=_SYMBOL_FETCH_LIMIT
            )
            result = [d["symbol"] for d in docs if d.get("symbol")]
            logger.info("[SymbolLoader] MongoDB에서 %d개 심볼 로드", len(result))
            return result
        except Exception as e:
            logger.debug("[SymbolLoader] MongoDB 심볼 조회 실패: %s", e)
            return []

    def _fetch_upbit_tickers_with_retry(self, max_retries: int = 3) -> List[str]:
        """Upbit API에서 KRW 마켓 심볼 목록 조회"""
        import time

        for attempt in range(1, max_retries + 1):
            try:
                import json
                import urllib.request

                url = "https://api.upbit.com/v1/market/all?isDetails=false"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())

                tickers = [
                    item["market"]
                    for item in data
                    if item.get("market", "").startswith("KRW-")
                ]
                if tickers:
                    logger.info(
                        "[SymbolLoader] Upbit API에서 %d개 심볼 로드 (시도 %d)",
                        len(tickers),
                        attempt,
                    )
                    return tickers
            except Exception as e:
                logger.debug(
                    "[SymbolLoader] Upbit API 조회 실패 (시도 %d/%d): %s",
                    attempt,
                    max_retries,
                    e,
                )
                if attempt < max_retries:
                    time.sleep(1)

        logger.warning("[SymbolLoader] Upbit API 조회 %d회 모두 실패", max_retries)
        return []

    def _check_load_done(self, thread: threading.Thread, timer: Any) -> None:
        """백그라운드 스레드 완료 시 타이머 중지 및 테이블 채우기"""
        if not thread.is_alive():
            timer.stop()
            self._populate_symbol_table()

    def _populate_symbol_table(self) -> None:
        """종목 테이블에 심볼 데이터를 채웁니다."""
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem

        symbols = self.main_window._pending_symbols
        if not symbols:
            logger.debug("[SymbolLoader] 표시할 심볼 없음")
            return

        try:
            table = self.main_window._symbol_table
            if not isinstance(table, QTableWidget):
                if table is not None and hasattr(table, "update_data"):
                    table.update_data(symbols)
                return

            table.setRowCount(len(symbols))
            for row, symbol in enumerate(symbols):
                table.setItem(row, 0, QTableWidgetItem(str(symbol)))
                for col in range(1, 4):
                    table.setItem(row, col, QTableWidgetItem("--"))

            logger.info("[SymbolLoader] 종목 테이블 %d개 항목 표시 완료", len(symbols))
        except Exception as e:
            logger.warning("[SymbolLoader] 종목 테이블 채우기 실패: %s", e)
