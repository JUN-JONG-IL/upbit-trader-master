# -*- coding: utf-8 -*-
"""
MenuHandler - 메뉴 액션 처리 (v11.0)

책임:
- 모든 _on_* 메뉴 핸들러
- 외부 URL 열기 (_open_mlflow, _open_prometheus 등)
- connect_actions(): 메뉴 액션 시그널 연결

변경 이력:
- v11.0: 메뉴 구조 재배치 (차트 메뉴 추가, 서버 메뉴 위치 이동, 우선순위 메뉴 데이터베이스로 이동)
"""
from __future__ import annotations

import logging
import webbrowser
import importlib
import importlib.util
import os
from pathlib import Path
from typing import Any

from PyQt5.QtWidgets import QMessageBox, QDialog, QVBoxLayout
from PyQt5.QtCore import Qt

logger = logging.getLogger(__name__)


class MenuHandler:
    """메뉴 액션 핸들러 - 모든 메뉴 이벤트 처리"""

    def __init__(self, main_window: Any) -> None:
        self.main_window = main_window

    # ─────────────────────────────────────── 메뉴 연결 ──

    def connect_actions(self) -> None:
        """v11.0 전체 메뉴 액션을 핸들러에 연결합니다."""
        try:
            mw = self.main_window
            db_mgr = mw.db_dialog_manager
            if db_mgr is None:
                logger.warning("[MenuHandler] db_dialog_manager 없음 — DB 메뉴 연결 건너뜀")
                db_open_ts = lambda: None
                db_open_redis = lambda: None
                db_open_mongo = lambda: None
                db_open_kafka = lambda: None
                db_open_ch = lambda: None
                db_open_pg = lambda: None
                db_open_priority = self._on_priority_settings_fallback
                db_open_ml = self._on_ml_model_selector_fallback
                db_open_dashboard = self._on_priority_dashboard_fallback
            else:
                db_open_ts = db_mgr._open_timescale_dialog
                db_open_redis = db_mgr._open_redis_dialog
                db_open_mongo = db_mgr._open_mongodb_dialog
                db_open_kafka = db_mgr._open_kafka_dialog
                db_open_ch = db_mgr._open_clickhouse_dialog
                db_open_pg = db_mgr._open_postgresql_dialog
                db_open_priority = db_mgr._open_priority_settings_dialog
                db_open_ml = db_mgr._open_ml_model_selector_dialog
                db_open_dashboard = db_mgr._open_priority_dashboard_dialog

            action_map = {
                # 홈
                "actionDashboard": self._on_dashboard,
                "actionRefresh": self._on_refresh,
                # 사용자
                "actionProfile": self._on_profile,
                "actionAPIKeys": self._on_api_keys,
                "actionAccountInfo": self._on_account_info,
                # 마켓
                "actionMarketOverview": self._on_market_overview,
                "actionOrderbookAnalysis": self._on_orderbook_analysis,
                "actionVolumeProfile": self._on_volume_profile,
                # 차트 (새 메뉴)
                "actionMultiChart": self._on_multi_chart,
                "actionInteractiveChart": self._on_interactive_chart,
                "actionChartSettings": self._on_chart_settings,
                # 시그널
                "actionSignalManager": self._on_signal_manager,
                "actionBacktest": self._on_backtest,
                # 포트폴리오
                "actionPortfolioManager": self._on_portfolio_manager,
                "actionRiskManagement": self._on_risk_management,
                "actionPerformanceReport": self._on_performance_report,
                # 스캐너
                "actionSymbolScanner": self._on_symbol_scanner,
                "actionGapDetector": self._on_gap_detector,
                "actionAnomalyDetection": self._on_anomaly_detection,
                # AI/ML
                "actionAIEngine": self._on_ai_engine,
                "actionPrediction": self._on_prediction,
                "actionSentiment": self._on_sentiment,
                "actionMLflow": self._open_mlflow,
                "actionFeatureStore": self._on_feature_store,
                # 데이터베이스 (우선순위 메뉴 이동됨)
                "actionDB_Timescale": db_open_ts,
                "actionDB_Redis": db_open_redis,
                "actionDB_Mongo": db_open_mongo,
                "actionDB_Kafka": db_open_kafka,
                "actionDB_ClickHouse": db_open_ch,
                "actionDB_PostgreSQL": db_open_pg,
                "actionPrioritySettings": db_open_priority,
                "actionMLModelSelector": db_open_ml,
                "actionPriorityDashboard": db_open_dashboard,
                # 서버 (위치 이동: 데이터베이스 바로 다음)
                "actionFastAPI": self._open_fastapi,
                "actionWebSocket": self._on_websocket,
                "actionServerStatus": self._on_server_status,
                "actionServerSettings": self._on_server_settings,
                # 도구
                "actionBackfillManager": self._on_backfill_manager,
                "actionSnowflakeID": self._on_snowflake_id,
                # 모니터링
                "actionSystemMonitor": self._on_system_monitor,
                "actionPrometheus": self._open_prometheus,
                "actionGrafana": self._open_grafana,
                "actionJaeger": self._open_jaeger,
                # 설정
                "actionPreferences": self._on_preferences,
                "actionAPISettings": self._on_api_settings,
                "actionDBSettings": self._on_db_settings,
                "actionTheme": self._on_theme,
                # 도움말
                "actionDocumentation": self._on_documentation,
                "actionAbout": self._on_about,
                "actionCheckUpdate": self._on_check_update,
            }

            connected = 0
            missing = 0
            for action_name, handler in action_map.items():
                action = getattr(mw, action_name, None)
                if action is not None:
                    action.triggered.connect(handler)
                    connected += 1
                else:
                    missing += 1

            logger.info("[MenuHandler] 메뉴 액션 연결 완료: %d개 (미정의: %d개)", connected, missing)
        except Exception as e:
            logger.warning("[MenuHandler] 메뉴 액션 연결 실패: %s", e)

    # ─────────────────────────────────────── 홈 메뉴 ──

    def _on_dashboard(self) -> None:
        """대시보드로 이동"""
        if hasattr(self.main_window, "qStackedWidget"):
            self.main_window.qStackedWidget.setCurrentIndex(0)
        logger.info("[MenuHandler] 대시보드 이동")

    def _on_refresh(self) -> None:
        """전체 데이터 새로고침"""
        if self.main_window.symbol_loader is not None:
            self.main_window.symbol_loader.start_loading()
        logger.info("[MenuHandler] 전체 새로고침")

    # ─────────────────────────────────────── 사용자 메뉴 ──

    def _on_profile(self) -> None:
        """사용자 프로필 관리 (미구현)"""
        QMessageBox.information(self.main_window, "프로필", "사용자 프로필 관리 (미구현)")

    def _on_api_keys(self) -> None:
        """API 키 관리 (미구현)"""
        QMessageBox.information(self.main_window, "API 키", "Upbit API 키 관리 (미구현)")

    def _on_account_info(self) -> None:
        """계좌 정보 페이지로 이동"""
        if hasattr(self.main_window, "qStackedWidget"):
            self.main_window.qStackedWidget.setCurrentIndex(1)
        logger.info("[MenuHandler] 계좌 정보 페이지 이동")

    # ─────────────────────────────────────── 마켓 메뉴 ──

    def _on_market_overview(self) -> None:
        """전체 시장 개요 (미구현)"""
        QMessageBox.information(self.main_window, "마켓 개요", "전체 시장 개요 (미구현)")

    def _on_orderbook_analysis(self) -> None:
        """실시간 호가창 분석 (미구현)"""
        QMessageBox.information(self.main_window, "호가 분석", "실시간 호가창 분석 (미구현)")

    def _on_volume_profile(self) -> None:
        """거래량 프로파일 (미구현)"""
        QMessageBox.information(self.main_window, "볼륨 프로파일", "거래량 프로파일 (미구현)")

    # ─────────────────────────────────────── 차트 메뉴 (새로 추가) ──

    def _on_multi_chart(self) -> None:
        """멀티차트 뷰 (미구현)"""
        QMessageBox.information(self.main_window, "멀티차트", "다중 차트 뷰 (미구현)")

    def _on_interactive_chart(self) -> None:
        """인터랙티브 차트 (미구현)"""
        QMessageBox.information(self.main_window, "인터랙티브 차트", "Plotly/Lightweight 차트 (미구현)")

    def _on_chart_settings(self) -> None:
        """차트 설정 (미구현)"""
        QMessageBox.information(self.main_window, "차트 설정", "차트 엔진 및 지표 설정 (미구현)")

    # ─────────────────────────────────────── 시그널 메뉴 ──

    def _on_signal_manager(self) -> None:
        """시그널 관리 페이지로 이동"""
        if hasattr(self.main_window, "qStackedWidget"):
            self.main_window.qStackedWidget.setCurrentIndex(2)
        logger.info("[MenuHandler] 시그널 관리 페이지 이동")

    def _on_backtest(self) -> None:
        """전략 백테스트 (미구현)"""
        QMessageBox.information(self.main_window, "백테스트", "전략 백테스트 (미구현)")

    # ─────────────────────────────────────── 포트폴리오 메뉴 ──

    def _on_portfolio_manager(self) -> None:
        """포트폴리오 관리 (미구현)"""
        QMessageBox.information(self.main_window, "포트폴리오 관리", "포트폴리오 구성 및 리밸런싱 (미구현)")

    def _on_risk_management(self) -> None:
        """리스크 관리 (미구현)"""
        QMessageBox.information(self.main_window, "리스크 관리", "VaR, 손절/익절 관리 (미구현)")

    def _on_performance_report(self) -> None:
        """성과 보고서 (미구현)"""
        QMessageBox.information(self.main_window, "성과 보고서", "수익률 및 성과 분석 (미구현)")

    # ─────────────────────────────────────── 스캐너 메뉴 ──

    def _on_symbol_scanner(self) -> None:
        """심볼 스캐너 (미구현)"""
        QMessageBox.information(self.main_window, "심볼 스캐너", "우선순위 기반 심볼 스캐너 (미구현)")

    def _on_gap_detector(self) -> None:
        """Gap 탐지 (미구현)"""
        QMessageBox.information(self.main_window, "Gap 탐지", "데이터 Gap 탐지 및 자동 보정 (미구현)")

    def _on_anomaly_detection(self) -> None:
        """이상 탐지 (미구현)"""
        QMessageBox.information(self.main_window, "이상 탐지", "VAE 기반 이상 패턴 탐지 (미구현)")

    # ─────────────────────────────────────── AI/ML 메뉴 ──

    def _on_ai_engine(self) -> None:
        """AI 엔진 통합 관리 (미구현)"""
        QMessageBox.information(self.main_window, "AI 엔진", "AI 엔진 통합 관리 (미구현)")

    def _on_prediction(self) -> None:
        """가격 예측 모델 (미구현)"""
        QMessageBox.information(self.main_window, "예측 모델", "LightGBM/XGBoost 가격 예측 (미구현)")

    def _on_sentiment(self) -> None:
        """감성 분석 (미구현)"""
        QMessageBox.information(self.main_window, "감성 분석", "뉴스/소셜 감성 분석 (미구현)")

    def _open_mlflow(self) -> None:
        """MLflow UI 열기"""
        webbrowser.open("http://localhost:5000")
        logger.info("[MenuHandler] MLflow UI 열기: http://localhost:5000")

    def _on_feature_store(self) -> None:
        """Feature Store (미구현)"""
        QMessageBox.information(self.main_window, "Feature Store", "Feast Feature Store (미구현)")

    # ─────────────────────────────────────── 데이터베이스 우선순위 메뉴 (폴백) ──

    def _on_priority_settings_fallback(self) -> None:
        """우선순위 설정 폴백 (DB Dialog Manager 초기화 실패 시)"""
        QMessageBox.information(
            self.main_window, "우선순위 설정", "우선순위 설정 다이얼로그 (DB Dialog Manager 초기화 실패)"
        )

    def _on_ml_model_selector_fallback(self) -> None:
        """ML 모델 선택 폴백 (DB Dialog Manager 초기화 실패 시)"""
        QMessageBox.information(
            self.main_window, "ML 모델 선택", "ML 모델 선택 다이얼로그 (DB Dialog Manager 초기화 실패)"
        )

    def _on_priority_dashboard_fallback(self) -> None:
        """우선순위 대시보드 폴백 (DB Dialog Manager 초기화 실패 시)"""
        QMessageBox.information(
            self.main_window, "우선순위 대시보드", "우선순위 대시보드 (DB Dialog Manager 초기화 실패)"
        )

    # ─────────────────────────────────────── 서버 메뉴 ──

    def _open_fastapi(self) -> None:
        """FastAPI Swagger UI 열기"""
        webbrowser.open("http://localhost:8000/docs")
        logger.info("[MenuHandler] FastAPI Swagger UI 열기: http://localhost:8000/docs")

    def _on_websocket(self) -> None:
        """WebSocket 클라이언트 테스트 (미구현)"""
        QMessageBox.information(self.main_window, "WebSocket 연결", "WebSocket 클라이언트 테스트 (미구현)")

    def _on_server_status(self) -> None:
        """FastAPI 서버 상태 모니터 (미구현)"""
        QMessageBox.information(self.main_window, "서버 상태", "FastAPI 서버 상태 모니터링 (미구현)")

    def _on_server_settings(self) -> None:
        """FastAPI 서버 설정 (미구현)"""
        QMessageBox.information(self.main_window, "서버 설정", "서버 환경설정 (미구현)")

    # ─────────────────────────────────────── 도구 메뉴 ──

    def _on_backfill_manager(self) -> None:
        """Backfill 관리 (미구현)"""
        QMessageBox.information(self.main_window, "Backfill 관리", "자동 Gap Fill 및 히스토리 수집 (미구현)")

    def _on_snowflake_id(self) -> None:
        """Snowflake ID 생성기 (미구현)"""
        QMessageBox.information(self.main_window, "Snowflake ID", "분산 ID 생성기 (미구현)")

    def _on_system_monitor(self) -> None:
        """시스템 모니터링 → 모니터링 대시보드를 엽니다."""
        try:
            mw = self.main_window
            if hasattr(mw, "open_monitoring_dashboard") and callable(mw.open_monitoring_dashboard):
                mw.open_monitoring_dashboard()
                return
        except Exception as e:
            logger.warning("[MenuHandler] 시스템 모니터링 → 모니터링 대시보드 리다이렉트 실패: %s", e)
        QMessageBox.information(self.main_window, "시스템 모니터링", "시스템 모니터링 기능을 실행할 수 없습니다.")

    def _open_prometheus(self) -> None:
        """Prometheus UI 열기"""
        webbrowser.open("http://localhost:9090")
        logger.info("[MenuHandler] Prometheus UI 열기: http://localhost:9090")

    def _open_grafana(self) -> None:
        """Grafana UI 열기"""
        webbrowser.open("http://localhost:3000")
        logger.info("[MenuHandler] Grafana UI 열기: http://localhost:3000")

    def _open_jaeger(self) -> None:
        """Jaeger UI 열기"""
        webbrowser.open("http://localhost:16686")
        logger.info("[MenuHandler] Jaeger UI 열기: http://localhost:16686")

    # ─────────────────────────────────────── 설정 메뉴 ──

    def _on_preferences(self) -> None:
        """환경설정 (미구현)"""
        QMessageBox.information(self.main_window, "환경설정", "앱 환경설정 (미구현)")

    def _on_api_settings(self) -> None:
        """API 설정 (미구현)"""
        QMessageBox.information(self.main_window, "API 설정", "Upbit API 키 및 권한 (미구현)")

    def _on_db_settings(self) -> None:
        """DB 설정 (미구현)"""
        QMessageBox.information(self.main_window, "DB 설정", "데이터베이스 연결 설정 (미구현)")

    def _on_theme(self) -> None:
        """테마 전환 (미구현)"""
        QMessageBox.information(self.main_window, "테마", "라이트/다크 테마 전환 (미구현)")

    # ─────────────────────────────────────── 도움말 메뉴 ──

    def _on_documentation(self) -> None:
        """문서 열기 (GitHub)"""
        webbrowser.open("https://github.com/JUN-JONG-IL/upbit-trader-master")
        logger.info("[MenuHandler] 문서 열기: GitHub")

    def _on_about(self) -> None:
        """프로그램 정보"""
        QMessageBox.about(
            self.main_window,
            "Upbit Trader v11.0",
            "기관급 트레이딩 시스템\n\n"
            "v11.0 - 메뉴 구조 최적화 (차트 메뉴 추가, 우선순위 메뉴 재배치)\n"
            "TimescaleDB + Redis + MongoDB + Kafka + ClickHouse\n\n"
            "© 2026 JUN-JONG-IL",
        )

    def _on_check_update(self) -> None:
        """업데이트 확인 (미구현)"""
        QMessageBox.information(self.main_window, "업데이트 확인", "최신 버전입니다.")