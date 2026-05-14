# -*- coding: utf-8 -*-
"""
Gap Monitor Dialog (愿由ъ옄??
- Redis ?대씪?댁뼵??import瑜??곷? import濡??쒕룄?섍퀬 ?ㅽ뙣?섎㈃ ?뚯씪寃쎈줈濡??숈쟻 濡쒕뱶 ?대갚???ъ슜?⑸땲??
- 釉붾줈??Redis ?몄텧? 諛깃렇?쇱슫???ㅻ젅?쒖뿉???ㅽ뻾?섏뿬 UI 李⑤떒??諛⑹??⑸땲??
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

# 紐⑤뱢 ?덈꺼 ?깃???Redis ?대씪?댁뼵??(?ы듃 怨좉컝 諛⑹?: ?곌껐 ? ?ъ궗??
_redis_client_singleton = None
_redis_client_singleton_kwargs: Dict[str, Any] = {}
_redis_client_lock = threading.Lock()

# RedisClient 濡쒕뱶: ?곷? import ?쒕룄 -> ?뚯씪寃쎈줈 ?대갚
RedisClient = None
try:
    # ?곷? import: package 援ъ“?먯꽌 '...redis.core.client'濡??묎렐 (ui -> pipeline -> data_01)
    from ...redis.core.client import RedisClient  # type: ignore
except Exception:
    try:
        # ?고??꾩뿉???⑦궎吏 寃쎈줈濡?濡쒕뱶 ?쒕룄 (?섍꼍???곕씪 ?숈옉)
        mod = importlib.import_module("src.data_01.redis.core.client")
        RedisClient = getattr(mod, "RedisClient", None)
    except Exception:
        # ?뚯씪寃쎈줈 ?대갚: src/data_01/redis/core/client.py
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
            logger.debug("RedisClient ?뚯씪寃쎈줈 濡쒕뱶 ?ㅽ뙣", exc_info=True)

class GapMonitorDialog(QDialog):
    """
    Gap ???곹깭瑜?蹂댁뿬二쇨퀬 愿由ы븯??媛꾨떒???ㅼ씠?쇰줈洹?
    - redis_kwargs: redis.Redis ?앹꽦?먯뿉 ?꾨떖???몄옄(?? host, port, db, password)
    """

    def __init__(self, parent=None, redis_kwargs: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gap Monitor")
        self.resize(900, 480)

        main = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Gap ??(gap_fill_queue) 紐⑤땲??))
        header_layout.addStretch()

        self.btnRefresh = QPushButton("?덈줈怨좎묠")
        self.btnDequeue = QPushButton("?좏깮 ?쒓굅 (ZREM)")
        self.btnRemove = QPushButton("?좏깮 ??젣 (ZREM)")
        self.btnExport = QPushButton("CSV ?대낫?닿린")

        header_layout.addWidget(self.btnRefresh)
        header_layout.addWidget(self.btnDequeue)
        header_layout.addWidget(self.btnRemove)
        header_layout.addWidget(self.btnExport)

        main.addLayout(header_layout)

        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["?щ낵", "??꾪봽?덉엫", "gap_seconds", "enqueued_at"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        main.addWidget(self.table)

        self.labelStatus = QLabel("?곹깭: 以鍮꾨맖")
        main.addWidget(self.labelStatus)

        self._redis_kwargs = redis_kwargs or {}
        self.btnRefresh.clicked.connect(self.refresh)
        self.btnDequeue.clicked.connect(self.dequeue_selected)
        self.btnRemove.clicked.connect(self.remove_selected)
        self.btnExport.clicked.connect(self.export_csv)

        self._rows: List[Dict[str, Any]] = []
        self.refresh()

    # Redis ?대씪?댁뼵??諛섑솚 (?깃??????ы듃 怨좉컝 諛⑹?)
    def _get_redis_client_sync(self):
        global _redis_client_singleton, _redis_client_singleton_kwargs
        try:
            kwargs = self._redis_kwargs

            with _redis_client_lock:
                # kwargs 蹂寃????ъ깮??
                if _redis_client_singleton is None or _redis_client_singleton_kwargs != kwargs:
                    # ?곗꽑 ?덊룷??RedisClient ?섑띁 ?ъ슜 ?쒕룄
                    if RedisClient is not None:
                        new_client = RedisClient(**kwargs).client if kwargs else RedisClient().client
                    else:
                        import redis as _redis
                        # max_connections 湲곕낯媛??ㅼ젙 (?ъ슜?먭? 吏?뺥븯吏 ?딆? 寃쎌슦?먮쭔)
                        merged = {"decode_responses": True}
                        if "max_connections" not in (kwargs or {}):
                            merged["max_connections"] = 10
                        merged.update(kwargs or {})
                        new_client = _redis.Redis(**merged)
                    _redis_client_singleton = new_client
                    _redis_client_singleton_kwargs = dict(kwargs)

            return _redis_client_singleton
        except Exception as e:
            logger.exception("Redis ?대씪?댁뼵???앹꽦 ?ㅽ뙣: %s", e)
            return None

    # UI ?≪뀡 ?몃뱾??(?ㅻ젅???ъ슜)
    def refresh(self) -> None:
        self.labelStatus.setText("?곹깭: ??議고쉶 以?..")
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        client = self._get_redis_client_sync()
        if client is None:
            self._set_status("Redis ?곌껐 遺덇?")
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
            self._set_status(f"議고쉶 ?꾨즺: {len(rows)}嫄?)
        except Exception as e:
            logger.exception("Gap ??議고쉶 ?ㅽ뙣: %s", e)
            self._set_status(f"議고쉶 ?ㅽ뙣: {e}")

    def _populate_table(self) -> None:
        self.table.setRowCount(0)
        for r_idx, row in enumerate(self._rows):
            self.table.insertRow(r_idx)
            self.table.setItem(r_idx, 0, QTableWidgetItem(str(row.get("symbol"))))
            self.table.setItem(r_idx, 1, QTableWidgetItem(str(row.get("timeframe"))))
            self.table.setItem(r_idx, 2, QTableWidgetItem(str(row.get("gap_seconds"))))
            self.table.setItem(r_idx, 3, QTableWidgetItem(str(row.get("enqueued_at"))))

    def _set_status(self, txt: str) -> None:
        self.labelStatus.setText(f"?곹깭: {txt}")

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
            QMessageBox.information(self, "?좏깮 ?꾩슂", "??젣????ぉ???좏깮?섏꽭??")
            return
        confirm = QMessageBox.question(self, "?뺤씤", f"{len(members)}媛???ぉ???먯뿉????젣?섏떆寃좎뒿?덇퉴?")
        if confirm != QMessageBox.Yes:
            return
        self.labelStatus.setText("?곹깭: ??젣 以?..")
        threading.Thread(target=self._remove_worker, args=(members,), daemon=True).start()

    def _remove_worker(self, members: List[str]) -> None:
        client = self._get_redis_client_sync()
        if client is None:
            self._set_status("Redis ?곌껐 遺덇?")
            return
        try:
            client.zrem("gap_fill_queue", *members)
            self._set_status(f"??젣 ?꾨즺: {len(members)}媛?)
            self.refresh()
        except Exception as e:
            logger.exception("Gap ??ぉ ??젣 ?ㅽ뙣: %s", e)
            self._set_status(f"??젣 ?ㅽ뙣: {e}")

    def dequeue_selected(self) -> None:
        sels = self.table.selectionModel().selectedRows()
        if not sels:
            QMessageBox.information(self, "?좏깮 ?꾩슂", "?먯뿉??爰쇰궪 ??ぉ???좏깮?섏꽭??")
            return
        confirm = QMessageBox.question(self, "?뺤씤", f"{len(sels)}媛???ぉ???먯뿉??爰쇰깄?덈떎 (愿由ъ옄 泥섎━??. 愿쒖갖?듬땲源?")
        if confirm != QMessageBox.Yes:
            return
        threading.Thread(target=self._dequeue_worker, args=(sels,), daemon=True).start()

    def _dequeue_worker(self, sels) -> None:
        client = self._get_redis_client_sync()
        if client is None:
            self._set_status("Redis ?곌껐 遺덇?")
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
                            logger.exception("媛쒕퀎 pop ?ㅽ뙣(臾댁떆)")
            self._set_status(f"?먯뿉???쒓굅 ?꾨즺: {len(popped)}媛?(愿由ъ옄 泥섎━ ?꾩슂)")
            self.refresh()
        except Exception as e:
            logger.exception("?????ㅽ뙣: %s", e)
            self._set_status(f"?????ㅽ뙣: {e}")

    def export_csv(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "?대낫?닿린", "?대낫????ぉ???놁뒿?덈떎.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Gap ??CSV濡????, "gap_queue.csv", "CSV Files (*.csv)")
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
            QMessageBox.information(self, "?대낫?닿린", f"CSV ????꾨즺: {path}")
            self._set_status(f"CSV ??? {Path(path).name}")
        except Exception as e:
            logger.exception("CSV ????ㅽ뙣: %s", e)
            QMessageBox.warning(self, "?ㅻ쪟", f"CSV ????ㅽ뙣: {e}")
