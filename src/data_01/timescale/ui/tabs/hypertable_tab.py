#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hypertable 관리 탭 컨트롤러 (QThread Worker 패턴)

타이머 주기: 15초 (메인스레드 블로킹 없음)
TimescaleQueryWorker 를 사용하여 컬럼명 기반 매핑으로 tuple index 오류를 원천 차단합니다.
1차 쿼리 실패 시 폴백 쿼리로 자동 재시도합니다.
"""

import os
import logging
from typing import List, Optional, Dict

try:
    from PyQt5.QtWidgets import (
        QWidget, QTableWidgetItem, QHeaderView, QLabel, QHBoxLayout,
    )
    from PyQt5.QtCore import QTimer, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    def pyqtSlot(*args, **kwargs):  # no-op 폴백
        def decorator(f): return f
        return decorator

try:
    from .db_worker import TimescaleQueryWorker
except ImportError:
    from db_worker import TimescaleQueryWorker  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

_UI_PATH = os.path.join(os.path.dirname(__file__), "hypertable_tab.ui")

# UI 테이블 헤더 정의 — SQL alias와 반드시 대응합니다.
_HEADERS = ["테이블명", "청크수", "압축률", "보존기간", "총크기"]
_COLUMN_COUNT = len(_HEADERS)

# SQL alias 이름 → 컬럼 위치 매핑 (tuple index 의존 완전 제거)
_COL_ALIAS = {
    "table_name":     0,
    "hypertable_name": 0,   # 폴백 쿼리 alias
    "chunk_count":    1,
    "compress_ratio": 2,
    "retention":      3,
    "total_size":     4,
}

# 1차 쿼리 — TimescaleDB 2.x 이상 권장
_QUERY_PRIMARY = """
    SELECT
        h.hypertable_name                              AS table_name,
        COUNT(c.chunk_name)::text                      AS chunk_count,
        CASE
            WHEN COUNT(c.chunk_name) > 0 THEN
                to_char(
                    COUNT(c.chunk_name) FILTER (WHERE c.is_compressed)::float
                    / NULLIF(COUNT(c.chunk_name), 0) * 100,
                    'FM999.0'
                ) || '%'
            ELSE '0.0%'
        END                                            AS compress_ratio,
        COALESCE(
            (SELECT j.config->>'drop_after'
               FROM timescaledb_information.jobs j
              WHERE j.hypertable_name = h.hypertable_name
                AND j.proc_name = 'policy_retention'
              LIMIT 1),
            '없음'
        )                                              AS retention,
        COALESCE(
            pg_size_pretty(
                hypertable_size(
                    format('%I.%I', h.hypertable_schema, h.hypertable_name)::regclass
                )
            ),
            '-'
        )                                              AS total_size
    FROM timescaledb_information.hypertables h
    LEFT JOIN timescaledb_information.chunks c
           ON c.hypertable_schema = h.hypertable_schema
          AND c.hypertable_name   = h.hypertable_name
    GROUP BY h.hypertable_schema, h.hypertable_name
    ORDER BY h.hypertable_name
"""

# 폴백 쿼리 — hypertable_size() 없거나 jobs 뷰 없는 구버전용
_QUERY_FALLBACK = """
    SELECT
        COALESCE(h.hypertable_name, '-')  AS table_name,
        '?'                               AS chunk_count,
        '?'                               AS compress_ratio,
        '없음'                            AS retention,
        COALESCE(
            pg_size_pretty(
                pg_total_relation_size(
                    quote_ident(h.hypertable_name)
                )
            ),
            '-'
        )                                 AS total_size
    FROM timescaledb_information.hypertables h
    ORDER BY h.hypertable_name
