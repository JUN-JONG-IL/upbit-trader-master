#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MongoDB 컬렉션 관리 컨트롤러 모듈"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CollectionManager:
    """MongoDB 컬렉션 생성, 삭제, 조회를 담당하는 컨트롤러.

    MongoDB 클라이언트를 주입받아 컬렉션 단위 CRUD 작업을
    추상화합니다.

    사용 예시::

        manager = CollectionManager(client, db_name="upbit")
        names = manager.list_collections()
        stats = manager.get_collection_stats("ohlcv")
        manager.drop_collection("temp_data")
    """

    def __init__(self, mongo_client=None, db_name: Optional[str] = None):
        """초기화.

        Args:
            mongo_client: MongoDB 클라이언트 인스턴스.
            db_name: 사용할 데이터베이스 이름. None이면 기본 DB 사용.
        """
        self._client = mongo_client
        self._db_name = db_name

    def set_client(self, client, db_name: Optional[str] = None) -> None:
        """MongoDB 클라이언트와 데이터베이스를 설정합니다.

        Args:
            client: 새 MongoDB 클라이언트.
            db_name: 데이터베이스 이름 (선택).
        """
        self._client = client
        if db_name is not None:
            self._db_name = db_name

    def _get_db(self):
        """현재 설정된 데이터베이스 객체를 반환합니다.

        Returns:
            pymongo Database 객체.

        Raises:
            RuntimeError: 클라이언트가 설정되지 않은 경우.
        """
        if self._client is None:
            raise RuntimeError("MongoDB 클라이언트가 설정되지 않았습니다.")
        if self._db_name:
            return self._client[self._db_name]
        return self._client.get_default_database()

    def list_collections(self) -> List[str]:
        """데이터베이스의 컬렉션 이름 목록을 반환합니다.

        Returns:
            컬렉션 이름 리스트.
        """
        try:
            db = self._get_db()
            return sorted(db.list_collection_names())
        except Exception as exc:
            logger.warning("컬렉션 목록 조회 실패: %s", exc)
            return []

    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """특정 컬렉션의 통계 정보를 반환합니다.

        Args:
            collection_name: 통계를 조회할 컬렉션 이름.

        Returns:
            도큐먼트 수, 크기, 인덱스 수 등을 포함한 딕셔너리.
        """
        try:
            db = self._get_db()
            raw = db.command("collstats", collection_name)
            return {
                "name": collection_name,
                "count": raw.get("count", 0),
                "size": raw.get("size", 0),
                "storage_size": raw.get("storageSize", 0),
                "nindexes": raw.get("nindexes", 0),
                "total_index_size": raw.get("totalIndexSize", 0),
            }
        except Exception as exc:
            logger.warning("컬렉션 통계 조회 실패 (%s): %s", collection_name, exc)
            return {}

    def create_collection(self, collection_name: str, **kwargs) -> bool:
        """새 컬렉션을 생성합니다.

        Args:
            collection_name: 생성할 컬렉션 이름.
            **kwargs: pymongo create_collection에 전달할 추가 옵션.

        Returns:
            생성 성공 여부.
        """
        try:
            db = self._get_db()
            db.create_collection(collection_name, **kwargs)
            logger.info("컬렉션 생성: %s", collection_name)
            return True
        except Exception as exc:
            logger.warning("컬렉션 생성 실패 (%s): %s", collection_name, exc)
            return False

    def drop_collection(self, collection_name: str) -> bool:
        """컬렉션을 삭제합니다.

        Args:
            collection_name: 삭제할 컬렉션 이름.

        Returns:
            삭제 성공 여부.
        """
        try:
            db = self._get_db()
            db.drop_collection(collection_name)
            logger.info("컬렉션 삭제: %s", collection_name)
            return True
        except Exception as exc:
            logger.warning("컬렉션 삭제 실패 (%s): %s", collection_name, exc)
            return False

    def count_documents(self, collection_name: str, query: Optional[Dict] = None) -> int:
        """컬렉션의 도큐먼트 수를 반환합니다.

        Args:
            collection_name: 조회할 컬렉션 이름.
            query: 필터 조건 딕셔너리. None이면 전체 카운트.

        Returns:
            도큐먼트 수. 오류 발생 시 -1.
        """
        try:
            db = self._get_db()
            return db[collection_name].count_documents(query or {})
        except Exception as exc:
            logger.warning("도큐먼트 수 조회 실패 (%s): %s", collection_name, exc)
            return -1
