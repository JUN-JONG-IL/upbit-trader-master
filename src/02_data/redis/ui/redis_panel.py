# -*- coding: utf-8 -*-
"""
Redis 모니터링 패널 (개별 DB UI)

기능:
- 백필 큐(backfill:queue) 크기 표시
- DLQ(backfill:dlq) 크기 표시
- Redis 메모리 사용량 표시
- 1초 주기 자동 갱신 (QTimer + asyncio)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

try:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
    from PyQt5.QtCore import QTimer
    _HAS_QT = True
except Exception:
    _HAS_QT = False


if _HAS_QT:
    class RedisPanel(QWidget):
        """Redis 모니터링 패널 (개별 DB UI)"""

        def __init__(self, redis_client=None, parent=None):
            super().__init__(parent)
            self._redis = redis_client
            self._init_ui()
            self._start_timer()

        def _init_ui(self):
            layout = QVBoxLayout(self)

            # 제목
            title = QLabel("Redis 모니터링")
            title.setStyleSheet("font-size: 16pt; font-weight: bold;")
            layout.addWidget(title)

            # 백필 큐 크기
            self._queue_label = QLabel("백필 큐: 0")
            layout.addWidget(self._queue_label)

            # DLQ 크기
            self._dlq_label = QLabel("DLQ: 0")
            layout.addWidget(self._dlq_label)

            # 메모리 사용량
            self._memory_label = QLabel("메모리: 0 MB")
            self._memory_progress = QProgressBar()
            layout.addWidget(self._memory_label)
            layout.addWidget(self._memory_progress)

        def _start_timer(self):
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._update_ui)
            self._timer.start(1000)  # 1초마다

        def _update_ui(self):
            """UI 데이터 갱신 스케줄"""
            if self._redis is None:
                return
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._update_ui_async())
            except Exception as exc:
                logger.debug("[RedisPanel] UI 업데이트 스케줄 실패: %s", exc)

        async def _update_ui_async(self):
            """비동기 UI 데이터 갱신"""
            try:
                queue_size = await self._redis.zcard("backfill:queue")
                self._queue_label.setText(f"백필 큐: {queue_size}")

                dlq_size = await self._redis.llen("backfill:dlq")
                self._dlq_label.setText(f"DLQ: {dlq_size}")

                info = await self._redis.info("memory")
                used_mb = info.get("used_memory", 0) / 1024 / 1024
                self._memory_label.setText(f"메모리: {used_mb:.1f} MB")
                self._memory_progress.setValue(int(used_mb))
            except Exception as exc:
                logger.error("[RedisPanel] UI 업데이트 실패: %s", exc)

        def stop_refresh(self):
            """타이머 중단"""
            if hasattr(self, "_timer"):
                self._timer.stop()

else:
    class RedisPanel:  # type: ignore
        """PyQt5 미설치 시 폴백 스텁"""

        def __init__(self, *args, **kwargs):
            logger.warning("[RedisPanel] PyQt5 미설치 - 폴백 스텁")

        def stop_refresh(self):
            pass
