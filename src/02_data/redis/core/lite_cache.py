"""
[Purpose]
인메모리 캐시 (Redis 대체)

[Responsibilities]
- 실행 파일 배포 시 Redis 대체
- TTL 지원
"""

import time
import threading
from typing import Any, Optional, Dict


class LiteCache:
    """경량 캐시 (인메모리)"""
    
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._ttl: Dict[str, float] = {}
        self._lock = threading.Lock()
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """값 저장"""
        with self._lock:
            self._data[key] = value
            if ttl:
                self._ttl[key] = time.time() + ttl
    
    def get(self, key: str) -> Optional[Any]:
        """값 조회"""
        with self._lock:
            if key in self._ttl:
                if time.time() > self._ttl[key]:
                    del self._data[key]
                    del self._ttl[key]
                    return None
            
            return self._data.get(key)
    
    def delete(self, key: str):
        """키 삭제"""
        with self._lock:
            if key in self._data:
                del self._data[key]
            if key in self._ttl:
                del self._ttl[key]
    
    def exists(self, key: str) -> bool:
        """키 존재 확인"""
        return self.get(key) is not None
    
    def setex(self, key: str, ttl: int, value: Any):
        """TTL과 함께 저장 (Redis 호환)"""
        self.set(key, value, ttl)
    
    def ping(self) -> bool:
        """연결 확인 (Redis 호환)"""
        return True
