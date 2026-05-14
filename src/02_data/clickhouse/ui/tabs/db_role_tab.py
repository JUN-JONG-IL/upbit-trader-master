# -*- coding: utf-8 -*-
"""ClickHouse 역할 안내 탭 (정적 정보 표시, DB 연결 불필요)

역할:
- ClickHouse의 플랫폼 내 역할, 저장 데이터, 특화 기능, 활용 방안을 표시
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

        ClickHouse의 역할, 저장 데이터, 특화 기능, 활용 방안을 정적으로 표시합니다.
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

            title = QLabel("🔵 ClickHouse — Cold Tier 장기 분석 저장소")
            title.setStyleSheet(
                "font-size: 14pt; font-weight: bold; "
                "color: #FFFFFF; background-color: #1E40AF; padding: 12px; border-radius: 6px;"
            )
            content_layout.addWidget(title)

            body_text = (
                "<b>📌 역할</b><br>"
                "ClickHouse는 초고성능 컬럼 지향 OLAP 데이터베이스입니다.<br>"
                "포트: 8123 | DB: upbit_trader | 데이터 보존: 5년<br><br>"

                "<b>💾 저장 데이터</b><br>"
                "• candles_1m / candles_5m / candles_1h / candles_1d — 장기 OHLCV 캔들<br>"
                "• market_ticks — 체결 데이터 장기 보관<br>"
                "• orderbook_aggregates — 호가 집계 데이터<br>"
                "• backtest_results — 백테스팅 결과 저장소<br>"
                "• technical_indicators_archive — 장기 기술지표 아카이브<br><br>"

                "<b>⚙️ 특화 기능</b><br>"
                "• MergeTree / ReplicatedMergeTree<br>"
                "• Kafka Engine — 실시간 자동 이관<br>"
                "• 컬럼 지향 압축 (Snappy/ZSTD)<br>"
                "• 매일 새벽 3시 배치 이관<br><br>"

                "<b>🚀 활용 방안</b><br>"
                "백테스팅 · 장기 추세 분석 · AI/ML 학습 데이터셋 · OLAP 리포팅"
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
