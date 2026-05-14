# -*- coding: utf-8 -*-
"""
TimescaleDB 인라인 모니터링 (레거시 구현)
- 별도 .ui 파일 없이 코드로 UI를 구성하는 구버전 구현
- 신규 코드는 TimescaleMonitorDialog (timescale_monitor.py) 사용 권장
"""
from __future__ import annotations

import sys
import logging
import pathlib
from typing import Optional, Dict

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QDialog, QVBoxLayout
    _HAS_QT = True
except Exception:
    _HAS_QT = False

if _HAS_QT:
    try:
        from PyQt5.QtWidgets import (
            QTabWidget, QGroupBox, QLabel, QTableWidget, QTableWidgetItem,
            QPushButton, QComboBox, QHBoxLayout, QGridLayout, QWidget,
        )
        from PyQt5.QtCore import QTimer
        _HAS_QT_EXTRA = True
    except Exception:
        _HAS_QT_EXTRA = False
else:
    _HAS_QT_EXTRA = False

if _HAS_QT and _HAS_QT_EXTRA:
    from datetime import datetime, timezone

    class TimescaleMonitor(QDialog):
        """
        TimescaleDB 모니터링 대시보드 (레거시 인라인 구현).

        6개 탭으로 구성:
        - 연결 상태: 실시간 연결 체크
        - Hypertable 관리: Hypertable 목록, Chunk 수, 압축 상태
        - 압축 정책: 압축 정책 목록, 압축률
        - Continuous Aggregates: CAGG 목록, 마지막 갱신 시간
        - 원시 데이터: 테이블별 행 수, 최신 데이터 시간
        - Gap Detection: Gap 목록, 백필 큐 상태
        """

        def __init__(self, parent=None, conn_params: Optional[Dict] = None, refresh_ms: int = 10_000):
            super().__init__(parent)
            self.setWindowTitle("TimescaleDB 모니터링")
            self.resize(1000, 700)

            self._conn_params = conn_params or {}
            self._ts_conn = None

            self._init_ui()

            # 타이머 (기본 10초 주기 갱신)
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._update_all)
            self._timer.start(refresh_ms)

            # 최초 갱신
            self._update_all()

        # ──────────────────────────────────────────────────────────────────
        # UI 초기화
        # ──────────────────────────────────────────────────────────────────

        def _init_ui(self):
            """UI 초기화"""
            layout = QVBoxLayout()

            self._tabs = QTabWidget()
            self._tabs.addTab(self._create_status_tab(), "연결 상태")
            self._tabs.addTab(self._create_hypertable_tab(), "Hypertable 관리")
            self._tabs.addTab(self._create_compression_tab(), "압축 정책")
            self._tabs.addTab(self._create_cagg_tab(), "Continuous Aggregates")
            self._tabs.addTab(self._create_raw_data_tab(), "원시 데이터")
            self._tabs.addTab(self._create_gap_tab(), "Gap Detection")

            layout.addWidget(self._tabs)
            self.setLayout(layout)

        def _create_status_tab(self) -> QWidget:
            """연결 상태 탭"""
            widget = QWidget()
            layout = QVBoxLayout()

            group = QGroupBox("연결 정보")
            grid = QGridLayout()

            self._status_label = QLabel("⚪ 상태: 확인 중...")
            self._host_label = QLabel("호스트: -")
            self._db_label = QLabel("데이터베이스: -")
            self._version_label = QLabel("버전: -")
            self._uptime_label = QLabel("업타임: -")
            self._connections_label = QLabel("활성 연결수: -")
            self._dsn_label = QLabel("DSN: -")

            tz_layout = QHBoxLayout()
            tz_layout.addWidget(QLabel("표시 시간대:"))
            self._timezone_combo = QComboBox()
            self._timezone_combo.addItems(["UTC", "KST (+09:00)"])
            tz_layout.addWidget(self._timezone_combo)
            tz_layout.addStretch()

            grid.addWidget(self._status_label, 0, 0)
            grid.addWidget(self._host_label, 0, 1)
            grid.addWidget(self._db_label, 1, 0)
            grid.addWidget(self._version_label, 1, 1)
            grid.addWidget(self._uptime_label, 2, 0)
            grid.addWidget(self._connections_label, 2, 1)
            grid.addLayout(tz_layout, 3, 0, 1, 2)
            grid.addWidget(self._dsn_label, 4, 0, 1, 2)

            group.setLayout(grid)
            layout.addWidget(group)

            btn_layout = QHBoxLayout()
            self._refresh_btn = QPushButton("연결 새로고침")
            self._refresh_btn.clicked.connect(self._update_status)
            btn_layout.addWidget(self._refresh_btn)
            btn_layout.addStretch()

            layout.addLayout(btn_layout)
            layout.addStretch()

            widget.setLayout(layout)
            return widget

        def _create_hypertable_tab(self) -> QWidget:
            """Hypertable 관리 탭"""
            widget = QWidget()
            layout = QVBoxLayout()

            self._hypertable_table = QTableWidget()
            self._hypertable_table.setColumnCount(5)
            self._hypertable_table.setHorizontalHeaderLabels([
                "Hypertable 이름", "Chunk 수", "총 크기", "압축률", "상태",
            ])
            layout.addWidget(self._hypertable_table)

            widget.setLayout(layout)
            return widget

        def _create_compression_tab(self) -> QWidget:
            """압축 정책 탭"""
            widget = QWidget()
            layout = QVBoxLayout()

            self._compression_table = QTableWidget()
            self._compression_table.setColumnCount(4)
            self._compression_table.setHorizontalHeaderLabels([
                "Hypertable", "압축 기준", "압축률", "마지막 실행",
            ])
            layout.addWidget(self._compression_table)

            widget.setLayout(layout)
            return widget

        def _create_cagg_tab(self) -> QWidget:
            """Continuous Aggregates 탭"""
            widget = QWidget()
            layout = QVBoxLayout()

            self._cagg_table = QTableWidget()
            self._cagg_table.setColumnCount(4)
            self._cagg_table.setHorizontalHeaderLabels([
                "View 이름", "소스 Hypertable", "마지막 갱신", "상태",
            ])
            layout.addWidget(self._cagg_table)

            widget.setLayout(layout)
            return widget

        def _create_raw_data_tab(self) -> QWidget:
            """원시 데이터 탭"""
            widget = QWidget()
            layout = QVBoxLayout()

            self._raw_data_table = QTableWidget()
            self._raw_data_table.setColumnCount(4)
            self._raw_data_table.setHorizontalHeaderLabels([
                "테이블", "행 수", "최신 데이터 시간", "크기",
            ])
            layout.addWidget(self._raw_data_table)

            widget.setLayout(layout)
            return widget

        def _create_gap_tab(self) -> QWidget:
            """Gap Detection 탭"""
            widget = QWidget()
            layout = QVBoxLayout()

            self._gap_table = QTableWidget()
            self._gap_table.setColumnCount(6)
            self._gap_table.setHorizontalHeaderLabels([
                "심볼", "시작 시간", "종료 시간", "Gap 크기 (초)", "우선순위", "상태",
            ])
            layout.addWidget(self._gap_table)

            widget.setLayout(layout)
            return widget

        # ──────────────────────────────────────────────────────────────────
        # DB 연결
        # ──────────────────────────────────────────────────────────────────

        def _get_ts_conn(self):
            """TimescaleDB 연결 가져오기 (캐싱)"""
            if self._ts_conn is not None:
                try:
                    if self._ts_conn.conn and not self._ts_conn.conn.closed:
                        return self._ts_conn
                except Exception:
                    pass

            try:
                _db_mod = sys.modules.get("_timescale_ui_db")
                if _db_mod is None:
                    _db_file = pathlib.Path(__file__).parent / "timescale_db.py"
                    if _db_file.exists():
                        import importlib.util as _ilu
                        _spec = _ilu.spec_from_file_location("_timescale_ui_db", str(_db_file))
                        if _spec and _spec.loader:
                            _db_mod = _ilu.module_from_spec(_spec)
                            sys.modules["_timescale_ui_db"] = _db_mod
                            _spec.loader.exec_module(_db_mod)

                if _db_mod is not None:
                    connect_fn = getattr(_db_mod, "_connect_db", None)
                    if connect_fn is not None:
                        cfg = self._conn_params or {}
                        conn, err = connect_fn(cfg)
                        if conn is not None:
                            self._ts_conn = type("_Conn", (), {"conn": conn, "dsn": str(cfg)})()
                            return self._ts_conn
                        if err:
                            logger.debug("[TimescaleMonitor] 연결 실패: %s", err)
            except Exception as e:
                logger.debug("[TimescaleMonitor] 연결 오류: %s", e)

            return None

        # ──────────────────────────────────────────────────────────────────
        # 갱신 메서드
        # ──────────────────────────────────────────────────────────────────

        def _update_all(self):
            """전체 갱신"""
            for fn_name, fn in (
                ("상태", self._update_status),
                ("Hypertable", self._update_hypertables),
                ("압축", self._update_compression),
                ("CAGG", self._update_cagg),
                ("원시 데이터", self._update_raw_data),
                ("Gap", self._update_gaps),
            ):
                try:
                    fn()
                except Exception as e:
                    logger.debug("[TimescaleMonitor] %s 갱신 실패: %s", fn_name, e)

        def _update_status(self):
            """연결 상태 갱신"""
            conn_wrapper = self._get_ts_conn()
            conn = getattr(conn_wrapper, "conn", None) if conn_wrapper else None

            if conn is not None and not getattr(conn, "closed", True):
                self._status_label.setText("🟢 연결됨")

                try:
                    dsn = getattr(conn_wrapper, "dsn", "") or ""
                    self._dsn_label.setText(f"DSN: {dsn}")
                    host = self._conn_params.get("host", "127.0.0.1")
                    db = self._conn_params.get("dbname") or self._conn_params.get("db", "upbit_trader")
                    self._host_label.setText(f"호스트: {host}")
                    self._db_label.setText(f"데이터베이스: {db}")
                except Exception:
                    pass

                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT version();")
                        row = cur.fetchone()
                        if row:
                            version_str = str(row[0])[:80]
                            self._version_label.setText(f"버전: {version_str}...")
                except Exception:
                    pass

                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT pg_postmaster_start_time();")
                        row = cur.fetchone()
                        if row and row[0]:
                            uptime = datetime.now(timezone.utc) - row[0]
                            h = int(uptime.total_seconds() // 3600)
                            m = int((uptime.total_seconds() % 3600) // 60)
                            s = int(uptime.total_seconds() % 60)
                            self._uptime_label.setText(f"업타임: {h:02d}:{m:02d}:{s:02d}")
                except Exception:
                    pass

                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database();"
                        )
                        row = cur.fetchone()
                        if row:
                            self._connections_label.setText(f"활성 연결수: {row[0]}")
                except Exception:
                    pass
            else:
                self._status_label.setText("🔴 연결 끊김")
                self._ts_conn = None

        def _update_hypertables(self):
            """Hypertable 목록 갱신"""
            conn_wrapper = self._get_ts_conn()
            conn = getattr(conn_wrapper, "conn", None) if conn_wrapper else None
            if conn is None:
                return

            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT
                            h.hypertable_name,
                            COUNT(c.chunk_name)::bigint AS num_chunks,
                            COALESCE(hypertable_size(
                                format('%I.%I', h.hypertable_schema, h.hypertable_name)::regclass
                            ), 0) AS total_bytes,
                            '-' AS compression_stats
                        FROM timescaledb_information.hypertables h
                        LEFT JOIN timescaledb_information.chunks c
                            ON c.hypertable_name = h.hypertable_name
                        GROUP BY h.hypertable_schema, h.hypertable_name
                        ORDER BY h.hypertable_name;
                    """)
                    rows = cur.fetchall()

                self._hypertable_table.setRowCount(len(rows))
                for i, row in enumerate(rows):
                    # 방어적 인덱싱 — tuple index out of range 방지
                    # SQL 반환 컬럼: (hypertable_name, num_chunks, total_bytes, compression_stats)
                    name_str   = str(row[0]) if len(row) > 0 and row[0] is not None else "-"
                    chunks_str = str(row[1]) if len(row) > 1 and row[1] is not None else "-"
                    total_bytes = int(row[2]) if len(row) > 2 and row[2] is not None else 0
                    self._hypertable_table.setItem(i, 0, QTableWidgetItem(name_str))
                    self._hypertable_table.setItem(i, 1, QTableWidgetItem(chunks_str))
                    self._hypertable_table.setItem(
                        i, 2, QTableWidgetItem(f"{total_bytes / 1024 / 1024:.2f} MB")
                    )
                    self._hypertable_table.setItem(i, 3, QTableWidgetItem("-"))
                    self._hypertable_table.setItem(i, 4, QTableWidgetItem("정상"))
            except Exception as e:
                logger.debug("[TimescaleMonitor] Hypertable 조회 실패: %s", e)

        def _update_compression(self):
            """압축 정책 갱신"""
            pass

        def _update_cagg(self):
            """Continuous Aggregates 갱신"""
            pass

        def _update_raw_data(self):
            """원시 데이터 통계 갱신 — fetchone() None 방어 코드 포함"""
            conn_wrapper = self._get_ts_conn()
            conn = getattr(conn_wrapper, "conn", None) if conn_wrapper else None
            if conn is None:
                return

            tables = ["market_ticks", "candles", "orderbook_snapshots", "execution_events"]
            self._raw_data_table.setRowCount(len(tables))

            for i, table in enumerate(tables):
                try:
                    import psycopg2.sql as _sql
                    with conn.cursor() as cur:
                        cur.execute(
                            _sql.SQL("SELECT COUNT(*) FROM {}").format(_sql.Identifier(table))
                        )
                        # fetchone() None 방어 — tuple index out of range 방지
                        _row = cur.fetchone()
                        count = int(_row[0]) if _row and len(_row) > 0 else 0

                    with conn.cursor() as cur:
                        cur.execute(
                            _sql.SQL("SELECT MAX(time) FROM {}").format(_sql.Identifier(table))
                        )
                        _row = cur.fetchone()
                        latest = _row[0] if _row and len(_row) > 0 else None

                    with conn.cursor() as cur:
                        cur.execute(
                            _sql.SQL("SELECT pg_total_relation_size({})").format(
                                _sql.Literal(table)
                            )
                        )
                        _row = cur.fetchone()
                        size = int(_row[0]) if _row and len(_row) > 0 and _row[0] else 0

                    self._raw_data_table.setItem(i, 0, QTableWidgetItem(table))
                    self._raw_data_table.setItem(i, 1, QTableWidgetItem(f"{count:,}"))
                    self._raw_data_table.setItem(
                        i, 2, QTableWidgetItem(str(latest) if latest else "-")
                    )
                    self._raw_data_table.setItem(
                        i, 3, QTableWidgetItem(f"{size / 1024 / 1024:.2f} MB")
                    )
                except Exception as e:
                    logger.debug("[TimescaleMonitor] %s 조회 실패: %s", table, e)
                    self._raw_data_table.setItem(i, 0, QTableWidgetItem(table))
                    for col in range(1, 4):
                        self._raw_data_table.setItem(i, col, QTableWidgetItem("-"))

        def _update_gaps(self):
            """Gap 목록 갱신"""
            conn_wrapper = self._get_ts_conn()
            conn = getattr(conn_wrapper, "conn", None) if conn_wrapper else None
            if conn is None:
                return

            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT symbol, start_ts, end_ts,
                               gap_seconds, user_priority, status
                        FROM gaps
                        WHERE status = 'pending'
                        ORDER BY user_priority DESC, gap_seconds DESC
                        LIMIT 100;
                    """)
                    rows = cur.fetchall()

                self._gap_table.setRowCount(len(rows))
                for i, row in enumerate(rows):
                    for col, val in enumerate(row):
                        self._gap_table.setItem(
                            i, col, QTableWidgetItem(
                                f"{val:,}" if isinstance(val, int) else str(val)
                            )
                        )
            except Exception as e:
                logger.debug("[TimescaleMonitor] Gap 조회 실패: %s", e)

        def closeEvent(self, event):
            """닫힐 때 타이머 정지 및 연결 해제"""
            try:
                self._timer.stop()
            except Exception:
                pass
            try:
                conn = getattr(self._ts_conn, "conn", None)
                if conn and not conn.closed:
                    conn.close()
            except Exception:
                pass
            super().closeEvent(event)

else:
    class TimescaleMonitor:  # type: ignore
        """PyQt5 미설치 시 폴백 스텁"""
        def __init__(self, *args, **kwargs):
            logger.warning("[TimescaleMonitor] PyQt5 미설치 - 폴백 스텁")

        def exec_(self):
            return 0

        def show(self):
            pass
