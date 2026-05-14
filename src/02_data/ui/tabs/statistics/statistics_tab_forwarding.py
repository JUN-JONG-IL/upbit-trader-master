# -*- coding: utf-8 -*-
"""
ForwardingRegistrar 모듈
- 파이썬 로깅 루트에 포워딩 핸들러를 등록/제거하는 책임을 담당합니다.
- Callback은 단일 인자(entry: dict)를 받아 처리하도록 설계합니다.
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Callable, Dict, Any

logger = logging.getLogger(__name__)

class ForwardingRegistrar:
    """로깅 포워딩 핸들러 등록기"""

    MARKER = "_StatisticsTabForwardingHandler"

    def __init__(self):
        self._handler = None

    def register(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """callback(entry: dict)을 호출하는 핸들러를 루트 로거에 등록"""
        try:
            root = logging.getLogger()
            for h in list(root.handlers):
                if getattr(h, "name", "") == self.MARKER:
                    self._handler = h
                    return

            class _H(logging.Handler):
                def __init__(self, cb):
                    super().__init__()
                    self.name = ForwardingRegistrar.MARKER
                    self._cb = cb
                    self.setLevel(logging.DEBUG)

                def emit(self, record):
                    try:
                        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
                        entry = {
                            "time": ts,
                            "level": record.levelname,
                            "module": record.name,
                            "message": self.format(record),
                        }
                        self._cb(entry)
                    except Exception:
                        pass

            h = _H(callback)
            h.setFormatter(logging.Formatter("%(asctime)s [%(name)s] [%(levelname)s] %(message)s"))
            root.addHandler(h)
            self._handler = h
            logger.info("[ForwardingRegistrar] handler registered")
        except Exception as e:
            logger.debug("[ForwardingRegistrar] register failed: %s", e)

    def unregister(self) -> None:
        """등록한 핸들러를 제거"""
        try:
            if self._handler is None:
                return
            root = logging.getLogger()
            try:
                root.removeHandler(self._handler)
            except Exception:
                pass
            self._handler = None
            logger.info("[ForwardingRegistrar] handler unregistered")
        except Exception as e:
            logger.debug("[ForwardingRegistrar] unregister failed: %s", e)