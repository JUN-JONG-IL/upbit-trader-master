#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DB ?곌껐 ?곹깭 LED ?꾩젽 (罹먯떆??紐⑤뱢 濡쒕뱶濡??대쭅 鍮꾩슜/濡쒓렇 媛먯냼)
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Optional, Callable, Any, Dict

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QLabel
    from PyQt5.QtCore import QTimer
    _HAS_QT = True
except Exception:
    QLabel = object  # type: ignore
    QTimer = None    # type: ignore
    _HAS_QT = False

_LED_COLORS = {
    "green": "#2ECC40",
    "red": "#FF4136",
    "gray": "#808080",
}

_LED_STYLE_TEMPLATE = """
    QLabel {{
        background-color: {color};
        border-radius: 8px;
        min-width: 16px;
        min-height: 16px;
        max-width: 16px;
        max-height: 16px;
    }}
"""

_POLL_INTERVAL_MS = 1000

# ?대옒??紐⑤뱢 李⑥썝??罹먯떆: ??踰?諛쒓껄??health_check 紐⑤뱢? ?ъ궗??
_module_cache: Dict[str, Any] = {}

def _call_maybe_async(func: Callable[..., Any], *args, **kwargs) -> Any:
    import asyncio as _aio
    try:
        res = func(*args, **kwargs)
        if hasattr(res, "__await__") or _aio.iscoroutine(res):
            try:
                return _aio.run(res)
            except Exception as e:
                logger.debug("[DBStatusLED] asyncio.run failed: %s", e)
                return None
        return res
    except Exception as e:
        logger.debug("[DBStatusLED] call failed: %s", e)
        return None

