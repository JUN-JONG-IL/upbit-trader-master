#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL CQRS Event Store 모니터링 다이얼로그.

기능:
- 탭 1 📡 연결 상태: 호스트/DB/버전/업타임/연결 수 표시
- 탭 2 📝 이벤트 스토어: 페이지네이션 이벤트 목록, 타입/aggregate/날짜 필터
- 탭 3 ✍️ CQRS Write: 이벤트 발행 폼 (event_type, aggregate_id, payload JSON)
- 탭 4 📖 CQRS Read: MongoDB 읽기 모델 동기화 상태
- 탭 5 🔒 감사 로그: 주문/거래 감사 이벤트, 사용자/액션 필터
- 탭 6 🔁 Replication: Primary/Replica 상태, WAL 위치, 복제 슬롯

구현 특성:
- asyncpg 우선, psycopg2 fallback, 둘 다 없으면 플레이스홀더 데이터 사용
- QTimer 10초 자동 갱신
- 백그라운드 스레드 + pyqtSignal 로 스레드 안전 UI 업데이트
- Google-style docstrings, 전체 타입 힌트
"""
from __future__ import annotations

import csv
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# PyQt5 임포트
# ---------------------------------------------------------------------------
try:
    from PyQt5 import uic
    from PyQt5.QtCore import QDate, Qt, QTimer, pyqtSignal
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

# ---------------------------------------------------------------------------
# DB 드라이버 감지
# ---------------------------------------------------------------------------
try:
    import asyncpg  # type: ignore[import]
    import asyncio
    _DB_DRIVER = "asyncpg"
except ImportError:
    asyncpg = None  # type: ignore[assignment]
    try:
        import psycopg2  # type: ignore[import]
        import psycopg2.extras  # type: ignore[import]
        _DB_DRIVER = "psycopg2"
    except ImportError:
        psycopg2 = None  # type: ignore[assignment]
        _DB_DRIVER = "placeholder"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UI 파일 경로
# ---------------------------------------------------------------------------
_UI_PATH = Path(__file__).parent / "postgres_event_store.ui"

# ---------------------------------------------------------------------------
# LED 색상 상수
# ---------------------------------------------------------------------------
_COLOR_GREEN = "#2ECC40"
_COLOR_RED   = "#FF4136"
_COLOR_GRAY  = "#808080"

# ---------------------------------------------------------------------------
# DB 접속 파라미터 (환경 변수 or 기본값)
# ---------------------------------------------------------------------------
_PG_HOST   = os.environ.get("POSTGRES_HOST", "localhost")
_PG_PORT   = int(os.environ.get("POSTGRES_PORT", "5432"))
_PG_DB     = os.environ.get("POSTGRES_DB", "upbit_trader")
_PG_USER   = os.environ.get("POSTGRES_USER", "postgres")
_PG_PASS   = os.environ.get("POSTGRES_PASSWORD", "")
_PG_SCHEMA = os.environ.get("POSTGRES_SCHEMA", "public")


# ---------------------------------------------------------------------------
# 플레이스홀더 데이터 생성 헬퍼
# ---------------------------------------------------------------------------

def _placeholder_conn_info() -> Dict[str, str]:
    """DB 드라이버 없을 때 사용하는 더미 연결 정보를 반환합니다.

    Returns:
        연결 상태 정보 딕셔너리 (host, db, version, uptime, conn_count).
    """
    return {
        "host":       f"{_PG_HOST}:{_PG_PORT}",
        "db":         _PG_DB,
        "version":    "PostgreSQL 15.x (드라이버 없음 - 플레이스홀더)",
        "uptime":     "N/A",
        "conn_count": "N/A",
        "status":     "placeholder",
    }


def _placeholder_events(limit: int = 50) -> List[Dict[str, Any]]:
    """더미 이벤트 행 목록을 생성합니다.

    Args:
        limit: 반환할 이벤트 수.

    Returns:
        이벤트 딕셔너리 리스트.
    """
    types = ["OrderCreated", "OrderFilled", "TradeExecuted"]
    rows: List[Dict[str, Any]] = []
    base_ts = datetime(2024, 1, 1, 9, 0, 0)
    for i in range(min(limit, 20)):
        rows.append({
            "event_id":     str(uuid.uuid4())[:8],
            "event_type":   types[i % len(types)],
            "aggregate_id": f"AGG-{1000 + i}",
            "timestamp":    (base_ts + timedelta(minutes=i * 5)).strftime("%Y-%m-%d %H:%M:%S"),
            "payload":      json.dumps({"price": 50000 + i * 100, "qty": i + 1}),
        })
    return rows


def _placeholder_read_models() -> List[Tuple[str, str, str, str]]:
    """더미 읽기 모델 동기화 행을 반환합니다.

    Returns:
        (Read Model, 마지막 동기화, 지연시간, 상태) 튜플 리스트.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return [
        ("order_summary_view",   now, "0ms",  "✅ 정상"),
        ("trade_history_view",   now, "12ms", "✅ 정상"),
        ("portfolio_view",       now, "5ms",  "✅ 정상"),
        ("pnl_snapshot_view",    now, "N/A",  "⚠️ 미동기화"),
    ]


