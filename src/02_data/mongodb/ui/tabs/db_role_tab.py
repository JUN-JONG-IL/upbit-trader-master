# -*- coding: utf-8 -*-
"""MongoDB 역할 안내 탭 (정적 정보 표시, DB 연결 불필요)

역할:
- MongoDB의 플랫폼 내 역할, 저장 데이터, 특화 기능, 활용 방안을 표시
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

        MongoDB의 역할, 저장 데이터, 특화 기능, 활용 방안을 정적으로 표시합니다.
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

            title = QLabel("🟣 MongoDB — Core Tier 메타데이터 & 전략 저장소")
            title.setStyleSheet(
                "font-size: 14pt; font-weight: bold; "
                "color: #FFFFFF; background-color: #7C3AED; padding: 12px; border-radius: 6px;"
            )
            content_layout.addWidget(title)

            body_text = (
                "<b>📌 역할</b><br>"
                "MongoDB는 유연한 스키마의 문서 지향 NoSQL 데이터베이스입니다.<br>"
                "포트: 27017 | DB: upbit_trader | 응답: &lt; 20ms<br><br>"

                "<b>💾 저장 데이터</b><br>"
                "• symbols — 종목 메타데이터<br>"
                "• ui_settings — 앱 전체 설정 저장소<br>"
                "• strategies — 매매 전략 정의 및 파라미터<br>"
                "• performance_baseline — AI 재학습 기준 메트릭<br>"
                "• collection_stats — 디스크 사용량·수집 통계<br><br>"

                "<b>⚙️ 특화 기능</b><br>"
                "• 유연한 스키마 (마이그레이션 없이 즉시 반영)<br>"
                "• symbol 필드 인덱스 (조회 &lt; 20ms)<br>"
                "• T+5초 설정 로드<br>"
                "• AI 모델 메타데이터 버전 관리<br><br>"

                "<b>🚀 활용 방안</b><br>"
                "스마트 스캐너 · 전략 관리 · AI/ML 파이프라인 · 앱 설정 영속화"
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
