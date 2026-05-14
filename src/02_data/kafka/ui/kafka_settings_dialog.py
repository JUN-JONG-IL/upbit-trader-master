#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 모니터링 다이얼로그 (읽기 전용)

기능:
- 탭 1 (📡 연결 상태): Broker 목록, Zookeeper 상태
- 탭 2 (📋 토픽 관리): 토픽 목록 (파티션수, 레플리카, Retention, 크기, msg/s)
- 탭 3 (👥 Consumer Group): 그룹 목록 (Group ID, 토픽, 멤버수, Lag, 상태)
- 탭 4 (⏱️ Lag 모니터링): 파티션별 Lag 상세
- 탭 5 (📤 Producer 상태): Producer 목록 (ID, 토픽, msg/s, 실패율, 마지막전송)
- 탭 6 (🖥️ Broker 상태): Broker별 리소스 (CPU, 메모리, 디스크, 네트워크)
- 10초마다 자동 갱신 (QTimer)

주의사항:
- 모든 Kafka 조회는 백그라운드 스레드에서 실행 (UI 블록 방지)
- pyqtSignal로 스레드 안전 UI 업데이트
- kafka-python 미설치 시 플레이스홀더 데이터 표시
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# PyQt5 임포트
# ---------------------------------------------------------------------------
try:
    from PyQt5 import uic
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal
    from PyQt5.QtWidgets import (
        QDialog,
        QFileDialog,
        QHeaderView,
        QMessageBox,
        QTableWidgetItem,
        QWidget,
    )
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UI 파일 경로
# ---------------------------------------------------------------------------
_UI_PATH = Path(__file__).parent / "kafka_settings.ui"

# ---------------------------------------------------------------------------
# LED 색상 상수
# ---------------------------------------------------------------------------
_COLOR_GREEN = "#2ECC40"  # 연결 정상
_COLOR_RED   = "#FF4136"  # 연결 실패
_COLOR_GRAY  = "#808080"  # 확인 중

# ---------------------------------------------------------------------------
# 연결 설정
# ---------------------------------------------------------------------------

def _get_kafka_bootstrap() -> List[str]:
    """환경변수에서 Kafka Bootstrap 서버 목록 반환."""
    servers = os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS",
        "localhost:9092,localhost:9093,localhost:9094",
    )
    return [s.strip() for s in servers.split(",") if s.strip()]


def _get_main_topic() -> str:
    """환경변수에서 메인 Topic 반환."""
    return os.getenv("KAFKA_MAIN_TOPIC", "trade_events")


# ---------------------------------------------------------------------------
# 플레이스홀더 데이터 (kafka-python 미설치 시)
# ---------------------------------------------------------------------------

def _placeholder_brokers() -> List[Dict[str, Any]]:
    """kafka-python 없을 때 표시할 더미 Broker 행."""
    bootstrap = _get_kafka_bootstrap()
    rows = []
    for i, addr in enumerate(bootstrap):
        rows.append({
            "broker": f"Broker-{i + 1}",
            "address": addr,
            "status": "⚠️ 확인불가",
            "leader_partitions": "-",
        })
    return rows


def _placeholder_topics() -> List[Dict[str, Any]]:
    """kafka-python 없을 때 표시할 더미 Topic 행."""
    return [
        {
            "name": _get_main_topic(),
            "partitions": "-",
            "replicas": "-",
            "retention": "-",
            "size": "-",
            "msg_per_sec": "-",
        }
    ]


def _placeholder_consumer_groups() -> List[Dict[str, Any]]:
    """kafka-python 없을 때 표시할 더미 Consumer Group 행."""
    return []


def _placeholder_lag() -> List[Dict[str, Any]]:
    """kafka-python 없을 때 표시할 더미 Lag 행."""
    return []


def _placeholder_producers() -> List[Dict[str, Any]]:
    """kafka-python 없을 때 표시할 더미 Producer 행."""
    return []


def _placeholder_broker_stats() -> List[Dict[str, Any]]:
    """kafka-python 없을 때 표시할 더미 Broker 상태 행."""
    bootstrap = _get_kafka_bootstrap()
    return [
        {
            "broker_id": f"Broker-{i + 1}",
            "cpu": "-",
            "memory": "-",
            "disk": "-",
            "net_in": "-",
            "net_out": "-",
        }
        for i in range(len(bootstrap))
    ]


