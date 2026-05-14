# -*- coding: utf-8 -*-
"""
statistics_settings_dialog.py
Loads statistics_settings_dialog.ui and provides a SettingsDialog that:
 - shows the UI,
 - loads initial settings into widgets,
 - supports "apply recommended", "restore defaults", "OK", "Cancel",
 - saves settings to a JSON file and calls an apply_callback with the new dict.
Place this file alongside the .ui (same folder).
"""
from __future__ import annotations
import json
import os
import logging
from typing import Any, Dict, Optional

try:
    from PyQt5 import uic
    from PyQt5.QtWidgets import QDialog, QMessageBox
    from PyQt5.QtCore import Qt
    _HAS_QT = True
except Exception:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "num_live_tabs": 3,
    "flush_interval_ms": 200,
    "flush_batch": 200,
    "max_pending": 100000,
    "enable_forwarding": True,
    "autostart_timer": True,
}

_RECOMMENDED = {
    "num_live_tabs": 2,
    "flush_interval_ms": 500,
    "flush_batch": 100,
    "max_pending": 200000,
    "enable_forwarding": True,
    "autostart_timer": True,
}

def _default_settings_path() -> str:
    layout_dir = os.path.join(os.path.expanduser("~"), ".upbit_trader")
    os.makedirs(layout_dir, exist_ok=True)
    return os.path.join(layout_dir, "statistics_tab_settings.json")

