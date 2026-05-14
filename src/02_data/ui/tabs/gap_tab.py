# -*- coding: utf-8 -*-
"""Tab 4: Gap 검출 제어 로직 - v2.0
다중 Redis 키 패턴 ���백, Gap 상태 통계, 더블클릭 상세 팝업 지원."""
from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================
# 상수
# ============================================================
_DEFAULT_GRACE_PERIOD_SEC: int = 300  # Grace Period 기본값 (초)
# Gap 수동 실행 트리거 키 유효 시간 (초)
_GAP_TRIGGER_EXPIRATION_SEC: int = 60
# Gap 시간 비교를 위한 타임스탬프 앞부분 길이 (YYYY-MM-DD HH:MM)
_GAP_TIME_COMPARE_LEN: int = 16
_EXCLUDED_WORKER_KEYS = frozenset({
    "gap:worker:count",
    "gap:worker:grace_period",
    "gap:worker:status",
})

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5.QtWidgets import (
        QWidget, QTableWidgetItem, QDialog, QVBoxLayout,
        QTextEdit, QPushButton, QMessageBox, QSizePolicy, QHeaderView,
        QHBoxLayout, QLayout, QWidgetItem
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

from ._mixins import TableCopyMixin

if _HAS_QT:
    class GapTab(TableCopyMixin, QWidget):
        """Tab 4: Gap 검출 — uic.loadUi() 기반 자립형 위젯

        - 탭 내부에서 자체적으로 레이아웃/크기 보정을 수행하도록 책임을 둡니다.
        - widget.py(로더)는 더 이상 탭의 레이아웃을 직접 수정하지 않아도 됩니다.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            ui_path = os.path.join(os.path.dirname(__file__), "gap_tab.ui")
            try:
                uic.loadUi(ui_path, self)
            except Exception as exc:
                logger.warning("[GapTab] UI 파일 로드 실패: %s", exc)

            # 테이블 복사 등 믹스인 초기화
            try:
                self._setup_table_copy()
            except Exception:
                pass

            # 자동 갱신 타이머
            self._timer = QTimer(self)
            self._timer.setInterval(3000)
            self._timer.timeout.connect(self._update_ui)

            # 버튼 연결 (존재 시 연결)
            try:
                if hasattr(self, "btn_refresh_gap"):
                    self.btn_refresh_gap.clicked.connect(self.refresh_gap_queue)
            except Exception:
                pass

            try:
                if hasattr(self, "btn_clear_queue"):
                    self.btn_clear_queue.clicked.connect(self._clear_gap_queue)
            except Exception:
                pass

            try:
                if hasattr(self, "btn_run_gap_worker"):
                    self.btn_run_gap_worker.clicked.connect(self._run_gap_worker)
            except Exception:
                pass

            # 테이블 더블클릭 이벤트 연결
            try:
                tbl = getattr(self, "table_gap_details", None)
                if tbl is not None:
                    tbl.doubleClicked.connect(self._on_gap_row_double_clicked)
            except Exception:
                pass

            # 탭 내부 UI 보정: 상단 패널 좌우 배치 및 테이블 확장성 확보
            try:
                self._apply_layout_fixes()
            except Exception:
                logger.debug("[GapTab] _apply_layout_fixes failed", exc_info=True)

        # ---------------------------
        # 기본 동작: 업데이트 제어
        # ---------------------------
        def start_updates(self, interval_ms: int = 3000) -> None:
            self._timer.setInterval(max(3000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

        def _update_ui(self) -> None:
            """Gap 탭 자동 갱신 (3초마다)"""
            self.refresh_gap_queue()

        # ---------------------------
        # Redis / DB 접근 헬퍼
        # ---------------------------
        def _get_redis_client(self) -> Optional[Any]:
            """단기 Redis 클라이언트 반환."""
            try:
                import redis as _redis_mod  # type: ignore
                host = os.getenv("REDIS_HOST", "localhost")
                port = int(os.getenv("REDIS_PORT", "58530"))
                password = os.getenv("REDIS_PASSWORD") or None
                return _redis_mod.Redis(
                    host=host, port=port, password=password,
                    decode_responses=True, socket_connect_timeout=1,
                )
            except Exception:
                return None

        # ---------------------------
        # UI 갱신: 큐/테이블/통계
        # ---------------------------
        def refresh_gap_queue(self) -> None:
            """Redis/DB Gap 큐를 조회하여 Gap 탭 UI를 갱신합니다."""
            try:
                from ..utils import get_gaps, get_gap_queue_size
            except Exception:
                # utils가 없으면 조용히 종료
                logger.debug("[GapTab] utils 모듈 로드 실패 - get_gaps/get_gap_queue_size 없음")
                return

            try:
                # Gap 큐 크기
                try:
                    queue_size = get_gap_queue_size()
                    if hasattr(self, "label_gap_queue_size"):
                        self.label_gap_queue_size.setText(f"{queue_size:,} 건")
                except Exception:
                    pass

                # Redis에서 GapWorker 상태 조회
                try:
                    self._refresh_worker_status()
                except Exception:
                    pass

                # Gap 상태별 통계 갱신
                try:
                    self._refresh_gap_statistics()
                except Exception:
                    pass

                # Gap 목록 상세 테이블
                tbl = getattr(self, "table_gap_details", None)
                if tbl is not None:
                    try:
                        gaps = get_gaps()
                        tbl.setRowCount(len(gaps))
                        for i, gap in enumerate(gaps):
                            tbl.setItem(i, 0, QTableWidgetItem(str(gap.get("symbol", ""))))
                            tbl.setItem(i, 1, QTableWidgetItem(str(gap.get("gap_start", gap.get("start", "")))))
                            tbl.setItem(i, 2, QTableWidgetItem(str(gap.get("gap_end", gap.get("end", "")))))
                            tbl.setItem(i, 3, QTableWidgetItem(str(gap.get("priority", 0))))
                            tbl.setItem(i, 4, QTableWidgetItem(str(gap.get("status", "pending"))))
                        try:
                            tbl.resizeColumnsToContents()
                        except Exception:
                            pass
                    except Exception:
                        logger.debug("[GapTab] get_gaps 호출 또는 테이블 채우기 실패", exc_info=True)
            except Exception as exc:
                logger.debug("[GapTab] Gap 큐 갱신 실패: %s", exc)

        def _refresh_worker_status(self) -> None:
            """Redis에서 GapWorker 상태를 읽어 Grace Period, Workers 레이블을 갱신합니다."""
            try:
                rc = self._get_redis_client()
                if rc is None:
                    return

                # Grace Period 조회 (우선순위 별)
                grace = None
                for key in ("gap:worker:grace_period", "gap:config:grace_period"):
                    try:
                        val = rc.get(key)
                        if val is not None:
                            grace = val
                            break
                    except Exception:
                        pass

                if grace is None:
                    try:
                        grace = rc.hget("gap:settings", "grace_period")
                    except Exception:
                        pass

                grace_display = f"{_DEFAULT_GRACE_PERIOD_SEC} 초 (기본값)" if grace is None else f"{grace} 초"
                if hasattr(self, "label_gap_grace"):
                    try:
                        self.label_gap_grace.setText(grace_display)
                    except Exception:
                        pass

                # 활성 워커 수 조회
                worker_count = None
                try:
                    worker_count = rc.get("gap:worker:count")
                except Exception:
                    pass

                if not worker_count:
                    try:
                        keys = list(rc.scan_iter("gap:worker:*", count=50))
                        active_keys = [k for k in keys if k not in _EXCLUDED_WORKER_KEYS]
                        if active_keys:
                            worker_count = str(len(active_keys))
                    except Exception:
                        pass

                if not worker_count:
                    try:
                        workers_hash = rc.hgetall("gap:workers")
                        if workers_hash:
                            worker_count = str(len(workers_hash))
                    except Exception:
                        pass

                if hasattr(self, "label_gap_workers"):
                    try:
                        self.label_gap_workers.setText(str(worker_count) if worker_count else "--")
                    except Exception:
                        pass

                # 워커 상태 JSON 처리
                try:
                    status_raw = rc.get("gap:worker:status")
                    if status_raw:
                        status_obj = json.loads(status_raw)
                        last_proc = status_obj.get("last_processed", "")
                        if last_proc and hasattr(self, "label_gap_last_processed"):
                            try:
                                self.label_gap_last_processed.setText(str(last_proc))
                            except Exception:
                                pass
                except Exception:
                    pass

            except Exception as exc:
                logger.debug("[GapTab] Worker 상태 조회 실패: %s", exc)

        def _refresh_gap_statistics(self) -> None:
            """Gap 상태별 통계 패널 갱신 (pending/processing/failed/completed)."""
            try:
                rc = self._get_redis_client()
                stats: Dict[str, int] = {
                    "pending": 0, "processing": 0, "failed": 0, "completed": 0, "today": 0,
                }

                if rc is not None:
                    try:
                        for status_key in ("gap:stats:pending", "gap:stats:processing",
                                           "gap:stats:failed", "gap:stats:completed"):
                            status_name = status_key.split(":")[-1]
                            val = rc.get(status_key)
                            if val is not None:
                                stats[status_name] = int(val)

                        if stats["pending"] == 0:
                            try:
                                zsize = rc.zcard("gap_fill_queue")
                                if zsize:
                                    stats["pending"] = int(zsize)
                            except Exception:
                                pass

                        today_val = rc.get("gap:stats:today")
                        if today_val is not None:
                            stats["today"] = int(today_val)
                    except Exception:
                        pass

                # Redis에 데이터 없으면 DB 조회 시도
                if all(v == 0 for v in stats.values()):
                    try:
                        self._refresh_gap_stats_from_db(stats)
                    except Exception:
                        pass

                # 레이블 업데이트
                try:
                    if hasattr(self, "label_gap_pending"):
                        self.label_gap_pending.setText(f"{stats['pending']:,} 건")
                    if hasattr(self, "label_gap_processing"):
                        self.label_gap_processing.setText(f"{stats['processing']:,} 건")
                    if hasattr(self, "label_gap_failed"):
                        self.label_gap_failed.setText(f"{stats['failed']:,} 건")
                    if hasattr(self, "label_gap_completed"):
                        self.label_gap_completed.setText(f"{stats['completed']:,} 건")
                    if hasattr(self, "label_gap_today"):
                        self.label_gap_today.setText(f"{stats['today']:,} 건")
                except Exception:
                    pass

                # 데이터 무결성 상태 표시
                failed = stats.get("failed", 0)
                pending = stats.get("pending", 0)
                if hasattr(self, "label_gap_integrity"):
                    try:
                        if failed > 10:
                            self.label_gap_integrity.setText(f"[오류] 실패 Gap {failed:,}건 확인 필요")
                        elif failed > 0 or pending > 50:
                            self.label_gap_integrity.setText(
                                f"[주의] 실패 {failed:,}건 / 대기 {pending:,}건 [TimescaleDB·Redis]"
                            )
                        else:
                            self.label_gap_integrity.setText("[OK] 정상 — 무결성 이상 없음 [TimescaleDB·Redis]")
                    except Exception:
                        pass

            except Exception as exc:
                logger.debug("[GapTab] Gap 통계 갱신 실패: %s", exc)

        def _refresh_gap_stats_from_db(self, stats: Dict[str, int]) -> None:
            """TimescaleDB gap_fill_queue에서 상태별 건수 조회."""
            try:
                import psycopg2  # type: ignore
                host = os.getenv("TIMESCALE_HOST", os.getenv("POSTGRES_HOST", "localhost"))
                port = int(os.getenv("TIMESCALE_PORT", os.getenv("POSTGRES_PORT", "5432")))
                dbname = os.getenv("TIMESCALE_DB", os.getenv("POSTGRES_DB", "upbit_trader"))
                user = os.getenv("TIMESCALE_USER", os.getenv("POSTGRES_USER", "postgres"))
                password = os.getenv("TIMESCALE_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
                conn = psycopg2.connect(
                    host=host, port=port, dbname=dbname, user=user, password=password,
                    connect_timeout=2,
                )
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT status, COUNT(*) FROM gap_fill_queue
                            GROUP BY status
                            """
                        )
                        for row in cur.fetchall():
                            status_name = str(row[0]).lower()
                            if status_name in stats:
                                stats[status_name] = int(row[1])
                    logger.debug("[GapTab] TimescaleDB gap_fill_queue 조회 성공")
                finally:
                    conn.close()
            except Exception as exc:
                logger.debug("[GapTab] TimescaleDB Gap 통계 조회 실패: %s", exc)

        # ---------------------------
        # 테이블 상세 팝업 및 삭제
        # ---------------------------
        def _on_gap_row_double_clicked(self, index) -> None:
            """Gap 상세 테이블 더블클릭 시 상세 정보 팝업."""
            tbl = getattr(self, "table_gap_details", None)
            if tbl is None:
                return
            row = index.row()
            try:
                symbol = tbl.item(row, 0).text() if tbl.item(row, 0) else ""
                gap_start = tbl.item(row, 1).text() if tbl.item(row, 1) else ""
                gap_end = tbl.item(row, 2).text() if tbl.item(row, 2) else ""
                priority = tbl.item(row, 3).text() if tbl.item(row, 3) else ""
                status = tbl.item(row, 4).text() if tbl.item(row, 4) else ""

                dlg = QDialog(self)
                dlg.setWindowTitle(f"Gap 상세 — {symbol}")
                dlg.setMinimumWidth(500)
                layout = QVBoxLayout(dlg)

                txt = QTextEdit()
                txt.setReadOnly(True)
                txt.setPlainText(
                    f"심볼: {symbol}\n"
                    f"Gap 시작: {gap_start}\n"
                    f"Gap 종료: {gap_end}\n"
                    f"우선순위: {priority}\n"
                    f"상태: {status}\n"
                )
                layout.addWidget(txt)

                # Gap 개별 삭제 버튼
                btn_delete_gap = QPushButton("🗑️ 이 Gap 삭제")
                btn_delete_gap.setStyleSheet("color: red;")
                btn_delete_gap.clicked.connect(
                    lambda: self._delete_single_gap(symbol, gap_start, gap_end, dlg)
                )
                layout.addWidget(btn_delete_gap)

                btn_close = QPushButton("✖ 닫기")
                btn_close.clicked.connect(dlg.close)
                layout.addWidget(btn_close)

                dlg.exec_()
            except Exception as exc:
                logger.warning("[GapTab] Gap 상세 팝업 실패: %s", exc)

        def _delete_single_gap(self, symbol: str, gap_start: str, gap_end: str, parent_dlg) -> None:
            """단일 Gap을 Redis sorted set에서 삭제합니다."""
            answer = QMessageBox.question(
                self,
                "Gap 삭제 확인",
                f"[{symbol}] Gap {gap_start} ~ {gap_end} 을(를) 삭제하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            try:
                rc = self._get_redis_client()
                if rc is None:
                    QMessageBox.warning(self, "오류", "Redis 연결 실패")
                    return
                members = rc.zrange("gap_fill_queue", 0, -1, withscores=False)
                deleted = 0
                for m in members:
                    try:
                        m_str = m if isinstance(m, str) else m.decode("utf-8")
                        if symbol in m_str and (gap_start[:_GAP_TIME_COMPARE_LEN] in m_str or gap_end[:_GAP_TIME_COMPARE_LEN] in m_str):
                            rc.zrem("gap_fill_queue", m)
                            deleted += 1
                    except Exception:
                        pass
                if deleted > 0:
                    QMessageBox.information(self, "삭제 완료", f"Gap {deleted}건 삭제되었습니다.")
                    parent_dlg.close()
                    self.refresh_gap_queue()
                else:
                    QMessageBox.information(self, "알림", "삭제할 Gap을 Redis에서 찾지 못했습니다.")
            except Exception as exc:
                logger.warning("[GapTab] Gap 삭제 실패: %s", exc)
                QMessageBox.warning(self, "삭제 실패", str(exc))

        def _clear_gap_queue(self) -> None:
            """Redis gap_fill_queue Sorted Set 전체 삭제."""
            answer = QMessageBox.question(
                self,
                "큐 초기화 확인",
                "Redis gap_fill_queue 전체를 삭제하시겠습니까?\n\n⚠ 이 작업은 되돌릴 수 없습니다.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            try:
                rc = self._get_redis_client()
                if rc is None:
                    QMessageBox.warning(self, "오류", "Redis 연결 실패")
                    return
                size = rc.zcard("gap_fill_queue")
                rc.delete("gap_fill_queue")
                QMessageBox.information(
                    self, "큐 초기화 완료", f"gap_fill_queue {size}건이 삭제되었습니다."
                )
                self.refresh_gap_queue()
            except Exception as exc:
                logger.warning("[GapTab] 큐 초기화 실패: %s", exc)
                QMessageBox.warning(self, "초기화 실패", str(exc))

        def _run_gap_worker(self) -> None:
            """Gap Consumer Worker 즉시 실행 트리거 (Redis 트리거 키 설정)."""
            try:
                rc = self._get_redis_client()
                if rc is None:
                    QMessageBox.warning(self, "오류", "Redis 연결 실패")
                    return
                rc.set("gap:trigger:manual", "1", ex=_GAP_TRIGGER_EXPIRATION_SEC)
                rc.publish("gap:trigger", "manual_run")
                QMessageBox.information(
                    self, "실행 트리거", "Gap Worker 즉시 실행 신호가 전송되었습니다.\n(Redis: gap:trigger:manual = 1)"
                )
                logger.info("[GapTab] Gap Worker 수동 실행 트리거 전송")
            except Exception as exc:
                logger.warning("[GapTab] Gap Worker 트리거 실패: %s", exc)
                QMessageBox.warning(self, "실패", str(exc))

        def update_gap_tab(self, pipeline_bg_cache: Dict[str, Any], pipeline_bg_lock) -> None:
            """Gap 탭 UI 갱신 (캐시 사용)"""
            try:
                with pipeline_bg_lock:
                    cache = dict(pipeline_bg_cache)
                gap_stats = cache.get("table_gap") or {}
                gap_count = gap_stats.get("row_count", 0)
                if hasattr(self, "label_gap_queue_size"):
                    try:
                        self.label_gap_queue_size.setText(f"{gap_count:,} 건")
                    except Exception:
                        pass
            except Exception as exc:
                logger.error("[GapTab] Gap 탭 갱신 실패: %s", exc)

        def update_gap_table(self, rows: List) -> None:
            """Gap 상세 테이블 갱신"""
            tbl = getattr(self, "table_gap_details", None)
            if tbl is None:
                return
            try:
                tbl.setRowCount(len(rows))
                for i, row in enumerate(rows):
                    for j, val in enumerate(row):
                        tbl.setItem(i, j, QTableWidgetItem(str(val or "")))
                try:
                    tbl.resizeColumnsToContents()
                except Exception:
                    pass
            except Exception as exc:
                logger.error("[GapTab] Gap 테이블 갱신 실패: %s", exc)

        # ------------------------------
        # 탭 내부 UI 보정: 레이아웃/테이블 크기 등을 탭이 책임지도록 함
        # ------------------------------
        def _apply_layout_fixes(self) -> None:
            """상단 요약/통계 좌우 배치 및 테이블 확장성 확보를 시도합니다.

            - 안전하게 동작: 필요한 위젯/레이아웃이 없으면 조용히 무시합니다.
            - .ui 파일의 구조에 따라 HBox로 묶어 재배치하거나, sizePolicy만 보정합니다.
            """
            try:
                # -------- 테이블 보정: 최소 높이 및 확장성 확보 --------
                try:
                    tbl = getattr(self, "table_gap_details", None)
                    if tbl is not None:
                        try:
                            tbl.setMinimumHeight(520)  # 더 크게 보이도록
                            tbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                            # 헤더 조정: 내용을 기준으로 ���기 조정, 마지막 열 스트레치
                            try:
                                hdr = tbl.horizontalHeader()
                                hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
                                hdr.setStretchLastSection(True)
                            except Exception:
                                pass
                            # 세로헤더 기본 높이 보정
                            try:
                                vh = tbl.verticalHeader()
                                if vh is not None and vh.defaultSectionSize() < 20:
                                    vh.setDefaultSectionSize(20)
                            except Exception:
                                pass
                        except Exception:
                            pass
                except Exception:
                    pass

                # -------- 상단: frame_gap_summary 와 groupBox_gap_stats를 좌우로 배치 시도 --------
                try:
                    frame = getattr(self, "frame_gap_summary", None)
                    stats_gb = getattr(self, "groupBox_gap_stats", None)

                    # sizePolicy 우선 보정
                    try:
                        if frame is not None:
                            frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                        if stats_gb is not None:
                            stats_gb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                    except Exception:
                        pass

                    # 시도: vLayout_gap_inner에서 두 위젯을 찾아 HBox로 묶어 상단에 배치
                    try:
                        vlayout = getattr(self, "vLayout_gap_inner", None)
                        if vlayout is None:
                            # fallback: name-based search for layout attribute
                            # attempt to find layout object on parent widget
                            parent_layout = self.layout()
                            if isinstance(parent_layout, QLayout):
                                vlayout = parent_layout
                        if vlayout is not None and frame is not None and stats_gb is not None:
                            # find indices of frame and stats_gb inside vlayout
                            frame_index = -1
                            stats_index = -1
                            for i in range(vlayout.count()):
                                item = vlayout.itemAt(i)
                                if item is None:
                                    continue
                                w = item.widget()
                                if w is frame:
                                    frame_index = i
                                if w is stats_gb:
                                    stats_index = i
                            # if both found and not already in same HBox, reparent into HBox at min index
                            if frame_index != -1 and stats_index != -1:
                                # ensure frame_index < stats_index
                                if frame_index > stats_index:
                                    frame_index, stats_index = stats_index, frame_index
                                # remove widgets from layout safely
                                # collect bottom widgets between/after
                                bottom_widgets = []
                                total = vlayout.count()
                                for i in range(total - 1, -1, -1):
                                    item = vlayout.itemAt(i)
                                    if item is None:
                                        continue
                                    w = item.widget()
                                    # If this widget is frame or stats_gb, take them out; else save for later
                                    try:
                                        if w is frame or w is stats_gb:
                                            # remove item
                                            it = vlayout.takeAt(i)
                                            if it is not None:
                                                try:
                                                    # disassociate widget
                                                    wid = it.widget()
                                                    if wid is not None:
                                                        wid.setParent(None)
                                                except Exception:
                                                    pass
                                        else:
                                            # take and collect to re-add later
                                            it = vlayout.takeAt(i)
                                            if it is not None:
                                                wid = it.widget()
                                                if wid is not None:
                                                    bottom_widgets.insert(0, wid)
                                                else:
                                                    # if it's a layout, skip
                                                    pass
                                    except Exception:
                                        pass
                                # create new HBox and add frame and stats
                                try:
                                    top_h = QHBoxLayout()
                                    top_h.setContentsMargins(0, 0, 0, 0)
                                    top_h.setSpacing(8)
                                    # reparent and add frame/stats to top_h
                                    try:
                                        frame.setParent(self)
                                        top_h.addWidget(frame, 1)
                                    except Exception:
                                        pass
                                    try:
                                        stats_gb.setParent(self)
                                        top_h.addWidget(stats_gb, 1)
                                    except Exception:
                                        pass
                                    # insert new top_h at beginning of vlayout
                                    vlayout.insertLayout(0, top_h)
                                    # re-add bottom widgets after top_h
                                    for bw in bottom_widgets:
                                        try:
                                            bw.setParent(self)
                                            vlayout.addWidget(bw)
                                        except Exception:
                                            # if bw is layout, try adding
                                            try:
                                                if isinstance(bw, QLayout):
                                                    vlayout.addLayout(bw)
                                            except Exception:
                                                pass
                                except Exception:
                                    # If any re-layout failed, fallback to only sizePolicy adjustments above
                                    logger.debug("[GapTab] top HBox reparent failed; fallback to sizePolicy only", exc_info=True)
                    except Exception:
                        pass

                except Exception:
                    pass

            except Exception as exc:
                logger.debug("[GapTab] _apply_layout_fixes error: %s", exc, exc_info=True)

else:
    class GapTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""
        def __init__(self, parent=None):
            pass
        def start_updates(self, interval_ms: int = 3000) -> None:
            pass
        def stop_updates(self) -> None:
            pass
        def update_gap_tab(self, *args, **kwargs) -> None:
            pass
        def update_gap_table(self, rows: List) -> None:
            pass
        def refresh_gap_queue(self) -> None:
            pass
        def _clear_gap_queue(self) -> None:
            pass
        def _run_gap_worker(self) -> None:
            pass