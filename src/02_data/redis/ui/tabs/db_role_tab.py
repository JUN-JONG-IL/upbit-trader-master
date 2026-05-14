# -*- coding: utf-8 -*-
"""Redis 역할 안내 탭 (정적 정보 표시, DB 연결 불필요)

역할:
- Redis의 플랫폼 내 역할, 저장 데이터, 특화 기능, 활용 방안을 표시
- DB 연결 없이 정적 정보만 표시하므로 start_updates()/stop_updates()는 no-op
"""
from __future__ import annotations

import os
import logging

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "db_role_tab.ui")


if _HAS_QT:
    class DbRoleTab(QWidget):
        """DB 역할 안내 탭.

        Redis의 역할, 저장 데이터, 특화 기능, 활용 방안을 정적으로 표시합니다.
        DB 연결이 불필요하며 start_updates()/stop_updates()는 no-op입니다.
        """

        def __init__(self, conn_params=None, parent=None):
            super().__init__(parent)
            # conn_params는 인터페이스 통일을 위해 받지만 사용하지 않음
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[DbRoleTab] UI 파일 로드 실패: %s", exc)
                self._build_fallback_ui()

        # ------------------------------------------------------------------
        # 생명 주기 (no-op — DB 연결 불필요)
        # ------------------------------------------------------------------

        def start_updates(self, interval_ms: int = 0) -> None:
            """인터페이스 통일용 no-op (DB 연결 불필요)."""

        def stop_updates(self) -> None:
            """인터페이스 통일용 no-op."""

        # ------------------------------------------------------------------
        # 폴백 UI (db_role_tab.ui 로드 실패 시)
        # ------------------------------------------------------------------

        def _build_fallback_ui(self) -> None:
            """UI 파일 로드 실패 시 최소한의 정보를 표시하는 폴백 레이아웃."""
            from PyQt5.QtWidgets import QVBoxLayout, QLabel, QScrollArea, QWidget
            from PyQt5.QtCore import Qt

            layout = QVBoxLayout(self)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            content = QWidget()
            content_layout = QVBoxLayout(content)

            title = QLabel("🔴 Redis — Hot Tier 실시간 캐시 & 메시지 버스")
            title.setStyleSheet(
                "font-size: 14pt; font-weight: bold; "
                "color: #FFFFFF; background-color: #DC2626; padding: 12px; border-radius: 6px;"
            )
            content_layout.addWidget(title)

            body_text = (
                "<b>📌 역할</b><br>"
                "Redis는 인메모리 데이터 구조 저장소입니다.<br>"
                "포트: 58530 | 응답: &lt; 2ms | TTL: 틱 5분 / 캔들 1시간<br><br>"

                "<b>💾 저장 데이터</b><br>"
                "• candle:{symbol}:{timeframe} — 실시간 캔들 캐시 (TTL: 1시간)<br>"
                "• candle:updates (Pub/Sub) — 캔들 갱신 채널<br>"
                "• gap:queue (ZSET) — 누락 데이터 백필 우선순위 큐<br>"
                "• gap:alerts (Pub/Sub) — Gap 감지 알림 채널<br>"
                "• feature:{symbol} — AI Feature Store (TTL: 1시간)<br>"
                "• orderbook:updates (Pub/Sub) — 호가창 갱신 채널<br><br>"

                "<b>⚙️ 특화 기능</b><br>"
                "• Pub/Sub 메시징 (&lt; 2ms)<br>"
                "• ZSET 우선순위 큐 (Gap 백필)<br>"
                "• TTL 기반 자동 만료<br>"
                "• Streams (L1 Cache, 최근 2,000개)<br><br>"

                "<b>🚀 활용 방안</b><br>"
                "차트 실시간 갱신 · Gap Detection · AI Feature Serving · L1 캐시 · 실시간 알림"
            )
            body = QLabel(body_text)
            body.setWordWrap(True)
            body.setAlignment(Qt.AlignTop)
            body.setStyleSheet("font-size: 9pt; color: #1E293B; padding: 12px;")
            content_layout.addWidget(body)
            content_layout.addStretch()

            scroll.setWidget(content)
            layout.addWidget(scroll)

else:
    class DbRoleTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 폴백 스텁."""
        def __init__(self, conn_params=None, parent=None): pass
        def start_updates(self, interval_ms: int = 0) -> None: pass
        def stop_updates(self) -> None: pass