class DBStatusLED(QLabel):  # type: ignore[misc]
    def __init__(self, db_name: str, parent=None) -> None:
        if not _HAS_QT:
            super().__init__()
            self.db_name = db_name
            self.status = "gray"
            return

        super().__init__(parent)
        self.db_name = db_name
        self.status = "gray"
        self._checking = False
        self._first_check_done = False
        self._apply_style("gray")
        self.setToolTip(f"{db_name}: ?뺤씤 以?..")
        # 罹먯떆 ???? "redis")濡?health module??李얠쓬
        self._health_module = None
        self._ensure_data_dir_in_sys_path()
        try:
            self._timer = QTimer(self)
            self._timer.setInterval(_POLL_INTERVAL_MS)
            self._timer.timeout.connect(self._trigger_check)
            self._timer.start()
        except Exception as e:
            logger.debug("[DBStatusLED] QTimer init failed: %s", e)
            self._timer = None

    def _ensure_data_dir_in_sys_path(self) -> None:
        """??踰덈쭔 ?ㅽ뻾: src/data_01 寃쎈줈瑜?sys.path??異붽?(以묐났 ?쎌엯 ?뚰뵾)."""
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
            data_dir = os.path.join(repo_root, "src", "data_01")
            # 湲곗〈 媛믩뱾怨?以묐났?????덉쑝誘濡???踰덈쭔 異붽?
            if os.path.isdir(data_dir) and data_dir not in sys.path:
                sys.path.insert(0, data_dir)
        except Exception:
            pass

    def _apply_style(self, status: str) -> None:
        if not _HAS_QT:
            return
        color = _LED_COLORS.get(status, _LED_COLORS["gray"])
        try:
            self.setStyleSheet(_LED_STYLE_TEMPLATE.format(color=color))
            status_text = {
                "green": "?곌껐??,
                "red": "?곌껐 ?ㅽ뙣",
                "gray": "?뺤씤 以?.."
            }.get(status, status)
            self.setToolTip(f"{self.db_name}: {status_text}")
        except Exception as e:
            logger.debug("[DBStatusLED] ?ㅽ????곸슜 ?ㅽ뙣: %s", e)

    def _trigger_check(self) -> None:
        if self._checking:
            return
        self._checking = True
        t = threading.Thread(target=self._run_check, daemon=True)
        try:
            t.start()
        except Exception as e:
            self._checking = False
            logger.debug("[DBStatusLED] thread start failed: %s", e)

    def _run_check(self) -> None:
        try:
            result = self._do_check()
        except Exception as e:
            logger.debug("[DBStatusLED] %s 泥댄겕 ?덉쇅: %s", self.db_name, e)
            result = "red"
        finally:
            self._checking = False

        if _HAS_QT and QTimer is not None:
            try:
                QTimer.singleShot(0, lambda: self._update_status(result))
            except Exception:
                pass

    def _do_check(self) -> str:
        """
        health_check 紐⑤뱢??罹먯떆?먯꽌 李얘퀬, ?녿떎硫??꾨낫 ?ㅼ엫?ㅽ럹?댁뒪/?뚯씪濡???踰덈쭔 濡쒕뱶.
        ?댄썑?먮뒗 罹먯떆??紐⑤뱢???⑥닔留??몄텧?⑼옙占쎈떎.
        """
        name = self.db_name.lower()

        # determine key: timescale/mongo/redis
        key = None
        if "timescale" in name:
            key = "timescale"
        elif "mongo" in name:
            key = "mongodb"
        elif "redis" in name:
            key = "redis"
        else:
            return "gray"

        # cached module lookup (class-level cache)
        mod = _module_cache.get(key)
        if mod is None:
            # try package names first
            candidates = {
                "timescale": ["src.data_01.timescale.health_check", "src.timescale.health_check", "timescale.health_check"],
                "mongodb": ["src.data_01.mongodb.health_check", "src.mongodb.health_check", "mongodb.health_check"],
                "redis": ["src.data_01.redis.health_check", "src.redis.health_check", "redis.health_check"],
            }.get(key, [])
            for nm in candidates:
                try:
                    mod = __import__(nm, fromlist=["*"])
                    _module_cache[key] = mod
                    logger.debug("[DBStatusLED] cached module %s for key=%s", getattr(mod, "__file__", None), key)
                    break
                except Exception:
                    continue

            # file fallback (very last resort)
            if mod is None:
                try:
                    here = os.path.dirname(os.path.abspath(__file__))
                    repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
                    file_cands = {
                        "redis": [
                            os.path.join(repo_root, "src", "data_01", "redis", "health_check.py"),
                            os.path.join(repo_root, "redis", "health_check.py"),
                        ],
                        "mongodb": [
                            os.path.join(repo_root, "src", "data_01", "mongodb", "health_check.py"),
                        ],
                        "timescale": [
                            os.path.join(repo_root, "src", "data_01", "timescale", "health_check.py"),
                        ],
                    }.get(key, [])
                    for f in file_cands:
                        if os.path.isfile(f):
                            import importlib.util as _il
                            spec = _il.spec_from_file_location(f"tmp_{key}_health", f)
                            if spec and spec.loader:
                                m = _il.module_from_spec(spec)
                                spec.loader.exec_module(m)
                                mod = m
                                _module_cache[key] = mod
                                logger.debug("[DBStatusLED] file-cached module %s for key=%s", f, key)
                                break
                except Exception as e:
                    logger.debug("[DBStatusLED] file-level module fallback failed: %s", e)

        if mod is None:
            logger.debug("[DBStatusLED] %s 泥댄겕 紐⑤뱢??李얠쓣 ???놁쓬 (key=%s)", self.db_name, key)
            return "red"

        # call health function
        try:
            if key == "timescale":
                fn = getattr(mod, "check_timescale_connection", None)
                if callable(fn):
                    res = _call_maybe_async(fn)
                    if isinstance(res, bool):
                        return "green" if res else "red"
                    if isinstance(res, str):
                        return res
            elif key == "mongodb":
                fn = getattr(mod, "check_mongo_connection", None) or getattr(mod, "health_check", None)
                if callable(fn):
                    res = _call_maybe_async(fn)
                    if isinstance(res, bool):
                        return "green" if res else "red"
                    if isinstance(res, dict) and "status" in res:
                        return res["status"]
                    if isinstance(res, str):
                        return res
            elif key == "redis":
                fn = getattr(mod, "check_redis_connection", None) or getattr(mod, "health_check", None)
                if callable(fn):
                    res = _call_maybe_async(fn)
                    if isinstance(res, bool):
                        return "green" if res else "red"
                    if isinstance(res, dict) and "status" in res:
                        return res["status"]
                    if isinstance(res, str):
                        return res
        except Exception as e:
            logger.debug("[DBStatusLED] %s 泥댄겕 ?ㅽ뙣 during call: %s", self.db_name, e)

        return "red"

    def _update_status(self, status: str) -> None:
        if not self._first_check_done:
            status_text = {
                "green": "?곌껐 ?깃났",
                "red": "?곌껐 ?ㅽ뙣",
                "gray": "?쒕씪?대쾭 誘몄꽕移?
            }.get(status, status)
            logger.info("[DBStatusLED] %s: %s", self.db_name, status_text)
            self._first_check_done = True

        if self.status != status:
            self.status = status

        self._apply_style(status)

    def stop(self) -> None:
        if _HAS_QT and getattr(self, "_timer", None) is not None:
            try:
                self._timer.stop()
            except Exception:
                pass
            try:
                self._timer.timeout.disconnect(self._trigger_check)
            except Exception:
                pass
            self._timer = None

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass
