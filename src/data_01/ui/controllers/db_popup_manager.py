# -*- coding: utf-8 -*-
"""
DB ?앹뾽 ?ㅼ씠?쇰줈洹?愿由?(6媛?DB + MLflow ?숈떆 ?ㅽ뻾 吏??

蹂寃??대젰:
- 媛?DB蹂??꾩슜 紐⑤땲?곕쭅 ?ㅼ씠?쇰줈洹??곗꽑 ?ъ슜 ({db}/ui/{db}_monitor.py)
- ?대갚: 湲곗〈 settings_dialog ?ъ슜
- MLflow: AI_MODE=MAX ?쒖뿉留??앹뾽 ?쒖떆
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
    logger.debug("[DBPopupManager] PyQt5 ?ъ슜 遺덇?")

# AI_MODE=MAX ?뺤씤 (MLflow ?쒖꽦??議곌굔)
_AI_MODE = os.environ.get("AI_MODE", "").upper()
_IS_AI_MAX = _AI_MODE == "MAX"


class DBPopupManager:
    """6媛?DB + MLflow ?앹뾽 ?숈떆 ?ㅽ뻾 愿由?(鍮꾨え??"""

    # DB紐???(?뚯씪 ?곷?寃쎈줈, ?대옒?ㅻ챸) 留ㅽ븨 (DB蹂??꾩슜 紐⑤땲?곕쭅 ?ㅼ씠?쇰줈洹??곗꽑)
    _MONITORING_DIALOG_MAP = {
        "timescale": ("timescale/ui/timescale_monitor.py", "TimescaleMonitorDialog"),
        "redis": ("redis/ui/redis_monitor.py", "RedisMonitorDialog"),
        "mongodb": ("mongodb/ui/mongodb_monitor.py", "MongoDBMonitorDialog"),
        "postgres": ("postgres/ui/postgres_monitor.py", "PostgresMonitorDialog"),
        "kafka": ("kafka/ui/kafka_monitor.py", "KafkaMonitorDialog"),
        "clickhouse": ("clickhouse/ui/clickhouse_monitor.py", "ClickHouseMonitorDialog"),
    }

    # DB紐???(?뚯씪 ?곷?寃쎈줈, ?대옒?ㅻ챸) 留ㅽ븨 (湲곗〈 settings ?ㅼ씠?쇰줈洹??대갚)
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
        # src/data_01 ?붾젆?좊━ 湲곗? 寃쎈줈
        self._base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    def _load_dialog_class(self, rel_path: str, class_name: str, cache_key: str) -> Optional[Any]:
        """?뚯씪 寃쎈줈?먯꽌 ?ㅼ씠?쇰줈洹??대옒?ㅻ? 濡쒕뱶?섍퀬 罹먯떆????ν빀?덈떎."""
        if cache_key in self._dialog_class_cache:
            return self._dialog_class_cache[cache_key]
        file_path = os.path.join(self._base_dir, rel_path)
        if not os.path.isfile(file_path):
            logger.debug("[DBPopupManager] ?뚯씪 ?놁쓬: %s", file_path)
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
            logger.debug("[DBPopupManager] 紐⑤뱢 濡쒕뱶 ?ㅽ뙣 %s: %s", file_path, load_err)
        return None

    def _load_conn_params(self, db_name: str) -> dict:
        """config.yaml?먯꽌 DB ?곌껐 ?뚮씪誘명꽣瑜??쎌뼱 諛섑솚?⑸땲??

        ?ㅽ뙣 ??鍮?dict瑜?諛섑솚?섎ŉ, 媛??ㅼ씠?쇰줈洹몄쓽 湲곕낯媛믪씠 ?ъ슜?⑸땲??
        """
        try:
            if not _HAS_YAML:
                logger.debug("[DBPopupManager] PyYAML 誘몄꽕移???conn_params 湲곕낯媛??ъ슜")
                return {}
            config_path = os.path.join(
                os.path.dirname(self._base_dir),  # src/
                "01_core", "config", "config.yaml",
            )
            if not os.path.isfile(config_path):
                logger.debug("[DBPopupManager] config.yaml ?놁쓬: %s", config_path)
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
                "[DBPopupManager] conn_params 濡쒕뱶 ?꾨즺 (%s): host=%s port=%s database=%s user=%s",
                db_name, params.get("host"), params.get("port"),
                params.get("database"), params.get("user"),
            )
            return params
        except Exception as exc:
            logger.debug("[DBPopupManager] conn_params 濡쒕뱶 ?ㅽ뙣 (%s): %s", db_name, exc)
            return {}

    def open_popup(self, db_name: str) -> None:
        """DB 紐⑤땲?곕쭅 ?앹뾽??鍮꾨え?щ줈 ?쎈땲??(?대? ?대젮?덉쑝硫??쒖꽦??.

        MLflow??AI_MODE=MAX ?쒖뿉留??대┰?덈떎.
        媛?DB蹂??꾩슜 紐⑤땲?곕쭅 ?ㅼ씠?쇰줈洹?{db}/ui/{db}_monitor.py)瑜??곗꽑 ?ъ슜?섍퀬,
        ?놁쑝硫?湲곗〈 settings ?ㅼ씠?쇰줈洹몃줈 ?대갚?⑸땲??
        """
        if not _HAS_QT:
            logger.warning("[DBPopupManager] PyQt5 誘몄꽕移????앹뾽 遺덇?")
            return

        # MLflow??AI_MODE=MAX ?쒖뿉留??덉슜
        if db_name == "mlflow" and not _IS_AI_MAX:
            if self.parent is not None:
                QMessageBox.information(
                    self.parent,
                    "MLflow 鍮꾪솢??,
                    "MLflow 紐⑤땲?곕쭅? AI_MODE=MAX ?섍꼍?먯꽌留??ъ슜 媛?ν빀?덈떎.\n\n"
                    "?섍꼍蹂?섎? ?ㅼ젙?섏꽭?? AI_MODE=MAX",
                )
            return

        try:
            # ?대? ?대젮?덉쑝硫??쒖꽦??(??젣 ?щ? ?덉쟾?섍쾶 ?뺤씤)
            if db_name in self.popups:
                popup_ref = self.popups[db_name]
                try:
                    if popup_ref.isVisible():
                        popup_ref.raise_()
                        popup_ref.activateWindow()
                        return
                except RuntimeError:
                    # ?꾩젽????젣??寃쎌슦 ?덈줈 ?앹꽦
                    del self.popups[db_name]

            dialog_cls = None

            # 1) DB蹂??꾩슜 紐⑤땲?곕쭅 ?ㅼ씠?쇰줈洹??곗꽑 ?쒕룄 ({db}/ui/{db}_monitor.py)
            if db_name in self._MONITORING_DIALOG_MAP:
                mon_rel_path, mon_class = self._MONITORING_DIALOG_MAP[db_name]
                dialog_cls = self._load_dialog_class(
                    mon_rel_path, mon_class, f"mon_{db_name}"
                )

            # 2) ?대갚: 湲곗〈 settings ?ㅼ씠?쇰줈洹?
            if dialog_cls is None and db_name in self._DIALOG_FILE_MAP:
                old_rel_path, old_class = self._DIALOG_FILE_MAP[db_name]
                dialog_cls = self._load_dialog_class(
                    old_rel_path, old_class, f"old_{db_name}"
                )

            if dialog_cls is None:
                all_known = {**self._MONITORING_DIALOG_MAP, **self._DIALOG_FILE_MAP}
                if db_name not in all_known and db_name != "mlflow":
                    logger.warning("[DBPopupManager] ?????녿뒗 DB: %s", db_name)
                else:
                    logger.warning("[DBPopupManager] ?ㅼ씠?쇰줈洹??대옒??濡쒕뱶 ?ㅽ뙣: %s", db_name)
                    if self.parent is not None:
                        QMessageBox.warning(
                            self.parent, "?ㅻ쪟",
                            f"{db_name} ?ㅼ씠?쇰줈洹?紐⑤뱢??遺덈윭?????놁뒿?덈떎."
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
                    "[DBPopupManager] conn_params ?꾨떖 ?ㅽ뙣 (%s), ?대갚 ?ъ슜: %s",
                    db_name, type_err,
                )
                popup = dialog_cls(self.parent)
            popup.setWindowModality(Qt.NonModal)
            popup.show()

            self.popups[db_name] = popup
            logger.info("[DBPopupManager] %s ?앹뾽 ?대┝", db_name)

        except Exception as e:
            logger.error("[DBPopupManager] %s ?앹뾽 ?닿린 ?ㅽ뙣: %s", db_name, e)
            try:
                if self.parent is not None:
                    QMessageBox.warning(self.parent, "?ㅻ쪟", f"{db_name} ?앹뾽???????놁뒿?덈떎:\n{e}")
            except Exception:
                pass

    def open_mlflow_popup(self) -> None:
        """MLflow 紐⑤땲?곕쭅 ?앹뾽???쎈땲??(AI_MODE=MAX ?쒖뿉留?."""
        self.open_popup("mlflow")

    def close_all(self) -> None:
        """紐⑤뱺 ?앹뾽 ?リ린"""
        for db_name, popup in list(self.popups.items()):
            try:
                popup.close()
            except Exception:
                pass
        self.popups.clear()

