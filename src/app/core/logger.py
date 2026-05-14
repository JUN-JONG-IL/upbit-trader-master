# -*- coding: utf-8 -*-
"""
SafeLogger - 안전한 로깅 래퍼
- 핸들러 스트림이 닫혀있으면 stderr로 폴백
"""
from __future__ import annotations

import logging
import sys
from typing import Set


class SafeLogger:
    """안전한 로깅 래퍼 (핸들러 닫힘 감지)"""

    def __init__(self, logger: logging.Logger, name: str = "bootstrap"):
        self._logger = logger
        self._name = name

    def _stream_closed(self) -> bool:
        try:
            handlers = getattr(self._logger, "handlers", []) or []
            for h in handlers:
                stream = getattr(h, "stream", None)
                if stream is not None:
                    try:
                        if getattr(stream, "closed", False):
                            return True
                    except Exception:
                        continue
        except Exception:
            pass
        return False

    def _fmt_msg(self, args):
        if not args:
            return ""
        try:
            if isinstance(args[0], str):
                return args[0] % args[1:] if len(args) > 1 else args[0]
        except Exception:
            pass
        try:
            return " ".join(str(a) for a in args)
        except Exception:
            return str(args)

    def _safe_call(self, func, *args, **kwargs):
        try:
            if self._stream_closed():
                try:
                    print(f"[{self._name}] " + self._fmt_msg(args), file=sys.stderr)
                except Exception:
                    pass
                return
        except Exception:
            pass
        try:
            func(*args, **kwargs)
        except Exception:
            try:
                print(f"[{self._name}] logging failed: " + self._fmt_msg(args), file=sys.stderr)
            except Exception:
                pass

    def debug(self, *args, **kwargs):
        self._safe_call(self._logger.debug, *args, **kwargs)

    def info(self, *args, **kwargs):
        self._safe_call(self._logger.info, *args, **kwargs)

    def warning(self, *args, **kwargs):
        self._safe_call(self._logger.warning, *args, **kwargs)

    def error(self, *args, **kwargs):
        self._safe_call(self._logger.error, *args, **kwargs)

    def exception(self, *args, **kwargs):
        kwargs.setdefault("exc_info", True)
        self._safe_call(self._logger.exception, *args, **kwargs)


# 전역 로거 생성 헬퍼
def create_safe_logger(name: str = "bootstrap") -> SafeLogger:
    """SafeLogger 인스턴스 생성"""
    native_logger = logging.getLogger(name)
    return SafeLogger(native_logger, name=name)


# 중복 import 로그 방지용 캐시
_imported_module_logged: Set[str] = set()


def mark_module_imported(module_name: str) -> bool:
    """모듈 import 로그 중복 방지 (True: 처음, False: 이미 로그됨)"""
    if module_name in _imported_module_logged:
        return False
    _imported_module_logged.add(module_name)
    return True