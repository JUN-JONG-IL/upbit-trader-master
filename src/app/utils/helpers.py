# -*- coding: utf-8 -*-
"""
앱 공통 헬퍼 함수 및 경량 RealtimeManager 어댑터(안전한 콜백 API 제공)

변경/추가 요지:
- format_timestamp, safe_get 기본 유틸 유지
- RealtimeManager 클래스 추가:
  - set_on_candle, register_callback, add_listener, subscribe, on_candle 속성 등 표준 콜백 API 제공
  - start/stop, alive 플래그 제공 (네트워크 연결 없음 — 스텁/어댑터 역할)
  - 외부에서 실시간 데이터(예: 테스트/시뮬레이션 또는 WS 핸들러) 주입을 위해 feed_candle() 제공
  - 내부적으로 예외를 흘리지 않도록 방어적 호출/로깅
- AI/ML 관련 동작이나 우선순위 설정은 전혀 활성화하지 않음(초기 상태 유지)
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Callable, Iterable, List
import threading
import logging

KST = timezone(timedelta(hours=9))

# ---------------------------
# 기본 유틸
# ---------------------------
def format_timestamp(dt: Optional[datetime] = None) -> str:
    """datetime을 KST ISO 포맷 문자열로 반환. None이면 현재 시각 사용.

    Parameters
    ----------
    dt: timezone-aware datetime 또는 None.
        None이면 현재 UTC 시각을 사용한다.
        naive datetime(tzinfo 없음)이 전달되면 UTC로 가정하고 변환한다.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    # naive datetime은 UTC로 간주
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).isoformat()


def safe_get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    """딕셔너리에서 안전하게 값을 조회"""
    try:
        return d.get(key, default)
    except Exception:
        return default

