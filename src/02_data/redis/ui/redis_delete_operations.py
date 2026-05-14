# -*- coding: utf-8 -*-
"""
redis_delete_operations.py — Redis 데이터 삭제 로직 (SRP 분리)

RedisDeleteMixin 클래스를 제공합니다.
RedisSettingsDialog 에서 다중 상속으로 사용합니다.

FLUSHDB 는 2단계 확인 (1차: 경고 팝업, 2차: "FLUSH" 문자 입력 확인)
모든 삭제 작업은 백그라운드 스레드에서 실행됩니다.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QMessageBox, QInputDialog, QLineEdit
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class RedisDeleteMixin:
    """Redis 데이터 삭제 기능 믹스인.

    사용법:
        class RedisSettingsDialog(QDialog, RedisDeleteMixin):
            def __init__(self, ...):
                ...
                self._bind_redis_delete_signals()
                self._refresh_redis_key_count()
    """

    # ------------------------------------------------------------------
    # 시그널 바인딩
    # ------------------------------------------------------------------

    def _bind_redis_delete_signals(self) -> None:
        """삭제 탭 버튼들을 슬롯에 연결합니다."""
        btn_map = {
            "btn_flush_all": self._on_flush_all,
            "btn_delete_candles_keys": self._on_delete_candles_keys,
            "btn_delete_ticker_keys": self._on_delete_ticker_keys,
            "btn_delete_gap_queue": self._on_delete_gap_queue,
            "btn_refresh_redis_keys": self._refresh_redis_key_count,
        }
        for btn_name, slot in btn_map.items():
            btn = getattr(self, btn_name, None)
            if btn is not None:
                btn.clicked.connect(slot)

    # ------------------------------------------------------------------
    # 삭제 핸들러
    # ------------------------------------------------------------------

    def _on_flush_all(self) -> None:
        """Redis 전체 삭제 (FLUSHDB) — 2단계 확인 필수"""
        # 1단계: 경고 팝업
        ret = QMessageBox.warning(
            self,
            "⚠️ Redis 전체 삭제 경고",
            "Redis DB의 모든 키를 삭제합니다!\n\n이 작업은 취소할 수 없습니다.\n정말로 계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return

        # 2단계: "FLUSH" 텍스트 입력 확인
        text, ok = QInputDialog.getText(
            self,
            "최종 확인",
            "모든 데이터가 삭제됩니다.\n확인하려면 'FLUSH' 를 입력하세요:",
            QLineEdit.Normal,
            "",
        )
        if not ok or text.strip() != "FLUSH":
            QMessageBox.information(self, "취소", "삭제가 취소되었습니다.")
            return

        threading.Thread(target=self._exec_flushdb, daemon=True).start()

    def _on_delete_candles_keys(self) -> None:
        """candles:* 패턴 키 삭제"""
        ret = QMessageBox.warning(
            self,
            "⚠️ 삭제 확인",
            "'candles:*' 패턴의 모든 키를 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        threading.Thread(
            target=self._exec_delete_pattern,
            args=("candles:*",),
            daemon=True,
        ).start()

    def _on_delete_ticker_keys(self) -> None:
        """ticker:* 패턴 키 삭제"""
        ret = QMessageBox.warning(
            self,
            "⚠️ 삭제 확인",
            "'ticker:*' 패턴의 모든 키를 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        threading.Thread(
            target=self._exec_delete_pattern,
            args=("ticker:*",),
            daemon=True,
        ).start()

    def _on_delete_gap_queue(self) -> None:
        """Gap Fill 큐 키 삭제"""
        ret = QMessageBox.warning(
            self,
            "⚠️ 삭제 확인",
            "Gap Fill 큐(gap_fill_queue)를 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        threading.Thread(
            target=self._exec_delete_key,
            args=("gap_fill_queue",),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Redis 실행 (백그라운드)
    # ------------------------------------------------------------------

    def _exec_flushdb(self) -> None:
        """FLUSHDB 실행"""
        try:
            r = self._get_redis_client()
            if r is None:
                return
            r.flushdb()
            logger.info("[RedisDeleteMixin] FLUSHDB 완료")
        except Exception as exc:
            logger.error("[RedisDeleteMixin] FLUSHDB 실패: %s", exc)
        finally:
            self._refresh_redis_key_count()

    def _exec_delete_pattern(self, pattern: str) -> None:
        """패턴에 매칭되는 키 모두 삭제 (SCAN + DEL)"""
        try:
            r = self._get_redis_client()
            if r is None:
                return
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=pattern, count=100)
                if keys:
                    r.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            logger.info("[RedisDeleteMixin] 패턴 '%s' 키 %d개 삭제 완료", pattern, deleted)
        except Exception as exc:
            logger.error("[RedisDeleteMixin] 패턴 삭제 실패 (%s): %s", pattern, exc)
        finally:
            self._refresh_redis_key_count()

    def _exec_delete_key(self, key: str) -> None:
        """단일 키 삭제"""
        try:
            r = self._get_redis_client()
            if r is None:
                return
            r.delete(key)
            logger.info("[RedisDeleteMixin] 키 '%s' 삭제 완료", key)
        except Exception as exc:
            logger.error("[RedisDeleteMixin] 키 삭제 실패 (%s): %s", key, exc)
        finally:
            self._refresh_redis_key_count()

    # ------------------------------------------------------------------
    # 건수 갱신
    # ------------------------------------------------------------------

    def _refresh_redis_key_count(self) -> None:
        """Redis 전체 키 수를 레이블에 표시합니다."""
        threading.Thread(target=self._bg_refresh_key_count, daemon=True).start()

    def _bg_refresh_key_count(self) -> None:
        """백그라운드: Redis DBSIZE 조회"""
        try:
            r = self._get_redis_client()
            if r is None:
                self._set_label_safe("labelRedisKeyCount", "전체 키 수: (연결 없음)")
                return
            count = r.dbsize()
            self._set_label_safe("labelRedisKeyCount", f"전체 키 수: {count:,}")
        except Exception as exc:
            logger.debug("[RedisDeleteMixin] 키 수 조회 실패: %s", exc)
            self._set_label_safe("labelRedisKeyCount", "전체 키 수: 조회 실패")

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    def _set_label_safe(self, label_name: str, text: str) -> None:
        """레이블 텍스트를 스레드 안전하게 설정합니다."""
        try:
            lbl = getattr(self, label_name, None)
            if lbl is None:
                return
            try:
                from PyQt5.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    lbl,
                    "setText",
                    Qt.QueuedConnection,
                    Q_ARG(str, text),
                )
            except Exception:
                lbl.setText(text)
        except Exception as exc:
            logger.debug("[RedisDeleteMixin] 레이블 갱신 실패 (%s): %s", label_name, exc)

    def _get_redis_client(self):
        """Redis 클라이언트를 반환합니다. 실패 시 None."""
        try:
            import redis as redis_mod  # type: ignore[import]
            import os
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                return redis_mod.Redis.from_url(redis_url, socket_connect_timeout=3)
            host = os.getenv("REDIS_HOST", "127.0.0.1")
            port = int(os.getenv("REDIS_PORT", "6379"))
            password = os.getenv("REDIS_PASSWORD") or None
            return redis_mod.Redis(
                host=host,
                port=port,
                password=password,
                socket_connect_timeout=3,
                decode_responses=False,
            )
        except Exception as exc:
            logger.debug("[RedisDeleteMixin] Redis 연결 실패: %s", exc)
            return None
