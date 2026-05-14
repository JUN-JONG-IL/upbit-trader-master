#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
UIStateManager
- UI 전역 상태(현재 선택 심볼 등)를 관리하고 변경 이벤트를 발행합니다.
- PyQt5가 없거나 헤드리스 환경에서도 동작하도록 경량 Signal 구현을 사용합니다.
- 다른 모듈은 `from src.app.ui.ui_state_manager import ui_state_manager` 로 싱글톤을 사용하세요.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Tuple, Optional

logger = logging.getLogger(__name__)


# 경량 Signal 구현: PyQt 의 pyqtSignal 대체용으로 connect/emit API 제공
class Signal:
    """간단한 시그널 구현: connect(fn), disconnect(fn), emit(*args, **kwargs)"""
    def __init__(self) -> None:
        self._slots: List[Callable[..., Any]] = []

    def connect(self, fn: Callable[..., Any]) -> None:
        try:
            if fn not in self._slots:
                self._slots.append(fn)
        except Exception:
            # 안전하게 무시
            logger.exception("[UIStateManager.Signal] connect 중 예외 발생")

    def disconnect(self, fn: Callable[..., Any]) -> None:
        try:
            self._slots = [s for s in self._slots if s != fn]
        except Exception:
            logger.exception("[UIStateManager.Signal] disconnect 중 예외 발생")

    def emit(self, *args: Any, **kwargs: Any) -> None:
        # 슬롯 호출 시 개별 예외는 무시하고 다른 슬롯은 계속 호출
        for slot in list(self._slots):
            try:
                slot(*args, **kwargs)
            except Exception:
                logger.exception("[UIStateManager.Signal] 슬롯 호출 중 예외 발생")


# PyQt5 import 시도는 하지 않음: 여기서는 경량 Signal 만으로 충분
# (PyQt 시그널을 반드시 사용해야 하는 경우 이후 확장 가능)

class UIStateManager:
    """
    전역 UI 상태 관리자 (싱글톤으로 사용 권장)
    책임:
    - 현재 소스(source)와 심볼(symbol) 상태 관리
    - state 변경 시 symbol_changed 시그널 발행
    """
    def __init__(self) -> None:
        # current: (source, symbol) 쌍을 저장합니다. 예: ("upbit", "KRW-BTC")
        self._current_source: Optional[str] = None
        self._current_symbol: Optional[str] = None

        # 외부에서 연결해서 변경을 수신할 수 있는 시그널
        # 시그널 호출 signature: emit(source: str, symbol: str)
        self.symbol_changed: Signal = Signal()

    # 상태 조회
    def get_symbol(self) -> Tuple[Optional[str], Optional[str]]:
        """현재 (source, symbol) 반환"""
        return (self._current_source, self._current_symbol)

    # 상태 설정
    def set_symbol(self, source: str, symbol: str) -> bool:
        """
        심볼 변경 시도.
        - 변경이 발생하면 symbol_changed.emit(source, symbol) 호출
        - 동일한 값이면 아무 동작도 하지 않고 False 반환
        반환:
        - True: 변경 발생 및 시그널 발행
        - False: 변경 없음
        """
        try:
            # 정상화: 입력을 문자열로 변환
            s_src = None if source is None else str(source)
            s_sym = None if symbol is None else str(symbol)

            # 변경이 없으면 무시
            if s_src == self._current_source and s_sym == self._current_symbol:
                return False

            # 상태 갱신
            self._current_source = s_src
            self._current_symbol = s_sym

            # 변경 시그널 발행 (예외는 내부에서 처리)
            try:
                self.symbol_changed.emit(s_src, s_sym)
            except Exception:
                logger.exception("[UIStateManager] symbol_changed.emit 호출 중 예외 발생")

            return True
        except Exception:
            logger.exception("[UIStateManager] set_symbol 처리 중 예외 발생")
            return False

    # 편의 메서드: 심볼 초기화
    def clear_symbol(self) -> None:
        """현재 심볼을 제거하고 시그널을 발행합니다."""
        try:
            self._current_source = None
            self._current_symbol = None
            try:
                self.symbol_changed.emit(None, None)
            except Exception:
                logger.exception("[UIStateManager] clear_symbol: emit 예외")
        except Exception:
            logger.exception("[UIStateManager] clear_symbol 중 예외 발생")

    def debug_info(self) -> dict:
        """디버그용 상태 정보"""
        return {
            "current_source": self._current_source,
            "current_symbol": self._current_symbol,
            "connected_slots": len(self.symbol_changed._slots) if hasattr(self.symbol_changed, "_slots") else 0
        }


# 모듈 레벨 싱글톤 (다른 모듈은 이 인스턴스를 import 해서 사용)
ui_state_manager = UIStateManager()