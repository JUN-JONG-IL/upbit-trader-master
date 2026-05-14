# -*- coding: utf-8 -*-
"""
DB 팝업 다이얼로그 관리 (6개 DB + MLflow 동시 실행 지원)

변경 이력:
- 각 DB별 전용 모니터링 다이얼로그 우선 사용 ({db}/ui/{db}_monitor.py)
- 폴백: 기존 settings_dialog 사용
- MLflow: AI_MODE=MAX 시에만 팝업 표시
"""
from __future__ import annotations
import importlib
import importlib.util
import inspect
import logging
import os
import pathlib
from typing import Dict, Any, Optional

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _yaml = None  # type: ignore[assignment]
    _HAS_YAML = False

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QMessageBox
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    logger.debug("[DBPopupManager] PyQt5 사용 불가")

# AI_MODE=MAX 확인 (MLflow 활성화 조건)
_AI_MODE = os.environ.get("AI_MODE", "").upper()
_IS_AI_MAX = _AI_MODE == "MAX"


class DBPopupManager:
    """6개 DB + MLflow 팝업 동시 실행 관리 (비모달)"""

    # DB명 → (파일 상대경로, 클래스명) 매핑 (DB별 전용 모니터링 다이얼로그 우선)
    _MONITORING_DIALOG_MAP = {
        "timescale": ("timescale/ui/timescale_monitor.py", "TimescaleMonitorDialog"),
        "redis": ("redis/ui/redis_monitor.py", "RedisMonitorDialog"),
        "mongodb": ("mongodb/ui/mongodb_monitor.py", "MongoDBMonitorDialog"),
        "postgres": ("postgres/ui/postgres_monitor.py", "PostgresMonitorDialog"),
        "kafka": ("kafka/ui/kafka_monitor.py", "KafkaMonitorDialog"),
        "clickhouse": ("clickhouse/ui/clickhouse_monitor.py", "ClickHouseMonitorDialog"),
    }

    # DB명 → (파일 상대경로, 클래스명) 매핑 (기존 settings 다이얼로그 폴백)
    _DIALOG_FILE_MAP = {
        "timescale": ("timescale/ui/timescale_settings_dialog.py", "TimescaleSettingsDialog"),
        "redis": ("redis/ui/redis_settings_dialog.py", "RedisSettingsDialog"),
        "mongodb": ("mongodb/ui/mongodb_settings_dialog.py", "MongoDBSettingsDialog"),
        "postgres": ("postgres/ui/postgres_dialog.py", "PostgresEventStoreDialog"),
        "kafka": ("kafka/ui/kafka_settings_dialog.py", "KafkaSettingsDialog"),
        "clickhouse": ("clickhouse/ui/clickhouse_settings_dialog.py", "ClickHouseSettingsDialog"),
    }

    def __init__(self, parent=None):
        self.parent = parent
        self.popups: Dict[str, Any] = {}
        self._dialog_class_cache: Dict[str, Any] = {}
        # src/02_data 디렉토리 기준 경로
        self._base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    def _load_dialog_class(self, rel_path: str, class_name: str, cache_key: str) -> Optional[Any]:
        """파일 경로에서 다이얼로그 클래스를 로드하고 캐시에 저장합니다."""
        if cache_key in self._dialog_class_cache:
            return self._dialog_class_cache[cache_key]
        file_path = os.path.join(self._base_dir, rel_path)
        if not os.path.isfile(file_path):
            logger.debug("[DBPopupManager] 파일 없음: %s", file_path)
            return None
        try:
            spec = importlib.util.spec_from_file_location(
                f"_db_dialog_{cache_key}", file_path
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                dialog_cls = getattr(mod, class_name, None)
                if dialog_cls:
                    self._dialog_class_cache[cache_key] = dialog_cls
                    return dialog_cls
        except Exception as load_err:
            logger.debug("[DBPopupManager] 모듈 로드 실패 %s: %s", file_path, load_err)
        return None

    def _load_conn_params(self, db_name: str) -> dict:
        """config.yaml에서 DB 연결 파라미터를 읽어 반환합니다.

        실패 시 빈 dict를 반환하며, 각 다이얼로그의 기본값이 사용됩니다.
        """
        try:
            if not _HAS_YAML:
                logger.debug("[DBPopupManager] PyYAML 미설치 — conn_params 기본값 사용")
                return {}
            config_path = os.path.join(
                os.path.dirname(self._base_dir),  # src/
                "01_core", "config", "config.yaml",
            )
            if not os.path.isfile(config_path):
                logger.debug("[DBPopupManager] config.yaml 없음: %s", config_path)
                return {}
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = _yaml.safe_load(f) or {}
            section = cfg.get(db_name.upper(), {})
            params = {
                "host":     section.get("HOST", "127.0.0.1"),
                "port":     section.get("PORT", 5432),
                "database": section.get("DATABASE", section.get("DB", "")),
                "user":     section.get("USER", "postgres"),
                "password": section.get("PASSWORD", ""),
            }
            logger.debug(
                "[DBPopupManager] conn_params 로드 완료 (%s): host=%s port=%s database=%s user=%s",
                db_name, params.get("host"), params.get("port"),
                params.get("database"), params.get("user"),
            )
            return params
        except Exception as exc:
            logger.debug("[DBPopupManager] conn_params 로드 실패 (%s): %s", db_name, exc)
            return {}

    def open_popup(self, db_name: str) -> None:
        """DB 모니터링 팝업을 비모달로 엽니다 (이미 열려있으면 활성화).

        MLflow는 AI_MODE=MAX 시에만 열립니다.
        각 DB별 전용 모니터링 다이얼로그({db}/ui/{db}_monitor.py)를 우선 사용하고,
        없으면 기존 settings 다이얼로그로 폴백합니다.
        """
        if not _HAS_QT:
            logger.warning("[DBPopupManager] PyQt5 미설치 — 팝업 불가")
            return

        # MLflow는 AI_MODE=MAX 시에만 허용
        if db_name == "mlflow" and not _IS_AI_MAX:
            if self.parent is not None:
                QMessageBox.information(
                    self.parent,
                    "MLflow 비활성",
                    "MLflow 모니터링은 AI_MODE=MAX 환경에서만 사용 가능합니다.\n\n"
                    "환경변수를 설정하세요: AI_MODE=MAX",
                )
            return

        try:
            # 이미 열려있으면 활성화 (삭제 여부 안전하게 확인)
            if db_name in self.popups:
                popup_ref = self.popups[db_name]
                try:
                    if popup_ref.isVisible():
                        popup_ref.raise_()
                        popup_ref.activateWindow()
                        return
                except RuntimeError:
                    # 위젯이 삭제된 경우 새로 생성
                    del self.popups[db_name]

            dialog_cls = None

            # 1) DB별 전용 모니터링 다이얼로그 우선 시도 ({db}/ui/{db}_monitor.py)
            if db_name in self._MONITORING_DIALOG_MAP:
                mon_rel_path, mon_class = self._MONITORING_DIALOG_MAP[db_name]
                dialog_cls = self._load_dialog_class(
                    mon_rel_path, mon_class, f"mon_{db_name}"
                )

            # 2) 폴백: 기존 settings 다이얼로그
            if dialog_cls is None and db_name in self._DIALOG_FILE_MAP:
                old_rel_path, old_class = self._DIALOG_FILE_MAP[db_name]
                dialog_cls = self._load_dialog_class(
                    old_rel_path, old_class, f"old_{db_name}"
                )

            if dialog_cls is None:
                all_known = {**self._MONITORING_DIALOG_MAP, **self._DIALOG_FILE_MAP}
                if db_name not in all_known and db_name != "mlflow":
                    logger.warning("[DBPopupManager] 알 수 없는 DB: %s", db_name)
                else:
                    logger.warning("[DBPopupManager] 다이얼로그 클래스 로드 실패: %s", db_name)
                    if self.parent is not None:
                        QMessageBox.warning(
                            self.parent, "오류",
                            f"{db_name} 다이얼로그 모듈을 불러올 수 없습니다."
                        )
                return

            conn_params = self._load_conn_params(db_name)
            try:
                sig = inspect.signature(dialog_cls.__init__)
                if "conn_params" in sig.parameters:
                    popup = dialog_cls(self.parent, conn_params=conn_params)
                else:
                    popup = dialog_cls(self.parent)
            except TypeError as type_err:
                logger.debug(
                    "[DBPopupManager] conn_params 전달 실패 (%s), 폴백 사용: %s",
                    db_name, type_err,
                )
                popup = dialog_cls(self.parent)
            popup.setWindowModality(Qt.NonModal)
            popup.show()

            self.popups[db_name] = popup
            logger.info("[DBPopupManager] %s 팝업 열림", db_name)

        except Exception as e:
            logger.error("[DBPopupManager] %s 팝업 열기 실패: %s", db_name, e)
            try:
                if self.parent is not None:
                    QMessageBox.warning(self.parent, "오류", f"{db_name} 팝업을 열 수 없습니다:\n{e}")
            except Exception:
                pass

    def open_mlflow_popup(self) -> None:
        """MLflow 모니터링 팝업을 엽니다 (AI_MODE=MAX 시에만)."""
        self.open_popup("mlflow")

    def close_all(self) -> None:
        """모든 팝업 닫기"""
        for db_name, popup in list(self.popups.items()):
            try:
                popup.close()
            except Exception:
                pass
        self.popups.clear()
