#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
timescale_ui_helpers.py

Small UI helper utilities for the Timescale dialog.

Responsibilities:
- Password toggle widget for QLineEdit
- Placeholder display helper for QTableView
- Safe CSV export wrapper that uses timescale_utils
- Small helpers to keep TimescaleDialog concise and testable
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from PyQt5 import QtWidgets, QtGui, QtCore

from ..timescale_utils import timescale_save_model_to_csv

logger = logging.getLogger("data.timescale.timescale_ui_helpers")
if logger.level == logging.NOTSET:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] [timescale_ui_helpers] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
logger.propagate = False


def add_password_toggle(line_edit: QtWidgets.QLineEdit) -> None:
    """
    Adds a small toggle button inside a QLineEdit to show/hide password.
    Non-destructive: preserves any existing resizeEvent by wrapping it.
    """
    try:
        if line_edit is None:
            return
        btn = QtWidgets.QToolButton(line_edit)
        btn.setCheckable(True)
        btn.setText("👁")
        btn.setToolTip("비밀번호 표시 토글")
        btn.setStyleSheet("border:none; background:transparent;")
        btn_size = btn.sizeHint().width()
        # adjust padding
        line_edit.setStyleSheet(f"QLineEdit {{ padding-right: {btn_size + 6}px; }}")

        def position_button():
            try:
                rect = line_edit.rect()
                btn.move(rect.right() - btn.width() - 2, (rect.height() - btn.height()) // 2)
            except Exception:
                pass

        orig_resize = getattr(line_edit, "resizeEvent", None)

        def resize_event(ev):
            position_button()
            if orig_resize:
                try:
                    orig_resize(ev)
                except Exception:
                    pass

        line_edit.resizeEvent = resize_event  # type: ignore
        position_button()

        def toggle(checked):
            line_edit.setEchoMode(QtWidgets.QLineEdit.Normal if checked else QtWidgets.QLineEdit.Password)
            btn.setText("🙈" if checked else "👁")

        btn.toggled.connect(toggle)
        line_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        btn.setChecked(False)
        btn.show()
    except Exception:
        logger.exception("add_password_toggle failed")


def show_select_symbol_placeholder(table: QtWidgets.QTableView, message: str = None) -> None:
    """
    Display a single-row, greyed message in the provided QTableView to indicate that the user should select a symbol.
    """
    try:
        if message is None:
            message = "종목을 선택하면 해당 심볼·타임프레임의 데이터가 표시됩니다."
        model = QtGui.QStandardItemModel(1, 1)
        model.setHorizontalHeaderLabels(["message"])
        item = QtGui.QStandardItem(message)
        item.setForeground(QtGui.QBrush(QtGui.QColor("gray")))
        model.setItem(0, 0, item)
        table.setModel(model)
    except Exception:
        logger.exception("show_select_symbol_placeholder failed")


def export_tableview_to_csv(tableview: QtWidgets.QTableView, parent: Optional[QtWidgets.QWidget] = None) -> Optional[str]:
    """
    Show save dialog and export the current model of tableview to CSV using timescale_save_model_to_csv.
    Returns the path when saved, otherwise None.
    """
    try:
        if tableview is None or tableview.model() is None:
            QtWidgets.QMessageBox.information(parent or tableview, "CSV 내보내기", "내보낼 데이터가 없습니다.")
            return None
        path, _ = QtWidgets.QFileDialog.getSaveFileName(parent or tableview, "CSV로 저장", "", "CSV Files (*.csv);;All Files (*)")
        if not path:
            return None
        model = tableview.model()
        timescale_save_model_to_csv(model, path)
        QtWidgets.QMessageBox.information(parent or tableview, "CSV 내보내기", f"CSV 저장 완료: {path}")
        return path
    except Exception:
        logger.exception("export_tableview_to_csv failed")
        QtWidgets.QMessageBox.warning(parent or tableview, "CSV 내보내기", "저장 중 오류가 발생했습니다.")
        return None