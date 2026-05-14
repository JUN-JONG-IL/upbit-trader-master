#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
세션 관리

[Responsibilities]
- 사용자 세션 생성/검증/폐기
- JWT 토큰 기반 세션 유효성 검사
- 세션 TTL 관리 (Redis 백엔드)

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# JWT 라이브러리 (옵션)
try:
    import jwt as pyjwt  # type: ignore
    JWT_AVAILABLE = True
except ImportError:
    pyjwt = None  # type: ignore
    JWT_AVAILABLE = False


class SessionManager:
    """
    세션 관리자

    JWT 토큰 기반으로 세션을 관리합니다.
    Redis 연결이 가능한 경우 세션을 Redis에 저장합니다.

    Attributes:
        secret_key: JWT 서명 키
        algorithm: JWT 알고리즘
        ttl_seconds: 세션 TTL (초)
    """

    DEFAULT_TTL = 3600  # 1시간

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        ttl_seconds: int = DEFAULT_TTL,
    ) -> None:
        self.secret_key: str = secret_key or os.getenv("JWT_SECRET_KEY", "upbit-trader-secret")
        self.algorithm: str = algorithm
        self.ttl_seconds: int = ttl_seconds

        # 인메모리 세션 저장소 (Redis 미사용 시 fallback)
        self._sessions: Dict[str, Dict[str, Any]] = {}

        self._redis: Optional[Any] = None
        self._init_redis()

    def _init_redis(self) -> None:
        """Redis 클라이언트 초기화 (옵션)"""
        try:
            import redis as redis_lib  # type: ignore
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            self._redis = redis_lib.Redis(host=host, port=port, decode_responses=True)
            self._redis.ping()
            logger.debug("[SessionManager] Redis 연결 성공")
        except Exception as exc:
            logger.debug("[SessionManager] Redis 연결 실패 (인메모리 사용): %s", exc)
            self._redis = None

    # ── 세션 생성 ─────────────────────────────────────────────────────────────

    def create_session(self, user_id: str, extra: Optional[Dict[str, Any]] = None) -> str:
        """
        새 세션 생성 및 JWT 토큰 반환

        Args:
            user_id: 사용자 ID
            extra: 추가 페이로드 (선택)

        Returns:
            JWT 토큰 문자열
        """
        session_id = str(uuid.uuid4())
        now = time.time()
        payload: Dict[str, Any] = {
            "sub": user_id,
            "sid": session_id,
            "iat": now,
            "exp": now + self.ttl_seconds,
        }
        if extra:
            payload.update(extra)

        if JWT_AVAILABLE and pyjwt is not None:
            try:
                token = pyjwt.encode(payload, self.secret_key, algorithm=self.algorithm)
            except Exception as exc:
                logger.warning("[SessionManager] JWT 인코딩 실패: %s", exc)
                token = session_id
        else:
            token = session_id

        self._store_session(session_id, payload)
        logger.debug("[SessionManager] 세션 생성: user=%s sid=%s", user_id, session_id)
        return token

    # ── 세션 검증 ─────────────────────────────────────────────────────────────

    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        JWT 토큰 검증

        Args:
            token: JWT 토큰 문자열

        Returns:
            페이로드 딕셔너리 또는 None (유효하지 않은 경우)
        """
        if not JWT_AVAILABLE or pyjwt is None:
            return self._sessions.get(token)

        try:
            payload = pyjwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
            session_id = payload.get("sid")
            if session_id and not self._get_session(session_id):
                logger.debug("[SessionManager] 세션 없음: sid=%s", session_id)
                return None
            return payload
        except Exception as exc:
            logger.debug("[SessionManager] 토큰 검증 실패: %s", exc)
            return None

    # ── 세션 폐기 ─────────────────────────────────────────────────────────────

    def revoke_session(self, session_id: str) -> bool:
        """
        세션 폐기

        Args:
            session_id: 세션 ID

        Returns:
            성공 여부
        """
        removed = self._delete_session(session_id)
        if removed:
            logger.debug("[SessionManager] 세션 폐기: sid=%s", session_id)
        return removed

    # ── 내부 저장소 ───────────────────────────────────────────────────────────

    def _store_session(self, session_id: str, payload: Dict[str, Any]) -> None:
        if self._redis:
            try:
                import json
                self._redis.setex(
                    f"session:{session_id}",
                    self.ttl_seconds,
                    json.dumps(payload),
                )
                return
            except Exception as exc:
                logger.debug("[SessionManager] Redis 저장 실패: %s", exc)
        self._sessions[session_id] = payload

    def _get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        if self._redis:
            try:
                import json
                raw = self._redis.get(f"session:{session_id}")
                return json.loads(raw) if raw else None
            except Exception:
                pass
        return self._sessions.get(session_id)

    def _delete_session(self, session_id: str) -> bool:
        if self._redis:
            try:
                result = self._redis.delete(f"session:{session_id}")
                return bool(result)
            except Exception:
                pass
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    @property
    def is_redis_connected(self) -> bool:
        """Redis 연결 상태"""
        return self._redis is not None
