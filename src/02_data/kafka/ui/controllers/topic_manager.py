#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 토픽 관리 모듈

토픽 목록 조회, 생성, 삭제 기능을 제공합니다.
kafka-python 라이브러리가 설치된 경우 실제 Kafka 클러스터와 통신하며,
없는 경우 더미 데이터를 반환합니다.
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from kafka import KafkaAdminClient
    from kafka.admin import NewTopic
    from kafka.errors import KafkaError, TopicAlreadyExistsError

    _HAS_KAFKA = True
except ImportError:
    _HAS_KAFKA = False
    logger.warning("kafka-python 라이브러리가 설치되지 않아 더미 모드로 동작합니다.")


class TopicManager:
    """
    Kafka 토픽 관리 클래스

    KafkaAdminClient를 통해 토픽 목록을 조회하고 생성/삭제 작업을 수행합니다.
    kafka-python이 없을 경우 더미 결과를 반환합니다.
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        client_id: str = "upbit-monitor-topic-manager",
        request_timeout_ms: int = 10000,
    ):
        """
        TopicManager 초기화

        Args:
            bootstrap_servers (str): 쉼표로 구분된 Kafka 브로커 주소 목록 (기본값: "localhost:9092").
            client_id (str): Kafka 클라이언트 식별자 (기본값: "upbit-monitor-topic-manager").
            request_timeout_ms (int): 요청 타임아웃 (밀리초, 기본값: 10000).
        """
        self._bootstrap_servers = bootstrap_servers
        self._client_id = client_id
        self._request_timeout_ms = request_timeout_ms
        self._admin_client: Optional[object] = None

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Kafka 관리 클라이언트 연결을 수립합니다.

        Returns:
            bool: 연결 성공 시 True, 실패 시 False.
        """
        if not _HAS_KAFKA:
            logger.warning("kafka-python 없음 — 연결 건너뜀")
            return False
        try:
            self._admin_client = KafkaAdminClient(
                bootstrap_servers=self._bootstrap_servers,
                client_id=self._client_id,
                request_timeout_ms=self._request_timeout_ms,
            )
            logger.info("Kafka AdminClient 연결 성공 (%s)", self._bootstrap_servers)
            return True
        except Exception as exc:
            logger.error("Kafka AdminClient 연결 실패: %s", exc)
            self._admin_client = None
            return False

    def disconnect(self):
        """Kafka 관리 클라이언트 연결을 종료합니다."""
        if self._admin_client:
            try:
                self._admin_client.close()
            except Exception as exc:
                logger.debug("AdminClient 종료 오류: %s", exc)
            finally:
                self._admin_client = None
            logger.info("Kafka AdminClient 연결 종료")

    def list_topics(self) -> List[dict]:
        """
        현재 Kafka 클러스터의 토픽 목록을 반환합니다.

        Returns:
            list: 토픽 정보 딕셔너리 리스트.
                각 항목은 'name', 'partitions', 'replicas' 키를 포함합니다.
                연결 불가 또는 kafka-python 없을 경우 빈 리스트를 반환합니다.
        """
        if not _HAS_KAFKA or self._admin_client is None:
            return []
        try:
            metadata = self._admin_client.list_topics()
            topics = []
            for name in metadata:
                topics.append({"name": name, "partitions": "-", "replicas": "-", "message_count": "-", "offset": "-"})
            return topics
        except Exception as exc:
            logger.error("토픽 목록 조회 실패: %s", exc)
            return []

    def create_topic(
        self,
        name: str,
        num_partitions: int = 1,
        replication_factor: int = 1,
    ) -> bool:
        """
        새 토픽을 생성합니다.

        Args:
            name (str): 생성할 토픽명.
            num_partitions (int): 파티션 수 (기본값: 1).
            replication_factor (int): 복제 수 (기본값: 1).

        Returns:
            bool: 생성 성공 시 True, 실패 시 False.
        """
        if not _HAS_KAFKA or self._admin_client is None:
            logger.warning("Kafka 미연결 상태에서 토픽 생성 시도: %s", name)
            return False
        try:
            new_topic = NewTopic(
                name=name,
                num_partitions=num_partitions,
                replication_factor=replication_factor,
            )
            self._admin_client.create_topics([new_topic])
            logger.info("토픽 생성 성공: %s (파티션: %d, 복제: %d)", name, num_partitions, replication_factor)
            return True
        except TopicAlreadyExistsError:
            logger.warning("이미 존재하는 토픽: %s", name)
            return False
        except Exception as exc:
            logger.error("토픽 생성 실패 (%s): %s", name, exc)
            return False

    def delete_topic(self, name: str) -> bool:
        """
        토픽을 삭제합니다.

        Args:
            name (str): 삭제할 토픽명.

        Returns:
            bool: 삭제 성공 시 True, 실패 시 False.
        """
        if not _HAS_KAFKA or self._admin_client is None:
            logger.warning("Kafka 미연결 상태에서 토픽 삭제 시도: %s", name)
            return False
        try:
            self._admin_client.delete_topics([name])
            logger.info("토픽 삭제 성공: %s", name)
            return True
        except Exception as exc:
            logger.error("토픽 삭제 실패 (%s): %s", name, exc)
            return False

    def set_bootstrap_servers(self, servers: str):
        """
        브로커 주소를 변경합니다. 변경 후 reconnect()를 호출해야 적용됩니다.

        Args:
            servers (str): 쉼표로 구분된 Kafka 브로커 주소 목록.
        """
        self._bootstrap_servers = servers

    def reconnect(self) -> bool:
        """
        현재 연결을 종료하고 재연결을 시도합니다.

        Returns:
            bool: 재연결 성공 시 True.
        """
        self.disconnect()
        return self.connect()
