# -*- coding: utf-8 -*-
"""
탭 초기화 및 자동갱신 관리 Mixin (tab_manager.py)

CHANGELOG:
    v6.0 (2026-04-28) | Copilot | status_widget.py → 패키지 완전 모듈화
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QTimer
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if TYPE_CHECKING:
    pass

if _HAS_QT:
    class TabManagerMixin:
        """탭 초기화 및 자동갱신 관리 Mixin.

        Attributes:
            _tab_dashboard: 대시보드 탭 인스턴스
            _tab_websocket: WebSocket 탭 인스턴스
            _tab_dataflow: 데이터 흐름 탭 인스턴스
            _tab_gap: Gap 검출 탭 인스턴스
            _tab_error: 에러 분석 탭 인스턴스
            _tab_resource: 시스템 리소스 탭 인스턴스
            _tab_collection: 수집 설정 탭 인스턴스
            _tab_scanner: 스마트 스캐너 탭 인스턴스
            _tab_statistics: 실시간 로그 탭 인스턴스
            _tab_aiml: AI/ML 탭 인스턴스
            _tab_db_data_viewer: DB 데이터 뷰어 탭 인스턴스
        """

        def _init_tabs(self) -> None:
            """탭 위젯 초기화 및 자동갱신 시작.

            탭 모듈이 없거나 tabWidget이 없으면 경고 로그만 출력하고 반환합니다.

            Raises:
                Exception: 개별 탭 생성 실패 시 에러 로그 출력 후 계속 진행
            """
            try:
                from ..tabs import (
                    DashboardTab, WebSocketTab, DataFlowTab, GapTab,
                    ErrorTab, ResourceTab, CollectionTab, StatisticsTab,
                    ScannerTab, AIMLTab, DBDataViewerTab,
                )
                _has_tabs = True
            except ImportError as exc:
                logger.warning("[StatusWidget] 탭 모듈 임포트 실패: %s", exc)
                _has_tabs = False

            if not _has_tabs:
                logger.warning("[StatusWidget] 탭 모듈 없음")
                return

            tab_widget = getattr(self, "tabWidget", None)
            if tab_widget is None:
                logger.warning("[StatusWidget] tabWidget 없음")
                return

            tab_definitions = [
                # ── 1. 홈/요약 ───────────────────────────────────────────
                ("_tab_dashboard",       DashboardTab,      "실시간 대시보드"),
                # ── 2. 설정 관리 ────────────────────────────────────────
                ("_tab_collection",      CollectionTab,     "수집 설정"),
                # ── 3. 분석 도구 ────────────────────────────────────────
                ("_tab_scanner",         ScannerTab,        "스마트 스캐너"),
                # ── 4. 자동화 ───────────────────────────────────────────
                ("_tab_aiml",            AIMLTab,           "AI/ML 제어"),
                # ── 5. 데이터 수집 (Process 1) ───────────────────────────
                ("_tab_websocket",       WebSocketTab,      "WebSocket 수신"),
                # ── 6. 검증/변환 (Process 2) ────────────────────────────
                ("_tab_dataflow",        DataFlowTab,       "데이터 파이프라인"),
                # ── 7. 저장 확인 (Process 3) ────────────────────────────
                ("_tab_db_data_viewer",  DBDataViewerTab,   "DB 데이터"),
                # ── 8. 결함 탐지 ────────────────────────────────────────
                ("_tab_gap",             GapTab,            "Gap 검출"),
                # ── 9. 오류 모니터링 ────────────────────────────────────
                ("_tab_error",           ErrorTab,          "에러 분석"),
                # ── 10. 인프라 ──────────────────────────────────────────
                ("_tab_resource",        ResourceTab,       "시스템 리소스"),
                # ── 11. 디버깅 ──────────────────────────────────────────
                ("_tab_statistics",      StatisticsTab,     "실시간 로그"),
            ]

            for attr_name, TabClass, tab_title in tab_definitions:
                try:
                    instance = TabClass(parent=self)
                    setattr(self, attr_name, instance)
                    tab_widget.addTab(instance, tab_title)
                    logger.debug("[StatusWidget] 탭 추가: %s", tab_title)
                except Exception as exc:
                    logger.error("[StatusWidget] 탭 생성 실패 (%s): %s", tab_title, exc)

            # 각 탭별 최적 갱신 주기 (ms)
            _TAB_REFRESH_INTERVALS = {
                "_tab_dashboard":      3000,
                "_tab_collection":     5000,
                "_tab_scanner":        2000,
                "_tab_aiml":           5000,
                "_tab_websocket":      1000,
                "_tab_dataflow":       3000,
                "_tab_db_data_viewer": 5000,
                "_tab_gap":            3000,
                "_tab_error":          5000,
                "_tab_resource":       3000,
                "_tab_statistics":     3000,
            }

            # 탭 초기화 후 일괄 start_updates
            for attr_name, interval_ms in _TAB_REFRESH_INTERVALS.items():
                tab_instance = getattr(self, attr_name, None)
                if tab_instance is not None and hasattr(tab_instance, "start_updates"):
                    try:
                        tab_instance.start_updates(interval_ms)
                        logger.info("[StatusWidget] ✅ %s 자동 갱신 시작 (%dms)", attr_name, interval_ms)
                    except Exception as exc:
                        logger.error("[StatusWidget] ❌ %s.start_updates() 실패: %s", attr_name, exc)

            logger.info("[StatusWidget] 🎉 모든 탭 자동 갱신 활성화 완료")

else:
    class TabManagerMixin:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 TabManagerMixin."""

        def _init_tabs(self) -> None:
            """탭 초기화 (더미)."""
            pass
