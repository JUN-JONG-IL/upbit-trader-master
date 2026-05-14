# -*- coding: utf-8 -*-
"""
Gap Monitor Dialog (관리자용)
- Redis 클라이언트 import를 상대 import로 시도하고 실패하면 파일경로로 동적 로드 폴백을 사용합니다.
- 블로킹 Redis 호출은 백그라운드 스레드에서 실행하여 UI 차단을 방지합니다.
"""
from __future__ import annotations

import json
import threading
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path
import importlib.util
import importlib

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QMessageBox,
    QHeaderView,
)

logger = logging.getLogger(__name__)

# 모듈 레벨 싱글톤 Redis 클라이언트 (포트 고갈 방지: 연결 풀 재사용)
_redis_client_singleton = None
_redis_client_singleton_kwargs: Dict[str, Any] = {}
_redis_client_lock = threading.Lock()

# RedisClient 로드: 상대 import 시도 -> 파일경로 폴백
RedisClient = None
try:
    # 상대 import: package 구조에서 '...redis.core.client'로 접근 (ui -> pipeline -> data_01)
    from ...redis.core.client import RedisClient  # type: ignore
except Exception:
    try:
        # 런타임에서 패키지 경로로 로드 시도 (환경에 따라 동작)
        mod = importlib.import_module("src.data_01.redis.core.client")
        RedisClient = getattr(mod, "RedisClient", None)
    except Exception:
        # 파일경로 폴백: src/data_01/redis/core/client.py
        try:
            base = Path(__file__).resolve().parents[3]  # repo/src
            candidate = base / "data_01" / "redis" / "core" / "client.py"
            if candidate.exists():
                spec = importlib.util.spec_from_file_location("redis_core_client", str(candidate))
                if spec and spec.loader:
                    m = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(m)  # type: ignore
                    RedisClient = getattr(m, "RedisClient", None)
        except Exception:
            logger.debug("RedisClient 파일경로 로드 실패", exc_info=True)

