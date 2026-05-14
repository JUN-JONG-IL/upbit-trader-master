#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Feature Store - Redis/ClickHouse 기반 특징 저장소
실시간 특징 조회 및 히스토리 관리
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis not available. Using in-memory store.")

logger = logging.getLogger(__name__)


@dataclass
class Feature:
    """특징 데이터 모델"""
    symbol: str
    timestamp: datetime
    features: Dict[str, float]
    metadata: Optional[Dict[str, Any]] = None


class FeatureStore:
    """
    Redis 기반 특징 저장소
    
    실시간 특징 저장/조회 및 히스토리 관리
    """
    
    def __init__(self, 
                 redis_host: str = "localhost",
                 redis_port: int = 6379,
                 redis_db: int = 0,
                 ttl_seconds: int = 86400):  # 24시간
        """
        Args:
            redis_host: Redis 호스트
            redis_port: Redis 포트
            redis_db: Redis 데이터베이스 번호
            ttl_seconds: 특징 데이터 TTL (초)
        """
        self.ttl_seconds = ttl_seconds
        self._memory_store: Dict[str, Feature] = {}
        
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=True
                )
                # 연결 테스트
                self.redis_client.ping()
                logger.info(f"Redis 연결 성공: {redis_host}:{redis_port}")
                self.use_redis = True
            except Exception as e:
                logger.warning(f"Redis 연결 실패: {e}. 메모리 저장소 사용.")
                self.redis_client = None
                self.use_redis = False
        else:
            self.redis_client = None
            self.use_redis = False
            logger.warning("Redis 미설치. 메모리 저장소 사용.")
    
    def store_features(self, symbol: str, features: Dict[str, float],
                      metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        특징 저장
        
        Args:
            symbol: 심볼 (예: KRW-BTC)
            features: 특징 딕셔너리
            metadata: 메타데이터
        
        Returns:
            bool: 성공 여부
        """
        try:
            feature = Feature(
                symbol=symbol,
                timestamp=datetime.now(),
                features=features,
                metadata=metadata
            )
            
            key = f"features:{symbol}:latest"
            
            if self.use_redis and self.redis_client:
                # Redis에 저장
                data = {
                    "symbol": feature.symbol,
                    "timestamp": feature.timestamp.isoformat(),
                    "features": json.dumps(feature.features),
                    "metadata": json.dumps(feature.metadata) if feature.metadata else None
                }
                
                self.redis_client.hset(key, mapping=data)
                self.redis_client.expire(key, self.ttl_seconds)
                
                # 히스토리에도 추가 (Sorted Set 사용)
                history_key = f"features:{symbol}:history"
                timestamp_score = feature.timestamp.timestamp()
                self.redis_client.zadd(
                    history_key,
                    {json.dumps(asdict(feature), default=str): timestamp_score}
                )
                
                # 오래된 히스토리 정리 (최근 1000개만 유지)
                self.redis_client.zremrangebyrank(history_key, 0, -1001)
            else:
                # 메모리에 저장
                self._memory_store[key] = feature
            
            logger.debug(f"특징 저장: {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"특징 저장 실패: {e}")
            return False
    
    def get_latest_features(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        최신 특징 조회
        
        Args:
            symbol: 심볼
        
        Returns:
            Optional[Dict[str, float]]: 특징 딕셔너리
        """
        try:
            key = f"features:{symbol}:latest"
            
            if self.use_redis and self.redis_client:
                data = self.redis_client.hgetall(key)
                if not data:
                    return None
                
                features = json.loads(data.get("features", "{}"))
                return features
            else:
                feature = self._memory_store.get(key)
                return feature.features if feature else None
                
        except Exception as e:
            logger.error(f"특징 조회 실패: {e}")
            return None
    
    def get_feature_history(self, symbol: str, 
                           start_time: Optional[datetime] = None,
                           end_time: Optional[datetime] = None,
                           limit: int = 100) -> List[Feature]:
        """
        특징 히스토리 조회
        
        Args:
            symbol: 심볼
            start_time: 시작 시간
            end_time: 종료 시간
            limit: 최대 개수
        
        Returns:
            List[Feature]: 특징 리스트
        """
        try:
            history_key = f"features:{symbol}:history"
            
            if self.use_redis and self.redis_client:
                # Sorted Set에서 범위 조회
                min_score = start_time.timestamp() if start_time else "-inf"
                max_score = end_time.timestamp() if end_time else "+inf"
                
                results = self.redis_client.zrangebyscore(
                    history_key,
                    min_score,
                    max_score,
                    start=0,
                    num=limit,
                    withscores=False
                )
                
                features = []
                for result in results:
                    feature_dict = json.loads(result)
                    # timestamp를 datetime으로 변환
                    if isinstance(feature_dict.get("timestamp"), str):
                        feature_dict["timestamp"] = datetime.fromisoformat(
                            feature_dict["timestamp"]
                        )
                    features.append(Feature(**feature_dict))
                
                return features
            else:
                # 메모리 저장소에서는 히스토리 미지원
                return []
                
        except Exception as e:
            logger.error(f"히스토리 조회 실패: {e}")
            return []
    
    def delete_features(self, symbol: str) -> bool:
        """
        특징 삭제
        
        Args:
            symbol: 심볼
        
        Returns:
            bool: 성공 여부
        """
        try:
            key = f"features:{symbol}:latest"
            history_key = f"features:{symbol}:history"
            
            if self.use_redis and self.redis_client:
                self.redis_client.delete(key)
                self.redis_client.delete(history_key)
            else:
                if key in self._memory_store:
                    del self._memory_store[key]
            
            logger.info(f"특징 삭제: {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"특징 삭제 실패: {e}")
            return False
    
    def list_symbols(self) -> List[str]:
        """
        저장된 심볼 목록 조회
        
        Returns:
            List[str]: 심볼 리스트
        """
        try:
            if self.use_redis and self.redis_client:
                keys = self.redis_client.keys("features:*:latest")
                symbols = [key.split(":")[1] for key in keys]
                return symbols
            else:
                symbols = [key.split(":")[1] for key in self._memory_store.keys()]
                return list(set(symbols))
                
        except Exception as e:
            logger.error(f"심볼 목록 조회 실패: {e}")
            return []
    
    def cleanup_expired(self):
        """만료된 특징 정리 (메모리 저장소용)"""
        if self.use_redis:
            # Redis는 자동으로 TTL 처리
            return
        
        try:
            cutoff_time = datetime.now() - timedelta(seconds=self.ttl_seconds)
            expired_keys = [
                key for key, feature in self._memory_store.items()
                if feature.timestamp < cutoff_time
            ]
            
            for key in expired_keys:
                del self._memory_store[key]
            
            if expired_keys:
                logger.info(f"{len(expired_keys)}개 만료된 특징 정리")
                
        except Exception as e:
            logger.error(f"정리 실패: {e}")


# 싱글톤 인스턴스
_store_instance = None


def get_feature_store() -> FeatureStore:
    """글로벌 Feature Store 인스턴스 반환"""
    global _store_instance
    if _store_instance is None:
        _store_instance = FeatureStore()
    return _store_instance
