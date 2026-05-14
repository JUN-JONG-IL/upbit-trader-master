# -*- coding: utf-8 -*-
"""
실시간 로그 수집 핸들러 (개선판)

책임
- 백그라운드 스레드에서 발생하는 로그를 Thread-Safe deque에 저장
- 모듈명뿐 아니라 메시지 본문 기반 키워드 매칭으로 통신/파이프라인/갭 로그 선별 수집
- UI가 호출하기 쉬운 get_logs(filters) API 제공 (검색어, 레벨, max_rows 지원)
- clear(), set_new_log_callback() 등 UI 연동 메서드 제공

변경 포인트 (중요)
- 더이상 `self.new_log_callback = self.set_new_log_callback` 같은 alias를 만들지 않습니다.
  (이전 구현은 emit()가 매 로그마다 setter를 호출하게 되어 오버헤드/예외를 유발함)
- set_new_log_callback에서 PyQt5가 사용 가능하면 QTimer.singleShot 래퍼를 만들어
  UI 콜백을 메인 스레드로 안전하게 전달합니다.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any

logger = logging.getLogger(__name__)


class RealtimeLogHandler(logging.Handler):
    """
    시스템 모니터 전용 로그 핸들러

    - Thread-Safe deque (최대 max_logs 제한)
    - RealtimeManager / PipelineProcessor / GapFinder 등 관련 로그 수집
    - get_logs(filters) 로 필터링된 최근 항목 반환

    옵션:
    - collect_all: bool (모든 로그 수집 여부)
    """

    DEFAULT_COLLECT_KEYWORDS = ("realtime", "pipeline", "gap", "candle", "websocket")
    DEFAULT_MAX_DISPLAY = 100

    def __init__(
        self,
        max_logs: int = 1000,
        collect_keywords: Optional[List[str]] = None,
        max_display: int = DEFAULT_MAX_DISPLAY,
        collect_all: bool = False,
    ) -> None:
        super().__init__()
        self._max_logs = int(max(100, max_logs))
        self.logs: deque = deque(maxlen=self._max_logs)
        self._lock = threading.Lock()
        self.setLevel(logging.DEBUG)
        self._collect_keywords = tuple(collect_keywords) if collect_keywords else self.DEFAULT_COLLECT_KEYWORDS
        self._max_display = int(max(1, max_display))
        self._collect_all = bool(collect_all)

        # 실제 콜백은 이 필드에 보관합니다. None이면 콜백 없음.
        # set_new_log_callback() 를 통해 설정하세요.
        self._new_log_callback: Optional[Callable[[Dict[str, str]], None]] = None

        # NOTE: 이전 코드의 backward-compat을 위해 'new_log_callback' 속성 접근을 허용하되,
        # 이 속성은 단지 getter/setter로 동작하도록 구현하지 않습니다.
        # (즉, 절대 self.new_log_callback = self.set_new_log_callback 같은 alias를 만들지 않음)
        # 기존 코드가 직접 attribute에 할당하는 경우를 위해 set_new_log_callback을 사용하세요.

    def _record_to_dict(self, record: logging.LogRecord) -> Dict[str, str]:
        try:
            ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        except Exception:
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            message = record.getMessage()
        except Exception:
            try:
                message = str(record.msg)
            except Exception:
                message = ""
        return {
            "time": ts,
            "level": getattr(record, "levelname", "INFO"),
            "module": getattr(record, "name", ""),
            "message": message,
        }

    def emit(self, record: logging.LogRecord) -> None:
        """
        로그 레코드 수집 (백그라운드 스레드에서 호출).

        수집 기준:
          - collect_all=True 면 모든 로그를 수집
          - 그렇지 않으면 모듈명(record.name) 또는 메시지(record.getMessage())에
            collect_keywords 중 하나가 포함되면 수집.
        """
        try:
            try:
                module_lower = (record.name or "").lower()
            except Exception:
                module_lower = ""
            try:
                message_lower = (record.getMessage() or "").lower()
            except Exception:
                message_lower = ""

            should_collect = False
            if self._collect_all:
                should_collect = True
            else:
                for kw in self._collect_keywords:
                    if not kw:
                        continue
                    kw_l = kw.lower()
                    if kw_l in module_lower or kw_l in message_lower:
                        should_collect = True
                        break

            if not should_collect:
                return

            log_item = self._record_to_dict(record)

            # append to deque under lock
            try:
                with self._lock:
                    self.logs.append(log_item)
            except Exception as exc:
                try:
                    self.logs.append(log_item)
                except Exception:
                    logger.debug("[RealtimeLogHandler] 로그 append 실패: %s", exc)

            # 호출은 _new_log_callback만 사용 (이미 set_new_log_callback에서 UI 안전 래퍼를 설정했을 수 있음)
            try:
                cb = self._new_log_callback
                if cb and callable(cb):
                    try:
                        cb(log_item)
                    except Exception as exc:
                        # 콜백 에러는 무시하되 debug로 남김
                        logger.debug("[RealtimeLogHandler] new_log_callback 호출 실패: %s", exc)
            except Exception as exc:
                logger.debug("[RealtimeLogHandler] 콜백 실행 중 예외: %s", exc)

        except Exception as exc:
            logger.debug("[RealtimeLogHandler] emit 처리 중 예외: %s", exc)

    def get_logs(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
        try:
            if filters is None:
                filters = {}

            search = (filters.get("search") or "").strip().lower() if filters is not None else ""
            level_text = (filters.get("level_text") or "").strip() if filters is not None else ""
            try:
                max_rows = int(filters.get("max_rows", self._max_display))
            except Exception:
                max_rows = self._max_display

            websocket_flag = bool(filters.get("websocket")) if "websocket" in (filters or {}) else None
            pipeline_flag = bool(filters.get("pipeline")) if "pipeline" in (filters or {}) else None
            gap_flag = bool(filters.get("gap")) if "gap" in (filters or {}) else None

            with self._lock:
                snapshot = list(self.logs)

            result: List[Dict[str, str]] = []
            for log in snapshot:
                try:
                    lvl = (log.get("level", "INFO") or "INFO").upper()
                    module = (log.get("module", "") or "").lower()
                    message = (log.get("message", "") or "").lower()

                    if level_text:
                        if level_text == "에러만":
                            if lvl not in ("ERROR", "CRITICAL"):
                                continue
                        elif level_text == "경고 이상":
                            if lvl not in ("WARNING", "ERROR", "CRITICAL"):
                                continue

                    if websocket_flag is True:
                        if not ("websocket" in module or "realtime" in module or "ws" in module or "socket" in module):
                            continue
                    if pipeline_flag is True:
                        if "pipeline" not in module and "pipeline" not in message:
                            continue
                    if gap_flag is True:
                        if "gap" not in module and "gap" not in message:
                            continue

                    if search:
                        if search not in module and search not in message:
                            continue

                    result.append(log)
                except Exception:
                    logger.debug("[RealtimeLogHandler] get_logs 필터 처리 중 항목 건너뜀", exc_info=True)
                    continue

            try:
                max_rows = max(1, min(self._max_display, int(max_rows)))
            except Exception:
                max_rows = self._max_display

            if len(result) > max_rows:
                result = result[-max_rows:]

            return result

        except Exception as exc:
            logger.debug("[RealtimeLogHandler] get_logs 실패: %s", exc)
            return []

    def clear(self) -> None:
        try:
            with self._lock:
                self.logs.clear()
        except Exception as exc:
            logger.debug("[RealtimeLogHandler] clear 실패: %s", exc)

    def set_new_log_callback(self, fn: Optional[Callable[[Dict[str, str]], None]]) -> None:
        """
        새로운 로그 콜백 설정.

        If PyQt5 is available and fn is a callable, a wrapper is registered that posts
        the callback to the Qt main thread via QTimer.singleShot(0, ...).
        This prevents the logging thread from calling UI code directly.
        """
        try:
            if fn is None:
                self._new_log_callback = None
                return

            if not callable(fn):
                raise TypeError("new_log_callback must be callable or None")

            # Try to wrap into Qt queued invoker if PyQt5 available
            try:
                from PyQt5.QtCore import QTimer

                def queued_invoker(item: Dict[str, str]) -> None:
                    try:
                        # schedule on Qt main thread
                        QTimer.singleShot(0, lambda it=item: fn(it))
                    except Exception:
                        # fallback: direct call (last resort)
                        try:
                            fn(item)
                        except Exception:
                            logger.debug("[RealtimeLogHandler] queued_invoker direct call 실패", exc_info=True)

                self._new_log_callback = queued_invoker
                return
            except Exception:
                # PyQt not available or wrapping failed; use direct callable
                self._new_log_callback = fn
                return

        except Exception as exc:
            logger.debug("[RealtimeLogHandler] set_new_log_callback 실패: %s", exc)

    # 런타임에 수집 키워드를 변경 가능
    def set_collect_keywords(self, keywords: Optional[List[str]]) -> None:
        try:
            if keywords:
                self._collect_keywords = tuple(keywords)
            else:
                self._collect_keywords = tuple(self.DEFAULT_COLLECT_KEYWORDS)
        except Exception as exc:
            logger.debug("[RealtimeLogHandler] set_collect_keywords 실패: %s", exc)

    def set_collect_all(self, enabled: bool) -> None:
        try:
            self._collect_all = bool(enabled)
        except Exception as exc:
            logger.debug("[RealtimeLogHandler] set_collect_all 실패: %s", exc)


# backward-compatible alias
UILogHandler = RealtimeLogHandler