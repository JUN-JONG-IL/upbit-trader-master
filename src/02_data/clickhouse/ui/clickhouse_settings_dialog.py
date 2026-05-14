#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ClickHouse 모니터링 다이얼로그 (6탭)

- 네이티브 TCP(드라이버) 연결이 실패할 경우(예: 사용자가 HTTP 포트 8123를 입력한 경우)
  HTTP 인터페이스로 폴백하여 최소한의 상태/테이블/쿼리 정보를 표시하도록 보강했습니다.
- 이전 HTTP 폴백 구현에서 URL 파라미터 'format=JSON'을 사용하면 일부 ClickHouse 설정/프록시 환경에서
  "Setting format is neither a builtin setting ..." (UNKNOWN_SETTING, Code 115) 오류가 발생했습니다.
  이를 방지하기 위해 HTTP 폴백은 이제 SQL 끝에 " FORMAT JSON"을 명시하고, 'format' 파라미터는 사용하지 않습니다.
- GET 요청이 실패하면 POST(body에 SQL)을 시도합니다. 인증은 환경변수 CLICKHOUSE_USER/CLICKHOUSE_PASSWORD를 사용합니다.
- 모든 emit 호출을 안전하게 감싸 스레드 예외로 UI가 종료되는 것을 방지합니다.
"""
from __future__ import annotations

import logging
import os
import threading
import json
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
        QListWidgetItem,
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
_UI_PATH = Path(__file__).parent / "clickhouse_settings.ui"

# ---------------------------------------------------------------------------
# ClickHouse 접속 기본값 (환경변수 우선)
# ---------------------------------------------------------------------------
_DEFAULT_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
_DEFAULT_PORT = int(os.getenv("CLICKHOUSE_PORT", "9000"))

# ---------------------------------------------------------------------------
# HTTP 폴백 관련: 환경변수 자격증명
# ---------------------------------------------------------------------------
def _get_ch_credentials() -> Tuple[str, str]:
    """환경변수에서 ClickHouse 자격증명 반환 (HTTP 폴백에서 사용)."""
    user = os.getenv("CLICKHOUSE_USER", "")
    password = os.getenv("CLICKHOUSE_PASSWORD", "")
    return user, password

# ---------------------------------------------------------------------------
# 쿼리 템플릿
# ---------------------------------------------------------------------------
_QUERY_TEMPLATES: List[Tuple[str, str]] = [
    ("(템플릿 선택)", ""),
    ("시스템 테이블 목록", "SELECT name, engine FROM system.tables WHERE database = currentDatabase() ORDER BY name"),
    ("파티션 현황", "SELECT partition, rows, formatReadableSize(bytes_on_disk) AS size, min_date, max_date FROM system.parts WHERE active ORDER BY partition"),
    ("느린 쿼리 (최근 10건)", "SELECT query, query_duration_ms, read_rows, formatReadableSize(read_bytes) AS read_bytes, formatReadableSize(memory_usage) AS memory FROM system.query_log WHERE type = 'QueryFinish' ORDER BY query_duration_ms DESC LIMIT 10"),
    ("활성 쿼리", "SELECT query_id, user, query, elapsed FROM system.processes ORDER BY elapsed DESC"),
]

# ---------------------------------------------------------------------------
# HTTP 폴백 유틸리티 (수정됨)
# ---------------------------------------------------------------------------
def _http_clickhouse_query(sql: str, host: str, port: int, timeout: float = 5.0) -> Tuple[List[str], List[tuple], Dict[str, Any]]:
    """
    ClickHouse HTTP 인터페이스로 SQL 쿼리 실행 후 열 이름, 행 튜플 리스트, 전체 JSON 반환.

    변경 요지:
      - 이전: ?query=...&format=JSON 사용 (일부 환경에서 UNKNOWN_SETTING 발생)
      - 변경: SQL 끝에 " FORMAT JSON"을 추가하고 'format' 파라미터는 사용하지 않음.
      - GET 실패(HTTPError 404/405/400 등) 시 POST(body=sql_with_format)로 재시도.
    """
    user, password = _get_ch_credentials()

    # ClickHouse HTTP에서 'format'을 설정 파라미터로 전달하는 대신
    # SQL 내부에 FORMAT JSON을 명시하여 서버 설정 해석 문제를 회피.
    sql_with_format = sql.rstrip().rstrip(";") + " FORMAT JSON"

    # 안전하게 인코딩된 query 파라미터 (format은 파라미터로 보내지 않음)
    params = {"query": sql_with_format}
    if user:
        params["user"] = user
    if password:
        params["password"] = password

    query_str = urllib.parse.urlencode(params, doseq=False, safe="/(),")
    url = f"http://{host}:{port}/?{query_str}"
    logger.debug("_http_clickhouse_query: requesting GET %s", url)

    # 1) GET 방식 시도
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            meta = data.get("meta", []) or []
            cols = [m.get("name") for m in meta]
            rows = []
            for row in data.get("data", []):
                rows.append(tuple(row.get(c) for c in cols))
            return cols, rows, data
    except urllib.error.HTTPError as he:
        # GET에서 404/405/400 등 발생하면 POST로 재시도 (프록시/라우터 케이스 대비)
        try:
            body = he.read().decode("utf-8", errors="ignore")
        except Exception:
            body = "<no body>"
        logger.debug("_http_clickhouse_query: GET HTTPError %s body=%s", he.code, body[:400])
        # 일반적으로 401/403은 인증 문제로 즉시 전달
        if he.code in (404, 405, 400):
            logger.debug("_http_clickhouse_query: attempting POST fallback to %s:%s", host, port)
            post_url = f"http://{host}:{port}/"
            # POST는 SQL을 바디에 담아 전송 (FORMAT JSON이 이미 SQL에 포함됨)
            headers = {"Content-Type": "text/plain", "Accept": "application/json"}
            # 인증을 URL에 포함하지 않고도 되면 괜찮지만, 일부 환경에서는 user/password 쿼리 파라미터 필요
            if user or password:
                auth_q = {}
                if user:
                    auth_q["user"] = user
                if password:
                    auth_q["password"] = password
                post_url = post_url + "?" + urllib.parse.urlencode(auth_q, doseq=False, safe="/(),")
            post_req = urllib.request.Request(post_url, data=sql_with_format.encode("utf-8"), headers=headers, method="POST")
            try:
                with urllib.request.urlopen(post_req, timeout=timeout) as resp2:
                    raw2 = resp2.read().decode("utf-8")
                    data2 = json.loads(raw2)
                    meta2 = data2.get("meta", []) or []
                    cols2 = [m.get("name") for m in meta2]
                    rows2 = []
                    for row in data2.get("data", []):
                        rows2.append(tuple(row.get(c) for c in cols2))
                    return cols2, rows2, data2
            except urllib.error.HTTPError as he2:
                try:
                    body2 = he2.read().decode("utf-8", errors="ignore")
                except Exception:
                    body2 = "<no body>"
                logger.debug("_http_clickhouse_query: POST HTTPError %s body=%s", he2.code, body2[:400])
                # GET/POST 둘다 실패하면 상세한 정보를 포함한 예외 발생
                raise RuntimeError(f"HTTP error GET {he.code} body[:400]={body[:400]!r}; POST {he2.code} body[:400]={body2[:400]!r}")
            except urllib.error.URLError as ue2:
                logger.debug("_http_clickhouse_query: POST URLError %s", ue2)
                raise
        else:
            # 인증/권한 이슈 등은 상위로 전달
            raise
    except urllib.error.URLError as ue:
        logger.debug("_http_clickhouse_query: GET URLError %s", ue)
        raise

# ---------------------------------------------------------------------------
# ClickHouse 드라이버(네이티브) 클라이언트 생성 함수 (lazy import)
# ---------------------------------------------------------------------------
def _make_client_native() -> Any:
    """
    clickhouse_driver.Client를 생성하여 반환.
    임포트 실패 시 ImportError를 발생시킵니다.
    """
    from clickhouse_driver import Client as ClickHouseClient  # type: ignore
    user = os.getenv("CLICKHOUSE_USER", "") or None
    password = os.getenv("CLICKHOUSE_PASSWORD", "") or None
    return ClickHouseClient(
        host=_DEFAULT_HOST,
        port=_DEFAULT_PORT,
        user=user,
        password=password,
        connect_timeout=3,
        send_receive_timeout=10,
    )

# ---------------------------------------------------------------------------
# ClickHouse 다이얼로그
# ---------------------------------------------------------------------------
if PYQT5_AVAILABLE:
    # 삭제 기능 믹스인 로드
    def _load_ch_delete_mixin():
        try:
            from pathlib import Path as _Path
            import importlib.util as _ilu
            _p = _Path(__file__).parent / "clickhouse_delete_operations.py"
            if _p.exists():
                _spec = _ilu.spec_from_file_location("clickhouse_delete_operations", str(_p))
                if _spec and _spec.loader:
                    _m = _ilu.module_from_spec(_spec)
                    _spec.loader.exec_module(_m)  # type: ignore
                    return getattr(_m, "ClickHouseDeleteMixin", None)
        except Exception:
            pass
        return None

    _ClickHouseDeleteMixin = _load_ch_delete_mixin()
    if _ClickHouseDeleteMixin is None:
        class _ClickHouseDeleteMixin:  # type: ignore[no-redef]
            def _bind_ch_delete_signals(self): pass

    class ClickHouseSettingsDialog(QDialog, _ClickHouseDeleteMixin):
        """ClickHouse 6탭 모니터링 다이얼로그 (네이티브 실패 시 HTTP 폴백 지원) + 데이터 삭제 탭."""

        # 시그널 인자: ok, status, host, version, uptime, active_queries
        _sig_conn = pyqtSignal(bool, str, str, str, str, str)
        _sig_tables = pyqtSignal(list)
        _sig_partitions = pyqtSignal(list)
        _sig_query_result = pyqtSignal(list, list)          # columns, rows
        _sig_migrations = pyqtSignal(list)
        _sig_perf = pyqtSignal(list, str, str, str)         # slow_queries, cpu, mem, diskio

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            uic.loadUi(_UI_PATH, self)
            self._query_history: List[str] = []
            self._setup_ui()
            self._connect_signals()

            # 삭제 탭 버튼 바인딩 (ClickHouseDeleteMixin)
            self._bind_ch_delete_signals()

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
                _geometry = _settings.value("clickhouse_geometry")
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

        def _setup_ui(self) -> None:
            for attr in (
                "tableClickHouseTables",
                "tablePartitions",
                "tableQueryResults",
                "tableMigrations",
                "tableSlowQueries",
            ):
                widget = getattr(self, attr, None)
                if widget is not None:
                    widget.horizontalHeader().setStretchLastSection(True)
                    widget.setAlternatingRowColors(True)

            if hasattr(self, "comboQueryTemplates"):
                self.comboQueryTemplates.clear()
                for label, _ in _QUERY_TEMPLATES:
                    self.comboQueryTemplates.addItem(label)

            if hasattr(self, "labelConnStatus"):
                self.labelConnStatus.setText("확인 중...")

        def _connect_signals(self) -> None:
            self._sig_conn.connect(self._on_conn)
            self._sig_tables.connect(self._on_tables)
            self._sig_partitions.connect(self._on_partitions)
            self._sig_query_result.connect(self._on_query_result)
            self._sig_migrations.connect(self._on_migrations)
            self._sig_perf.connect(self._on_perf)

            if hasattr(self, "btnConnect"):
                self.btnConnect.clicked.connect(self._refresh_conn)
            if hasattr(self, "btnCreateTable"):
                self.btnCreateTable.clicked.connect(self._on_create_table)
            if hasattr(self, "btnDropTable"):
                self.btnDropTable.clicked.connect(self._on_drop_table)
            if hasattr(self, "btnOptimize"):
                self.btnOptimize.clicked.connect(self._on_optimize)
            if hasattr(self, "btnDropPartition"):
                self.btnDropPartition.clicked.connect(self._on_drop_partition)
            if hasattr(self, "btnMergePartition"):
                self.btnMergePartition.clicked.connect(self._on_merge_partition)
            if hasattr(self, "btnRunQuery"):
                self.btnRunQuery.clicked.connect(self._on_run_query)
            if hasattr(self, "listQueryHistory"):
                self.listQueryHistory.itemDoubleClicked.connect(self._on_history_select)
            if hasattr(self, "comboQueryTemplates"):
                self.comboQueryTemplates.currentIndexChanged.connect(self._on_template_select)
            if hasattr(self, "btnRunMigration"):
                self.btnRunMigration.clicked.connect(self._on_run_migration)
            if hasattr(self, "btnEditSchedule"):
                self.btnEditSchedule.clicked.connect(self._on_edit_schedule)
            if hasattr(self, "btnRefreshPerf"):
                self.btnRefreshPerf.clicked.connect(self._refresh_perf)
            if hasattr(self, "btnSearch"):
                self.btnSearch.clicked.connect(self._on_search_data)
            if hasattr(self, "btnPrevPage"):
                self.btnPrevPage.clicked.connect(self._on_prev_page)
            if hasattr(self, "btnNextPage"):
                self.btnNextPage.clicked.connect(self._on_next_page)
            if hasattr(self, "btnExportCSV"):
                self.btnExportCSV.clicked.connect(self._on_export_csv)
            if hasattr(self, "buttonBox"):
                self.buttonBox.rejected.connect(self.reject)

        # ------------------------------------------------------------------
        # 갱신 트리거
        # ------------------------------------------------------------------
        def _refresh_all(self) -> None:
            threading.Thread(target=self._fetch_conn, daemon=True).start()
            threading.Thread(target=self._fetch_tables, daemon=True).start()
            threading.Thread(target=self._fetch_partitions, daemon=True).start()
            threading.Thread(target=self._fetch_migrations, daemon=True).start()
            threading.Thread(target=self._fetch_perf, daemon=True).start()

        def _refresh_conn(self) -> None:
            threading.Thread(target=self._fetch_conn, daemon=True).start()

        def _refresh_perf(self) -> None:
            threading.Thread(target=self._fetch_perf, daemon=True).start()

        # ------------------------------------------------------------------
        # 탭 1: 연결 상태 (네이티브 -> HTTP 폴백)
        # ------------------------------------------------------------------
        def _fetch_conn(self) -> None:
            """네이티브 드라이버 우선 시도, 실패 시 HTTP 폴백으로 최소 상태 획득."""
            # 1) 네이티브 시도
            try:
                client = _make_client_native()
                version = client.execute("SELECT version()")[0][0]
                uptime_sec = None
                try:
                    uptime_sec = client.execute("SELECT uptime()")[0][0]
                except Exception:
                    uptime_sec = None
                try:
                    active = client.execute("SELECT count() FROM system.processes")[0][0]
                except Exception:
                    active = "-"
                if uptime_sec is not None:
                    try:
                        hours, rem = divmod(int(uptime_sec), 3600)
                        minutes = rem // 60
                        uptime_str = f"{hours}h {minutes}m"
                    except Exception:
                        uptime_str = str(uptime_sec)
                else:
                    uptime_str = "-"
                try:
                    self._sig_conn.emit(True, "🟢 연결됨 (네이티브)", f"{_DEFAULT_HOST}:{_DEFAULT_PORT}", str(version), uptime_str, str(active))
                except Exception:
                    logger.exception("_sig_conn.emit 실패 (네이티브 성공)")
                return
            except ImportError:
                logger.debug("_fetch_conn: clickhouse-driver 미설치, HTTP 폴백 시도")
            except Exception as exc:
                exc_str = str(exc) or ""
                logger.debug("네이티브 연결 실패: %s", exc_str)

            # 2) HTTP 폴백 시도 (GET -> POST)
            try:
                cols, rows, _ = _http_clickhouse_query("SELECT version() AS version", _DEFAULT_HOST, _DEFAULT_PORT, timeout=5.0)
                version = rows[0][0] if rows else "-"
                # active 쿼리
                try:
                    _, arows, _ = _http_clickhouse_query("SELECT count() AS cnt FROM system.processes", _DEFAULT_HOST, _DEFAULT_PORT, timeout=5.0)
                    active = arows[0][0] if arows else "-"
                except Exception:
                    active = "-"
                uptime_str = "-"  # HTTP로 정확한 uptime 획득이 보장되지 않음
                try:
                    self._sig_conn.emit(True, "🟡 연결됨 (HTTP 폴백)", f"{_DEFAULT_HOST}:{_DEFAULT_PORT}", str(version), uptime_str, str(active))
                except Exception:
                    logger.exception("_sig_conn.emit 실패 (HTTP 폴백 성공)")
                return
            except Exception as hexc:
                hexc_str = str(hexc) or ""
                if "404" in hexc_str or "Not Found" in hexc_str:
                    user_msg = ("🔴 연결 실패: HTTP 응답이 404 또는 Not Found입니다. "
                                "해당 호스트/포트가 ClickHouse HTTP가 아닐 수 있습니다(예: nginx, 다른 서비스). "
                                "ClickHouse의 HTTP 포트(기본 8123) 또는 네이티브 포트(기본 9000)를 확인하세요.")
                elif "Unexpected packet" in hexc_str or "Unknown packet" in hexc_str:
                    user_msg = ("🔴 연결 실패: 네이티브 프로토콜 응답이 예상 형태가 아닙니다 (Unexpected packet). "
                                "포트가 HTTP(8123)로 설정되어 있거나 다른 서비스가 바인딩되어 있을 수 있습니다.")
                else:
                    user_msg = f"🔴 연결 실패: {hexc_str[:200]}"
                logger.debug("HTTP 폴백 실패 세부: %s", hexc_str)
                try:
                    self._sig_conn.emit(False, user_msg, f"{_DEFAULT_HOST}:{_DEFAULT_PORT}", "-", "-", "-")
                except Exception:
                    logger.exception("_sig_conn.emit 실패 (최종 폴백)")

        # ------------------------------------------------------------------
        # 탭 2: 테이블 목록 (네이티브 -> HTTP 폴백)
        # ------------------------------------------------------------------
        def _fetch_tables(self) -> None:
            query = (
                "SELECT name, engine, partition_key, sorting_key, "
                "formatReadableQuantity(total_rows) AS rows, "
                "formatReadableSize(total_bytes) AS size "
                "FROM system.tables "
                "WHERE database = currentDatabase() "
                "ORDER BY name"
            )
            rows_out: List[Dict[str, Any]] = []
            # native
            try:
                client = _make_client_native()
                result = client.execute(query)
                rows_out = [
                    {
                        "name": r[0],
                        "engine": r[1],
                        "partition_key": r[2] or "-",
                        "sorting_key": r[3] or "-",
                        "rows": r[4] or "0",
                        "size": r[5] or "0 B",
                    }
                    for r in result
                ]
                try:
                    self._sig_tables.emit(rows_out)
                except Exception:
                    logger.exception("_sig_tables.emit 실패 (네이티브 성공)")
                return
            except Exception as exc:
                logger.debug("네이티브 테이블 조회 실패: %s", exc)

            # HTTP fallback
            try:
                cols, rows, _ = _http_clickhouse_query(query, _DEFAULT_HOST, _DEFAULT_PORT, timeout=8.0)
                for r in rows:
                    rows_out.append({
                        "name": r[0],
                        "engine": r[1],
                        "partition_key": r[2] or "-",
                        "sorting_key": r[3] or "-",
                        "rows": r[4] or "0",
                        "size": r[5] or "0 B",
                    })
                try:
                    self._sig_tables.emit(rows_out)
                except Exception:
                    logger.exception("_sig_tables.emit 실패 (HTTP 폴백 성공)")
                return
            except Exception as hexc:
                logger.debug("HTTP 테이블 조회 실패: %s", hexc)
                try:
                    self._sig_tables.emit([])
                except Exception:
                    logger.exception("_sig_tables.emit 실패 (최종 폴백)")

        # ------------------------------------------------------------------
        # 탭 3: 파티션 목록 (네이티브 -> HTTP 폴백)
        # ------------------------------------------------------------------
        def _fetch_partitions(self) -> None:
            query = (
                "SELECT partition, sum(rows) AS rows_sum, "
                "formatReadableSize(sum(bytes_on_disk)) AS size, "
                "min(min_date) AS min_date, max(max_date) AS max_date "
                "FROM system.parts "
                "WHERE active "
                "GROUP BY partition "
                "ORDER BY partition"
            )
            rows_out: List[Dict[str, Any]] = []
            try:
                client = _make_client_native()
                result = client.execute(query)
                rows_out = [
                    {
                        "partition": str(r[0]),
                        "rows": f"{r[1]:,}",
                        "size": str(r[2]),
                        "min_date": str(r[3]) if r[3] else "-",
                        "max_date": str(r[4]) if r[4] else "-",
                    }
                    for r in result
                ]
                try:
                    self._sig_partitions.emit(rows_out)
                except Exception:
                    logger.exception("_sig_partitions.emit 실패 (네이티브 성공)")
                return
            except Exception as exc:
                logger.debug("네이티브 파티션 조회 실패: %s", exc)

            try:
                cols, rows, _ = _http_clickhouse_query(query, _DEFAULT_HOST, _DEFAULT_PORT, timeout=8.0)
                for r in rows:
                    rows_out.append({
                        "partition": str(r[0]),
                        "rows": str(r[1]),
                        "size": str(r[2]),
                        "min_date": str(r[3]) if r[3] else "-",
                        "max_date": str(r[4]) if r[4] else "-",
                    })
                try:
                    self._sig_partitions.emit(rows_out)
                except Exception:
                    logger.exception("_sig_partitions.emit 실패 (HTTP 폴백 성공)")
                return
            except Exception as hexc:
                logger.debug("HTTP 파티션 조회 실패: %s", hexc)
                try:
                    self._sig_partitions.emit([])
                except Exception:
                    logger.exception("_sig_partitions.emit 실패 (최종 폴백)")

        # ------------------------------------------------------------------
        # 탭 5: 이관 스케줄 (플레이스홀더)
        # ------------------------------------------------------------------
        def _fetch_migrations(self) -> None:
            rows: List[Dict[str, Any]] = [
                {
                    "job_id": "migration-001",
                    "source": "timescaledb.trade_events",
                    "target": "clickhouse.trade_events",
                    "schedule": "매시 정각",
                    "last_run": "-",
                    "next_run": "-",
                    "migrated_rows": "-",
                    "status": "⏸ 대기",
                }
            ]
            try:
                self._sig_migrations.emit(rows)
            except Exception:
                logger.exception("_sig_migrations.emit 실패")

        # ------------------------------------------------------------------
        # 탭 6: 성능 모니터링 (네이티브 -> HTTP 폴백)
        # ------------------------------------------------------------------
        def _fetch_perf(self) -> None:
            slow_query = (
                "SELECT query, query_duration_ms, read_rows, "
                "formatReadableSize(read_bytes) AS read_bytes, "
                "formatReadableSize(memory_usage) AS memory "
                "FROM system.query_log "
                "WHERE type = 'QueryFinish' "
                "ORDER BY query_duration_ms DESC "
                "LIMIT 20"
            )
            slow_rows_out: List[Dict[str, Any]] = []
            cpu, mem, disk_io = "-", "-", "-"
            try:
                client = _make_client_native()
                slow = client.execute(slow_query)
                slow_rows_out = [
                    {
                        "query": str(r[0])[:120],
                        "duration_ms": f"{r[1]:,} ms",
                        "read_rows": f"{r[2]:,}",
                        "read_bytes": str(r[3]),
                        "memory": str(r[4]),
                    }
                    for r in slow
                ]
                metrics = client.execute(
                    "SELECT metric, value FROM system.metrics "
                    "WHERE metric IN ('CPUUsage', 'MemoryTracking', 'DiskReadElapsedMicroseconds')"
                )
                metric_map = {r[0]: r[1] for r in metrics}
                cpu = str(metric_map.get("CPUUsage", "-"))
                mem = str(metric_map.get("MemoryTracking", "-"))
                disk_io = str(metric_map.get("DiskReadElapsedMicroseconds", "-"))
                try:
                    self._sig_perf.emit(slow_rows_out, cpu, mem, disk_io)
                except Exception:
                    logger.exception("_sig_perf.emit 실패 (네이티브 성공)")
                return
            except Exception as exc:
                logger.debug("네이티브 성능 조회 실패: %s", exc)

            try:
                cols, rows, _ = _http_clickhouse_query(slow_query, _DEFAULT_HOST, _DEFAULT_PORT, timeout=8.0)
                for r in rows:
                    slow_rows_out.append({
                        "query": str(r[0])[:120],
                        "duration_ms": f"{r[1]} ms" if r[1] is not None else "-",
                        "read_rows": str(r[2]) if r[2] is not None else "-",
                        "read_bytes": str(r[3]) if r[3] is not None else "-",
                        "memory": str(r[4]) if r[4] is not None else "-",
                    })
                try:
                    self._sig_perf.emit(slow_rows_out, cpu, mem, disk_io)
                except Exception:
                    logger.exception("_sig_perf.emit 실패 (HTTP 폴백 성공)")
                return
            except Exception as hexc:
                logger.debug("HTTP 성능 조회 실패: %s", hexc)
                try:
                    self._sig_perf.emit([], "-", "-", "-")
                except Exception:
                    logger.exception("_sig_perf.emit 실패 (최종 폴백)")

        # ------------------------------------------------------------------
        # 탭 4: 쿼리 실행 (네이티브 -> HTTP 폴백)
        # ------------------------------------------------------------------
        def _on_run_query(self) -> None:
            if not hasattr(self, "textQueryEditor"):
                return
            sql = self.textQueryEditor.toPlainText().strip()
            if not sql:
                return
            self._add_query_history(sql)
            threading.Thread(target=self._exec_query, args=(sql,), daemon=True).start()

        def _exec_query(self, sql: str) -> None:
            # 네이티브 시도
            try:
                client = _make_client_native()
                result = client.execute(sql, with_column_types=True)
                data, col_types = result
                columns = [c[0] for c in col_types]
                try:
                    self._sig_query_result.emit(columns, list(data))
                except Exception:
                    logger.exception("_sig_query_result.emit 실패 (네이티브 성공)")
                return
            except ImportError:
                logger.debug("_exec_query: clickhouse-driver 미설치, HTTP 폴백 시도")
            except Exception as exc:
                logger.debug("네이티브 쿼리 실패: %s", exc)

            # HTTP 폴백
            try:
                cols, rows, _ = _http_clickhouse_query(sql, _DEFAULT_HOST, _DEFAULT_PORT, timeout=15.0)
                try:
                    self._sig_query_result.emit(cols, rows)
                except Exception:
                    logger.exception("_sig_query_result.emit 실패 (HTTP 폴백 성공)")
            except Exception as hexc:
                logger.warning("쿼리 실행 오류: %s", hexc)
                try:
                    self._sig_query_result.emit(["오류"], [(str(hexc),)])
                except Exception:
                    logger.exception("_sig_query_result.emit 실패 (최종 폴백)")

        # ------------------------------------------------------------------
        # 신호 수신(메인 스레드) 핸들러들...
        # ------------------------------------------------------------------
        def _on_conn(self, ok: bool, status: str, host: str, version: str, uptime: str, active_queries: str) -> None:
            if hasattr(self, "labelConnStatus"):
                self.labelConnStatus.setText(status)
            if hasattr(self, "labelHost"):
                self.labelHost.setText(host)
            if hasattr(self, "labelVersion"):
                self.labelVersion.setText(version)
            if hasattr(self, "labelUptime"):
                self.labelUptime.setText(uptime)
            if hasattr(self, "labelActiveQueries"):
                self.labelActiveQueries.setText(active_queries)

        def _on_tables(self, rows: List[Dict[str, Any]]) -> None:
            if not hasattr(self, "tableClickHouseTables"):
                return
            self.tableClickHouseTables.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tableClickHouseTables.setItem(i, 0, _item(row["name"]))
                self.tableClickHouseTables.setItem(i, 1, _item(row["engine"]))
                self.tableClickHouseTables.setItem(i, 2, _item(row["partition_key"]))
                self.tableClickHouseTables.setItem(i, 3, _item(row["sorting_key"]))
                self.tableClickHouseTables.setItem(i, 4, _item(row["rows"]))
                self.tableClickHouseTables.setItem(i, 5, _item(row["size"]))

        def _on_partitions(self, rows: List[Dict[str, Any]]) -> None:
            if not hasattr(self, "tablePartitions"):
                return
            self.tablePartitions.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tablePartitions.setItem(i, 0, _item(row["partition"]))
                self.tablePartitions.setItem(i, 1, _item(row["rows"]))
                self.tablePartitions.setItem(i, 2, _item(row["size"]))
                self.tablePartitions.setItem(i, 3, _item(row["min_date"]))
                self.tablePartitions.setItem(i, 4, _item(row["max_date"]))

        def _on_query_result(self, columns: List[str], rows: List[tuple]) -> None:
            if not hasattr(self, "tableQueryResults"):
                return
            self.tableQueryResults.setColumnCount(len(columns))
            self.tableQueryResults.setHorizontalHeaderLabels(columns)
            self.tableQueryResults.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, cell in enumerate(row):
                    self.tableQueryResults.setItem(i, j, _item(str(cell)))
            if hasattr(self, "tableQueryResults"):
                self.tableQueryResults.horizontalHeader().setStretchLastSection(True)

        def _on_migrations(self, rows: List[Dict[str, Any]]) -> None:
            if not hasattr(self, "tableMigrations"):
                return
            self.tableMigrations.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tableMigrations.setItem(i, 0, _item(row["job_id"]))
                self.tableMigrations.setItem(i, 1, _item(row["source"]))
                self.tableMigrations.setItem(i, 2, _item(row["target"]))
                self.tableMigrations.setItem(i, 3, _item(row["schedule"]))
                self.tableMigrations.setItem(i, 4, _item(row["last_run"]))
                self.tableMigrations.setItem(i, 5, _item(row["next_run"]))
                self.tableMigrations.setItem(i, 6, _item(row["migrated_rows"]))
                self.tableMigrations.setItem(i, 7, _item(row["status"]))

        def _on_perf(self, slow_rows: List[Dict[str, Any]], cpu: str, mem: str, disk_io: str) -> None:
            if hasattr(self, "labelCPU"):
                self.labelCPU.setText(cpu)
            if hasattr(self, "labelMemory"):
                self.labelMemory.setText(mem)
            if hasattr(self, "labelDiskIO"):
                self.labelDiskIO.setText(disk_io)
            if not hasattr(self, "tableSlowQueries"):
                return
            self.tableSlowQueries.setRowCount(len(slow_rows))
            for i, row in enumerate(slow_rows):
                self.tableSlowQueries.setItem(i, 0, _item(row["query"]))
                self.tableSlowQueries.setItem(i, 1, _item(row["duration_ms"]))
                self.tableSlowQueries.setItem(i, 2, _item(row["read_rows"]))
                self.tableSlowQueries.setItem(i, 3, _item(row["read_bytes"]))
                self.tableSlowQueries.setItem(i, 4, _item(row["memory"]))

        # ------------------------------------------------------------------
        # 버튼 핸들러(미구현 영역)
        # ------------------------------------------------------------------
        def _add_query_history(self, sql: str) -> None:
            if sql in self._query_history:
                self._query_history.remove(sql)
            self._query_history.insert(0, sql)
            self._query_history = self._query_history[:20]
            if hasattr(self, "listQueryHistory"):
                self.listQueryHistory.clear()
                for q in self._query_history:
                    self.listQueryHistory.addItem(QListWidgetItem(q[:80]))

        def _on_history_select(self, item: "QListWidgetItem") -> None:
            idx = self.listQueryHistory.row(item)
            if 0 <= idx < len(self._query_history):
                if hasattr(self, "textQueryEditor"):
                    self.textQueryEditor.setPlainText(self._query_history[idx])

        def _on_template_select(self, index: int) -> None:
            if index <= 0 or index >= len(_QUERY_TEMPLATES):
                return
            _, sql = _QUERY_TEMPLATES[index]
            if sql and hasattr(self, "textQueryEditor"):
                self.textQueryEditor.setPlainText(sql)

        def _on_create_table(self) -> None:
            logger.info("테이블 생성 버튼 클릭 (미구현)")

        def _on_drop_table(self) -> None:
            logger.info("테이블 삭제 버튼 클릭 (미구현)")

        def _on_optimize(self) -> None:
            logger.info("최적화 버튼 클릭 (미구현)")

        def _on_drop_partition(self) -> None:
            logger.info("파티션 삭제 버튼 클릭 (미구현)")

        def _on_merge_partition(self) -> None:
            logger.info("파티션 병합 버튼 클릭 (미구현)")

        def _on_run_migration(self) -> None:
            logger.info("이관 수동 실행 버튼 클릭 (미구현)")

        def _on_edit_schedule(self) -> None:
            logger.info("스케줄 수정 버튼 클릭 (미구현)")

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
                logger.debug("[ClickHouseSettingsDialog] 검색: table=%s keyword=%s", table_name, keyword)
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
                logger.debug("[ClickHouseSettingsDialog] CSV 내보내기 예외: %s", e, exc_info=True)
                QMessageBox.warning(self, "오류", f"CSV 저장 실패: {e}")

        def closeEvent(self, event) -> None:
            """다이얼로그 닫힐 때 타이머를 정지한다."""
            try:
                from PyQt5.QtCore import QSettings
                _settings = QSettings("UpbitTrader", "DBMonitor")
                _settings.setValue("clickhouse_geometry", self.saveGeometry())
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

else:
    class ClickHouseSettingsDialog:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("PyQt5가 설치되어 있지 않습니다.")

# ---------------------------------------------------------------------------
# 헬퍼: 편집 불가 테이블 아이템
# ---------------------------------------------------------------------------
def _item(text: str) -> "QTableWidgetItem":
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item