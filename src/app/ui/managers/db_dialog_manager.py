"""
DBDialogManager - DB ?¤ì´?¼ë¡œê·?ê´€ë¦?(v11.0)

ì±…ìž„:
- ê°?DB ?¤ì •/ëª¨ë‹ˆ???¤ì´?¼ë¡œê·??´ê¸° (_open_*_dialog ë©”ì„œ??
- ?°ì„ ?œìœ„ ?¤ì • ?¤ì´?¼ë¡œê·?ê´€ë¦?(AI/ML ?¹ì…˜?ì„œ ?°ì´?°ë² ?´ìŠ¤ ?¹ì…˜?¼ë¡œ ?´ë™)
- ?¤ì´?¼ë¡œê·?ëª¨ë“ˆ ?™ì  ë¡œë”© ë°?ImportError ?ˆì „ ì²˜ë¦¬
- ?¤ì´?¼ë¡œê·??¤ë¥˜ ë©”ì‹œì§€ ?œì‹œ

ë³€ê²??´ë ¥:
- v11.0: ?°ì„ ?œìœ„ ê´€??3ê°??¤ì´?¼ë¡œê·?ê²½ë¡œ ë°??´ëž˜?¤ëª… ?˜ì •
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
    """DB ?¤ì´?¼ë¡œê·?ê´€ë¦?- ê°?DB???¤ì •/ëª¨ë‹ˆ???¤ì´?¼ë¡œê·¸ë? ?™ì ?¼ë¡œ ë¡œë“œ?˜ê³  ?´ê¸°."""

    def __init__(self, main_window: Any) -> None:
        self.main_window = main_window

    # ?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€ ? í‹¸ë¦¬í‹° ?€?€

    @staticmethod
    def _ensure_data_path() -> None:
        """src/data_01/ ë¥?sys.path ??ì¶”ê?"""
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
        """src/11_server/ui/settings/ ë¥?sys.path ??ì¶”ê?"""
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
        """src/data_01/{db_name}/ui/ ë¥?sys.path ??ì¶”ê?"""
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
        """src/06_ai/priority/ui/ ë¥?sys.path ??ì¶”ê?"""
        _ui_dir = os.path.normpath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "..", "06_ai", "priority", "ui",
            )
        )
        if _ui_dir not in sys.path:
            sys.path.insert(0, _ui_dir)
            logger.debug("[DBDialogManager] sys.path ì¶”ê?: %s", _ui_dir)

    def _show_dialog_error(self, db_name: str, exc: Exception) -> None:
        """?¤ì´?¼ë¡œê·?ë¡œë“œ ?¤íŒ¨ ???¬ìš©??ì¹œí™”???¤ë¥˜ ë©”ì‹œì§€ ?œì‹œ"""
        QMessageBox.critical(
            self.main_window,
            f"{db_name} ?¤ì´?¼ë¡œê·??´ê¸° ?¤íŒ¨",
            f"?¤ë¥˜: {str(exc)}\n\n"
            f"?•ì¸ ?¬í•­:\n"
            f"  1. Docker ì»¨í…Œ?´ë„ˆ ?¤í–‰ ?¬ë? ?•ì¸ (docker ps)\n"
            f"  2. DB ?°ê²° ?¤ì • ?•ì¸ (?¸ìŠ¤???¬íŠ¸/?¬ìš©??\n"
            f"  3. ë¡œê·¸ ?Œì¼ ?•ì¸: logs/app.log\n\n"
            f"ëª¨ë“ˆ ê²½ë¡œ: src/data_01/{db_name.lower()}/ui/",
        )

    @staticmethod
    def _try_import_dialog(module_paths: list, class_name: str) -> Optional[Any]:
        """?„ë³´ ëª¨ë“ˆ ê²½ë¡œ?ì„œ ?¤ì´?¼ë¡œê·??´ëž˜?¤ë? ?™ì  ?„í¬?¸í•©?ˆë‹¤."""
        for module_path in module_paths:
            try:
                mod = importlib.import_module(module_path)
                dialog_class = getattr(mod, class_name, None)
                if dialog_class:
                    logger.debug("[DBDialogManager] %s ë¡œë“œ ?±ê³µ: %s", class_name, module_path)
                    return dialog_class
            except ModuleNotFoundError as e:
                logger.debug("[DBDialogManager] ëª¨ë“ˆ ?†ìŒ: %s (%s)", module_path, e)
                continue
            except Exception as e:
                logger.warning("[DBDialogManager] ëª¨ë“ˆ ë¡œë“œ ?¤ë¥˜: %s (%s)", module_path, e)
                continue
        return None

    # ?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€ DB ?¤ì´?¼ë¡œê·??¸ë“¤???€?€

    def _open_timescale_dialog(self) -> None:
        """TimescaleDB ?¤ì • ?¤ì´?¼ë¡œê·??´ê¸° (data_01 ê²½ë¡œ)"""
        try:
            self._ensure_db_ui_path("timescale")
            dialog_class = self._try_import_dialog(
                ["timescale_settings_dialog"],
                "TimescaleSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("TimescaleSettingsDialogë¥?ì°¾ì„ ???†ìŠµ?ˆë‹¤.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] TimescaleDB ?¤ì´?¼ë¡œê·??´ê¸° ?¤íŒ¨: %s", e, exc_info=True)
            self._show_dialog_error("TimescaleDB", e)

    def _open_mongodb_dialog(self) -> None:
        """MongoDB ë¸Œë¼?°ì? ?¤ì´?¼ë¡œê·??´ê¸° (data_01 ê²½ë¡œ)"""
        try:
            self._ensure_db_ui_path("mongodb")
            dialog_class = self._try_import_dialog(
                ["mongodb_settings_dialog"],
                "MongoDBSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("MongoDBSettingsDialogë¥?ì°¾ì„ ???†ìŠµ?ˆë‹¤.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] MongoDB ?¤ì´?¼ë¡œê·??´ê¸° ?¤íŒ¨: %s", e, exc_info=True)
            self._show_dialog_error("MongoDB", e)

    def _open_redis_dialog(self) -> None:
        """Redis ?íƒœ ëª¨ë‹ˆ???¤ì´?¼ë¡œê·??´ê¸° (data_01 ê²½ë¡œ)"""
        try:
            self._ensure_db_ui_path("redis")
            dialog_class = self._try_import_dialog(
                ["redis_settings_dialog", "widget_redis_settings"],
                "RedisSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("RedisSettingsDialogë¥?ì°¾ì„ ???†ìŠµ?ˆë‹¤.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] Redis ?¤ì´?¼ë¡œê·??´ê¸° ?¤íŒ¨: %s", e, exc_info=True)
            self._show_dialog_error("Redis", e)

    def _open_kafka_dialog(self) -> None:
        """Kafka ëª¨ë‹ˆ???¤ì´?¼ë¡œê·??´ê¸° (data_01 ê²½ë¡œ)"""
        try:
            self._ensure_db_ui_path("kafka")
            dialog_class = self._try_import_dialog(
                ["kafka_settings_dialog"],
                "KafkaSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("KafkaSettingsDialogë¥?ì°¾ì„ ???†ìŠµ?ˆë‹¤.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] Kafka ?¤ì´?¼ë¡œê·??´ê¸° ?¤íŒ¨: %s", e, exc_info=True)
            self._show_dialog_error("Kafka", e)

    def _open_clickhouse_dialog(self) -> None:
        """ClickHouse ëª¨ë‹ˆ???¤ì´?¼ë¡œê·??´ê¸° (data_01 ê²½ë¡œ)"""
        try:
            self._ensure_db_ui_path("clickhouse")
            dialog_class = self._try_import_dialog(
                ["clickhouse_settings_dialog"],
                "ClickHouseSettingsDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("ClickHouseSettingsDialogë¥?ì°¾ì„ ???†ìŠµ?ˆë‹¤.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] ClickHouse ?¤ì´?¼ë¡œê·??´ê¸° ?¤íŒ¨: %s", e, exc_info=True)
            self._show_dialog_error("ClickHouse", e)

    def _open_postgresql_dialog(self) -> None:
        """PostgreSQL CQRS ?¤ì´?¼ë¡œê·??´ê¸° (data_01 ê²½ë¡œ)"""
        try:
            self._ensure_db_ui_path("postgres")
            dialog_class = self._try_import_dialog(
                ["postgres_dialog"],
                "PostgresEventStoreDialog",
            )
            if dialog_class is None:
                raise ModuleNotFoundError("PostgresEventStoreDialogë¥?ì°¾ì„ ???†ìŠµ?ˆë‹¤.")
            dlg = dialog_class(self.main_window)
            dlg.exec_()
        except Exception as e:
            logger.warning("[DBDialogManager] PostgreSQL ?¤ì´?¼ë¡œê·??´ê¸° ?¤íŒ¨: %s", e, exc_info=True)
            self._show_dialog_error("PostgreSQL", e)

    # ?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€ ?°ì„ ?œìœ„ ?¤ì • ?¤ì´?¼ë¡œê·??¸ë“¤???€?€

    def _open_priority_settings_dialog(self) -> None:
        """?°ì„ ?œìœ„ ì¢…ëª© ?¤ì • ?¤ì´?¼ë¡œê·??´ê¸° (06_ai/priority/ui)"""
        try:
            self._ensure_priority_ui_path()
            
            # widget_priority_settings.py?ì„œ PrioritySettingsDialog ?´ëž˜??ë¡œë“œ
            dialog_class = self._try_import_dialog(
                ["widget_priority_settings"],
                "PrioritySettingsDialog",
            )
            
            if dialog_class is None:
                raise ModuleNotFoundError(
                    "PrioritySettingsDialogë¥?ì°¾ì„ ???†ìŠµ?ˆë‹¤.\n"
                    "ê²½ë¡œ: src/06_ai/priority/ui/widget_priority_settings.py"
                )
            
            # ?¤ì´?¼ë¡œê·??ì„± ë°??œì‹œ
            dlg = dialog_class(parent=self.main_window)
            
            # QDialog??ê²½ìš° exec_(), ?„ë‹ˆë©?show()
            if isinstance(dlg, QDialog):
                dlg.exec_()
            else:
                dlg.show()
                
            logger.info("[DBDialogManager] ?°ì„ ?œìœ„ ?¤ì • ?¤ì´?¼ë¡œê·??´ë¦¼")
            
        except Exception as e:
            logger.error("[DBDialogManager] ?°ì„ ?œìœ„ ?¤ì • ?¤ì´?¼ë¡œê·??´ê¸° ?¤íŒ¨: %s", e, exc_info=True)
            QMessageBox.critical(
                self.main_window,
                "?°ì„ ?œìœ„ ?¤ì • ?¤ë¥˜",
                f"?°ì„ ?œìœ„ ?¤ì • ?¤ì´?¼ë¡œê·¸ë? ë¶ˆëŸ¬?????†ìŠµ?ˆë‹¤.\n\n"
                f"?¤ë¥˜: {str(e)}\n\n"
                f"?•ì¸ ?¬í•­:\n"
                f"  1. ?Œì¼ ì¡´ìž¬ ?¬ë?: src/06_ai/priority/ui/widget_priority_settings.py\n"
                f"  2. ?´ëž˜?¤ëª…: PrioritySettingsDialog\n"
                f"  3. ë¡œê·¸ ?Œì¼: logs/app.log",
            )

    def _open_ml_model_selector_dialog(self) -> None:
        """ML ëª¨ë¸ ? íƒ ?¤ì´?¼ë¡œê·??´ê¸° (06_ai/priority/ui)"""
        try:
            self._ensure_priority_ui_path()
            
            # widget_ml_model_selector.py?ì„œ MLModelSelectorDialog ?´ëž˜??ë¡œë“œ
            dialog_class = self._try_import_dialog(
                ["widget_ml_model_selector"],
                "MLModelSelectorDialog",
            )
            
            if dialog_class is None:
                raise ModuleNotFoundError(
                    "MLModelSelectorDialogë¥?ì°¾ì„ ???†ìŠµ?ˆë‹¤.\n"
                    "ê²½ë¡œ: src/06_ai/priority/ui/widget_ml_model_selector.py"
                )
            
            # ?¤ì´?¼ë¡œê·??ì„± ë°??œì‹œ
            dlg = dialog_class(parent=self.main_window)
            
            # QDialog??ê²½ìš° exec_(), ?„ë‹ˆë©?show()
            if isinstance(dlg, QDialog):
                dlg.exec_()
            else:
                dlg.show()
                
            logger.info("[DBDialogManager] ML ëª¨ë¸ ? íƒ ?¤ì´?¼ë¡œê·??´ë¦¼")
            
        except Exception as e:
            logger.error("[DBDialogManager] ML ëª¨ë¸ ? íƒ ?¤ì´?¼ë¡œê·??´ê¸° ?¤íŒ¨: %s", e, exc_info=True)
            QMessageBox.critical(
                self.main_window,
                "ML ëª¨ë¸ ? íƒ ?¤ë¥˜",
                f"ML ëª¨ë¸ ? íƒ ?¤ì´?¼ë¡œê·¸ë? ë¶ˆëŸ¬?????†ìŠµ?ˆë‹¤.\n\n"
                f"?¤ë¥˜: {str(e)}\n\n"
                f"?•ì¸ ?¬í•­:\n"
                f"  1. ?Œì¼ ì¡´ìž¬ ?¬ë?: src/06_ai/priority/ui/widget_ml_model_selector.py\n"
                f"  2. ?´ëž˜?¤ëª…: MLModelSelectorDialog\n"
                f"  3. ë¡œê·¸ ?Œì¼: logs/app.log",
            )

    def _open_priority_dashboard_dialog(self) -> None:
        """?°ì„ ?œìœ„ ?€?œë³´???¤ì´?¼ë¡œê·??´ê¸° (06_ai/priority/ui)"""
        try:
            # ?°ì„ ?œìœ„ ?€?œë³´?œëŠ” ë³„ë„ ?„ì ¯???†ìœ¼ë¯€ë¡??°ì„ ?œìœ„ ?¤ì •?¼ë¡œ ?ˆë‚´
            logger.info("[DBDialogManager] ?°ì„ ?œìœ„ ?€?œë³´?????°ì„ ?œìœ„ ?¤ì •?¼ë¡œ ?ˆë‚´")
            QMessageBox.information(
                self.main_window,
                "?°ì„ ?œìœ„ ?€?œë³´??,
                "?°ì„ ?œìœ„ ?€?œë³´?œëŠ” '?°ì„ ?œìœ„ ì¢…ëª© ?¤ì •' ë©”ë‰´?ì„œ\n"
                "?€?œë³´????„ ?µí•´ ?•ì¸?????ˆìŠµ?ˆë‹¤.\n\n"
                "?°ì„ ?œìœ„ ?¤ì • ?¤ì´?¼ë¡œê·¸ë? ?½ë‹ˆ??",
            )
            self._open_priority_settings_dialog()
            
        except Exception as e:
            logger.error("[DBDialogManager] ?°ì„ ?œìœ„ ?€?œë³´???´ê¸° ?¤íŒ¨: %s", e, exc_info=True)
            QMessageBox.critical(
                self.main_window,
                "?°ì„ ?œìœ„ ?€?œë³´???¤ë¥˜",
                f"?°ì„ ?œìœ„ ?€?œë³´?œë? ë¶ˆëŸ¬?????†ìŠµ?ˆë‹¤.\n\n"
                f"?¤ë¥˜: {str(e)}\n\n"
                f"?€??'?°ì„ ?œìœ„ ì¢…ëª© ?¤ì •' ë©”ë‰´ë¥??¬ìš©?´ì£¼?¸ìš”.",
            )