# ---------------------------
# RealtimeManager (경량 어댑터)
# ---------------------------
class RealtimeManager:
    """
    경량 RealtimeManager 어댑터

    목적:
    - pipeline_loader 등에서 기대하는 표준 콜백 API를 제공하여
      RealtimeManager와 Pipeline 간의 연결을 정석적으로 수행할 수 있게 함.
    - 실제 네트워크(예: WebSocket) 연결은 하지 않으며, 외부에서 feed_candle()으로 데이터 주입 가능.
    - 안전성: 내부 예외는 로깅 처리하고 호출자에게 전파하지 않음.

    사용 예:
        rm = RealtimeManager(codes=['KRW-BTC'], logger=static.log)
        rm.set_on_candle(process_fn)
        rm.start()
        rm.feed_candle({'symbol':'KRW-BTC', 'ts':..., 'open':...})
    """

    def __init__(self, codes: Optional[Iterable[str]] = None, logger: Optional[logging.Logger] = None):
        # codes는 iterable 또는 None
        self._codes: List[str] = []
        if codes:
            try:
                self._codes = [str(c) for c in codes if c is not None]
            except Exception:
                try:
                    # if codes is a single string
                    self._codes = [str(codes)]
                except Exception:
                    self._codes = []
        self._callbacks: List[Callable[[Any], None]] = []
        self._on_candle: Optional[Callable[[Any], None]] = None
        self._lock = threading.RLock()
        self.alive = False
        self.logger = logger or logging.getLogger("RealtimeManager")

    # ---------------------------
    # 코드/심볼 관련
    # ---------------------------
    def codes(self) -> List[str]:
        """현재 구독(또는 관리) 중인 코드 리스트 반환 (복사본)."""
        with self._lock:
            return list(self._codes)

    def set_codes(self, codes: Iterable[str]) -> None:
        """관리할 코드 리스트를 설정합니다."""
        with self._lock:
            try:
                self._codes = [str(c) for c in codes if c is not None]
            except Exception:
                self._codes = []

    # ---------------------------
    # 생명 주기
    # ---------------------------
    def start(self) -> None:
        """RealtimeManager 시작 표시(네트워크 연결은 없음)."""
        with self._lock:
            if not self.alive:
                self.alive = True
                try:
                    self.logger.debug("[RealtimeManager] started (adapter mode)")
                except Exception:
                    pass

    def stop(self) -> None:
        """RealtimeManager 중지 표시."""
        with self._lock:
            if self.alive:
                self.alive = False
                try:
                    self.logger.debug("[RealtimeManager] stopped (adapter mode)")
                except Exception:
                    pass

    # ---------------------------
    # 콜백 등록 / 관리 (pipeline_loader가 기대하는 API)
    # ---------------------------
    def set_on_candle(self, fn: Callable[[Any], None]) -> None:
        """단일 콜백을 설정(기존 콜백 리스트에도 추가)."""
        if fn is None:
            return
        with self._lock:
            self._on_candle = fn
            # 또한 콜백 리스트에도 보관(중복 방지)
            if fn not in self._callbacks:
                self._callbacks.append(fn)
            try:
                self.logger.debug("[RealtimeManager] set_on_candle registered: %s", getattr(fn, "__name__", repr(fn)))
            except Exception:
                pass

    @property
    def on_candle(self) -> Optional[Callable[[Any], None]]:
        """on_candle 속성 접근자."""
        with self._lock:
            return self._on_candle

    @on_candle.setter
    def on_candle(self, fn: Callable[[Any], None]) -> None:
        """on_candle 속성 설정자(assignment) — pipeline_loader가 직접 할당할 때 사용."""
        self.set_on_candle(fn)

    def register_callback(self, fn: Callable[[Any], None]) -> None:
        """콜백을 추가로 등록합니다."""
        if fn is None:
            return
        with self._lock:
            if fn not in self._callbacks:
                self._callbacks.append(fn)
            try:
                self.logger.debug("[RealtimeManager] register_callback: %s", getattr(fn, "__name__", repr(fn)))
            except Exception:
                pass

    # alias methods to match pipeline_loader expectations
    add_listener = register_callback
    subscribe = register_callback

    # ---------------------------
    # 데이터 주입 / 디스패치
    # ---------------------------
    def feed_candle(self, candle: Any) -> None:
        """
        외부(collector, test harness 등)에서 틱/캔들 데이터를 주입하는 용도.
        등록된 콜백들을 안전하게 호출한다.
        """
        # 방어: None 또는 비활성 시 무시
        with self._lock:
            if not self.alive:
                # 허용: 비활성 상태에서도 콜백을 호출하지 않음
                try:
                    self.logger.debug("[RealtimeManager] feed_candle ignored (not alive)")
                except Exception:
                    pass
                return
            callbacks = list(self._callbacks)
            on_candle_cb = self._on_candle

        # 먼저 on_candle 단일 콜백 호출(우선)
        if on_candle_cb:
            try:
                on_candle_cb(candle)
            except Exception:
                try:
                    self.logger.exception("[RealtimeManager] exception in on_candle callback")
                except Exception:
                    pass

        # 그리고 등록된 콜백들 호출
        for cb in callbacks:
            try:
                cb(candle)
            except Exception:
                try:
                    self.logger.exception("[RealtimeManager] exception in registered callback")
                except Exception:
                    pass

    # ---------------------------
    # 유틸: 안전한 브리징(실제 collector/WS에서 사용)
    # ---------------------------
    def handle_incoming_message(self, raw_msg: Any) -> None:
        """
        외부에서 들어오는 메시지를 받아 내부 판별 후 feed_candle로 전달.
        (실제 파서/정규화는 실행환경에 맞게 collector에서 처리하는 것이 바람직함.)
        """
        try:
            # 기본적으로 메시지를 그대로 candle로 간주
            candle = raw_msg
            self.feed_candle(candle)
        except Exception:
            try:
                self.logger.exception("[RealtimeManager] handle_incoming_message failed")
            except Exception:
                pass

    # ---------------------------
    # 디버그/상태
    # ---------------------------
    def info(self) -> Dict[str, Any]:
        """간단한 상태 정보(디버그용)를 반환합니다."""
        with self._lock:
            return {
                "alive": bool(self.alive),
                "codes": list(self._codes),
                "callbacks": len(self._callbacks),
                "has_on_candle": self._on_candle is not None,
            }