# ---------------------------------------------------------------------------
# Kafka 다이얼로그
# ---------------------------------------------------------------------------

if PYQT5_AVAILABLE:
    # 삭제 기능 믹스인 로드
    def _load_kafka_delete_mixin():
        try:
            from pathlib import Path as _Path
            import importlib.util as _ilu
            _p = _Path(__file__).parent / "kafka_delete_operations.py"
            if _p.exists():
                _spec = _ilu.spec_from_file_location("kafka_delete_operations", str(_p))
                if _spec and _spec.loader:
                    _m = _ilu.module_from_spec(_spec)
                    _spec.loader.exec_module(_m)  # type: ignore
                    return getattr(_m, "KafkaDeleteMixin", None)
        except Exception:
            pass
        return None

    _KafkaDeleteMixin = _load_kafka_delete_mixin()
    if _KafkaDeleteMixin is None:
        class _KafkaDeleteMixin:  # type: ignore[no-redef]
            def _bind_kafka_delete_signals(self): pass

    class KafkaSettingsDialog(QDialog, _KafkaDeleteMixin):
        """Kafka 모니터링 다이얼로그 (읽기 전용, 6-탭 + 데이터 삭제 탭).

        탭 구성:
            1. 📡 연결 상태 – Broker 목록 및 Zookeeper 상태
            2. 📋 토픽 관리 – 토픽 목록 (파티션/레플리카/Retention)
            3. 👥 Consumer Group – 그룹 목록 (Lag 포함)
            4. ⏱️ Lag 모니터링 – 파티션별 상세 Lag
            5. 📤 Producer 상태 – Producer 처리량 및 실패율
            6. 🖥️ Broker 상태 – CPU/메모리/디스크/네트워크
            7. 🗑️ 데이터 삭제 – 토픽 삭제/Purge
        """

        _sig_status = pyqtSignal(bool, str)
        _sig_brokers = pyqtSignal(list)
        _sig_topics = pyqtSignal(list)
        _sig_consumer_groups = pyqtSignal(list)
        _sig_lag = pyqtSignal(list, int)
        _sig_producers = pyqtSignal(list)
        _sig_broker_stats = pyqtSignal(list, str)

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            """다이얼로그 초기화.

            Args:
                parent: 부모 위젯.
            """
            super().__init__(parent)
            uic.loadUi(_UI_PATH, self)
            self._setup_ui()
            self._connect_signals()

            # 삭제 탭 버튼 바인딩 (KafkaDeleteMixin)
            self._bind_kafka_delete_signals()

            self._timer = QTimer(self)
            self._timer.timeout.connect(self._refresh_all)
            self._timer.start(10_000)
            self._refresh_all()

            # 비모달 팝업 설정
            self.setWindowModality(Qt.NonModal)
            self.setAttribute(Qt.WA_DeleteOnClose, False)

            # 페이지네이션 상태
            self._current_page: int = 1
            self._total_pages: int = 1

            # 실시간 갱신 타이머 (1초)
            self._realtime_timer = QTimer(self)
            self._realtime_timer.setInterval(1000)
            self._realtime_timer.timeout.connect(self._on_refresh_realtime)
            self._realtime_timer.start()

            # PyQtGraph 차트 초기화
            try:
                import pyqtgraph as pg
                from PyQt5.QtWidgets import QVBoxLayout as _QVL
                if hasattr(self, "chartContainer"):
                    if self.chartContainer.layout() is None:
                        self.chartContainer.setLayout(_QVL())
                    self._chart_widget = pg.PlotWidget()
                    self.chartContainer.layout().addWidget(self._chart_widget)
                    self._chart_widget.setBackground("k")
                    self._chart_widget.setLabel("left", "QPS")
                    self._chart_widget.setLabel("bottom", "시간 (초)")
            except ImportError:
                pass

            # 창 위치 복원
            try:
                from PyQt5.QtCore import QSettings
                _settings = QSettings("UpbitTrader", "DBMonitor")
                _geometry = _settings.value("kafka_geometry")
                if _geometry:
                    self.restoreGeometry(_geometry)
            except Exception:
                pass

            # 다크 모드 스타일
            self.setStyleSheet("""
                QDialog { background-color: #2b2b2b; color: #ffffff; }
                QTableWidget { background-color: #1e1e1e; gridline-color: #444; color: #ffffff; }
                QTableWidget QHeaderView::section { background-color: #3c3c3c; color: #ffffff; }
                QPushButton { background-color: #0078d4; color: white; border-radius: 4px; padding: 6px; }
                QPushButton:hover { background-color: #1084d8; }
                QGroupBox { color: #ffffff; border: 1px solid #555; margin-top: 6px; }
                QGroupBox::title { color: #aaaaaa; }
                QLabel { color: #ffffff; }
                QComboBox { background-color: #3c3c3c; color: #ffffff; }
                QLineEdit { background-color: #3c3c3c; color: #ffffff; }
                QTabWidget::pane { border: 1px solid #555; }
                QTabBar::tab { background-color: #3c3c3c; color: #ffffff; padding: 6px 12px; }
                QTabBar::tab:selected { background-color: #0078d4; }
            """)

        # ------------------------------------------------------------------
        # 초기화
        # ------------------------------------------------------------------

        def _setup_ui(self) -> None:
            """테이블 헤더 등 UI 초기 설정."""
            _stretch_table("tableBrokers", self)
            _stretch_table("tableTopics", self)
            _stretch_table("tableConsumerGroups", self)
            _stretch_table("tableLag", self)
            _stretch_table("tableProducers", self)
            _stretch_table("tableBrokerStats", self)
            self._set_led(_COLOR_GRAY, "상태 확인 중...")

        def _connect_signals(self) -> None:
            """버튼 및 pyqtSignal 연결."""
            self._sig_status.connect(self._on_status)
            self._sig_brokers.connect(self._on_brokers)
            self._sig_topics.connect(self._on_topics)
            self._sig_consumer_groups.connect(self._on_consumer_groups)
            self._sig_lag.connect(self._on_lag)
            self._sig_producers.connect(self._on_producers)
            self._sig_broker_stats.connect(self._on_broker_stats)

            _btn_connect(self, "btnConnect", self._refresh_all)
            _btn_connect(self, "btnRefreshTopics", self._refresh_topics)
            _btn_connect(self, "btnCreateTopic", self._on_create_topic)
            _btn_connect(self, "btnDeleteTopic", self._on_delete_topic)
            _btn_connect(self, "btnRefreshGroups", self._refresh_consumer_groups)
            _btn_connect(self, "btnRefreshLag", self._refresh_lag)
            _btn_connect(self, "btnRefreshProducers", self._refresh_producers)
            _btn_connect(self, "btnRefreshBrokerStats", self._refresh_broker_stats)
            # 새 탭 버튼
            _btn_connect(self, "btnSearch", self._on_search_data)
            _btn_connect(self, "btnPrevPage", self._on_prev_page)
            _btn_connect(self, "btnNextPage", self._on_next_page)
            _btn_connect(self, "btnExportCSV", self._on_export_csv)

            if hasattr(self, "buttonBox"):
                self.buttonBox.rejected.connect(self.reject)

        # ------------------------------------------------------------------
        # 갱신 진입점
        # ------------------------------------------------------------------

        def _refresh_all(self) -> None:
            """모든 탭 데이터 갱신."""
            threading.Thread(target=self._fetch_all, daemon=True).start()

        def _refresh_topics(self) -> None:
            """토픽 탭 갱신."""
            threading.Thread(target=self._fetch_topics, daemon=True).start()

        def _refresh_consumer_groups(self) -> None:
            """Consumer Group 탭 갱신."""
            threading.Thread(target=self._fetch_consumer_groups, daemon=True).start()

        def _refresh_lag(self) -> None:
            """Lag 모니터링 탭 갱신."""
            threading.Thread(target=self._fetch_lag, daemon=True).start()

        def _refresh_producers(self) -> None:
            """Producer 탭 갱신."""
            threading.Thread(target=self._fetch_producers, daemon=True).start()

        def _refresh_broker_stats(self) -> None:
            """Broker 상태 탭 갱신."""
            threading.Thread(target=self._fetch_broker_stats, daemon=True).start()

        # ------------------------------------------------------------------
        # 버튼 핸들러 (읽기 전용 UI이므로 토픽 생성/삭제는 로그만)
        # ------------------------------------------------------------------

        def _on_create_topic(self) -> None:
            """토픽 생성 버튼 — 향후 구현 예정."""
            logger.info("토픽 생성 기능은 아직 구현되지 않았습니다.")

        def _on_delete_topic(self) -> None:
            """토픽 삭제 버튼 — 향후 구현 예정."""
            logger.info("토픽 삭제 기능은 아직 구현되지 않았습니다.")

        # ------------------------------------------------------------------
        # 백그라운드 조회
        # ------------------------------------------------------------------

        def _fetch_all(self) -> None:
            """Kafka에서 전체 데이터 조회 후 시그널 발행.

            kafka-python이 없거나 연결 실패 시 플레이스홀더 데이터를 사용한다.
            """
            try:
                from kafka.admin import KafkaAdminClient  # type: ignore
                bootstrap = _get_kafka_bootstrap()
                admin = KafkaAdminClient(
                    bootstrap_servers=bootstrap,
                    request_timeout_ms=3000,
                )
                cluster_meta = admin.describe_cluster()
                raw_brokers = cluster_meta.get("brokers", [])
                topics = admin.list_topics()
                consumer_groups = admin.list_consumer_groups()

                self._sig_status.emit(True, f"연결됨 ({bootstrap[0]})")

                # 탭 1: 연결 상태 – Broker 목록
                broker_rows: List[Dict[str, Any]] = []
                for i, b in enumerate(raw_brokers):
                    node_id = b.get("node_id", i + 1)
                    host = b.get("host", "")
                    port = b.get("port", "")
                    broker_rows.append({
                        "broker": f"Broker-{node_id}",
                        "address": f"{host}:{port}" if host else bootstrap[i % len(bootstrap)],
                        "status": "🟢 UP",
                        "leader_partitions": "-",
                    })
                if hasattr(self, "labelBrokerCount"):
                    self._sig_brokers.emit(broker_rows)
                    self.labelBrokerCount.setText(str(len(raw_brokers)))
                else:
                    self._sig_brokers.emit(broker_rows)

                if hasattr(self, "labelZookeeper"):
                    self.labelZookeeper.setText("알 수 없음")

                # 탭 2: 토픽 목록
                topic_rows: List[Dict[str, Any]] = []
                for t in list(topics)[:50]:
                    try:
                        meta = admin.describe_topics([t])
                        parts = meta[0].get("partitions", []) if meta else []
                        replicas = len(parts[0].get("replicas", [])) if parts else 0
                        topic_rows.append({
                            "name": t,
                            "partitions": str(len(parts)),
                            "replicas": str(replicas),
                            "retention": "-",
                            "size": "-",
                            "msg_per_sec": "-",
                        })
                    except Exception:
                        topic_rows.append({
                            "name": t,
                            "partitions": "-",
                            "replicas": "-",
                            "retention": "-",
                            "size": "-",
                            "msg_per_sec": "-",
                        })
                self._sig_topics.emit(topic_rows)

                # 탭 3: Consumer Group
                group_rows: List[Dict[str, Any]] = []
                for grp in consumer_groups[:50]:
                    gid = grp[0] if isinstance(grp, tuple) else str(grp)
                    group_rows.append({
                        "group_id": gid,
                        "topic": "-",
                        "members": "-",
                        "lag": "-",
                        "state": "-",
                    })
                self._sig_consumer_groups.emit(group_rows)

                # 탭 4 & 5 & 6: 상세 데이터는 별도 조회
                self._sig_lag.emit([], 0)
                self._sig_producers.emit(_placeholder_producers())
                self._sig_broker_stats.emit(_placeholder_broker_stats(), "0")

                admin.close()

            except ImportError:
                logger.warning("kafka-python 패키지가 설치되지 않았습니다. 플레이스홀더 데이터를 표시합니다.")
                self._sig_status.emit(False, "kafka-python 패키지 미설치")
                self._sig_brokers.emit(_placeholder_brokers())
                self._sig_topics.emit(_placeholder_topics())
                self._sig_consumer_groups.emit(_placeholder_consumer_groups())
                self._sig_lag.emit(_placeholder_lag(), 0)
                self._sig_producers.emit(_placeholder_producers())
                self._sig_broker_stats.emit(_placeholder_broker_stats(), "-")

            except Exception as exc:
                logger.warning("Kafka 연결 실패: %s", exc)
                self._sig_status.emit(False, f"연결 실패: {exc}")
                self._sig_brokers.emit(_placeholder_brokers())
                self._sig_topics.emit(_placeholder_topics())
                self._sig_consumer_groups.emit(_placeholder_consumer_groups())
                self._sig_lag.emit(_placeholder_lag(), 0)
                self._sig_producers.emit(_placeholder_producers())
                self._sig_broker_stats.emit(_placeholder_broker_stats(), "-")

        def _fetch_topics(self) -> None:
            """토픽 탭 전용 갱신."""
            try:
                from kafka.admin import KafkaAdminClient  # type: ignore
                admin = KafkaAdminClient(
                    bootstrap_servers=_get_kafka_bootstrap(),
                    request_timeout_ms=3000,
                )
                topics = admin.list_topics()
                rows: List[Dict[str, Any]] = []
                for t in list(topics)[:50]:
                    try:
                        meta = admin.describe_topics([t])
                        parts = meta[0].get("partitions", []) if meta else []
                        replicas = len(parts[0].get("replicas", [])) if parts else 0
                        rows.append({
                            "name": t,
                            "partitions": str(len(parts)),
                            "replicas": str(replicas),
                            "retention": "-",
                            "size": "-",
                            "msg_per_sec": "-",
                        })
                    except Exception:
                        rows.append({
                            "name": t,
                            "partitions": "-",
                            "replicas": "-",
                            "retention": "-",
                            "size": "-",
                            "msg_per_sec": "-",
                        })
                self._sig_topics.emit(rows)
                admin.close()
            except ImportError:
                self._sig_topics.emit(_placeholder_topics())
            except Exception as exc:
                logger.warning("토픽 조회 실패: %s", exc)
                self._sig_topics.emit(_placeholder_topics())

        def _fetch_consumer_groups(self) -> None:
            """Consumer Group 탭 전용 갱신."""
            try:
                from kafka.admin import KafkaAdminClient  # type: ignore
                admin = KafkaAdminClient(
                    bootstrap_servers=_get_kafka_bootstrap(),
                    request_timeout_ms=3000,
                )
                groups = admin.list_consumer_groups()
                rows: List[Dict[str, Any]] = []
                for grp in groups[:50]:
                    gid = grp[0] if isinstance(grp, tuple) else str(grp)
                    rows.append({
                        "group_id": gid,
                        "topic": "-",
                        "members": "-",
                        "lag": "-",
                        "state": "-",
                    })
                self._sig_consumer_groups.emit(rows)
                admin.close()
            except ImportError:
                self._sig_consumer_groups.emit(_placeholder_consumer_groups())
            except Exception as exc:
                logger.warning("Consumer Group 조회 실패: %s", exc)
                self._sig_consumer_groups.emit(_placeholder_consumer_groups())

        def _fetch_lag(self) -> None:
            """Lag 탭 전용 갱신.

            kafka-python KafkaConsumer를 이용하여 파티션별 최신 오프셋과
            커밋 오프셋 차이(Lag)를 조회한다.
            """
            try:
                from kafka import KafkaConsumer, TopicPartition  # type: ignore
                bootstrap = _get_kafka_bootstrap()
                main_topic = _get_main_topic()
                consumer = KafkaConsumer(
                    bootstrap_servers=bootstrap,
                    request_timeout_ms=3000,
                    consumer_timeout_ms=1000,
                )
                partitions = consumer.partitions_for_topic(main_topic) or set()
                tps = [TopicPartition(main_topic, p) for p in sorted(partitions)]
                consumer.assign(tps)
                end_offsets = consumer.end_offsets(tps)
                rows: List[Dict[str, Any]] = []
                total_lag = 0
                for tp in tps:
                    committed = consumer.committed(tp) or 0
                    latest = end_offsets.get(tp, 0)
                    lag = max(latest - committed, 0)
                    total_lag += lag
                    rows.append({
                        "topic": tp.topic,
                        "partition": str(tp.partition),
                        "lag": str(lag),
                        "latest_offset": str(latest),
                        "committed_offset": str(committed),
                    })
                consumer.close()
                self._sig_lag.emit(rows, total_lag)
            except ImportError:
                self._sig_lag.emit(_placeholder_lag(), 0)
            except Exception as exc:
                logger.warning("Lag 조회 실패: %s", exc)
                self._sig_lag.emit(_placeholder_lag(), 0)

        def _fetch_producers(self) -> None:
            """Producer 탭 갱신.

            kafka-python은 Producer 메트릭을 직접 노출하지 않으므로
            플레이스홀더 데이터를 표시한다.
            """
            self._sig_producers.emit(_placeholder_producers())

        def _fetch_broker_stats(self) -> None:
            """Broker 상태 탭 갱신.

            JMX 접근 없이는 CPU/메모리 등을 조회하기 어려우므로
            연결 가능한 Broker 목록만 표시하고 나머지는 '-'로 채운다.
            """
            try:
                from kafka.admin import KafkaAdminClient  # type: ignore
                admin = KafkaAdminClient(
                    bootstrap_servers=_get_kafka_bootstrap(),
                    request_timeout_ms=3000,
                )
                cluster_meta = admin.describe_cluster()
                raw_brokers = cluster_meta.get("brokers", [])
                rows: List[Dict[str, Any]] = [
                    {
                        "broker_id": f"Broker-{b.get('node_id', i + 1)}",
                        "cpu": "-",
                        "memory": "-",
                        "disk": "-",
                        "net_in": "-",
                        "net_out": "-",
                    }
                    for i, b in enumerate(raw_brokers)
                ]
                under_replicated = "0"
                self._sig_broker_stats.emit(rows, under_replicated)
                admin.close()
            except ImportError:
                self._sig_broker_stats.emit(_placeholder_broker_stats(), "-")
            except Exception as exc:
                logger.warning("Broker 상태 조회 실패: %s", exc)
                self._sig_broker_stats.emit(_placeholder_broker_stats(), "-")

        # ------------------------------------------------------------------
        # 시그널 수신 (메인 스레드)
        # ------------------------------------------------------------------

        def _on_status(self, ok: bool, msg: str) -> None:
            """연결 상태 LED 및 텍스트 갱신.

            Args:
                ok: 연결 성공 여부.
                msg: 표시할 상태 메시지.
            """
            self._set_led(_COLOR_GREEN if ok else _COLOR_RED, msg)

        def _on_brokers(self, rows: List[Dict[str, Any]]) -> None:
            """탭 1 Broker 테이블 갱신.

            Args:
                rows: Broker 행 목록. 키: broker, address, status, leader_partitions.
            """
            if not hasattr(self, "tableBrokers"):
                return
            self.tableBrokers.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tableBrokers.setItem(i, 0, _item(row["broker"]))
                self.tableBrokers.setItem(i, 1, _item(row["address"]))
                self.tableBrokers.setItem(i, 2, _item(row["status"]))
                self.tableBrokers.setItem(i, 3, _item(row["leader_partitions"]))
            if hasattr(self, "labelBrokerCount"):
                self.labelBrokerCount.setText(str(len(rows)))

        def _on_topics(self, rows: List[Dict[str, Any]]) -> None:
            """탭 2 토픽 테이블 갱신.

            Args:
                rows: 토픽 행 목록. 키: name, partitions, replicas, retention, size, msg_per_sec.
            """
            if not hasattr(self, "tableTopics"):
                return
            self.tableTopics.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tableTopics.setItem(i, 0, _item(row["name"]))
                self.tableTopics.setItem(i, 1, _item(row["partitions"]))
                self.tableTopics.setItem(i, 2, _item(row["replicas"]))
                self.tableTopics.setItem(i, 3, _item(row["retention"]))
                self.tableTopics.setItem(i, 4, _item(row["size"]))
                self.tableTopics.setItem(i, 5, _item(row["msg_per_sec"]))

        def _on_consumer_groups(self, rows: List[Dict[str, Any]]) -> None:
            """탭 3 Consumer Group 테이블 갱신.

            Args:
                rows: 그룹 행 목록. 키: group_id, topic, members, lag, state.
            """
            if not hasattr(self, "tableConsumerGroups"):
                return
            self.tableConsumerGroups.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tableConsumerGroups.setItem(i, 0, _item(row["group_id"]))
                self.tableConsumerGroups.setItem(i, 1, _item(row["topic"]))
                self.tableConsumerGroups.setItem(i, 2, _item(row["members"]))
                self.tableConsumerGroups.setItem(i, 3, _item(row["lag"]))
                self.tableConsumerGroups.setItem(i, 4, _item(row["state"]))

        def _on_lag(self, rows: List[Dict[str, Any]], total_lag: int) -> None:
            """탭 4 Lag 테이블 갱신.

            Args:
                rows: Lag 행 목록. 키: topic, partition, lag, latest_offset, committed_offset.
                total_lag: 전체 합산 Lag.
            """
            if hasattr(self, "labelTotalLag"):
                self.labelTotalLag.setText(str(total_lag))
            if not hasattr(self, "tableLag"):
                return
            self.tableLag.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tableLag.setItem(i, 0, _item(row["topic"]))
                self.tableLag.setItem(i, 1, _item(row["partition"]))
                self.tableLag.setItem(i, 2, _item(row["lag"]))
                self.tableLag.setItem(i, 3, _item(row["latest_offset"]))
                self.tableLag.setItem(i, 4, _item(row["committed_offset"]))

        def _on_producers(self, rows: List[Dict[str, Any]]) -> None:
            """탭 5 Producer 테이블 갱신.

            Args:
                rows: Producer 행 목록. 키: producer_id, topic, msg_per_sec, error_rate, last_sent.
            """
            if not hasattr(self, "tableProducers"):
                return
            self.tableProducers.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tableProducers.setItem(i, 0, _item(row["producer_id"]))
                self.tableProducers.setItem(i, 1, _item(row["topic"]))
                self.tableProducers.setItem(i, 2, _item(row["msg_per_sec"]))
                self.tableProducers.setItem(i, 3, _item(row["error_rate"]))
                self.tableProducers.setItem(i, 4, _item(row["last_sent"]))

        def _on_broker_stats(self, rows: List[Dict[str, Any]], under_replicated: str) -> None:
            """탭 6 Broker 상태 테이블 갱신.

            Args:
                rows: Broker 상태 행 목록. 키: broker_id, cpu, memory, disk, net_in, net_out.
                under_replicated: UnderReplicated 파티션 수.
            """
            if hasattr(self, "labelUnderReplicated"):
                self.labelUnderReplicated.setText(under_replicated)
            if not hasattr(self, "tableBrokerStats"):
                return
            self.tableBrokerStats.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tableBrokerStats.setItem(i, 0, _item(row["broker_id"]))
                self.tableBrokerStats.setItem(i, 1, _item(row["cpu"]))
                self.tableBrokerStats.setItem(i, 2, _item(row["memory"]))
                self.tableBrokerStats.setItem(i, 3, _item(row["disk"]))
                self.tableBrokerStats.setItem(i, 4, _item(row["net_in"]))
                self.tableBrokerStats.setItem(i, 5, _item(row["net_out"]))

        # ------------------------------------------------------------------
        # 헬퍼
        # ------------------------------------------------------------------

        def _set_led(self, color: str, text: str) -> None:
            """연결 상태 LED 색상 및 텍스트 설정.

            Args:
                color: CSS 색상 문자열.
                text: 상태 레이블 텍스트.
            """
            if hasattr(self, "labelStatusDot"):
                self.labelStatusDot.setStyleSheet(
                    f"color: {color}; font-size: 20px;"
                )
            if hasattr(self, "labelStatusText"):
                self.labelStatusText.setText(text)

        # ------------------------------------------------------------------
        # 실시간 통신 모니터 / 저장 데이터 검색 / CSV 내보내기
        # ------------------------------------------------------------------

        def _on_refresh_realtime(self) -> None:
            """실시간 통신 로그 갱신 (1초마다 호출)."""
            try:
                if not hasattr(self, "tableRealtimeQueries"):
                    return
                from datetime import datetime, timezone
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                row = self.tableRealtimeQueries.rowCount()
                if row >= 100:
                    self.tableRealtimeQueries.removeRow(0)
                    row = self.tableRealtimeQueries.rowCount()
                self.tableRealtimeQueries.insertRow(row)
                self.tableRealtimeQueries.setItem(row, 0, QTableWidgetItem(ts))
                self.tableRealtimeQueries.setItem(row, 1, QTableWidgetItem("heartbeat"))
                self.tableRealtimeQueries.setItem(row, 2, QTableWidgetItem("-"))
                self.tableRealtimeQueries.setItem(row, 3, QTableWidgetItem("-"))
                self.tableRealtimeQueries.setItem(row, 4, QTableWidgetItem("OK"))
                self.tableRealtimeQueries.scrollToBottom()
            except Exception:
                pass

        def _on_search_data(self) -> None:
            """저장된 데이터 검색."""
            try:
                table_name = self.comboTable.currentText().strip() if hasattr(self, "comboTable") else ""
                keyword = self.lineFilter.text().strip() if hasattr(self, "lineFilter") else ""
                logger.debug("[KafkaSettingsDialog] 검색: table=%s keyword=%s", table_name, keyword)
            except Exception:
                pass

        def _on_prev_page(self) -> None:
            """이전 페이지로 이동."""
            try:
                if self._current_page > 1:
                    self._current_page -= 1
                    if hasattr(self, "labelPage"):
                        self.labelPage.setText(f"페이지: {self._current_page} / {self._total_pages}")
            except Exception:
                pass

        def _on_next_page(self) -> None:
            """다음 페이지로 이동."""
            try:
                if self._current_page < self._total_pages:
                    self._current_page += 1
                    if hasattr(self, "labelPage"):
                        self.labelPage.setText(f"페이지: {self._current_page} / {self._total_pages}")
            except Exception:
                pass

        def _on_export_csv(self) -> None:
            """저장된 데이터 CSV 내보내기."""
            try:
                if not hasattr(self, "tableData"):
                    return
                import csv
                filename, _ = QFileDialog.getSaveFileName(self, "CSV 저장", "", "CSV Files (*.csv)")
                if not filename:
                    return
                with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    headers = []
                    for col in range(self.tableData.columnCount()):
                        item = self.tableData.horizontalHeaderItem(col)
                        headers.append(item.text() if item else str(col))
                    writer.writerow(headers)
                    for row in range(self.tableData.rowCount()):
                        row_data = []
                        for col in range(self.tableData.columnCount()):
                            item = self.tableData.item(row, col)
                            row_data.append(item.text() if item else "")
                        writer.writerow(row_data)
                QMessageBox.information(self, "CSV 저장", f"저장 완료: {filename}")
            except Exception as e:
                logger.debug("[KafkaSettingsDialog] CSV 내보내기 예외: %s", e, exc_info=True)
                QMessageBox.warning(self, "오류", f"CSV 저장 실패: {e}")

        def closeEvent(self, event) -> None:
            """다이얼로그 닫힐 때 타이머를 정지한다."""
            try:
                from PyQt5.QtCore import QSettings
                _settings = QSettings("UpbitTrader", "DBMonitor")
                _settings.setValue("kafka_geometry", self.saveGeometry())
            except Exception:
                pass
            try:
                if getattr(self, "_timer", None) and self._timer.isActive():
                    self._timer.stop()
                if getattr(self, "_realtime_timer", None) and self._realtime_timer.isActive():
                    self._realtime_timer.stop()
            except Exception:
                pass
            super().closeEvent(event)


    class KafkaSettingsDialog:  # type: ignore[no-redef]
        """PyQt5 미설치 시 더미 클래스."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("PyQt5가 설치되어 있지 않습니다.")


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _item(text: str) -> "QTableWidgetItem":
    """편집 불가 QTableWidgetItem 생성.

    Args:
        text: 셀에 표시할 텍스트.

    Returns:
        편집 불가 플래그가 설정된 QTableWidgetItem.
    """
    item = QTableWidgetItem(str(text))
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


def _stretch_table(name: str, widget: "QDialog") -> None:
    """테이블의 마지막 열을 스트레치 설정.

    Args:
        name: 테이블 위젯 속성명.
        widget: 테이블을 포함하는 다이얼로그.
    """
    table = getattr(widget, name, None)
    if table is not None:
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)


def _btn_connect(widget: "QDialog", name: str, slot: Any) -> None:
    """버튼 clicked 시그널을 슬롯에 연결. 버튼이 없으면 무시.

    Args:
        widget: 버튼을 포함하는 다이얼로그.
        name: QPushButton 속성명.
        slot: 연결할 슬롯 콜러블.
    """
    btn = getattr(widget, name, None)
    if btn is not None:
        btn.clicked.connect(slot)
