#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DB 연결 상태 LED 위젯 (캐시된 모듈 로드로 폴링 비용/로그 감소)
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

# 클래스/모듈 차원의 캐시: 한 번 발견한 health_check 모듈은 재사용
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
        self.setToolTip(f"{db_name}: 확인 중...")
        # 캐시 키(예: "redis")로 health module을 찾음
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
        """한 번만 실행: src/data_01 경로를 sys.path에 추가(중복 삽입 회피)."""
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
            data_dir = os.path.join(repo_root, "src", "data_01")
            # 기존 값들과 중복될 수 있으므로 한 번만 추가
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
                "green": "연결됨",
                "red": "연결 실패",
                "gray": "확인 중..."
            }.get(status, status)
            self.setToolTip(f"{self.db_name}: {status_text}")
        except Exception as e:
            logger.debug("[DBStatusLED] 스타일 적용 실패: %s", e)

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
            logger.debug("[DBStatusLED] %s 체크 예외: %s", self.db_name, e)
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
        health_check 모듈을 캐시에서 찾고, 없다면 후보 네임스페이스/파일로 한 번만 로드.
        이후에는 캐시된 모듈의 함수만 호출합��다.
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
            logger.debug("[DBStatusLED] %s 체크 모듈을 찾을 수 없음 (key=%s)", self.db_name, key)
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
            logger.debug("[DBStatusLED] %s 체크 실패 during call: %s", self.db_name, e)

        return "red"

    def _update_status(self, status: str) -> None:
        if not self._first_check_done:
            status_text = {
                "green": "연결 성공",
                "red": "연결 실패",
                "gray": "드라이버 미설치"
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