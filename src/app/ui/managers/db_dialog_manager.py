"""
DBDialogManager - DB ?ㅼ씠?쇰줈洹?愿由?(v11.0)

梨낆엫:
- 媛?DB ?ㅼ젙/紐⑤땲???ㅼ씠?쇰줈洹??닿린 (_open_*_dialog 硫붿꽌??
- ?곗꽑?쒖쐞 ?ㅼ젙 ?ㅼ씠?쇰줈洹?愿由?(AI/ML ?뱀뀡?먯꽌 ?곗씠?곕쿋?댁뒪 ?뱀뀡?쇰줈 ?대룞)
- ?ㅼ씠?쇰줈洹?紐⑤뱢 ?숈쟻 濡쒕뵫 諛?ImportError ?덉쟾 泥섎━
- ?ㅼ씠?쇰줈洹??ㅻ쪟 硫붿떆吏 ?쒖떆

蹂寃??대젰:
- v11.0: ?곗꽑?쒖쐞 愿??3媛??ㅼ씠?쇰줈洹?寃쎈줈 諛??대옒?ㅻ챸 ?섏젙
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
    """DB ?ㅼ씠?쇰줈洹?愿由?- 媛?DB???ㅼ젙/紐⑤땲???ㅼ씠?쇰줈洹몃? ?숈쟻?쇰줈 濡쒕뱶?섍퀬 ?닿린."""

    def __init__(self, main_window: Any) -> None:
        self.main_window = main_window

    # ??????????????????????????????????????? ?좏떥由ы떚 ??

    @staticmethod
    def _ensure_data_path() -> None:
        """src/data_01/ 瑜?sys.path ??異붽?"""
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
        """src/11_server/ui/settings/ 瑜?sys.path ??異붽?"""
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
        """src/data_01/{db_name}/ui/ 瑜?sys.path ??異붽?"""
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
        """src/06_ai/priority/ui/ 瑜?sys.path ??異붽?"""
        _ui_dir = os.path.normpath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "..", "06_ai", "priority", "ui",
            )
        )
        if _ui_dir not in sys.path:
            sys.path.insert(0, _ui_dir)
            logger.debug("[DBDialogManager] sys.path 異붽?: %s", _ui_dir)

    def _show_dialog_error(self, db_name: str, exc: Exception) -> None:
        """?ㅼ씠?쇰줈洹?濡쒕뱶 ?ㅽ뙣 ???ъ슜??移쒗솕???ㅻ쪟 硫붿떆吏 ?쒖떆"""
        QMessageBox.critical(
            self.main_window,
            f"{db_name} ?ㅼ씠?쇰줈洹??닿린 ?ㅽ뙣",
            f"?ㅻ쪟: {str(exc)}\n\n"
            f"?뺤씤 ?ы빆:\n"
            f"  1. Docker 而⑦뀒?대꼫 ?ㅽ뻾 ?щ? ?뺤씤 (docker ps)\n"
            f"  2. DB ?곌껐 ?ㅼ젙 ?뺤씤 (?몄뒪???ы듃/?ъ슜??\n"
            f"  3. 濡쒓렇 ?뚯씪 ?뺤씤: logs/app.log\n\n"
            f"紐⑤뱢 寃쎈줈: src/data_01/{db_name.lower()}/ui/",
        )

    @staticmethod
    def _try_import_dialog(module_paths: list, class_name: str) -> Optional[Any]:
        """?꾨낫 紐⑤뱢 寃쎈줈?먯꽌 ?ㅼ씠?쇰줈洹??대옒?ㅻ? ?숈쟻 ?꾪룷?명빀?덈떎."""
        for module_path in module_paths:
            try:
                mod = importlib.import_module(module_path)
                dialog_class = getattr(mod, class_name, None)
                if dialog_class:
                    logger.debug("[DBDialogManager] %s 濡쒕뱶 ?깃났: %s", class_name, module_path)
                    return dialog_class
            except ModuleNotFoundError as e:
                logger.debug("[DBDialogManager] 紐⑤뱢 ?놁쓬: %s (%s)", module_path, e)
                continue
            except Exception as e:
                logger.warning("[DBDialogManager] 紐⑤뱢 濡쒕뱶 ?ㅻ쪟: %s (%s)", module_path, e)
                continue
        return None

    # ??????????????????????????????????????? DB ?ㅼ씠?쇰줈洹??몃뱾????

    def _open_timescale_dialog(self) -> None:
        """TimescaleDB ?ㅼ젙 ?ㅼ씠?쇰줈洹??닿린 (data_01 寃쎈줈)"""
        try:
            self._ensure_db_ui_path("timescale")
            dialog_class = self._try_import_dialog(
                ["timescale_settings_dialog"],
                "TimescaleSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("TimescaleSettingsDialog瑜?李얠쓣 ???놁뒿?덈떎.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] TimescaleDB ?ㅼ씠?쇰줈洹??닿린 ?ㅽ뙣: %s", e, exc_info=True)
            self._show_dialog_error("TimescaleDB", e)

    def _open_mongodb_dialog(self) -> None:
        """MongoDB 釉뚮씪?곗? ?ㅼ씠?쇰줈洹??닿린 (data_01 寃쎈줈)"""
        try:
            self._ensure_db_ui_path("mongodb")
            dialog_class = self._try_import_dialog(
                ["mongodb_settings_dialog"],
                "MongoDBSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("MongoDBSettingsDialog瑜?李얠쓣 ???놁뒿?덈떎.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] MongoDB ?ㅼ씠?쇰줈洹??닿린 ?ㅽ뙣: %s", e, exc_info=True)
            self._show_dialog_error("MongoDB", e)

    def _open_redis_dialog(self) -> None:
        """Redis ?곹깭 紐⑤땲???ㅼ씠?쇰줈洹??닿린 (data_01 寃쎈줈)"""
        try:
            self._ensure_db_ui_path("redis")
            dialog_class = self._try_import_dialog(
                ["redis_settings_dialog", "widget_redis_settings"],
                "RedisSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("RedisSettingsDialog瑜?李얠쓣 ???놁뒿?덈떎.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] Redis ?ㅼ씠?쇰줈洹??닿린 ?ㅽ뙣: %s", e, exc_info=True)
            self._show_dialog_error("Redis", e)

    def _open_kafka_dialog(self) -> None:
        """Kafka 紐⑤땲???ㅼ씠?쇰줈洹??닿린 (data_01 寃쎈줈)"""
        try:
            self._ensure_db_ui_path("kafka")
            dialog_class = self._try_import_dialog(
                ["kafka_settings_dialog"],
                "KafkaSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("KafkaSettingsDialog瑜?李얠쓣 ???놁뒿?덈떎.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] Kafka ?ㅼ씠?쇰줈洹??닿린 ?ㅽ뙣: %s", e, exc_info=True)
            self._show_dialog_error("Kafka", e)

    def _open_clickhouse_dialog(self) -> None:
        """ClickHouse 紐⑤땲???ㅼ씠?쇰줈洹??닿린 (data_01 寃쎈줈)"""
        try:
            self._ensure_db_ui_path("clickhouse")
            dialog_class = self._try_import_dialog(
                ["clickhouse_settings_dialog"],
                "ClickHouseSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("ClickHouseSettingsDialog瑜?李얠쓣 ???놁뒿?덈떎.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] ClickHouse ?ㅼ씠?쇰줈洹??닿린 ?ㅽ뙣: %s", e, exc_info=True)
            self._show_dialog_error("ClickHouse", e)

    def _open_postgresql_dialog(self) -> None:
        """PostgreSQL CQRS ?ㅼ씠?쇰줈洹??닿린 (data_01 寃쎈줈)"""
        try:
            self._ensure_db_ui_path("postgres")
            dialog_class = self._try_import_dialog(
                ["postgres_dialog"],
                "PostgresEventStoreDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("PostgresEventStoreDialog瑜?李얠쓣 ???놁뒿?덈떎.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] PostgreSQL ?ㅼ씠?쇰줈洹??닿린 ?ㅽ뙣: %s", e, exc_info=True)
            self._show_dialog_error("PostgreSQL", e)

    # ??????????????????????????????????????? ?곗꽑?쒖쐞 ?ㅼ젙 ?ㅼ씠?쇰줈洹??몃뱾????

    def _open_priority_settings_dialog(self) -> None:
        """?곗꽑?쒖쐞 醫낅ぉ ?ㅼ젙 ?ㅼ씠?쇰줈洹??닿린 (06_ai/priority/ui)"""
        try:
            self._ensure_priority_ui_path()
            
            # widget_priority_settings.py?먯꽌 PrioritySettingsDialog ?대옒??濡쒕뱶
            dialog_class = self._try_import_dialog(
                ["widget_priority_settings"],
                "PrioritySettingsDialog",
            )
            
            if dialog_class is None:
                raise ModuleNotFoundError(
                    "PrioritySettingsDialog瑜?李얠쓣 ???놁뒿?덈떎.\n"
                    "寃쎈줈: src/06_ai/priority/ui/widget_priority_settings.py"
                )
            
            # ?ㅼ씠?쇰줈洹??앹꽦 諛??쒖떆
            dlg = dialog_class(parent=self.main_window)
            
            # QDialog??寃쎌슦 exec_(), ?꾨땲硫?show()
            if isinstance(dlg, QDialog):
                dlg.exec_()
            else:
                dlg.show()
                
            logger.info("[DBDialogManager] ?곗꽑?쒖쐞 ?ㅼ젙 ?ㅼ씠?쇰줈洹??대┝")
            
        except Exception as e:
            logger.error("[DBDialogManager] ?곗꽑?쒖쐞 ?ㅼ젙 ?ㅼ씠?쇰줈洹??닿린 ?ㅽ뙣: %s", e, exc_info=True)
            QMessageBox.critical(
                self.main_window,
                "?곗꽑?쒖쐞 ?ㅼ젙 ?ㅻ쪟",
                f"?곗꽑?쒖쐞 ?ㅼ젙 ?ㅼ씠?쇰줈洹몃? 遺덈윭?????놁뒿?덈떎.\n\n"
                f"?ㅻ쪟: {str(e)}\n\n"
                f"?뺤씤 ?ы빆:\n"
                f"  1. ?뚯씪 議댁옱 ?щ?: src/06_ai/priority/ui/widget_priority_settings.py\n"
                f"  2. ?대옒?ㅻ챸: PrioritySettingsDialog\n"
                f"  3. 濡쒓렇 ?뚯씪: logs/app.log",
            )

    def _open_ml_model_selector_dialog(self) -> None:
        """ML 紐⑤뜽 ?좏깮 ?ㅼ씠?쇰줈洹??닿린 (06_ai/priority/ui)"""
        try:
            self._ensure_priority_ui_path()
            
            # widget_ml_model_selector.py?먯꽌 MLModelSelectorDialog ?대옒??濡쒕뱶
            dialog_class = self._try_import_dialog(
                ["widget_ml_model_selector"],
                "MLModelSelectorDialog",
            )
            
            if dialog_class is None:
                raise ModuleNotFoundError(
                    "MLModelSelectorDialog瑜?李얠쓣 ???놁뒿?덈떎.\n"
                    "寃쎈줈: src/06_ai/priority/ui/widget_ml_model_selector.py"
                )
            
            # ?ㅼ씠?쇰줈洹??앹꽦 諛??쒖떆
            dlg = dialog_class(parent=self.main_window)
            
            # QDialog??寃쎌슦 exec_(), ?꾨땲硫?show()
            if isinstance(dlg, QDialog):
                dlg.exec_()
            else:
                dlg.show()
                
            logger.info("[DBDialogManager] ML 紐⑤뜽 ?좏깮 ?ㅼ씠?쇰줈洹??대┝")
            
        except Exception as e:
            logger.error("[DBDialogManager] ML 紐⑤뜽 ?좏깮 ?ㅼ씠?쇰줈洹??닿린 ?ㅽ뙣: %s", e, exc_info=True)
            QMessageBox.critical(
                self.main_window,
                "ML 紐⑤뜽 ?좏깮 ?ㅻ쪟",
                f"ML 紐⑤뜽 ?좏깮 ?ㅼ씠?쇰줈洹몃? 遺덈윭?????놁뒿?덈떎.\n\n"
                f"?ㅻ쪟: {str(e)}\n\n"
                f"?뺤씤 ?ы빆:\n"
                f"  1. ?뚯씪 議댁옱 ?щ?: src/06_ai/priority/ui/widget_ml_model_selector.py\n"
                f"  2. ?대옒?ㅻ챸: MLModelSelectorDialog\n"
                f"  3. 濡쒓렇 ?뚯씪: logs/app.log",
            )

    def _open_priority_dashboard_dialog(self) -> None:
        """?곗꽑?쒖쐞 ??쒕낫???ㅼ씠?쇰줈洹??닿린 (06_ai/priority/ui)"""
        try:
            # ?곗꽑?쒖쐞 ??쒕낫?쒕뒗 蹂꾨룄 ?꾩젽???놁쑝誘濡??곗꽑?쒖쐞 ?ㅼ젙?쇰줈 ?덈궡
            logger.info("[DBDialogManager] ?곗꽑?쒖쐞 ??쒕낫?????곗꽑?쒖쐞 ?ㅼ젙?쇰줈 ?덈궡")
            QMessageBox.information(
                self.main_window,
                "?곗꽑?쒖쐞 ??쒕낫??,
                "?곗꽑?쒖쐞 ??쒕낫?쒕뒗 '?곗꽑?쒖쐞 醫낅ぉ ?ㅼ젙' 硫붾돱?먯꽌\n"
                "??쒕낫????쓣 ?듯빐 ?뺤씤?????덉뒿?덈떎.\n\n"
                "?곗꽑?쒖쐞 ?ㅼ젙 ?ㅼ씠?쇰줈洹몃? ?쎈땲??",
            )
            self._open_priority_settings_dialog()
            
        except Exception as e:
            logger.error("[DBDialogManager] ?곗꽑?쒖쐞 ??쒕낫???닿린 ?ㅽ뙣: %s", e, exc_info=True)
            QMessageBox.critical(
                self.main_window,
                "?곗꽑?쒖쐞 ??쒕낫???ㅻ쪟",
                f"?곗꽑?쒖쐞 ??쒕낫?쒕? 遺덈윭?????놁뒿?덈떎.\n\n"
                f"?ㅻ쪟: {str(e)}\n\n"
                f"???'?곗꽑?쒖쐞 醫낅ぉ ?ㅼ젙' 硫붾돱瑜??ъ슜?댁＜?몄슂.",
            )
