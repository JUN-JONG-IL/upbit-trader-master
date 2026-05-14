# -*- coding: utf-8 -*-
"""
Buffer 모듈
- 로그 항목을 안전하게 버퍼링하고 배치로 꺼내주는 책임만 가집니다.
- 동기(스레드 안전) 방식으로 설계되��� Controller에서 즉시 사용 가능.
"""
from __future__ import annotations
import threading
from collections import deque
from typing import Any, Deque, Dict, List

class BufferManager:
    """로그 버퍼 관리 클래스"""

    def __init__(self, max_pending: int = 100000):
        self._pending: Deque[Dict[str, Any]] = deque()
        self._lock = threading.Lock()
        self.max_pending = int(max_pending)

    def append(self, item: Dict[str, Any]) -> None:
        """새 로그 항목을 버퍼에 추가"""
        with self._lock:
            self._pending.append(item)
            if len(self._pending) > self.max_pending:
                target = int(self.max_pending * 0.8)
                while len(self._pending) > target:
                    try:
                        self._pending.popleft()
                    except Exception:
                        break

    def pop_batch(self, batch_size: int) -> List[Dict[str, Any]]:
        """최대 batch_size 만큼의 항목을 안전하게 추출하여 반환"""
        out: List[Dict[str, Any]] = []
        with self._lock:
            for _ in range(min(batch_size, len(self._pending))):
                try:
                    out.append(self._pending.popleft())
                except Exception:
                    break
        return out

    def snapshot(self) -> List[Dict[str, Any]]:
        """버퍼 현재 상태를 복사본으로 반환(읽기 전용)"""
        with self._lock:
            return list(self._pending)

    def __len__(self) -> int:
        with self._lock:
            return len(self._pending)