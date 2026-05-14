# -*- coding: utf-8 -*-
"""
prelogin.py

PreLoginChecker QThread 를 분리한 모듈.
- TCP 포트 확인 및 optional health_check 모듈 호출
- UI 스레드로 상태 dict를 emit 합니다.
"""
from __future__ import annotations
import os
import time
import socket
import importlib
import logging
from typing import Dict, Optional
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

class PreLoginChecker(QThread):
    sig_status = pyqtSignal(dict)

    def __init__(self, parent=None, timeout: float = 1.0):
        super().__init__(parent)
        self.timeout = float(timeout)
        self.targets = {
            "redis": (os.getenv("REDIS_HOST", "127.0.0.1"), int(os.getenv("REDIS_PORT", "58530"))),
            "timescale": (os.getenv("TIMESCALE_HOST", "127.0.0.1"), int(os.getenv("TIMESCALE_PORT", "58529"))),
            "mongo": (os.getenv("MONGO_HOST", "127.0.0.1"), int(os.getenv("MONGO_PORT", "27017"))),
            "kafka": (os.getenv("KAFKA_HOST", "127.0.0.1"), int(os.getenv("KAFKA_PORT", "9092"))),
        }
        self._stopped = False

    def stop(self):
        self._stopped = True

    def _check_tcp(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=self.timeout):
                return True
        except Exception:
            return False

    def _try_health_module(self, key: str) -> Optional[bool]:
        """
        optional health 모듈을 찾아 실행합니다. 모듈 함수가 coroutine일 수 있으므로
        호출자는 필요한 경우 상위에서 async-safe하게 호출하도록 구현해야 합니다.
        여기서는 단순 동기 호출(호출자에서 안전화)으로 두어 책임 분리합니다.
        """
        candidates = {
            "redis": ["src.data_01.redis.health_check", "src.redis.health_check", "redis.health_check"],
            "mongodb": ["src.data_01.mongodb.health_check", "src.mongodb.health_check", "mongodb.health_check"],
            "mongo": ["src.data_01.mongodb.health_check", "src.mongodb.health_check", "mongodb.health_check"],
            "timescale": ["src.data_01.timescale.health_check", "src.timescale.health_check", "timescale.health_check"],
            "kafka": ["src.data_01.kafka.health_check", "src.kafka.health_check", "kafka.health_check"],
        }.get(key, [])
        for modname in candidates:
            try:
                mod = importlib.import_module(modname)
                for fn_name in ("check_redis_connection", "check_redis", "health_check",
                                "check_mongo_connection", "check_timescale_connection",
                                "check_kafka_connection", "check_kafka"):
                    fn = getattr(mod, fn_name, None)
                    if callable(fn):
                        try:
                            res = fn()
                            if isinstance(res, bool):
                                return res
                            if isinstance(res, dict):
                                st = res.get("status")
                                if isinstance(st, bool):
                                    return st
                                if isinstance(st, str):
                                    return st.lower() in ("ok", "true", "green")
                        except Exception:
                            logger.debug("[PreLoginChecker] health fn failed: %s.%s", modname, fn_name, exc_info=True)
                            continue
            except Exception:
                continue
        return None

    def run(self):
        results: Dict[str, bool] = {}
        for name, (host, port) in self.targets.items():
            if self._stopped:
                break
            tcp_ok = self._check_tcp(host, port)
            health_key = "mongodb" if name == "mongo" else name
            health_ok = None
            if tcp_ok:
                try:
                    health_ok = self._try_health_module(health_key)
                except Exception:
                    health_ok = None
            final_ok = True if health_ok is True else (False if health_ok is False else bool(tcp_ok))
            results[name] = final_ok
            try:
                self.sig_status.emit({name: final_ok})
            except Exception:
                pass
            time.sleep(0.08)

        # 가벼운 gap 힌트 검사 (부작용 최소화)
        try:
            gf_mod = importlib.import_module("src.data_01.timescale.operations.gap_finder")
            gap_hint = False
            if hasattr(gf_mod, "find_gaps"):
                try:
                    res = getattr(gf_mod, "find_gaps")([], interval="1m")
                    gap_hint = bool(res)
                except Exception:
                    gap_hint = False
            elif hasattr(gf_mod, "GapFinder"):
                try:
                    GF = getattr(gf_mod, "GapFinder")
                    inst = GF(symbols=[])
                    gap_hint = bool(getattr(inst, "has_gaps", lambda: False)())
                except Exception:
                    gap_hint = False
            if gap_hint:
                results["gap_hint"] = True
        except Exception:
            pass

        try:
            self.sig_status.emit(results)
        except Exception:
            pass