if _HAS_QT:
    class SettingsDialog(QDialog):
        def __init__(
            self,
            parent=None,
            initial_settings: Optional[Dict[str, Any]] = None,
            settings_path: Optional[str] = None,
            apply_callback=None,
            ui_filename: Optional[str] = None,
        ):
            """
            initial_settings: dict to pre-populate the dialog (overrides defaults)
            settings_path: where to save JSON (defaults to ~/.upbit_trader/statistics_tab_settings.json)
            apply_callback: callable(settings_dict) called when OK is pressed
            ui_filename: path to statistics_settings_dialog.ui (if None, looks in same folder)
            """
            super().__init__(parent)
            # determine ui path (default: same folder)
            if ui_filename is None:
                ui_filename = os.path.join(os.path.dirname(__file__), "statistics_settings_dialog.ui")
            try:
                uic.loadUi(ui_filename, self)
            except Exception as e:
                logger.exception("UI 파일 로드 실패: %s", e)
                QMessageBox.critical(self, "UI 로드 실패", f"UI 파일을 열 수 없습니다: {ui_filename}\n{e}")
                raise

            self._apply_callback = apply_callback
            self._settings_path = settings_path or _default_settings_path()

            # merge settings
            self._settings = {}
            self._settings.update(_DEFAULTS)
            if isinstance(initial_settings, dict):
                self._settings.update(initial_settings)

            # populate widgets safely
            self._populate_widgets_from_settings()

            # wire buttons
            try:
                btn_apply = getattr(self, "btn_apply_recommended", None)
                if btn_apply is not None:
                    btn_apply.clicked.connect(self._on_apply_recommended)
            except Exception:
                pass
            try:
                btn_restore = getattr(self, "btn_restore_defaults", None)
                if btn_restore is not None:
                    btn_restore.clicked.connect(self._on_restore_defaults)
            except Exception:
                pass
            try:
                btn_ok = getattr(self, "btn_ok", None)
                if btn_ok is not None:
                    btn_ok.clicked.connect(self._on_ok)
            except Exception:
                pass
            try:
                btn_cancel = getattr(self, "btn_cancel", None)
                if btn_cancel is not None:
                    btn_cancel.clicked.connect(self.reject)
            except Exception:
                pass

        # widget helpers
        def _populate_widgets_from_settings(self) -> None:
            s = self._settings
            try:
                sb = getattr(self, "sb_num_live_tabs", None)
                if sb is not None:
                    sb.setValue(int(s.get("num_live_tabs", _DEFAULTS["num_live_tabs"])))
            except Exception:
                pass
            try:
                sb = getattr(self, "sb_flush_interval", None)
                if sb is not None:
                    sb.setValue(int(s.get("flush_interval_ms", _DEFAULTS["flush_interval_ms"])))
            except Exception:
                pass
            try:
                sb = getattr(self, "sb_flush_batch", None)
                if sb is not None:
                    sb.setValue(int(s.get("flush_batch", _DEFAULTS["flush_batch"])))
            except Exception:
                pass
            try:
                sb = getattr(self, "sb_max_pending", None)
                if sb is not None:
                    sb.setValue(int(s.get("max_pending", _DEFAULTS["max_pending"])))
            except Exception:
                pass
            try:
                chk = getattr(self, "chk_enable_forwarding", None)
                if chk is not None:
                    chk.setChecked(bool(s.get("enable_forwarding", _DEFAULTS["enable_forwarding"])))
            except Exception:
                pass
            try:
                chk = getattr(self, "chk_autostart_timer", None)
                if chk is not None:
                    chk.setChecked(bool(s.get("autostart_timer", _DEFAULTS["autostart_timer"])))
            except Exception:
                pass

        def _read_values_from_widgets(self) -> Dict[str, Any]:
            new = {}
            try:
                sb = getattr(self, "sb_num_live_tabs", None)
                if sb is not None:
                    new["num_live_tabs"] = int(sb.value())
            except Exception:
                new["num_live_tabs"] = _DEFAULTS["num_live_tabs"]
            try:
                sb = getattr(self, "sb_flush_interval", None)
                if sb is not None:
                    new["flush_interval_ms"] = int(sb.value())
            except Exception:
                new["flush_interval_ms"] = _DEFAULTS["flush_interval_ms"]
            try:
                sb = getattr(self, "sb_flush_batch", None)
                if sb is not None:
                    new["flush_batch"] = int(sb.value())
            except Exception:
                new["flush_batch"] = _DEFAULTS["flush_batch"]
            try:
                sb = getattr(self, "sb_max_pending", None)
                if sb is not None:
                    new["max_pending"] = int(sb.value())
            except Exception:
                new["max_pending"] = _DEFAULTS["max_pending"]
            try:
                chk = getattr(self, "chk_enable_forwarding", None)
                if chk is not None:
                    new["enable_forwarding"] = bool(chk.isChecked())
            except Exception:
                new["enable_forwarding"] = _DEFAULTS["enable_forwarding"]
            try:
                chk = getattr(self, "chk_autostart_timer", None)
                if chk is not None:
                    new["autostart_timer"] = bool(chk.isChecked())
            except Exception:
                new["autostart_timer"] = _DEFAULTS["autostart_timer"]
            return new

        def _on_apply_recommended(self) -> None:
            # apply recommended preset values to widgets (not saving yet)
            try:
                vals = _RECOMMENDED
                sb = getattr(self, "sb_num_live_tabs", None)
                if sb is not None:
                    sb.setValue(int(vals["num_live_tabs"]))
                sb = getattr(self, "sb_flush_interval", None)
                if sb is not None:
                    sb.setValue(int(vals["flush_interval_ms"]))
                sb = getattr(self, "sb_flush_batch", None)
                if sb is not None:
                    sb.setValue(int(vals["flush_batch"]))
                sb = getattr(self, "sb_max_pending", None)
                if sb is not None:
                    sb.setValue(int(vals["max_pending"]))
                chk = getattr(self, "chk_enable_forwarding", None)
                if chk is not None:
                    chk.setChecked(bool(vals["enable_forwarding"]))
                chk = getattr(self, "chk_autostart_timer", None)
                if chk is not None:
                    chk.setChecked(bool(vals["autostart_timer"]))
            except Exception as e:
                logger.exception("권장값 적용 실패: %s", e)

        def _on_restore_defaults(self) -> None:
            try:
                vals = _DEFAULTS
                sb = getattr(self, "sb_num_live_tabs", None)
                if sb is not None:
                    sb.setValue(int(vals["num_live_tabs"]))
                sb = getattr(self, "sb_flush_interval", None)
                if sb is not None:
                    sb.setValue(int(vals["flush_interval_ms"]))
                sb = getattr(self, "sb_flush_batch", None)
                if sb is not None:
                    sb.setValue(int(vals["flush_batch"]))
                sb = getattr(self, "sb_max_pending", None)
                if sb is not None:
                    sb.setValue(int(vals["max_pending"]))
                chk = getattr(self, "chk_enable_forwarding", None)
                if chk is not None:
                    chk.setChecked(bool(vals["enable_forwarding"]))
                chk = getattr(self, "chk_autostart_timer", None)
                if chk is not None:
                    chk.setChecked(bool(vals["autostart_timer"]))
            except Exception as e:
                logger.exception("기본값 복원 실패: %s", e)

        def _on_ok(self) -> None:
            # read values, save to file, and call apply callback if present
            new_vals = self._read_values_from_widgets()
            try:
                # save JSON
                try:
                    d = os.path.dirname(self._settings_path)
                    if d and not os.path.isdir(d):
                        os.makedirs(d, exist_ok=True)
                    with open(self._settings_path, "w", encoding="utf-8") as f:
                        json.dump(new_vals, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.exception("설정 저장 실패: %s", e)
                    QMessageBox.warning(self, "저장 실패", f"설정 파일을 저장하지 못했습니다:\n{e}")

                # call apply callback
                if callable(self._apply_callback):
                    try:
                        self._apply_callback(new_vals)
                    except Exception as e:
                        logger.exception("apply_callback 호출 실패: %s", e)
                self.accept()
            except Exception as e:
                logger.exception("OK 처리 실패: %s", e)
                QMessageBox.critical(self, "오류", f"설정을 적용하는 중 오류가 발생했습니다:\n{e}")

    def show_settings_dialog(parent=None, initial_settings: Optional[Dict[str, Any]] = None, apply_callback=None, settings_path: Optional[str] = None):
        """
        Convenience function to show the settings dialog modal.
        - initial_settings: dict to pre-populate dialog
        - apply_callback: callable(settings_dict) when OK pressed
        - settings_path: where to save settings (optional)
        """
        settings_path = settings_path or _default_settings_path()
        dlg = SettingsDialog(parent=parent, initial_settings=initial_settings, settings_path=settings_path, apply_callback=apply_callback)
        return dlg.exec_()

else:
    # stub for environments without PyQt
    class SettingsDialog:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PyQt not available")

    def show_settings_dialog(*args, **kwargs):
        raise RuntimeError("PyQt not available")