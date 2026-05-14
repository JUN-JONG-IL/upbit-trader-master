"""
[Purpose]
Redis 클라이언트

[Responsibilities]
- Redis 연결 관리
- 캐시 저장/조회
"""

from typing import Optional, Any

try:
    from redis import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None


class RedisClient:
    """Redis 클라이언트"""
    
    def __init__(self, host: str = "localhost", port: int = 58530, db: int = 0):
        if not REDIS_AVAILABLE:
            raise ImportError("redis 패키지가 설치되지 않았습니다.")
        
        self.client = Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True
        )
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """값 저장"""
        if ttl:
            self.client.setex(key, ttl, value)
        else:
            self.client.set(key, value)
    
    def get(self, key: str) -> Optional[str]:
        """값 조회"""
        return self.client.get(key)
    
    def ping(self) -> bool:
        """연결 확인"""
        try:
            return self.client.ping()
        except:
            return False