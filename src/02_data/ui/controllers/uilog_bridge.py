# -*- coding: utf-8 -*-
"""
UILogBridge — RealtimeLogHandler(비동기 수집)와 PyQt UI를 연결하는 브리지

책임:
- RealtimeLogHandler의 new_log_callback을 받아 PyQt 시그널(log_signal)로 전달
- UI에서 안전하게 get_logs(filters), clear(), set_collect_keywords() 등을 호출할 수 있게 위임 제공
- 루트 로거에 핸들러를 설치/제거하는 헬퍼 제공

설계 원칙:
- Pylance 경고를 피하기 위해 시그널 타입은 object로 선언하고,
  메서드 시그니처는 복잡한 제너릭 표기를 최소화합니다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)

# 내부 핸들러 import 시도를 하되 실패하면 None으로 둡니다.
try:
    from .log_handler import RealtimeLogHandler  # type: ignore
except Exception:
    RealtimeLogHandler = None  # type: ignore

# PyQt5 유무 분기
try:
    from PyQt5 import QtCore  # type: ignore
    _HAS_QT = True
except Exception:
    _HAS_QT = False


if _HAS_QT:
    class UILogBridge(QtCore.QObject):
        """Qt 시그널을 통해 실시간 로그를 UI로 전달하는 브리지.

        시그널:
            log_signal: object (실제 전달되는 값은 dict류)
        """
        # PyQt 시그널은 런타임 타입 체크 때문에 object를 쓰는 것이 안전합니다.
        log_signal = QtCore.pyqtSignal(object)

        def __init__(self, handler: Optional[Any] = None):
            super().__init__()
            if handler is None:
                if RealtimeLogHandler is None:
                    raise RuntimeError("RealtimeLogHandler를 찾을 수 없습니다. import 경로를 확인하세요.")
                handler = RealtimeLogHandler()
            self._handler = handler

            # handler 의 콜백 등록 — 존재하는 API에 맞춰 시도
            try:
                # 우선 표준 API를 호출
                setter = getattr(self._handler, "set_new_log_callback", None)
                if callable(setter):
                    setter(self._on_new_log_from_handler)
                else:
                    # 레거시 방식으로 new_log_callback 속성에 직접 할당 시도
                    try:
                        setattr(self._handler, "new_log_callback", self._on_new_log_from_handler)
                    except Exception:
                        logger.debug("[UILogBridge] handler에 콜백 등록 실패(속성 할당)", exc_info=True)
            except Exception:
                logger.debug("[UILogBridge] handler 콜백 등록 시 예외 발생", exc_info=True)

        # -----------------------------------------------------------------
        # Handler -> Bridge 콜백 (비UI 스레드에서 호출될 수 있음)
        # -----------------------------------------------------------------
        def _on_new_log_from_handler(self, log_item: Any) -> None:
            """Handler에서 새 로그가 들어올 때 호출됩니다."""
            try:
                # 실무상 log_item은 dict 형태임. 안전하게 복사하여 emit.
                try:
                    payload = dict(log_item) if isinstance(log_item, dict) else log_item
                except Exception:
                    payload = log_item
                # emit은 다른 스레드에서 호출되어도 queued되어 메인 스레드에서 슬롯이 실행됩니다.
                self.log_signal.emit(payload)
            except Exception:
                logger.debug("[UILogBridge] 시그널 emit 실패", exc_info=True)

        # -------------------------
        # 위임 API (UI에서 호출)
        # -------------------------
        def get_logs(self, filters: Optional[Any] = None) -> list:
            """핸들러의 get_logs를 위임하여 결과 리스트를 반환합니다."""
            try:
                fn = getattr(self._handler, "get_logs", None)
                if callable(fn):
                    return fn(filters) if filters is not None else fn()
            except Exception:
                logger.debug("[UILogBridge] get_logs 호출 실패", exc_info=True)
            return []

        def clear(self) -> None:
            """핸들러 clear 위임."""
            try:
                fn = getattr(self._handler, "clear", None)
                if callable(fn):
                    fn()
            except Exception:
                logger.debug("[UILogBridge] clear 호출 실패", exc_info=True)

        def set_collect_keywords(self, keywords: Optional[list]) -> None:
            """핸들러의 수집 키워드를 변경하도록 위임."""
            try:
                fn = getattr(self._handler, "set_collect_keywords", None)
                if callable(fn):
                    fn(keywords)
            except Exception:
                logger.debug("[UILogBridge] set_collect_keywords 호출 실패", exc_info=True)

        def install_into_root_logger(self, level: int = logging.DEBUG) -> None:
            """루트 로거에 핸들러를 추가하여 전역 로그를 수집하도록 함."""
            try:
                root = logging.getLogger()
                try:
                    self._handler.setLevel(level)
                except Exception:
                    pass
                root.addHandler(self._handler)
            except Exception:
                logger.debug("[UILogBridge] install_into_root_logger 실패", exc_info=True)

        def remove_from_root_logger(self) -> None:
            """루트 로거에서 핸들러를 제거."""
            try:
                root = logging.getLogger()
                try:
                    root.removeHandler(self._handler)
                except Exception:
                    pass
            except Exception:
                logger.debug("[UILogBridge] remove_from_root_logger 실패", exc_info=True)

        @property
        def handler(self) -> Any:
            """내부 핸들러 참조 반환 (테스트/세팅용)."""
            return self._handler

        # 레거시 API 호환: UI가 브리지에 직접 콜백을 설정하려는 경우 위임
        def set_new_log_callback(self, fn: Optional[Callable]) -> None:
            try:
                setter = getattr(self._handler, "set_new_log_callback", None)
                if callable(setter):
                    setter(fn)
                else:
                    # 속성 방식 폴백
                    try:
                        setattr(self._handler, "new_log_callback", fn)
                    except Exception:
                        logger.debug("[UILogBridge] set_new_log_callback 위임 실패", exc_info=True)
            except Exception:
                logger.debug("[UILogBridge] set_new_log_callback 예외", exc_info=True)

else:
    # PyQt 미설치 시 폴백: 시그널 대신 콜백 등록/호출 방식 제공
    class UILogBridge:
        """폴백 브리지 — PyQt 없이도 로직 테스트 가능하도록 최소 API 제공."""

        def __init__(self, handler: Optional[Any] = None):
            if handler is None:
                if RealtimeLogHandler is None:
                    raise RuntimeError("RealtimeLogHandler를 찾을 수 없습니다.")
                handler = RealtimeLogHandler()
            self._handler = handler
            self._callback: Optional[Callable] = None
            try:
                setter = getattr(self._handler, "set_new_log_callback", None)
                if callable(setter):
                    setter(self._on_new_log_from_handler)
                else:
                    try:
                        setattr(self._handler, "new_log_callback", self._on_new_log_from_handler)
                    except Exception:
                        logger.debug("[UILogBridge] handler 콜백 등록 실패 (폴백)", exc_info=True)
            except Exception:
                logger.debug("[UILogBridge] handler 콜백 등록 예외 (폴백)", exc_info=True)

        def _on_new_log_from_handler(self, log_item: Any) -> None:
            """백그라운드 콜백 — 등록된 콜백을 동기 호출합니다."""
            try:
                if self._callback:
                    try:
                        self._callback(dict(log_item) if isinstance(log_item, dict) else log_item)
                    except Exception:
                        # 콜백 실패는 로깅만
                        logger.debug("[UILogBridge] 폴백 콜백 처리 중 예외", exc_info=True)
            except Exception:
                logger.debug("[UILogBridge] 폴백 _on_new_log_from_handler 예외", exc_info=True)

        def get_logs(self, filters: Optional[Any] = None) -> list:
            try:
                fn = getattr(self._handler, "get_logs", None)
                if callable(fn):
                    return fn(filters) if filters is not None else fn()
            except Exception:
                logger.debug("[UILogBridge] get_logs 호출 실패 (폴백)", exc_info=True)
            return []

        def clear(self) -> None:
            try:
                fn = getattr(self._handler, "clear", None)
                if callable(fn):
                    fn()
            except Exception:
                logger.debug("[UILogBridge] clear 호출 실패 (폴백)", exc_info=True)

        def set_collect_keywords(self, keywords: Optional[list]) -> None:
            try:
                fn = getattr(self._handler, "set_collect_keywords", None)
                if callable(fn):
                    fn(keywords)
            except Exception:
                logger.debug("[UILogBridge] set_collect_keywords 호출 실패 (폴백)", exc_info=True)

        def install_into_root_logger(self, level: int = logging.DEBUG) -> None:
            try:
                root = logging.getLogger()
                try:
                    self._handler.setLevel(level)
                except Exception:
                    pass
                root.addHandler(self._handler)
            except Exception:
                logger.debug("[UILogBridge] install_into_root_logger 실패 (폴백)", exc_info=True)

        def remove_from_root_logger(self) -> None:
            try:
                root = logging.getLogger()
                try:
                    root.removeHandler(self._handler)
                except Exception:
                    pass
            except Exception:
                logger.debug("[UILogBridge] remove_from_root_logger 실패 (폴백)", exc_info=True)

        @property
        def handler(self) -> Any:
            return self._handler

        def set_new_log_callback(self, fn: Optional[Callable]) -> None:
            """폴백 API: 내부 콜백을 등록합니다."""
            self._callback = fn