class GapMonitorDialog(QDialog):
    """
    Gap 큐 상태를 보여주고 관리하는 간단한 다이얼로그.
    - redis_kwargs: redis.Redis 생성자에 전달할 인자(예: host, port, db, password)
    """

    def __init__(self, parent=None, redis_kwargs: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gap Monitor")
        self.resize(900, 480)

        main = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Gap 큐 (gap_fill_queue) 모니터"))
        header_layout.addStretch()

        self.btnRefresh = QPushButton("새로고침")
        self.btnDequeue = QPushButton("선택 제거 (ZREM)")
        self.btnRemove = QPushButton("선택 삭제 (ZREM)")
        self.btnExport = QPushButton("CSV 내보내기")

        header_layout.addWidget(self.btnRefresh)
        header_layout.addWidget(self.btnDequeue)
        header_layout.addWidget(self.btnRemove)
        header_layout.addWidget(self.btnExport)

        main.addLayout(header_layout)

        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["심볼", "타임프레임", "gap_seconds", "enqueued_at"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        main.addWidget(self.table)

        self.labelStatus = QLabel("상태: 준비됨")
        main.addWidget(self.labelStatus)

        self._redis_kwargs = redis_kwargs or {}
        self.btnRefresh.clicked.connect(self.refresh)
        self.btnDequeue.clicked.connect(self.dequeue_selected)
        self.btnRemove.clicked.connect(self.remove_selected)
        self.btnExport.clicked.connect(self.export_csv)

        self._rows: List[Dict[str, Any]] = []
        self.refresh()

    # Redis 클라이언트 반환 (싱글톤 — 포트 고갈 방지)
    def _get_redis_client_sync(self):
        global _redis_client_singleton, _redis_client_singleton_kwargs
        try:
            kwargs = self._redis_kwargs

            with _redis_client_lock:
                # kwargs 변경 시 재생성
                if _redis_client_singleton is None or _redis_client_singleton_kwargs != kwargs:
                    # 우선 레포의 RedisClient 래퍼 사용 시도
                    if RedisClient is not None:
                        new_client = RedisClient(**kwargs).client if kwargs else RedisClient().client
                    else:
                        import redis as _redis
                        # max_connections 기본값 설정 (사용자가 지정하지 않은 경우에만)
                        merged = {"decode_responses": True}
                        if "max_connections" not in (kwargs or {}):
                            merged["max_connections"] = 10
                        merged.update(kwargs or {})
                        new_client = _redis.Redis(**merged)
                    _redis_client_singleton = new_client
                    _redis_client_singleton_kwargs = dict(kwargs)

            return _redis_client_singleton
        except Exception as e:
            logger.exception("Redis 클라이언트 생성 실패: %s", e)
            return None

    # UI 액션 핸들러 (스레드 사용)
    def refresh(self) -> None:
        self.labelStatus.setText("상태: 큐 조회 중...")
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        client = self._get_redis_client_sync()
        if client is None:
            self._set_status("Redis 연결 불가")
            return
        try:
            raw = client.zrange("gap_fill_queue", 0, -1, withscores=True)
            rows = []
            for member, score in raw:
                try:
                    obj = json.loads(member)
                except Exception:
                    try:
                        obj = json.loads(member)
                    except Exception:
                        obj = {"raw": str(member)}
                rows.append({
                    "member": member,
                    "score": score,
                    "symbol": obj.get("symbol") or obj.get("market") or "",
                    "timeframe": obj.get("timeframe") or obj.get("tf") or "",
                    "gap_seconds": obj.get("gap_seconds") or "",
                    "enqueued_at": obj.get("enqueued_at") or "",
                    "payload": obj,
                })
            self._rows = rows[::-1]
            self._populate_table()
            self._set_status(f"조회 완료: {len(rows)}건")
        except Exception as e:
            logger.exception("Gap 큐 조회 실패: %s", e)
            self._set_status(f"조회 실패: {e}")

    def _populate_table(self) -> None:
        self.table.setRowCount(0)
        for r_idx, row in enumerate(self._rows):
            self.table.insertRow(r_idx)
            self.table.setItem(r_idx, 0, QTableWidgetItem(str(row.get("symbol"))))
            self.table.setItem(r_idx, 1, QTableWidgetItem(str(row.get("timeframe"))))
            self.table.setItem(r_idx, 2, QTableWidgetItem(str(row.get("gap_seconds"))))
            self.table.setItem(r_idx, 3, QTableWidgetItem(str(row.get("enqueued_at"))))

    def _set_status(self, txt: str) -> None:
        self.labelStatus.setText(f"상태: {txt}")

    def _selected_members(self) -> List[str]:
        sels = self.table.selectionModel().selectedRows()
        members = []
        for idx in sels:
            r = idx.row()
            if 0 <= r < len(self._rows):
                members.append(self._rows[r]["member"])
        return members

    def remove_selected(self) -> None:
        members = self._selected_members()
        if not members:
            QMessageBox.information(self, "선택 필요", "삭제할 항목을 선택하세요.")
            return
        confirm = QMessageBox.question(self, "확인", f"{len(members)}개 항목을 큐에서 삭제하시겠습니까?")
        if confirm != QMessageBox.Yes:
            return
        self.labelStatus.setText("상태: 삭제 중...")
        threading.Thread(target=self._remove_worker, args=(members,), daemon=True).start()

    def _remove_worker(self, members: List[str]) -> None:
        client = self._get_redis_client_sync()
        if client is None:
            self._set_status("Redis 연결 불가")
            return
        try:
            client.zrem("gap_fill_queue", *members)
            self._set_status(f"삭제 완료: {len(members)}개")
            self.refresh()
        except Exception as e:
            logger.exception("Gap 항목 삭제 실패: %s", e)
            self._set_status(f"삭제 실패: {e}")

    def dequeue_selected(self) -> None:
        sels = self.table.selectionModel().selectedRows()
        if not sels:
            QMessageBox.information(self, "선택 필요", "큐에서 꺼낼 항목을 선택하세요.")
            return
        confirm = QMessageBox.question(self, "확인", f"{len(sels)}개 항목을 큐에서 꺼냅니다 (관리자 처리용). 괜찮습니까?")
        if confirm != QMessageBox.Yes:
            return
        threading.Thread(target=self._dequeue_worker, args=(sels,), daemon=True).start()

    def _dequeue_worker(self, sels) -> None:
        client = self._get_redis_client_sync()
        if client is None:
            self._set_status("Redis 연결 불가")
            return
        try:
            popped = []
            for idx in sels:
                r = idx.row()
                if 0 <= r < len(self._rows):
                    member = self._rows[r]["member"]
                    try:
                        removed = client.zrem("gap_fill_queue", member)
                        if removed:
                            popped.append(member)
                    except Exception:
                        try:
                            client.zrem("gap_fill_queue", member)
                            popped.append(member)
                        except Exception:
                            logger.exception("개별 pop 실패(무시)")
            self._set_status(f"큐에서 제거 완료: {len(popped)}개 (관리자 처리 필요)")
            self.refresh()
        except Exception as e:
            logger.exception("큐 팝 실패: %s", e)
            self._set_status(f"큐 팝 실패: {e}")

    def export_csv(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "내보내기", "내보낼 항목이 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Gap 큐 CSV로 저장", "gap_queue.csv", "CSV Files (*.csv)")
        if not path:
            return
        try:
            import csv as _csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = _csv.writer(f)
                writer.writerow(["symbol", "timeframe", "gap_seconds", "enqueued_at", "raw_payload"])
                for row in self._rows:
                    writer.writerow([
                        row.get("symbol"),
                        row.get("timeframe"),
                        row.get("gap_seconds"),
                        row.get("enqueued_at"),
                        json.dumps(row.get("payload", {}), ensure_ascii=False),
                    ])
            QMessageBox.information(self, "내보내기", f"CSV 저장 완료: {path}")
            self._set_status(f"CSV 저장: {Path(path).name}")
        except Exception as e:
            logger.exception("CSV 저장 실패: %s", e)
            QMessageBox.warning(self, "오류", f"CSV 저장 실패: {e}")