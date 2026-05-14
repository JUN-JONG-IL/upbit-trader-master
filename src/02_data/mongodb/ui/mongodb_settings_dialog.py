#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MongoDB 모니터링 다이얼로그 (6-탭 확장 버전)

탭 구성:
- 탭 1 📡 연결 상태: 연결 LED, Host/DB/Version/ReplicaSet/Uptime/연결 수
- 탭 2 📋 컬렉션 관리: 컬렉션 목록 테이블, 문서 미리보기 테이블
- 탭 3 🔄 CQRS Projection: Projection 동기화 상태 및 수동 동기화
- 탭 4 🌐 Replica Set 상태: 노드 목록, Oplog 정보, Stepdown 버튼
- 탭 5 🔍 인덱스 관리: 컬렉션별 인덱스 목록, 생성/삭제 버튼
- 탭 6 🔀 Sharding: Shard 목록, Balancer 상태

주의사항:
- 모든 DB 쿼리는 백그라운드 스레드에서 실행 (UI 블록 방지)
- pyqtSignal로 스레드 안전 UI 업데이트
- pymongo 미설치 또는 MongoDB 미연결 시 플레이스홀더 데이터 표시
- 10초마다 자동 갱신 (QTimer)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

# ---------------------------------------------------------------------------
# PyQt5 임포트
# ---------------------------------------------------------------------------
try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer, pyqtSignal
    from PyQt5.QtWidgets import (
        QDialog,
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
_UI_PATH = Path(__file__).parent / "mongodb_settings.ui"

# ---------------------------------------------------------------------------
# 연결 상태 색상 상수
# ---------------------------------------------------------------------------
_COLOR_GREEN = "#2ECC40"
_COLOR_RED   = "#FF4136"
_COLOR_GRAY  = "#808080"

# ---------------------------------------------------------------------------
# MongoDB 연결 타임아웃 (ms)
# ---------------------------------------------------------------------------
_CONNECT_TIMEOUT_MS = 5_000


def _get_mongo_uri() -> Tuple[str, str, str, str]:
    """환경변수에서 MongoDB 연결 정보를 읽어 반환한다.

    Returns:
        (uri, host_port, database, user) 튜플.
    """
    host = os.getenv("MONGO_HOST", "localhost")
    port = os.getenv("MONGO_PORT", "27017")
    user = (
        os.getenv("MONGO_USER")
        or os.getenv("MONGO_ID")
        or os.getenv("MONGO_INITDB_ROOT_USERNAME")
        or ""
    )
    password = (
        os.getenv("MONGO_PASSWORD")
        or os.getenv("MONGO_INITDB_ROOT_PASSWORD")
        or ""
    )
    database = os.getenv("MONGO_DB", "upbit_trader")

    if user and password:
        uri = (
            f"mongodb://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:{port}/{database}?authSource=admin"
        )
    else:
        uri = f"mongodb://{host}:{port}/{database}"

    return uri, f"{host}:{port}", database, user


def _make_client():
    """pymongo MongoClient를 생성한다.

    Returns:
        MongoClient 인스턴스.

    Raises:
        ImportError: pymongo가 설치되지 않은 경우.
        pymongo.errors.ServerSelectionTimeoutError: 서버에 연결할 수 없는 경우.
    """
    from pymongo import MongoClient  # noqa: PLC0415

    uri, _, _, _ = _get_mongo_uri()
    return MongoClient(
        uri,
        serverSelectionTimeoutMS=_CONNECT_TIMEOUT_MS,
        connectTimeoutMS=_CONNECT_TIMEOUT_MS,
    )


# ===========================================================================
# MongoDBSettingsDialog
# ===========================================================================
if PYQT5_AVAILABLE:
    # 삭제 기능 믹스인 로드
    def _load_mongo_delete_mixin():
        try:
            from pathlib import Path as _Path
            import importlib.util as _ilu
            _p = _Path(__file__).parent / "mongodb_delete_operations.py"
            if _p.exists():
                _spec = _ilu.spec_from_file_location("mongodb_delete_operations", str(_p))
                if _spec and _spec.loader:
                    _m = _ilu.module_from_spec(_spec)
                    _spec.loader.exec_module(_m)  # type: ignore
                    return getattr(_m, "MongoDeleteMixin", None)
        except Exception:
            pass
        return None

    _MongoDeleteMixin = _load_mongo_delete_mixin()
    if _MongoDeleteMixin is None:
        class _MongoDeleteMixin:  # type: ignore[no-redef]
            def _bind_mongo_delete_signals(self): pass

    class MongoDBSettingsDialog(QDialog, _MongoDeleteMixin):
        """MongoDB 6-탭 읽기 전용 모니터링 다이얼로그.

        탭 구성:
            - 탭 1 📡 연결 상태
            - 탭 2 📋 컬렉션 관리
            - 탭 3 🔄 CQRS Projection
            - 탭 4 🌐 Replica Set 상태
            - 탭 5 🔍 인덱스 관리
            - 탭 6 🔀 Sharding
            - 탭 7 🗑️ 데이터 삭제
        """

        # ------------------------------------------------------------------
        # 스레드 → UI 업데이트용 시그널 (스레드 안전)
        # ------------------------------------------------------------------
        _sig_conn_ready        = pyqtSignal(dict)   # 탭 1: 연결 상태
        _sig_conn_status_color = pyqtSignal(str)    # 탭 1: LED 색상
        _sig_collections_ready = pyqtSignal(list)   # 탭 2: 컬렉션 목록
        _sig_documents_ready   = pyqtSignal(list)   # 탭 2: 문서 미리보기
        _sig_projections_ready = pyqtSignal(list)   # 탭 3: Projection 목록
        _sig_replica_ready     = pyqtSignal(dict)   # 탭 4: Replica Set
        _sig_indexes_ready     = pyqtSignal(list)   # 탭 5: 인덱스 목록
        _sig_sharding_ready    = pyqtSignal(dict)   # 탭 6: Sharding 정보

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)

            try:
                uic.loadUi(str(_UI_PATH), self)
            except Exception as exc:
                logger.error("[MongoDBSettingsDialog] UI 파일 로드 실패: %s", exc)
                return

            self._uri, self._host_port, self._database, self._user = _get_mongo_uri()

            self._setup_tables()
            self._connect_signals()
            self._show_static_conn_info()

            # 삭제 탭 버튼 바인딩 (MongoDeleteMixin)
            self._bind_mongo_delete_signals()

            # 10초 자동 갱신 타이머
            self._timer = QTimer(self)
            self._timer.setInterval(10_000)
            self._timer.timeout.connect(self.refresh_data)
            self._timer.start()

            self.refresh_data()

            # 비모달 팝업 설정
            from PyQt5.QtCore import Qt
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
                _geometry = _settings.value("mongodb_geometry")
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
        # 초기 설정
        # ------------------------------------------------------------------

        def _setup_tables(self) -> None:
            """모든 탭의 테이블 위젯 컬럼 헤더 및 리사이즈 정책을 설정한다."""
            _tables: List[Tuple[Any, List[str]]] = []
            try:
                _tables = [
                    (self.tableCollections,
                     ["컬렉션명", "문서수", "크기", "평균크기", "인덱스수"]),
                    (self.tableDocuments,
                     ["_id", "문서 (JSON 미리보기)"]),
                    (self.tableProjections,
                     ["이름", "원본", "마지막 동기화", "지연시간", "문서수"]),
                    (self.tableReplicaNodes,
                     ["역할", "주소", "상태", "우선순위", "복제 지연"]),
                    (self.tableIndexes,
                     ["컬렉션", "인덱스명", "필드", "유형", "고유", "크기"]),
                    (self.tableShards,
                     ["Shard", "조건", "데이터 비율"]),
                ]
            except AttributeError as exc:
                logger.debug("[MongoDBSettingsDialog] 테이블 위젯 접근 오류: %s", exc)
                return

            for table, headers in _tables:
                try:
                    table.setColumnCount(len(headers))
                    table.setHorizontalHeaderLabels(headers)
                    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    table.setEditTriggers(table.NoEditTriggers)
                    table.setSelectionBehavior(table.SelectRows)
                    table.setAlternatingRowColors(True)
                except Exception as exc:
                    logger.debug("[MongoDBSettingsDialog] 테이블 설정 오류: %s", exc)

        def _connect_signals(self) -> None:
            """버튼 클릭 및 스레드 시그널을 슬롯에 연결한다."""
            try:
                # 탭 1
                self.btnConnect.clicked.connect(self.load_connection_info)
                # 탭 2
                self.btnRefreshCollections.clicked.connect(self.load_collections)
                self.tableCollections.itemSelectionChanged.connect(
                    self._on_collection_selected
                )
                # 탭 3
                self.btnSyncProjection.clicked.connect(self._on_sync_projection)
                # 탭 4
                self.btnStepDown.clicked.connect(self._on_step_down)
                # 탭 5
                self.btnCreateIndex.clicked.connect(self._on_create_index)
                self.btnDropIndex.clicked.connect(self._on_drop_index)
                # 닫기
                self.buttonBox.rejected.connect(self.reject)
                # 새 탭 버튼
                if hasattr(self, "btnSearch"):
                    self.btnSearch.clicked.connect(self._on_search_data)
                if hasattr(self, "btnPrevPage"):
                    self.btnPrevPage.clicked.connect(self._on_prev_page)
                if hasattr(self, "btnNextPage"):
                    self.btnNextPage.clicked.connect(self._on_next_page)
                if hasattr(self, "btnExportCSV"):
                    self.btnExportCSV.clicked.connect(self._on_export_csv)
            except AttributeError as exc:
                logger.debug("[MongoDBSettingsDialog] 버튼 연결 오류: %s", exc)

            # 스레드 → UI 시그널
            try:
                self._sig_conn_ready.connect(self._update_conn_ui)
                self._sig_conn_status_color.connect(self._update_conn_led)
                self._sig_collections_ready.connect(self._update_collections_ui)
                self._sig_documents_ready.connect(self._update_documents_ui)
                self._sig_projections_ready.connect(self._update_projections_ui)
                self._sig_replica_ready.connect(self._update_replica_ui)
                self._sig_indexes_ready.connect(self._update_indexes_ui)
                self._sig_sharding_ready.connect(self._update_sharding_ui)
            except AttributeError as exc:
                logger.debug("[MongoDBSettingsDialog] 시그널 연결 오류: %s", exc)

        def _show_static_conn_info(self) -> None:
            """탭 1에 정적 연결 정보(Host, DB)를 즉시 표시한다."""
            try:
                self.labelHost.setText(self._host_port)
                self.labelDB.setText(self._database)
            except AttributeError:
                pass

        # ------------------------------------------------------------------
        # 공개 메서드: 데이터 로드
        # ------------------------------------------------------------------

        def refresh_data(self) -> None:
            """모든 탭 데이터를 병렬로 새로고침한다."""
            self.load_connection_info()
            self.load_collections()
            self.load_projections()
            self.load_replica_set()
            self.load_indexes()
            self.load_sharding()

        def load_connection_info(self) -> None:
            """탭 1: MongoDB 서버 연결 정보를 백그라운드에서 조회한다."""
            threading.Thread(target=self._fetch_conn_info, daemon=True).start()

        def load_collections(self) -> None:
            """탭 2: 컬렉션 목록을 백그라운드에서 조회한다."""
            threading.Thread(target=self._fetch_collections, daemon=True).start()

        def load_documents(self, collection_name: str) -> None:
            """탭 2: 지정 컬렉션의 문서 미리보기를 백그라운드에서 조회한다.

            Args:
                collection_name: 조회할 컬렉션 이름.
            """
            threading.Thread(
                target=self._fetch_documents, args=(collection_name,), daemon=True
            ).start()

        def load_projections(self) -> None:
            """탭 3: CQRS Projection 상태를 백그라운드에서 조회한다."""
            threading.Thread(target=self._fetch_projections, daemon=True).start()

        def load_replica_set(self) -> None:
            """탭 4: Replica Set 상태를 백그라운드에서 조회한다."""
            threading.Thread(target=self._fetch_replica_set, daemon=True).start()

        def load_indexes(self) -> None:
            """탭 5: 컬렉션별 인덱스 목록을 백그라운드에서 조회한다."""
            threading.Thread(target=self._fetch_indexes, daemon=True).start()

        def load_sharding(self) -> None:
            """탭 6: Sharding 구성 정보를 백그라운드에서 조회한다."""
            threading.Thread(target=self._fetch_sharding, daemon=True).start()

        # ------------------------------------------------------------------
        # 백그라운드 쿼리 메서드
        # ------------------------------------------------------------------

        def _fetch_conn_info(self) -> None:
            """백그라운드: 탭 1 연결 상태 데이터를 수집한다."""
            result: Dict[str, str] = {
                "version":     "-",
                "replica_set": "없음",
                "uptime":      "-",
                "conn_count":  "-",
            }
            color = "red"
            try:
                client = _make_client()
                try:
                    info = client.server_info()
                    result["version"] = f"MongoDB {info.get('version', '-')}"

                    status = client.admin.command("serverStatus")
                    uptime_sec = status.get("uptime", 0)
                    hours, rem = divmod(int(uptime_sec), 3600)
                    mins = rem // 60
                    result["uptime"] = f"{hours}시간 {mins}분"
                    result["conn_count"] = str(
                        status.get("connections", {}).get("current", "-")
                    )
                    result["replica_set"] = (
                        status.get("repl", {}).get("setName", "없음") or "없음"
                    )
                    color = "green"
                finally:
                    client.close()
            except Exception as exc:
                logger.debug("[MongoDBSettingsDialog] 연결 정보 조회 오류: %s", exc)

            self._sig_conn_status_color.emit(color)
            self._sig_conn_ready.emit(result)

        def _fetch_collections(self) -> None:
            """백그라운드: 탭 2 컬렉션 목록 데이터를 수집한다."""
            rows: List[Dict[str, Any]] = []
            try:
                client = _make_client()
                try:
                    db = client[self._database]
                    for name in sorted(db.list_collection_names()):
                        try:
                            stats = db.command("collstats", name)
                            rows.append({
                                "name":       name,
                                "count":      f"{stats.get('count', 0):,}",
                                "size":       f"{stats.get('size', 0) / 1024:.1f} KB",
                                "avg_size":   f"{stats.get('avgObjSize', 0):.0f} B",
                                "index_count": str(stats.get("nindexes", 0)),
                            })
                        except Exception:
                            rows.append({
                                "name": name, "count": "-",
                                "size": "-", "avg_size": "-", "index_count": "-",
                            })
                finally:
                    client.close()
            except Exception as exc:
                logger.debug("[MongoDBSettingsDialog] 컬렉션 목록 조회 오류: %s", exc)
                rows = [{"name": "(연결 불가)", "count": "-", "size": "-",
                         "avg_size": "-", "index_count": "-"}]

            self._sig_collections_ready.emit(rows)

        def _fetch_documents(self, collection_name: str) -> None:
            """백그라운드: 탭 2 문서 미리보기 데이터를 수집한다.

            Args:
                collection_name: 조회할 컬렉션 이름.
            """
            rows: List[Tuple[str, str]] = []
            try:
                client = _make_client()
                try:
                    db = client[self._database]
                    for doc in db[collection_name].find().limit(20):
                        doc_id = str(doc.pop("_id", "-"))
                        preview = json.dumps(doc, ensure_ascii=False, default=str)
                        if len(preview) > 200:
                            preview = preview[:200] + "..."
                        rows.append((doc_id, preview))
                finally:
                    client.close()
            except Exception as exc:
                logger.debug("[MongoDBSettingsDialog] 문서 조회 오류: %s", exc)
                rows = [("(오류)", str(exc))]

            self._sig_documents_ready.emit(rows)

        def _fetch_projections(self) -> None:
            """백그라운드: 탭 3 CQRS Projection 상태를 수집한다.

            MongoDB에 cqrs_projections 컬렉션이 없으면 플레이스홀더를 반환한다.
            """
            rows: List[Dict[str, str]] = []
            try:
                client = _make_client()
                try:
                    db = client[self._database]
                    colls = db.list_collection_names()
                    if "cqrs_projections" in colls:
                        for doc in db.cqrs_projections.find():
                            rows.append({
                                "name":      doc.get("name", "-"),
                                "source":    doc.get("source", "-"),
                                "last_sync": str(doc.get("last_sync", "-")),
                                "lag":       str(doc.get("lag_ms", "-")) + " ms",
                                "count":     str(doc.get("count", "-")),
                            })
                    else:
                        rows = [{"name": "(cqrs_projections 컬렉션 없음)",
                                 "source": "-", "last_sync": "-",
                                 "lag": "-", "count": "-"}]
                finally:
                    client.close()
            except Exception as exc:
                logger.debug("[MongoDBSettingsDialog] Projection 조회 오류: %s", exc)
                rows = [{"name": "(연결 불가)", "source": "-",
                         "last_sync": "-", "lag": "-", "count": "-"}]

            self._sig_projections_ready.emit(rows)

        def _fetch_replica_set(self) -> None:
            """백그라운드: 탭 4 Replica Set 노드 및 Oplog 정보를 수집한다."""
            result: Dict[str, Any] = {
                "nodes":         [],
                "oplog_size":    "-",
                "oplog_lag":     "-",
                "last_election": "-",
            }
            try:
                client = _make_client()
                try:
                    rs_status = client.admin.command("replSetGetStatus")
                    members = rs_status.get("members", [])
                    nodes: List[Dict[str, str]] = []
                    for m in members:
                        state_str = m.get("stateStr", "-")
                        role = "PRIMARY" if state_str == "PRIMARY" else "SECONDARY"
                        nodes.append({
                            "role":     role,
                            "address":  m.get("name", "-"),
                            "state":    state_str,
                            "priority": str(m.get("priority", "-")),
                            "lag":      str(m.get("optimeDate", "-")),
                        })
                    result["nodes"] = nodes
                    result["last_election"] = str(
                        rs_status.get("lastStableRecoveryTimestamp", "-")
                    )

                    # Oplog
                    try:
                        oplog_stats = client.local.oplog.rs.stats()
                        size_mb = oplog_stats.get("maxSize", 0) / (1024 * 1024)
                        result["oplog_size"] = f"{size_mb:.1f} MB"
                    except Exception:
                        result["oplog_size"] = "조회 불가"
                finally:
                    client.close()
            except Exception as exc:
                logger.debug("[MongoDBSettingsDialog] Replica Set 조회 오류: %s", exc)
                result["nodes"] = [{"role": "(연결 불가)", "address": "-",
                                    "state": "-", "priority": "-", "lag": "-"}]

            self._sig_replica_ready.emit(result)

        def _fetch_indexes(self) -> None:
            """백그라운드: 탭 5 컬렉션별 인덱스 목록을 수집한다."""
            rows: List[Dict[str, str]] = []
            try:
                client = _make_client()
                try:
                    db = client[self._database]
                    for coll_name in sorted(db.list_collection_names()):
                        try:
                            for idx in db[coll_name].index_information().values():
                                fields = ", ".join(
                                    f"{k}({v})" for k, v in idx.get("key", [])
                                )
                                idx_type = "text" if "textIndexVersion" in idx else "btree"
                                rows.append({
                                    "collection": coll_name,
                                    "name":       idx.get("name", "-"),
                                    "fields":     fields,
                                    "type":       idx_type,
                                    "unique":     "✔" if idx.get("unique") else "",
                                    "size":       "-",
                                })
                        except Exception:
                            pass
                finally:
                    client.close()
            except Exception as exc:
                logger.debug("[MongoDBSettingsDialog] 인덱스 목록 조회 오류: %s", exc)
                rows = [{"collection": "(연결 불가)", "name": "-", "fields": "-",
                         "type": "-", "unique": "-", "size": "-"}]

            self._sig_indexes_ready.emit(rows)

        def _fetch_sharding(self) -> None:
            """백그라운드: 탭 6 Sharding 구성 정보를 수집한다."""
            result: Dict[str, Any] = {
                "shards":           [],
                "balancer_status":  "-",
                "last_balance":     "-",
            }
            try:
                client = _make_client()
                try:
                    config_db = client["config"]
                    shards_col = config_db["shards"]
                    shards: List[Dict[str, str]] = []
                    for shard in shards_col.find():
                        shards.append({
                            "id":   shard.get("_id", "-"),
                            "host": shard.get("host", "-"),
                            "ratio": "-",
                        })
                    result["shards"] = shards if shards else [
                        {"id": "(Sharding 미구성)", "host": "-", "ratio": "-"}
                    ]

                    try:
                        balancer = client.admin.command("balancerStatus")
                        result["balancer_status"] = (
                            "활성" if balancer.get("mode") == "full" else "비활성"
                        )
                    except Exception:
                        result["balancer_status"] = "조회 불가"
                finally:
                    client.close()
            except Exception as exc:
                logger.debug("[MongoDBSettingsDialog] Sharding 조회 오류: %s", exc)
                result["shards"] = [{"id": "(연결 불가)", "host": "-", "ratio": "-"}]

            self._sig_sharding_ready.emit(result)

        # ------------------------------------------------------------------
        # UI 업데이트 슬롯 (메인 스레드에서 실행)
        # ------------------------------------------------------------------

        def _update_conn_led(self, color: str) -> None:
            """탭 1: 연결 상태 LED 색상과 텍스트를 업데이트한다.

            Args:
                color: "green", "red", 또는 "gray".
            """
            try:
                css_color = {"green": _COLOR_GREEN, "red": _COLOR_RED}.get(
                    color, _COLOR_GRAY
                )
                text = {
                    "green": "● 연결 정상",
                    "red":   "● 연결 실패",
                }.get(color, "● 확인 중...")
                self.labelConnStatus.setStyleSheet(
                    f"color: {css_color}; font-size: 14px;"
                )
                self.labelConnStatus.setText(text)
            except AttributeError:
                pass

        def _update_conn_ui(self, data: Dict[str, str]) -> None:
            """탭 1: 연결 세부 정보 레이블을 업데이트한다.

            Args:
                data: version, replica_set, uptime, conn_count 키를 포함하는 딕셔너리.
            """
            try:
                self.labelVersion.setText(data.get("version", "-"))
                self.labelReplicaSet.setText(data.get("replica_set", "-"))
                self.labelUptime.setText(data.get("uptime", "-"))
                self.labelConnCount.setText(data.get("conn_count", "-"))
            except AttributeError as exc:
                logger.debug("[MongoDBSettingsDialog] 연결 UI 업데이트 오류: %s", exc)

        def _update_collections_ui(self, rows: List[Dict[str, Any]]) -> None:
            """탭 2: 컬렉션 목록 테이블을 업데이트한다.

            Args:
                rows: 컬렉션별 통계 딕셔너리 목록 (name, count, size, avg_size, index_count).
            """
            try:
                table = self.tableCollections
                table.setRowCount(0)
                for row in rows:
                    r = table.rowCount()
                    table.insertRow(r)
                    table.setItem(r, 0, QTableWidgetItem(row.get("name", "-")))
                    table.setItem(r, 1, QTableWidgetItem(row.get("count", "-")))
                    table.setItem(r, 2, QTableWidgetItem(row.get("size", "-")))
                    table.setItem(r, 3, QTableWidgetItem(row.get("avg_size", "-")))
                    table.setItem(r, 4, QTableWidgetItem(row.get("index_count", "-")))
            except AttributeError as exc:
                logger.debug("[MongoDBSettingsDialog] 컬렉션 UI 오류: %s", exc)

        def _update_documents_ui(self, rows: List[Tuple[str, str]]) -> None:
            """탭 2: 문서 미리보기 테이블을 업데이트한다.

            Args:
                rows: (_id 문자열, JSON 미리보기 문자열) 튜플 목록.
            """
            try:
                table = self.tableDocuments
                table.setRowCount(0)
                for doc_id, preview in rows:
                    r = table.rowCount()
                    table.insertRow(r)
                    table.setItem(r, 0, QTableWidgetItem(doc_id))
                    table.setItem(r, 1, QTableWidgetItem(preview))
            except AttributeError as exc:
                logger.debug("[MongoDBSettingsDialog] 문서 미리보기 UI 오류: %s", exc)

        def _update_projections_ui(self, rows: List[Dict[str, str]]) -> None:
            """탭 3: Projection 목록 테이블을 업데이트한다.

            Args:
                rows: projection 정보 딕셔너리 목록 (name, source, last_sync, lag, count).
            """
            try:
                table = self.tableProjections
                table.setRowCount(0)
                for row in rows:
                    r = table.rowCount()
                    table.insertRow(r)
                    table.setItem(r, 0, QTableWidgetItem(row.get("name", "-")))
                    table.setItem(r, 1, QTableWidgetItem(row.get("source", "-")))
                    table.setItem(r, 2, QTableWidgetItem(row.get("last_sync", "-")))
                    table.setItem(r, 3, QTableWidgetItem(row.get("lag", "-")))
                    table.setItem(r, 4, QTableWidgetItem(row.get("count", "-")))

                has_data = bool(rows) and rows[0].get("name", "").startswith("(") is False
                status = "정상" if has_data else "데이터 없음"
                self.labelProjectionStatus.setText(f"Projection 상태: {status}")
            except AttributeError as exc:
                logger.debug("[MongoDBSettingsDialog] Projection UI 오류: %s", exc)

        def _update_replica_ui(self, data: Dict[str, Any]) -> None:
            """탭 4: Replica Set 노드 테이블 및 Oplog 레이블을 업데이트한다.

            Args:
                data: nodes 리스트와 oplog_size, oplog_lag, last_election 키를 포함하는 딕셔너리.
            """
            try:
                table = self.tableReplicaNodes
                table.setRowCount(0)
                for node in data.get("nodes", []):
                    r = table.rowCount()
                    table.insertRow(r)
                    table.setItem(r, 0, QTableWidgetItem(node.get("role", "-")))
                    table.setItem(r, 1, QTableWidgetItem(node.get("address", "-")))
                    table.setItem(r, 2, QTableWidgetItem(node.get("state", "-")))
                    table.setItem(r, 3, QTableWidgetItem(node.get("priority", "-")))
                    table.setItem(r, 4, QTableWidgetItem(node.get("lag", "-")))

                self.labelOplogSize.setText(data.get("oplog_size", "-"))
                self.labelOplogLag.setText(data.get("oplog_lag", "-"))
                self.labelLastElection.setText(str(data.get("last_election", "-")))
            except AttributeError as exc:
                logger.debug("[MongoDBSettingsDialog] Replica Set UI 오류: %s", exc)

        def _update_indexes_ui(self, rows: List[Dict[str, str]]) -> None:
            """탭 5: 인덱스 목록 테이블을 업데이트한다.

            Args:
                rows: 인덱스 정보 딕셔너리 목록 (collection, name, fields, type, unique, size).
            """
            try:
                table = self.tableIndexes
                table.setRowCount(0)
                for row in rows:
                    r = table.rowCount()
                    table.insertRow(r)
                    table.setItem(r, 0, QTableWidgetItem(row.get("collection", "-")))
                    table.setItem(r, 1, QTableWidgetItem(row.get("name", "-")))
                    table.setItem(r, 2, QTableWidgetItem(row.get("fields", "-")))
                    table.setItem(r, 3, QTableWidgetItem(row.get("type", "-")))
                    table.setItem(r, 4, QTableWidgetItem(row.get("unique", "")))
                    table.setItem(r, 5, QTableWidgetItem(row.get("size", "-")))
            except AttributeError as exc:
                logger.debug("[MongoDBSettingsDialog] 인덱스 UI 오류: %s", exc)

        def _update_sharding_ui(self, data: Dict[str, Any]) -> None:
            """탭 6: Shard 목록 테이블 및 Balancer 레이블을 업데이트한다.

            Args:
                data: shards 리스트, balancer_status, last_balance 키를 포함하는 딕셔너리.
            """
            try:
                table = self.tableShards
                table.setRowCount(0)
                for shard in data.get("shards", []):
                    r = table.rowCount()
                    table.insertRow(r)
                    table.setItem(r, 0, QTableWidgetItem(shard.get("id", "-")))
                    table.setItem(r, 1, QTableWidgetItem(shard.get("host", "-")))
                    table.setItem(r, 2, QTableWidgetItem(shard.get("ratio", "-")))

                self.labelBalancerStatus.setText(data.get("balancer_status", "-"))
                self.labelLastBalance.setText(data.get("last_balance", "-"))
            except AttributeError as exc:
                logger.debug("[MongoDBSettingsDialog] Sharding UI 오류: %s", exc)

        # ------------------------------------------------------------------
        # 버튼 이벤트 핸들러
        # ------------------------------------------------------------------

        def _on_collection_selected(self) -> None:
            """탭 2: 컬렉션 선택 시 해당 컬렉션의 문서 미리보기를 로드한다."""
            try:
                selected = self.tableCollections.selectedItems()
                if selected:
                    coll_name = selected[0].text()
                    if not coll_name.startswith("("):
                        self.load_documents(coll_name)
            except Exception as exc:
                logger.debug("[MongoDBSettingsDialog] 컬렉션 선택 오류: %s", exc)

        def _on_sync_projection(self) -> None:
            """탭 3: 수동 Projection 동기화 버튼 핸들러 (스텁)."""
            try:
                self.labelProjectionStatus.setText("Projection 상태: 동기화 요청됨...")
                self.load_projections()
            except AttributeError:
                pass

        def _on_step_down(self) -> None:
            """탭 4: Replica Set PRIMARY Stepdown 버튼 핸들러."""
            reply = QMessageBox.warning(
                self,
                "Stepdown 확인",
                "PRIMARY를 Stepdown 하시겠습니까?\n이 작업은 Replica Set 재선출을 유발합니다.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            def _do_stepdown() -> None:
                try:
                    client = _make_client()
                    try:
                        client.admin.command("replSetStepDown", 60)
                    finally:
                        client.close()
                except Exception as exc:
                    logger.warning("[MongoDBSettingsDialog] Stepdown 실패: %s", exc)
                self._sig_replica_ready.emit({
                    "nodes": [{"role": "-", "address": "-", "state": "재선출 중",
                               "priority": "-", "lag": "-"}],
                    "oplog_size": "-", "oplog_lag": "-", "last_election": "-",
                })
            threading.Thread(target=_do_stepdown, daemon=True).start()

        def _on_create_index(self) -> None:
            """탭 5: 인덱스 생성 버튼 핸들러 (스텁 — 별도 UI 필요)."""
            QMessageBox.information(
                self, "인덱스 생성", "인덱스 생성 기능은 별도 다이얼로그에서 지원 예정입니다."
            )

        def _on_drop_index(self) -> None:
            """탭 5: 인덱스 삭제 버튼 핸들러 (스텁 — 별도 UI 필요)."""
            QMessageBox.information(
                self, "인덱스 삭제", "인덱스 삭제 기능은 별도 다이얼로그에서 지원 예정입니다."
            )

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
                logger.debug("[MongoDBSettingsDialog] 검색: table=%s keyword=%s", table_name, keyword)
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
                from PyQt5.QtWidgets import QFileDialog
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
                logger.debug("[MongoDBSettingsDialog] CSV 내보내기 예외: %s", e, exc_info=True)
                QMessageBox.warning(self, "오류", f"CSV 저장 실패: {e}")

        # ------------------------------------------------------------------
        # 다이얼로그 종료 처리
        # ------------------------------------------------------------------

        def closeEvent(self, event) -> None:
            """다이얼로그 닫힐 때 자동 갱신 타이머를 정지한다."""
            try:
                from PyQt5.QtCore import QSettings
                _settings = QSettings("UpbitTrader", "DBMonitor")
                _settings.setValue("mongodb_geometry", self.saveGeometry())
            except Exception:
                pass
            try:
                self._timer.stop()
                if getattr(self, "_realtime_timer", None) and self._realtime_timer.isActive():
                    self._realtime_timer.stop()
            except Exception:
                pass
            super().closeEvent(event)

else:
    # PyQt5 미설치 환경을 위한 더미 클래스
    class MongoDBSettingsDialog:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 빈 클래스."""

        def __init__(self, parent: object = None) -> None:
            logger.warning("[MongoDBSettingsDialog] PyQt5 미설치 - 다이얼로그 생성 불가")