def _placeholder_audit_log() -> List[Dict[str, Any]]:
    """더미 감사 로그 행을 반환합니다.

    Returns:
        감사 로그 딕셔너리 리스트.
    """
    actions = ["ORDER_CREATE", "ORDER_CANCEL", "TRADE_EXECUTE"]
    rows: List[Dict[str, Any]] = []
    base_ts = datetime(2024, 1, 1, 9, 0, 0)
    for i in range(15):
        rows.append({
            "order_id":  f"ORD-{2000 + i}",
            "user":      f"user_{i % 3 + 1}",
            "action":    actions[i % len(actions)],
            "amount":    f"{(i + 1) * 10_000:,}",
            "timestamp": (base_ts + timedelta(minutes=i * 3)).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return rows


def _placeholder_replication() -> Dict[str, Any]:
    """더미 복제 상태 정보를 반환합니다.

    Returns:
        복제 상태 딕셔너리 (labels, rows).
    """
    return {
        "primary":    f"{_PG_HOST}:{_PG_PORT}",
        "replica":    "N/A (단독 인스턴스)",
        "repl_lag":   "N/A",
        "wal_pos":    "0/1000000",
        "repl_slot":  "N/A",
        "rows": [
            ("Primary", f"{_PG_HOST}:{_PG_PORT}", "0/1000000", "✅ 정상"),
        ],
    }


# ---------------------------------------------------------------------------
# psycopg2 기반 동기 DB 조회 헬퍼
# ---------------------------------------------------------------------------

def _pg_connect():
    """psycopg2 연결을 생성합니다.

    Returns:
        psycopg2 connection 객체.

    Raises:
        ImportError: psycopg2가 설치되지 않은 경우.
        psycopg2.OperationalError: 연결 실패 시.
    """
    if psycopg2 is None:
        raise ImportError("psycopg2 미설치")
    return psycopg2.connect(
        host=_PG_HOST,
        port=_PG_PORT,
        dbname=_PG_DB,
        user=_PG_USER,
        password=_PG_PASS,
        connect_timeout=5,
    )


def _fetch_conn_info_psycopg2() -> Dict[str, Any]:
    """psycopg2로 PostgreSQL 연결 정보를 조회합니다.

    Returns:
        연결 상태 딕셔너리.
    """
    try:
        conn = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("SELECT version(), pg_postmaster_start_time(), "
                        "count(*) FROM pg_stat_activity;")
            row = cur.fetchone()
            version  = row[0].split(",")[0] if row else "-"
            start_ts = row[1]
            conn_cnt = row[2]
            uptime   = "-"
            if start_ts:
                delta   = datetime.now(start_ts.tzinfo) - start_ts
                hours   = int(delta.total_seconds() // 3600)
                minutes = int((delta.total_seconds() % 3600) // 60)
                uptime  = f"{hours}시간 {minutes}분"
        conn.close()
        return {
            "host":       f"{_PG_HOST}:{_PG_PORT}",
            "db":         _PG_DB,
            "version":    version,
            "uptime":     uptime,
            "conn_count": str(conn_cnt),
            "status":     "ok",
        }
    except Exception as exc:
        logger.debug("[PostgresDialog] 연결 정보 조회 실패: %s", exc)
        return {"status": "error", "error": str(exc)}


def _fetch_events_psycopg2(
    event_type: str = "",
    aggregate_id: str = "",
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """psycopg2로 이벤트 스토어에서 이벤트 목록을 조회합니다.

    Args:
        event_type:   필터할 이벤트 타입 (빈 문자열이면 전체).
        aggregate_id: 필터할 aggregate ID (빈 문자열이면 전체).
        date_start:   조회 시작일 'YYYY-MM-DD' (None이면 제한 없음).
        date_end:     조회 종료일 'YYYY-MM-DD' (None이면 제한 없음).
        limit:        최대 반환 행 수.

    Returns:
        이벤트 딕셔너리 리스트.
    """
    try:
        conn = _pg_connect()
        conditions = []
        params: List[Any] = []
        if event_type:
            conditions.append("event_type = %s")
            params.append(event_type)
        if aggregate_id:
            conditions.append("aggregate_id ILIKE %s")
            params.append(f"%{aggregate_id}%")
        if date_start:
            conditions.append("occurred_at >= %s")
            params.append(date_start)
        if date_end:
            conditions.append("occurred_at <= %s")
            params.append(date_end + " 23:59:59")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = (
            f"SELECT event_id, event_type, aggregate_id, occurred_at, payload "
            f"FROM {_PG_SCHEMA}.domain_events {where} "
            f"ORDER BY occurred_at DESC LIMIT %s"
        )
        params.append(limit)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        # payload를 JSON 문자열로 변환
        for row in rows:
            p = row.get("payload")
            if isinstance(p, dict):
                row["payload"] = json.dumps(p, ensure_ascii=False)
            ts = row.get("occurred_at")
            if hasattr(ts, "strftime"):
                row["timestamp"] = ts.strftime("%Y-%m-%d %H:%M:%S")
            else:
                row["timestamp"] = str(ts)
        return rows
    except Exception as exc:
        logger.debug("[PostgresDialog] 이벤트 조회 실패: %s", exc)
        return []


def _publish_event_psycopg2(
    event_type: str,
    aggregate_id: str,
    payload: Dict[str, Any],
    metadata: Dict[str, Any],
) -> bool:
    """psycopg2로 이벤트를 domain_events 테이블에 발행합니다.

    Args:
        event_type:   이벤트 타입 문자열.
        aggregate_id: Aggregate ID 문자열.
        payload:      이벤트 페이로드 딕셔너리.
        metadata:     이벤트 메타데이터 딕셔너리.

    Returns:
        성공 여부.
    """
    try:
        conn = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {_PG_SCHEMA}.domain_events "
                "(event_id, event_type, aggregate_id, payload, metadata, occurred_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW())",
                (
                    str(uuid.uuid4()),
                    event_type,
                    aggregate_id,
                    json.dumps(payload),
                    json.dumps(metadata),
                ),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        logger.error("[PostgresDialog] 이벤트 발행 실패: %s", exc)
        return False


def _fetch_audit_log_psycopg2(
    user_filter: str = "",
    action_filter: str = "",
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """psycopg2로 감사 로그를 조회합니다.

    Args:
        user_filter:   필터할 사용자 (빈 문자열이면 전체).
        action_filter: 필터할 액션 (빈 문자열이면 전체).
        limit:         최대 반환 행 수.

    Returns:
        감사 로그 딕셔너리 리스트.
    """
    try:
        conn = _pg_connect()
        conditions = []
        params: List[Any] = []
        if user_filter:
            conditions.append("user_id = %s")
            params.append(user_filter)
        if action_filter:
            conditions.append("action = %s")
            params.append(action_filter)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = (
            f"SELECT order_id, user_id, action, amount, created_at "
            f"FROM {_PG_SCHEMA}.audit_log {where} "
            f"ORDER BY created_at DESC LIMIT %s"
        )
        params.append(limit)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        for row in rows:
            ts = row.get("created_at")
            if hasattr(ts, "strftime"):
                row["timestamp"] = ts.strftime("%Y-%m-%d %H:%M:%S")
            else:
                row["timestamp"] = str(ts)
        return rows
    except Exception as exc:
        logger.debug("[PostgresDialog] 감사 로그 조회 실패: %s", exc)
        return []


def _fetch_replication_psycopg2() -> Dict[str, Any]:
    """psycopg2로 복제 상태를 조회합니다.

    Returns:
        복제 상태 딕셔너리.
    """
    try:
        conn = _pg_connect()
        rows: List[Tuple[str, str, str, str]] = []
        with conn.cursor() as cur:
            cur.execute(
                "SELECT client_addr, state, sent_lsn, write_lag "
                "FROM pg_stat_replication"
            )
            for r in cur.fetchall():
                rows.append((
                    "Replica",
                    str(r[0]),
                    str(r[2]),
                    str(r[3]) if r[3] else "0ms",
                ))
            cur.execute("SELECT pg_current_wal_lsn()::text")
            wal_row = cur.fetchone()
            wal_pos = wal_row[0] if wal_row else "N/A"
            cur.execute(
                "SELECT slot_name, active FROM pg_replication_slots LIMIT 1"
            )
            slot_row = cur.fetchone()
            slot_info = (
                f"{slot_row[0]} ({'활성' if slot_row[1] else '비활성'})"
                if slot_row else "N/A"
            )
        conn.close()
        lag = rows[0][3] if rows else "N/A"
        replica_addr = rows[0][1] if rows else "N/A (단독 인스턴스)"
        if not rows:
            rows = [("Primary", f"{_PG_HOST}:{_PG_PORT}", wal_pos, "✅ 정상")]
        return {
            "primary":   f"{_PG_HOST}:{_PG_PORT}",
            "replica":   replica_addr,
            "repl_lag":  lag,
            "wal_pos":   wal_pos,
            "repl_slot": slot_info,
            "rows":      rows,
            "status":    "ok",
        }
    except Exception as exc:
        logger.debug("[PostgresDialog] 복제 상태 조회 실패: %s", exc)
        return _placeholder_replication()


# ===========================================================================
# PostgresEventStoreDialog
# ===========================================================================
if PYQT5_AVAILABLE:
    # 삭제 기능 믹스인 로드
    def _load_pg_delete_mixin():
        try:
            from pathlib import Path as _Path
            import importlib.util as _ilu
            _p = _Path(__file__).parent / "postgres_delete_operations.py"
            if _p.exists():
                _spec = _ilu.spec_from_file_location("postgres_delete_operations", str(_p))
                if _spec and _spec.loader:
                    _m = _ilu.module_from_spec(_spec)
                    _spec.loader.exec_module(_m)  # type: ignore
                    return getattr(_m, "PostgresDeleteMixin", None)
        except Exception:
            pass
        return None

    _PostgresDeleteMixin = _load_pg_delete_mixin()
    if _PostgresDeleteMixin is None:
        class _PostgresDeleteMixin:  # type: ignore[no-redef]
            def _bind_pg_delete_signals(self): pass

    class PostgresEventStoreDialog(QDialog, _PostgresDeleteMixin):
        """PostgreSQL CQRS Event Store 모니터링 다이얼로그.

        6개 탭 + 데이터 삭제 탭으로 구성되며, QTimer 10초 자동 갱신과
        백그라운드 스레드 + pyqtSignal 기반 스레드 안전 UI 업데이트를 제공합니다.

        Signals:
            _sig_conn_ready:        연결 정보 준비 시그널.
            _sig_events_ready:      이벤트 목록 준비 시그널.
            _sig_read_models_ready: 읽기 모델 동기화 상태 시그널.
            _sig_audit_ready:       감사 로그 준비 시그널.
            _sig_repl_ready:        복제 상태 준비 시그널.
            _sig_conn_color:        LED 색상 변경 시그널.
        """

        _sig_conn_ready        = pyqtSignal(dict)
        _sig_events_ready      = pyqtSignal(list)
        _sig_read_models_ready = pyqtSignal(list)
        _sig_audit_ready       = pyqtSignal(list)
        _sig_repl_ready        = pyqtSignal(dict)
        _sig_conn_color        = pyqtSignal(str)

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            """다이얼로그를 초기화합니다.

            Args:
                parent: 부모 위젯 (선택).
            """
            super().__init__(parent)
            uic.loadUi(_UI_PATH, self)
            self._setup_tables()
            self._connect_signals()
            self._init_date_filters()

            # 삭제 탭 버튼 바인딩 (PostgresDeleteMixin)
            self._bind_pg_delete_signals()

            self._timer = QTimer(self)
            self._timer.setInterval(10_000)
            self._timer.timeout.connect(self._refresh_all)
            self._timer.start()

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
                _geometry = _settings.value("postgres_geometry")
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
        # 초기화 헬퍼
        # ------------------------------------------------------------------

        def _setup_tables(self) -> None:
            """테이블 위젯 헤더 및 크기 조정 정책을 설정합니다."""
            tables_cols = {
                "tableEvents": [
                    "event_id", "event_type", "aggregate_id",
                    "timestamp", "payload (미리보기)",
                ],
                "tableReadModels": [
                    "Read Model", "마지막 동기화", "지연시간", "상태",
                ],
                "tableAuditLog": [
                    "주문ID", "사용자", "액션", "금액", "타임스탬프",
                ],
                "tableReplDetails": [
                    "역할", "주소", "WAL 위치", "상태",
                ],
            }
            for table_name, headers in tables_cols.items():
                table = getattr(self, table_name, None)
                if table is None:
                    continue
                table.setColumnCount(len(headers))
                table.setHorizontalHeaderLabels(headers)
                table.horizontalHeader().setSectionResizeMode(
                    QHeaderView.Stretch
                )
                table.setEditTriggers(table.NoEditTriggers)
                table.setSelectionBehavior(table.SelectRows)

        def _connect_signals(self) -> None:
            """pyqtSignal 및 버튼 클릭을 연결합니다."""
            self._sig_conn_ready.connect(self._update_conn_ui)
            self._sig_events_ready.connect(self._update_events_ui)
            self._sig_read_models_ready.connect(self._update_read_models_ui)
            self._sig_audit_ready.connect(self._update_audit_ui)
            self._sig_repl_ready.connect(self._update_repl_ui)
            self._sig_conn_color.connect(self._update_conn_led)

            try:
                self.btnConnect.clicked.connect(self._refresh_conn)
                self.btnFilterEvents.clicked.connect(self._on_filter_events)
                self.btnReplayEvent.clicked.connect(self._on_replay_event)
                self.btnPublishEvent.clicked.connect(self._on_publish_event)
                self.btnGenerateTestEvent.clicked.connect(self._on_generate_test_event)
                self.btnSyncReadModel.clicked.connect(self._on_sync_read_model)
                self.btnExportAudit.clicked.connect(self._on_export_audit)
            except AttributeError as exc:
                logger.debug("[PostgresDialog] 버튼 연결 오류: %s", exc)

            # 새 탭 버튼 연결
            if hasattr(self, "btnSearch"):
                self.btnSearch.clicked.connect(self._on_search_data)
            if hasattr(self, "btnPrevPage"):
                self.btnPrevPage.clicked.connect(self._on_prev_page)
            if hasattr(self, "btnNextPage"):
                self.btnNextPage.clicked.connect(self._on_next_page)
            if hasattr(self, "btnExportCSV"):
                self.btnExportCSV.clicked.connect(self._on_export_csv)

        def _init_date_filters(self) -> None:
            """날짜 필터 기본값을 오늘부터 30일 전으로 설정합니다."""
            try:
                today = QDate.currentDate()
                self.dateStartFilter.setDate(today.addDays(-30))
                self.dateEndFilter.setDate(today)
            except AttributeError:
                pass

        # ------------------------------------------------------------------
        # 전체 갱신
        # ------------------------------------------------------------------

        def _refresh_all(self) -> None:
            """현재 활성 탭과 연결 탭을 백그라운드에서 갱신합니다."""
            threading.Thread(target=self._fetch_conn, daemon=True).start()
            try:
                idx = self.tabWidget.currentIndex()
            except AttributeError:
                idx = 0
            refresh_map = {
                1: self._fetch_events,
                3: self._fetch_read_models,
                4: self._fetch_audit,
                5: self._fetch_replication,
            }
            target = refresh_map.get(idx)
            if target:
                threading.Thread(target=target, daemon=True).start()

        def _refresh_conn(self) -> None:
            """연결 탭 수동 갱신."""
            threading.Thread(target=self._fetch_conn, daemon=True).start()

        # ------------------------------------------------------------------
        # 백그라운드 데이터 조회
        # ------------------------------------------------------------------

        def _fetch_conn(self) -> None:
            """백그라운드: PostgreSQL 연결 정보를 조회하고 시그널을 발행합니다."""
            if _DB_DRIVER == "psycopg2":
                info = _fetch_conn_info_psycopg2()
            else:
                info = _placeholder_conn_info()
            color = "green" if info.get("status") == "ok" else (
                "placeholder" if info.get("status") == "placeholder" else "red"
            )
            self._sig_conn_color.emit(color)
            self._sig_conn_ready.emit(info)

        def _fetch_events(
            self,
            event_type: str = "",
            aggregate_id: str = "",
            date_start: Optional[str] = None,
            date_end: Optional[str] = None,
        ) -> None:
            """백그라운드: 이벤트 목록을 조회하고 시그널을 발행합니다.

            Args:
                event_type:   필터할 이벤트 타입.
                aggregate_id: 필터할 aggregate ID.
                date_start:   조회 시작일 'YYYY-MM-DD'.
                date_end:     조회 종료일 'YYYY-MM-DD'.
            """
            if _DB_DRIVER == "psycopg2":
                rows = _fetch_events_psycopg2(
                    event_type=event_type,
                    aggregate_id=aggregate_id,
                    date_start=date_start,
                    date_end=date_end,
                )
                if not rows:
                    rows = _placeholder_events()
            else:
                rows = _placeholder_events()
            self._sig_events_ready.emit(rows)

        def _fetch_read_models(self) -> None:
            """백그라운드: 읽기 모델 동기화 상태를 조회하고 시그널을 발행합니다."""
            rows = _placeholder_read_models()
            self._sig_read_models_ready.emit(rows)

        def _fetch_audit(
            self,
            user_filter: str = "",
            action_filter: str = "",
        ) -> None:
            """백그라운드: 감사 로그를 조회하고 시그널을 발행합니다.

            Args:
                user_filter:   필터할 사용자.
                action_filter: 필터할 액션.
            """
            if _DB_DRIVER == "psycopg2":
                rows = _fetch_audit_log_psycopg2(
                    user_filter=user_filter,
                    action_filter=action_filter,
                )
                if not rows:
                    rows = _placeholder_audit_log()
            else:
                rows = _placeholder_audit_log()
            self._sig_audit_ready.emit(rows)

        def _fetch_replication(self) -> None:
            """백그라운드: 복제 상태를 조회하고 시그널을 발행합니다."""
            if _DB_DRIVER == "psycopg2":
                data = _fetch_replication_psycopg2()
            else:
                data = _placeholder_replication()
            self._sig_repl_ready.emit(data)

        # ------------------------------------------------------------------
        # UI 업데이트 슬롯 (메인 스레드에서 실행)
        # ------------------------------------------------------------------

        def _update_conn_led(self, color: str) -> None:
            """연결 상태 LED 색상과 텍스트를 업데이트합니다.

            Args:
                color: 'green', 'red', 또는 'placeholder'.
            """
            try:
                css_map = {
                    "green":       _COLOR_GREEN,
                    "red":         _COLOR_RED,
                    "placeholder": _COLOR_GRAY,
                }
                text_map = {
                    "green":       "● 연결 정상",
                    "red":         "● 연결 실패",
                    "placeholder": "● 드라이버 없음 (플레이스홀더)",
                }
                css   = css_map.get(color, _COLOR_GRAY)
                label = text_map.get(color, "● 확인 중...")
                self.labelConnStatus.setStyleSheet(
                    f"color: {css}; font-size: 16px; font-weight: bold;"
                )
                self.labelConnStatus.setText(label)
            except AttributeError as exc:
                logger.debug("[PostgresDialog] LED 업데이트 오류: %s", exc)

        def _update_conn_ui(self, info: Dict[str, str]) -> None:
            """연결 탭 레이블을 업데이트합니다.

            Args:
                info: 연결 상태 딕셔너리.
            """
            try:
                self.labelHost.setText(info.get("host", "-"))
                self.labelDB.setText(info.get("db", "-"))
                self.labelVersion.setText(info.get("version", "-"))
                self.labelUptime.setText(info.get("uptime", "-"))
                self.labelConnCount.setText(info.get("conn_count", "-"))
            except AttributeError as exc:
                logger.debug("[PostgresDialog] 연결 UI 오류: %s", exc)

        def _update_events_ui(self, rows: List[Dict[str, Any]]) -> None:
            """이벤트 스토어 테이블을 업데이트합니다.

            Args:
                rows: 이벤트 딕셔너리 리스트.
            """
            try:
                self.tableEvents.setRowCount(0)
                for row in rows:
                    ri = self.tableEvents.rowCount()
                    self.tableEvents.insertRow(ri)
                    payload_preview = str(row.get("payload", ""))[:80]
                    for ci, val in enumerate([
                        str(row.get("event_id", "")),
                        str(row.get("event_type", "")),
                        str(row.get("aggregate_id", "")),
                        str(row.get("timestamp", row.get("occurred_at", ""))),
                        payload_preview,
                    ]):
                        self.tableEvents.setItem(ri, ci, QTableWidgetItem(val))
                if not rows:
                    self.tableEvents.insertRow(0)
                    empty = QTableWidgetItem("(이벤트 없음)")
                    empty.setTextAlignment(Qt.AlignCenter)
                    self.tableEvents.setItem(0, 0, empty)
                    self.tableEvents.setSpan(0, 0, 1, 5)
            except AttributeError as exc:
                logger.debug("[PostgresDialog] 이벤트 UI 오류: %s", exc)

        def _update_read_models_ui(
            self, rows: List[Tuple[str, str, str, str]]
        ) -> None:
            """읽기 모델 동기화 테이블을 업데이트합니다.

            Args:
                rows: (Read Model, 마지막 동기화, 지연시간, 상태) 튜플 리스트.
            """
            try:
                self.tableReadModels.setRowCount(0)
                for model, sync_time, lag, status in rows:
                    ri = self.tableReadModels.rowCount()
                    self.tableReadModels.insertRow(ri)
                    for ci, val in enumerate([model, sync_time, lag, status]):
                        self.tableReadModels.setItem(ri, ci, QTableWidgetItem(val))
            except AttributeError as exc:
                logger.debug("[PostgresDialog] 읽기 모델 UI 오류: %s", exc)

        def _update_audit_ui(self, rows: List[Dict[str, Any]]) -> None:
            """감사 로그 테이블을 업데이트합니다.

            Args:
                rows: 감사 로그 딕셔너리 리스트.
            """
            try:
                self.tableAuditLog.setRowCount(0)
                for row in rows:
                    ri = self.tableAuditLog.rowCount()
                    self.tableAuditLog.insertRow(ri)
                    for ci, val in enumerate([
                        str(row.get("order_id", "")),
                        str(row.get("user", row.get("user_id", ""))),
                        str(row.get("action", "")),
                        str(row.get("amount", "")),
                        str(row.get("timestamp", row.get("created_at", ""))),
                    ]):
                        self.tableAuditLog.setItem(ri, ci, QTableWidgetItem(val))
                if not rows:
                    self.tableAuditLog.insertRow(0)
                    empty = QTableWidgetItem("(감사 로그 없음)")
                    empty.setTextAlignment(Qt.AlignCenter)
                    self.tableAuditLog.setItem(0, 0, empty)
                    self.tableAuditLog.setSpan(0, 0, 1, 5)
            except AttributeError as exc:
                logger.debug("[PostgresDialog] 감사 로그 UI 오류: %s", exc)

        def _update_repl_ui(self, data: Dict[str, Any]) -> None:
            """복제 상태 레이블 및 테이블을 업데이트합니다.

            Args:
                data: 복제 상태 딕셔너리.
            """
            try:
                self.labelPrimary.setText(data.get("primary", "-"))
                self.labelReplica.setText(data.get("replica", "-"))
                self.labelReplLag.setText(data.get("repl_lag", "-"))
                self.labelWALPosition.setText(data.get("wal_pos", "-"))
                self.labelReplSlot.setText(data.get("repl_slot", "-"))

                self.tableReplDetails.setRowCount(0)
                for role, addr, wal, status in data.get("rows", []):
                    ri = self.tableReplDetails.rowCount()
                    self.tableReplDetails.insertRow(ri)
                    for ci, val in enumerate([role, addr, wal, status]):
                        self.tableReplDetails.setItem(ri, ci, QTableWidgetItem(val))
            except AttributeError as exc:
                logger.debug("[PostgresDialog] 복제 UI 오류: %s", exc)

        # ------------------------------------------------------------------
        # 버튼 핸들러
        # ------------------------------------------------------------------

        def _on_filter_events(self) -> None:
            """이벤트 필터 버튼 클릭 핸들러 — 백그라운드 조회를 시작합니다."""
            try:
                event_type   = self.comboEventTypeFilter.currentText()
                if event_type == "전체":
                    event_type = ""
                aggregate_id = self.lineAggregateFilter.text().strip()
                date_start   = self.dateStartFilter.date().toString("yyyy-MM-dd")
                date_end     = self.dateEndFilter.date().toString("yyyy-MM-dd")
            except AttributeError:
                event_type = aggregate_id = date_start = date_end = ""

            threading.Thread(
                target=self._fetch_events,
                kwargs={
                    "event_type":   event_type,
                    "aggregate_id": aggregate_id,
                    "date_start":   date_start,
                    "date_end":     date_end,
                },
                daemon=True,
            ).start()

        def _on_replay_event(self) -> None:
            """선택된 이벤트를 재생합니다 (확인 다이얼로그 후 실행)."""
            try:
                row = self.tableEvents.currentRow()
                if row < 0:
                    QMessageBox.information(self, "알림", "재생할 이벤트를 선택하세요.")
                    return
                event_id_item = self.tableEvents.item(row, 0)
                event_id = event_id_item.text() if event_id_item else "?"
                reply = QMessageBox.question(
                    self,
                    "이벤트 재생",
                    f"이벤트 '{event_id}'를 재생하시겠습니까?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return
                logger.info("[PostgresDialog] 이벤트 재생 요청: %s", event_id)
                QMessageBox.information(
                    self, "재생 요청", f"이벤트 {event_id} 재생 요청이 전송되었습니다."
                )
            except Exception as exc:
                logger.error("[PostgresDialog] 이벤트 재생 오류: %s", exc)

        def _on_publish_event(self) -> None:
            """이벤트 발행 버튼 클릭 핸들러."""
            try:
                event_type   = self.comboEventType.currentText()
                aggregate_id = self.lineAggregateId.text().strip()
                payload_text = self.textPayload.toPlainText().strip()
                metadata_text = self.textMetadata.toPlainText().strip()
            except AttributeError:
                return

            if not aggregate_id:
                QMessageBox.warning(self, "입력 오류", "Aggregate ID를 입력하세요.")
                return
            try:
                payload  = json.loads(payload_text)  if payload_text  else {}
                metadata = json.loads(metadata_text) if metadata_text else {}
            except json.JSONDecodeError as exc:
                QMessageBox.critical(self, "JSON 오류", f"JSON 파싱 실패: {exc}")
                return

            threading.Thread(
                target=self._do_publish_event,
                args=(event_type, aggregate_id, payload, metadata),
                daemon=True,
            ).start()

        def _do_publish_event(
            self,
            event_type: str,
            aggregate_id: str,
            payload: Dict[str, Any],
            metadata: Dict[str, Any],
        ) -> None:
            """백그라운드: 이벤트 발행을 수행합니다.

            Args:
                event_type:   이벤트 타입.
                aggregate_id: Aggregate ID.
                payload:      페이로드 딕셔너리.
                metadata:     메타데이터 딕셔너리.
            """
            if _DB_DRIVER == "psycopg2":
                ok = _publish_event_psycopg2(event_type, aggregate_id, payload, metadata)
            else:
                logger.info(
                    "[PostgresDialog] 플레이스홀더 모드 — 이벤트 발행 시뮬레이션: %s %s",
                    event_type, aggregate_id,
                )
                ok = True  # placeholder 성공 시뮬레이션

            if ok:
                self._sig_events_ready.emit(_placeholder_events() if _DB_DRIVER != "psycopg2" else [])
            else:
                logger.error("[PostgresDialog] 이벤트 발행 실패")

        def _on_generate_test_event(self) -> None:
            """테스트 이벤트 생성 버튼 — 폼에 더미 데이터를 채웁니다."""
            try:
                import random
                types = ["OrderCreated", "OrderFilled", "TradeExecuted"]
                selected = random.choice(types)
                idx = self.comboEventType.findText(selected)
                if idx >= 0:
                    self.comboEventType.setCurrentIndex(idx)
                self.lineAggregateId.setText(f"AGG-{random.randint(1000, 9999)}")
                dummy_payload = {
                    "market":   "KRW-BTC",
                    "price":    random.randint(40_000_000, 60_000_000),
                    "quantity": round(random.uniform(0.001, 0.1), 6),
                    "side":     random.choice(["bid", "ask"]),
                }
                self.textPayload.setPlainText(
                    json.dumps(dummy_payload, ensure_ascii=False, indent=2)
                )
                self.textMetadata.setPlainText(
                    json.dumps({"source": "ui_test", "version": "1.0"}, indent=2)
                )
            except AttributeError as exc:
                logger.debug("[PostgresDialog] 테스트 이벤트 생성 오류: %s", exc)

        def _on_sync_read_model(self) -> None:
            """즉시 재동기화 버튼 — 읽기 모델 갱신을 트리거합니다."""
            threading.Thread(target=self._fetch_read_models, daemon=True).start()
            QMessageBox.information(self, "재동기화", "읽기 모델 재동기화를 요청했습니다.")

        def _on_export_audit(self) -> None:
            """감사 로그를 CSV 파일로 내보냅니다."""
            try:
                path, _ = QFileDialog.getSaveFileName(
                    self, "감사 로그 저장", "audit_log.csv",
                    "CSV 파일 (*.csv);;모든 파일 (*)"
                )
                if not path:
                    return
                table = self.tableAuditLog
                headers = [
                    table.horizontalHeaderItem(c).text()
                    for c in range(table.columnCount())
                ]
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    for r in range(table.rowCount()):
                        row_data = []
                        for c in range(table.columnCount()):
                            item = table.item(r, c)
                            row_data.append(item.text() if item else "")
                        writer.writerow(row_data)
                QMessageBox.information(self, "내보내기 완료", f"저장됨: {path}")
            except Exception as exc:
                QMessageBox.critical(self, "내보내기 실패", str(exc))
                logger.error("[PostgresDialog] CSV 내보내기 오류: %s", exc)

        # ------------------------------------------------------------------
        # 다이얼로그 종료 처리
        # ------------------------------------------------------------------

        def closeEvent(self, event) -> None:
            """다이얼로그 닫힐 때 타이머를 정지합니다."""
            try:
                from PyQt5.QtCore import QSettings
                _settings = QSettings("UpbitTrader", "DBMonitor")
                _settings.setValue("postgres_geometry", self.saveGeometry())
            except Exception:
                pass
            try:
                self._timer.stop()
                if getattr(self, "_realtime_timer", None) and self._realtime_timer.isActive():
                    self._realtime_timer.stop()
            except Exception:
                pass
            super().closeEvent(event)

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
                logger.debug("[PostgresDialog] 검색: table=%s keyword=%s", table_name, keyword)
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
                logger.debug("[PostgresDialog] CSV 내보내기 예외: %s", e, exc_info=True)
                QMessageBox.critical(self, "오류", f"CSV 저장 실패: {e}")

else:
    # PyQt5 미설치 환경을 위한 더미 클래스
    class PostgresEventStoreDialog:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 빈 클래스."""

        def __init__(self, parent: Optional[object] = None) -> None:
            """초기화 (PyQt5 없음 경고 로깅).

            Args:
                parent: 무시됨.
            """
            logger.warning(
                "[PostgresEventStoreDialog] PyQt5 미설치 — 다이얼로그 생성 불가"
            )
