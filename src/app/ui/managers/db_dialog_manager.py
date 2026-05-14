"""
DBDialogManager - DB 다이얼로그 관리 (v11.0)

책임:
- 각 DB 설정/모니터 다이얼로그 열기 (_open_*_dialog 메서드)
- 우선순위 설정 다이얼로그 관리 (AI/ML 섹션에서 데이터베이스 섹션으로 이동)
- 다이얼로그 모듈 동적 로딩 및 ImportError 안전 처리
- 다이얼로그 오류 메시지 표시

변경 이력:
- v11.0: 우선순위 관련 3개 다이얼로그 경로 및 클래스명 수정
  - PrioritySettingsDialog (widget_priority_settings.py)
  - MLModelSelectorDialog (widget_ml_model_selector.py)
"""
from __future__ import annotations

import importlib
import logging
import os
import sys
from typing import Any, Optional

from PyQt5.QtWidgets import QDialog, QMessageBox

logger = logging.getLogger(__name__)


class DBDialogManager:
    """DB 다이얼로그 관리 - 각 DB의 설정/모니터 다이얼로그를 동적으로 로드하고 열기."""

    def __init__(self, main_window: Any) -> None:
        self.main_window = main_window

    # ─────────────────────────────────────── 유틸리티 ──

    @staticmethod
    def _ensure_data_path() -> None:
        """src/data_01/ 를 sys.path 에 추가"""
        _data_dir = os.path.normpath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "..", "data_01",
            )
        )
        if _data_dir not in sys.path:
            sys.path.insert(0, _data_dir)

    @staticmethod
    def _ensure_settings_path() -> None:
        """src/11_server/ui/settings/ 를 sys.path 에 추가"""
        _settings_dir = os.path.normpath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "..", "11_server", "ui", "settings",
            )
        )
        if _settings_dir not in sys.path:
            sys.path.insert(0, _settings_dir)

    @staticmethod
    def _ensure_db_ui_path(db_name: str) -> None:
        """src/data_01/{db_name}/ui/ 를 sys.path 에 추가"""
        _ui_dir = os.path.normpath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "..", "data_01", db_name, "ui",
            )
        )
        if _ui_dir not in sys.path:
            sys.path.insert(0, _ui_dir)

    @staticmethod
    def _ensure_priority_ui_path() -> None:
        """src/06_ai/priority/ui/ 를 sys.path 에 추가"""
        _ui_dir = os.path.normpath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "..", "06_ai", "priority", "ui",
            )
        )
        if _ui_dir not in sys.path:
            sys.path.insert(0, _ui_dir)
            logger.debug("[DBDialogManager] sys.path 추가: %s", _ui_dir)

    def _show_dialog_error(self, db_name: str, exc: Exception) -> None:
        """다이얼로그 로드 실패 시 사용자 친화적 오류 메시지 표시"""
        QMessageBox.critical(
            self.main_window,
            f"{db_name} 다이얼로그 열기 실패",
            f"오류: {str(exc)}\n\n"
            f"확인 사항:\n"
            f"  1. Docker 컨테이너 실행 여부 확인 (docker ps)\n"
            f"  2. DB 연결 설정 확인 (호스트/포트/사용자)\n"
            f"  3. 로그 파일 확인: logs/app.log\n\n"
            f"모듈 경로: src/data_01/{db_name.lower()}/ui/",
        )

    @staticmethod
    def _try_import_dialog(module_paths: list, class_name: str) -> Optional[Any]:
        """후보 모듈 경로에서 다이얼로그 클래스를 동적 임포트합니다."""
        for module_path in module_paths:
            try:
                mod = importlib.import_module(module_path)
                dialog_class = getattr(mod, class_name, None)
                if dialog_class:
                    logger.debug("[DBDialogManager] %s 로드 성공: %s", class_name, module_path)
                    return dialog_class
            except ModuleNotFoundError as e:
                logger.debug("[DBDialogManager] 모듈 없음: %s (%s)", module_path, e)
                continue
            except Exception as e:
                logger.warning("[DBDialogManager] 모듈 로드 오류: %s (%s)", module_path, e)
                continue
        return None

    # ─────────────────────────────────────── DB 다이얼로그 핸들러 ──

    def _open_timescale_dialog(self) -> None:
        """TimescaleDB 설정 다이얼로그 열기 (data_01 경로)"""
        try:
            self._ensure_db_ui_path("timescale")
            dialog_class = self._try_import_dialog(
                ["timescale_settings_dialog"],
                "TimescaleSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("TimescaleSettingsDialog를 찾을 수 없습니다.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] TimescaleDB 다이얼로그 열기 실패: %s", e, exc_info=True)
            self._show_dialog_error("TimescaleDB", e)

    def _open_mongodb_dialog(self) -> None:
        """MongoDB 브라우저 다이얼로그 열기 (data_01 경로)"""
        try:
            self._ensure_db_ui_path("mongodb")
            dialog_class = self._try_import_dialog(
                ["mongodb_settings_dialog"],
                "MongoDBSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("MongoDBSettingsDialog를 찾을 수 없습니다.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] MongoDB 다이얼로그 열기 실패: %s", e, exc_info=True)
            self._show_dialog_error("MongoDB", e)

    def _open_redis_dialog(self) -> None:
        """Redis 상태 모니터 다이얼로그 열기 (data_01 경로)"""
        try:
            self._ensure_db_ui_path("redis")
            dialog_class = self._try_import_dialog(
                ["redis_settings_dialog", "widget_redis_settings"],
                "RedisSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("RedisSettingsDialog를 찾을 수 없습니다.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] Redis 다이얼로그 열기 실패: %s", e, exc_info=True)
            self._show_dialog_error("Redis", e)

    def _open_kafka_dialog(self) -> None:
        """Kafka 모니터 다이얼로그 열기 (data_01 경로)"""
        try:
            self._ensure_db_ui_path("kafka")
            dialog_class = self._try_import_dialog(
                ["kafka_settings_dialog"],
                "KafkaSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("KafkaSettingsDialog를 찾을 수 없습니다.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] Kafka 다이얼로그 열기 실패: %s", e, exc_info=True)
            self._show_dialog_error("Kafka", e)

    def _open_clickhouse_dialog(self) -> None:
        """ClickHouse 모니터 다이얼로그 열기 (data_01 경로)"""
        try:
            self._ensure_db_ui_path("clickhouse")
            dialog_class = self._try_import_dialog(
                ["clickhouse_settings_dialog"],
                "ClickHouseSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("ClickHouseSettingsDialog를 찾을 수 없습니다.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] ClickHouse 다이얼로그 열기 실패: %s", e, exc_info=True)
            self._show_dialog_error("ClickHouse", e)

    def _open_postgresql_dialog(self) -> None:
        """PostgreSQL CQRS 다이얼로그 열기 (data_01 경로)"""
        try:
            self._ensure_db_ui_path("postgres")
            dialog_class = self._try_import_dialog(
                ["postgres_dialog"],
                "PostgresEventStoreDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("PostgresEventStoreDialog를 찾을 수 없습니다.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] PostgreSQL 다이얼로그 열기 실패: %s", e, exc_info=True)
            self._show_dialog_error("PostgreSQL", e)

    # ─────────────────────────────────────── 우선순위 설정 다이얼로그 핸들러 ──

    def _open_priority_settings_dialog(self) -> None:
        """우선순위 종목 설정 다이얼로그 열기 (06_ai/priority/ui)"""
        try:
            self._ensure_priority_ui_path()
            
            # widget_priority_settings.py에서 PrioritySettingsDialog 클래스 로드
            dialog_class = self._try_import_dialog(
                ["widget_priority_settings"],
                "PrioritySettingsDialog",
            )
            
            if dialog_class is None:
                raise ModuleNotFoundError(
                    "PrioritySettingsDialog를 찾을 수 없습니다.\n"
                    "경로: src/06_ai/priority/ui/widget_priority_settings.py"
                )
            
            # 다이얼로그 생성 및 표시
            dlg = dialog_class(parent=self.main_window)
            
            # QDialog인 경우 exec_(), 아니면 show()
            if isinstance(dlg, QDialog):
                dlg.exec_()
            else:
                dlg.show()
                
            logger.info("[DBDialogManager] 우선순위 설정 다이얼로그 열림")
            
        except Exception as e:
            logger.error("[DBDialogManager] 우선순위 설정 다이얼로그 열기 실패: %s", e, exc_info=True)
            QMessageBox.critical(
                self.main_window,
                "우선순위 설정 오류",
                f"우선순위 설정 다이얼로그를 불러올 수 없습니다.\n\n"
                f"오류: {str(e)}\n\n"
                f"확인 사항:\n"
                f"  1. 파일 존재 여부: src/06_ai/priority/ui/widget_priority_settings.py\n"
                f"  2. 클래스명: PrioritySettingsDialog\n"
                f"  3. 로그 파일: logs/app.log",
            )

    def _open_ml_model_selector_dialog(self) -> None:
        """ML 모델 선택 다이얼로그 열기 (06_ai/priority/ui)"""
        try:
            self._ensure_priority_ui_path()
            
            # widget_ml_model_selector.py에서 MLModelSelectorDialog 클래스 로드
            dialog_class = self._try_import_dialog(
                ["widget_ml_model_selector"],
                "MLModelSelectorDialog",
            )
            
            if dialog_class is None:
                raise ModuleNotFoundError(
                    "MLModelSelectorDialog를 찾을 수 없습니다.\n"
                    "경로: src/06_ai/priority/ui/widget_ml_model_selector.py"
                )
            
            # 다이얼로그 생성 및 표시
            dlg = dialog_class(parent=self.main_window)
            
            # QDialog인 경우 exec_(), 아니면 show()
            if isinstance(dlg, QDialog):
                dlg.exec_()
            else:
                dlg.show()
                
            logger.info("[DBDialogManager] ML 모델 선택 다이얼로그 열림")
            
        except Exception as e:
            logger.error("[DBDialogManager] ML 모델 선택 다이얼로그 열기 실패: %s", e, exc_info=True)
            QMessageBox.critical(
                self.main_window,
                "ML 모델 선택 오류",
                f"ML 모델 선택 다이얼로그를 불러올 수 없습니다.\n\n"
                f"오류: {str(e)}\n\n"
                f"확인 사항:\n"
                f"  1. 파일 존재 여부: src/06_ai/priority/ui/widget_ml_model_selector.py\n"
                f"  2. 클래스명: MLModelSelectorDialog\n"
                f"  3. 로그 파일: logs/app.log",
            )

    def _open_priority_dashboard_dialog(self) -> None:
        """우선순위 대시보드 다이얼로그 열기 (06_ai/priority/ui)"""
        try:
            # 우선순위 대시보드는 별도 위젯이 없으므로 우선순위 설정으로 안내
            logger.info("[DBDialogManager] 우선순위 대시보드 → 우선순위 설정으로 안내")
            QMessageBox.information(
                self.main_window,
                "우선순위 대시보드",
                "우선순위 대시보드는 '우선순위 종목 설정' 메뉴에서\n"
                "대시보드 탭을 통해 확인할 수 있습니다.\n\n"
                "우선순위 설정 다이얼로그를 엽니다.",
            )
            self._open_priority_settings_dialog()
            
        except Exception as e:
            logger.error("[DBDialogManager] 우선순위 대시보드 열기 실패: %s", e, exc_info=True)
            QMessageBox.critical(
                self.main_window,
                "우선순위 대시보드 오류",
                f"우선순위 대시보드를 불러올 수 없습니다.\n\n"
                f"오류: {str(e)}\n\n"
                f"대신 '우선순위 종목 설정' 메뉴를 사용해주세요.",
            )