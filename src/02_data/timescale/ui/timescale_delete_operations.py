# -*- coding: utf-8 -*-
"""
timescale_delete_operations.py — TimescaleDB 데이터 삭제 로직 (SRP 분리)

TimescaleDeleteMixin 클래스를 제공합니다.
TimescaleSettingsDialog 에서 다중 상속으로 사용합니다.

모든 삭제 작업은:
  1. QMessageBox.warning 확인 팝업 필수
  2. QThread Worker 내에서만 실행 (threading.Thread 금지)
  3. 삭제 완료 후 건수 레이블 자동 갱신
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QThread, pyqtSignal, QMetaObject, Qt, Q_ARG
    from PyQt5.QtWidgets import QMessageBox, QInputDialog, QLineEdit
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

try:
    from .tabs.db_worker import build_connect_kwargs
except Exception:
    try:
        from tabs.db_worker import build_connect_kwargs  # type: ignore[no-redef]
    except Exception:
        def build_connect_kwargs(p: dict, connect_timeout: int = 5) -> dict:  # type: ignore[misc]
            return {
                "host": p.get("host", "127.0.0.1"),
                "port": int(p.get("port", 58529)),
                "database": p.get("database") or p.get("db") or "upbit_trader",
                "user": p.get("user", "postgres"),
                "password": p.get("password") or p.get("pass", ""),
                "connect_timeout": connect_timeout,
            }


if _HAS_QT:
    class _DeleteWorker(QThread):
        """백그라운드 DELETE 실행 Worker (QThread)."""

        finished = pyqtSignal(str, str, int)  # table_name, label_name, rowcount
        error    = pyqtSignal(str, str, str)  # table_name, label_name, error_msg

        def __init__(self, conn_params: dict, sql: str, table_name: str,
                     label_name: str, params: tuple = (), parent=None) -> None:
            super().__init__(parent)
            self._conn_params = conn_params or {}
            self._sql         = sql
            self._table_name  = table_name
            self._label_name  = label_name
            self._params      = params

        def run(self) -> None:
            try:
                import psycopg2
                kwargs = build_connect_kwargs(self._conn_params)
                conn = psycopg2.connect(**kwargs)
                conn.autocommit = False
                try:
                    with conn.cursor() as cur:
                        cur.execute(self._sql, self._params)
                        rowcount = cur.rowcount if cur.rowcount >= 0 else 0
                    conn.commit()
                    self.finished.emit(self._table_name, self._label_name, rowcount)
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception as exc:
                logger.error("[_DeleteWorker] 삭제 실패 (%s): %s", self._table_name, exc)
                self.error.emit(self._table_name, self._label_name, str(exc))


    class _CountWorker(QThread):
        """백그라운드 COUNT 조회 Worker (QThread)."""

        result = pyqtSignal(str, int)  # label_name, count

        def __init__(self, conn_params: dict, table_name: str,
                     label_name: str, parent=None) -> None:
            super().__init__(parent)
            self._conn_params = conn_params or {}
            self._table_name  = table_name
            self._label_name  = label_name

        def run(self) -> None:
            try:
                import psycopg2
                from psycopg2 import sql as pgsql
                kwargs = build_connect_kwargs(self._conn_params)
                conn = psycopg2.connect(**kwargs)
                try:
                    with conn.cursor() as cur:
                        stmt = pgsql.SQL("SELECT COUNT(*) FROM {}").format(
                            pgsql.Identifier(self._table_name)
                        )
                        cur.execute(stmt)
                        cnt = cur.fetchone()[0]
                    self.result.emit(self._label_name, cnt)
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[_CountWorker] 건수 조회 실패 (%s): %s", self._table_name, exc)
                self.result.emit(self._label_name, -1)


class TimescaleDeleteMixin:
    """TimescaleDB 데이터 삭제 기능 믹스인.

    사용법:
        class TimescaleSettingsDialog(QDialog, TimescaleDeleteMixin):
            def __init__(self, ...):
                ...
                self._bind_delete_signals()
                self._refresh_delete_counts()
    """

    # 허용된 테이블 이름 화이트리스트 (SQL injection 방지)
    _ALLOWED_TABLES = frozenset({"candles", "staging_candles", "isolated_candles"})

    # ------------------------------------------------------------------
    # 테이블명 검증
    # ------------------------------------------------------------------

    def _validate_table_name(self, table_name: str) -> bool:
        """테이블 이름이 허용 목록에 있는지 검증합니다."""
        return table_name in self._ALLOWED_TABLES

    # ------------------------------------------------------------------
    # 시그널 바인딩 (독립 메서드)
    # ------------------------------------------------------------------

    def _bind_delete_signals(self) -> None:
        """삭제 탭 버튼들을 슬롯에 연결합니다."""
        btn_map = {
            "btn_delete_candles_all":       self._on_delete_candles_all,
            "btn_delete_candles_by_symbol": self._on_delete_candles_by_symbol,
            "btn_delete_staging_all":       self._on_delete_staging_all,
            "btn_delete_isolated_all":      self._on_delete_isolated_all,
            "btn_delete_symbol_data":       self._on_delete_symbol_data,
        }
        for btn_name, slot in btn_map.items():
            btn = getattr(self, btn_name, None)
            if btn is not None:
                try:
                    btn.clicked.connect(slot)
                except Exception as exc:
                    logger.debug("[TimescaleDeleteMixin] 버튼 연결 실패 (%s): %s", btn_name, exc)

    # ------------------------------------------------------------------
    # 삭제 핸들러
    # ------------------------------------------------------------------

    def _on_delete_candles_all(self) -> None:
        """candles 테이블 전체 삭제"""
        if not self._confirm_delete("candles 테이블", "모든 캔들 데이터"):
            return
        self._start_delete_worker("candles", "labelCandlesCount")

    def _on_delete_candles_by_symbol(self) -> None:
        """candles 테이블 심볼별 삭제 (입력 다이얼로그)"""
        symbol = self._ask_symbol()
        if not symbol:
            return
        if not self._confirm_delete(f"candles[{symbol}]", f"{symbol} 캔들 데이터"):
            return
        self._start_delete_worker("candles", "labelCandlesCount", symbol=symbol)

    def _on_delete_staging_all(self) -> None:
        """staging_candles 테이블 전체 삭제"""
        if not self._confirm_delete("staging_candles 테이블", "모든 스테이징 캔들 데이터"):
            return
        self._start_delete_worker("staging_candles", "labelStagingCount")

    def _on_delete_isolated_all(self) -> None:
        """isolated_candles 테이블 전체 삭제"""
        if not self._confirm_delete("isolated_candles 테이블", "모든 격리 캔들 데이터"):
            return
        self._start_delete_worker("isolated_candles", "labelIsolatedCount")

    def _on_delete_symbol_data(self) -> None:
        """입력된 심볼의 모든 테이블 데이터 삭제"""
        edit = getattr(self, "edit_delete_symbol", None)
        symbol = edit.text().strip() if edit is not None else ""
        if not symbol:
            if _HAS_QT:
                QMessageBox.warning(self, "입력 오류", "삭제할 심볼을 입력하세요.")
            return
        if not self._confirm_delete(f"심볼 {symbol}", f"{symbol} 의 모든 테이블 데이터"):
            return
        for tbl, lbl in [
            ("candles",          "labelCandlesCount"),
            ("staging_candles",  "labelStagingCount"),
            ("isolated_candles", "labelIsolatedCount"),
        ]:
            self._start_delete_worker(tbl, lbl, symbol=symbol)

    # ------------------------------------------------------------------
    # QThread Worker 시작
    # ------------------------------------------------------------------

    def _start_delete_worker(
        self,
        table_name: str,
        label_name: str,
        symbol: str = "",
    ) -> None:
        """psycopg2.sql.Identifier로 SQL을 안전하게 구성 후 QThread Worker를 실행합니다."""
        if not _HAS_QT:
            logger.warning("[TimescaleDeleteMixin] PyQt5 미설치 — 삭제 불가")
            return
        if not self._validate_table_name(table_name):
            logger.warning("[TimescaleDeleteMixin] 허용되지 않는 테이블명: %s", table_name)
            return
        try:
            from psycopg2 import sql as pgsql
        except ImportError:
            logger.error("[TimescaleDeleteMixin] psycopg2 미설치")
            return

        if symbol:
            sql    = pgsql.SQL("DELETE FROM {} WHERE symbol = %s").format(
                pgsql.Identifier(table_name)
            )
            params = (symbol,)
        else:
            sql    = pgsql.SQL("DELETE FROM {}").format(pgsql.Identifier(table_name))
            params = ()

        conn_params = (
            getattr(self, "_conn_params", None) or
            getattr(self, "_config", {})
        )
        worker = _DeleteWorker(conn_params, sql, table_name, label_name, params)
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        # Worker 레퍼런스 보관 (GC 방지)
        if not hasattr(self, "_delete_workers"):
            object.__setattr__(self, "_delete_workers", [])
        self._delete_workers.append(worker)
        worker.start()

    def _on_worker_finished(self, table_name: str, label_name: str, rowcount: int) -> None:
        logger.info("[TimescaleDeleteMixin] 삭제 완료: %s %d건", table_name, rowcount)
        self._refresh_single_count(table_name, label_name)

    def _on_worker_error(self, table_name: str, label_name: str, msg: str) -> None:
        logger.error("[TimescaleDeleteMixin] 삭제 실패 (%s): %s", table_name, msg)
        self._set_label_text(label_name, "삭제 실패")

    # ------------------------------------------------------------------
    # 건수 갱신
    # ------------------------------------------------------------------

    def _refresh_delete_counts(self) -> None:
        """삭제 탭 건수 레이블을 백그라운드에서 갱신합니다."""
        for tbl, lbl in [
            ("candles",          "labelCandlesCount"),
            ("staging_candles",  "labelStagingCount"),
            ("isolated_candles", "labelIsolatedCount"),
        ]:
            self._refresh_single_count(tbl, lbl)

    def _refresh_single_count(self, table_name: str, label_name: str) -> None:
        """단일 테이블 건수를 QThread Worker로 갱신합니다."""
        if not self._validate_table_name(table_name):
            logger.warning("[TimescaleDeleteMixin] 허용되지 않는 테이블명: %s", table_name)
            return
        if not _HAS_QT:
            return
        conn_params = (
            getattr(self, "_conn_params", None) or
            getattr(self, "_config", {})
        )
        worker = _CountWorker(conn_params, table_name, label_name)
        worker.result.connect(self._on_count_result)
        if not hasattr(self, "_delete_workers"):
            object.__setattr__(self, "_delete_workers", [])
        self._delete_workers.append(worker)
        worker.start()

    def _on_count_result(self, label_name: str, count: int) -> None:
        if count >= 0:
            self._set_label_text(label_name, f"건수: {count:,}")
        else:
            self._set_label_text(label_name, "건수: 조회 실패")

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    def _confirm_delete(self, target: str, description: str) -> bool:
        """삭제 전 확인 팝업을 표시합니다."""
        if not _HAS_QT:
            return False
        ret = QMessageBox.warning(
            self,
            "⚠️ 삭제 확인",
            (
                f"정말로 [{target}] 의 [{description}] 을 삭제하시겠습니까?\n\n"
                "삭제된 데이터는 복구할 수 없습니다!"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return ret == QMessageBox.Yes

    def _ask_symbol(self) -> str:
        """심볼 입력 다이얼로그를 표시합니다."""
        if not _HAS_QT:
            return ""
        symbol, ok = QInputDialog.getText(
            self,
            "심볼 입력",
            "삭제할 심볼을 입력하세요 (예: KRW-BTC):",
            QLineEdit.Normal,
            "",
        )
        return symbol.strip() if ok else ""

    def _set_label_text(self, label_name: str, text: str) -> None:
        """레이블 텍스트를 GUI 스레드에서 안전하게 설정합니다."""
        try:
            lbl = getattr(self, label_name, None)
            if lbl is None:
                return
            if not _HAS_QT:
                return
            try:
                QMetaObject.invokeMethod(
                    lbl,
                    "setText",
                    Qt.QueuedConnection,
                    Q_ARG(str, text),
                )
            except Exception:
                try:
                    lbl.setText(text)
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("[TimescaleDeleteMixin] 레이블 갱신 실패 (%s): %s", label_name, exc)
