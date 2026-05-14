# -*- coding: utf-8 -*-
"""
prelogin.py

PreLoginChecker QThread 瑜?遺꾨━??紐⑤뱢.
- TCP ?ы듃 ?뺤씤 諛?optional health_check 紐⑤뱢 ?몄텧
- UI ?ㅻ젅?쒕줈 ?곹깭 dict瑜?emit ?⑸땲??
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
        optional health 紐⑤뱢??李얠븘 ?ㅽ뻾?⑸땲?? 紐⑤뱢 ?⑥닔媛 coroutine?????덉쑝誘濡?
        ?몄텧?먮뒗 ?꾩슂??寃쎌슦 ?곸쐞?먯꽌 async-safe?섍쾶 ?몄텧?섎룄濡?援ы쁽?댁빞 ?⑸땲??
        ?ш린?쒕뒗 ?⑥닚 ?숆린 ?몄텧(?몄텧?먯뿉???덉쟾???쇰줈 ?먯뼱 梨낆엫 遺꾨━?⑸땲??
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

        # 媛踰쇱슫 gap ?뚰듃 寃??(遺?묒슜 理쒖냼??
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
