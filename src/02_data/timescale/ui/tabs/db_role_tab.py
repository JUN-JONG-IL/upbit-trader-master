# -*- coding: utf-8 -*-
"""TimescaleDB 역할 안내 탭 (정적 정보 표시, DB 연결 불필요)

역할:
- TimescaleDB의 플랫폼 내 역할, 저장 데이터, 특화 기능, 활용 방안을 표시
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

        TimescaleDB의 역할, 저장 데이터, 특화 기능, 활용 방안을 정적으로 표시합니다.
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

            title = QLabel("🗄️ TimescaleDB — Warm Tier 중간 저장소")
            title.setStyleSheet(
                "font-size: 14pt; font-weight: bold; "
                "color: #FFFFFF; background-color: #2563EB; padding: 12px; border-radius: 6px;"
            )
            content_layout.addWidget(title)

            body_text = (
                "<b>📌 역할</b><br>"
                "TimescaleDB는 PostgreSQL 기반 시계열 데이터베이스 확장입니다.<br>"
                "포트: 58529 | DB: upbit_trades | 보존: 3개월(Hot) / 1년(Warm)<br><br>"

                "<b>💾 저장 데이터</b><br>"
                "• candles_1m / candles_5m / candles_1h — OHLCV 캔들 데이터<br>"
                "• market_ticks — 실시간 체결 데이터<br>"
                "• orderbook_snapshots — 호가 스냅샷<br>"
                "• gap_queue — 누락 데이터 백필 큐<br>"
                "• technical_indicators — 기술적 지표<br><br>"

                "<b>⚙️ 특화 기능</b><br>"
                "• Hypertable (시간 파티셔닝)<br>"
                "• 압축 (목표 90%)<br>"
                "• 연속 집계 CAGG: 1m→5m→1h→1d<br>"
                "• 보존 정책 (Hot/Warm/Cold)<br><br>"

                "<b>🚀 활용 방안</b><br>"
                "차트 렌더링 · AI/ML 피처 · Gap 백필 자동화 · 백테스팅<br>"
                "암호화폐(업비트·빗썸·바이낸스) / KRX / NYSE·NASDAQ / CME·CBOE"
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