"""


class HypertableTab(QWidget if _HAS_QT else object):
    """Hypertable 관리 탭.

    TimescaleDB 하이퍼테이블 목록, 청크 수, 압축률, 보존 기간, 크기를
    15초마다 자동으로 갱신합니다.

    오류 방지 설계:
    - TimescaleQueryWorker 사용 → cursor.description 으로 컬럼명 확보
    - 컬럼명 dict 기반 값 조회 → tuple index 의존 없음
    - 1차 쿼리 실패 시 폴백 쿼리 자동 재시도
    - 빈 결과/오류 시 에러 행 대신 상태 배너로 친절한 메시지 표시
    """

    def __init__(self, db_conn=None, conn_params: Optional[Dict] = None, parent=None):
        if not _HAS_QT:
            raise RuntimeError("PyQt5가 설치되지 않았습니다.")
        super().__init__(parent)
        self._conn_params: Dict = conn_params or {}
        self._worker: Optional[TimescaleQueryWorker] = None
        self._use_fallback: bool = False  # 1차 쿼리 실패 시 True

        try:
            uic.loadUi(_UI_PATH, self)
        except Exception as exc:
            logger.warning("[HypertableTab] UI 로드 실패: %s", exc)

        self._setup_table()
        self._add_status_label()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)

    # ------------------------------------------------------------------
    # 내부 설정
    # ------------------------------------------------------------------

    def _setup_table(self) -> None:
        """테이블 위젯 컬럼 초기 설정."""
        tbl = getattr(self, "table_hypertables", None)
        if tbl is None:
            return
        tbl.setColumnCount(_COLUMN_COUNT)
        tbl.setHorizontalHeaderLabels(_HEADERS)
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for i in range(1, _COLUMN_COUNT):
            hdr.setSectionResizeMode(i, QHeaderView.Stretch)
        tbl.setAlternatingRowColors(True)
        tbl.setSortingEnabled(True)

    def _add_status_label(self) -> None:
        """상태 라벨을 레이아웃 하단에 추가합니다."""
        layout = self.layout()
        if layout is None:
            return
        row = QHBoxLayout()
        self._lbl_status = QLabel("상태: 대기 중")
        self._lbl_status.setStyleSheet("color: #7F8C8D; font-size: 8pt;")
        row.addWidget(self._lbl_status)
        row.addStretch()
        layout.addLayout(row)

    # ------------------------------------------------------------------
    # 갱신 로직 (Worker 패턴, 컬럼명 기반 매핑)
    # ------------------------------------------------------------------

    def _update(self) -> None:
        """Worker 중복 실행을 방지하고 새 Worker 를 시작합니다."""
        if self._worker and self._worker.isRunning():
            return
        lbl = getattr(self, "_lbl_status", None)
        if lbl:
            lbl.setText("상태: 조회 중…")
            lbl.setStyleSheet("color: #F39C12; font-size: 8pt;")

        query = _QUERY_FALLBACK if self._use_fallback else _QUERY_PRIMARY
        self._worker = TimescaleQueryWorker(self._conn_params, query)
        self._worker.finished.connect(self._on_data_ready)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(list, list)
    def _on_data_ready(self, headers: List[str], rows: List[list]) -> None:
        """Worker 완료 — 컬럼명 기반 매핑으로 UI 를 갱신합니다.

        tuple index 의존을 완전히 제거합니다.
        각 행의 값을 headers 에서 찾은 이름으로 조회하므로
        쿼리 컬럼 수나 순서가 바뀌어도 안전합니다.
        """
        from datetime import datetime
        tbl = getattr(self, "table_hypertables", None)
        if tbl is None:
            return

        rows = rows or []

        if not rows:
            # 빈 결과 — 테이블에 메시지 표시
            tbl.setRowCount(1)
            tbl.setColumnCount(_COLUMN_COUNT)
            tbl.setItem(0, 0, QTableWidgetItem("(하이퍼테이블이 없습니다)"))
            for col in range(1, _COLUMN_COUNT):
                tbl.setItem(0, col, QTableWidgetItem(""))
            lbl = getattr(self, "_lbl_status", None)
            if lbl:
                lbl.setText("⚠️ Hypertable 없음 — timescaledb 익스텐션 확인 필요")
                lbl.setStyleSheet("color: #E67E22; font-size: 8pt;")
            return

        # 컬럼명 → 결과 리스트 인덱스 매핑 빌드
        # headers 에 없는 alias 는 "-" 로 폴백
        name_to_idx: Dict[str, int] = {h: i for i, h in enumerate(headers)}

        def _get(row: list, alias: str) -> str:
            """alias 이름으로 row 값을 안전하게 가져옵니다."""
            # _COL_ALIAS 의 alias 에 대응하는 실제 컬럼 이름(헤더)을 검색
            for col_alias, _pos in _COL_ALIAS.items():
                if col_alias == alias and col_alias in name_to_idx:
                    idx = name_to_idx[col_alias]
                    if 0 <= idx < len(row):
                        v = row[idx]
                        return str(v) if v is not None else "-"
            return "-"

        tbl.setSortingEnabled(False)
        tbl.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            # 컬럼별 값 추출 (alias 이름 기반, index 하드코딩 없음)
            cells = [
                _get(row, "table_name"),
                _get(row, "chunk_count"),
                _get(row, "compress_ratio"),
                _get(row, "retention"),
                _get(row, "total_size"),
            ]
            # 폴백: _get 이 모두 "-" 를 반환하면 headers 순서대로 채움
            if all(v == "-" for v in cells) and len(row) >= 1:
                cells = [
                    str(row[i]) if i < len(row) and row[i] is not None else "-"
                    for i in range(_COLUMN_COUNT)
                ]
            for c_idx, cell_val in enumerate(cells):
                item = QTableWidgetItem(cell_val)
                tbl.setItem(r_idx, c_idx, item)
        tbl.setSortingEnabled(True)

        lbl = getattr(self, "_lbl_status", None)
        if lbl:
            now = datetime.now().strftime("%H:%M:%S")
            src = " (폴백 쿼리)" if self._use_fallback else ""
            lbl.setText(f"✅ 마지막 갱신: {now}  |  {len(rows)}개 테이블{src}")
            lbl.setStyleSheet("color: #27AE60; font-size: 8pt;")

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        """Worker 오류 — 상태 배너에 원인 메시지를 표시합니다.

        에러 행을 테이블에 삽입하지 않고 상태 라벨에만 표시합니다.
        1차 쿼리 실패 시 다음 주기에 폴백 쿼리를 시도합니다.
        """
        hint = ""
        msg_lo = msg.lower()
        if "hypertable_size" in msg_lo or "does not exist" in msg_lo:
            hint = " → hypertable_size() 미지원 버전일 수 있습니다. 다음 갱신에 폴백 쿼리를 시도합니다."
            self._use_fallback = True
        elif "connection" in msg_lo or "connect" in msg_lo:
            hint = " → DB 연결 실패. TimescaleDB 컨테이너 실행 여부를 확인하세요."
        elif "permission" in msg_lo:
            hint = " → 조회 권한이 없습니다. DB 사용자 권한을 확인하세요."
        elif "timescaledb_information" in msg_lo:
            hint = " → timescaledb_information 뷰를 찾을 수 없습니다. TimescaleDB 익스텐션을 확인하세요."
            self._use_fallback = True

        tbl = getattr(self, "table_hypertables", None)
        if tbl is not None:
            # 오류 시 테이블을 비움 (에러 행 삽입 대신 상태 배너 사용)
            tbl.setRowCount(0)

        lbl = getattr(self, "_lbl_status", None)
        if lbl:
            lbl.setText(f"🔴 조회 오류 — {msg[:120]}{hint}")
            lbl.setStyleSheet("color: #E74C3C; font-size: 8pt;")

        logger.debug("[HypertableTab] Worker 오류: %s", msg)

    # ------------------------------------------------------------------
    # 생명 주기
    # ------------------------------------------------------------------

    def start_updates(self, interval_ms: int = 15_000) -> None:
        """자동 갱신 시작. 즉시 첫 갱신도 실행합니다."""
        self._timer.setInterval(max(1000, int(interval_ms)))
        if not self._timer.isActive():
            self._timer.start()
        self._update()

    def stop_updates(self) -> None:
        """자동 갱신 중지."""
        self._timer.stop()

    def closeEvent(self, event):
        """위젯 닫힘 시 타이머와 Worker 를 정리합니다."""
        self._timer.stop()
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        super().closeEvent(event)
