"""
Export Manager - Export charts to various formats

This module provides functionality to export charts and layouts to different file formats.
Supports PNG, PDF, HTML, SVG exports with QThread async processing.

Version: v2.0
Last Modified: 2026-02-09 | Copilot
"""

import logging
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
try:
    from PyQt5.QtWidgets import QWidget, QApplication, QFileDialog, QMessageBox
    from PyQt5.QtCore import QThread, Qt
    from PyQt5.QtGui import QPixmap
except Exception as _e:
    QWidget = None  # type: ignore[assignment,misc]
    QFileDialog = None  # type: ignore[assignment,misc]
    QMessageBox = None  # type: ignore[assignment,misc]
    QPixmap = None  # type: ignore[assignment,misc]
    QThread = None  # type: ignore[assignment,misc]
    Qt = None  # type: ignore[assignment,misc]

log = logging.getLogger(__name__)


class ExportManager:
    """Chart export utilities."""

    @staticmethod
    def export_widget_to_png(
        widget,
        default_filename: str = "chart.png",
        scale: float = 2.0,
        parent: Optional[object] = None,
    ) -> bool:
        """Export a widget to a PNG file via a save dialog.

        Args:
            widget: The QWidget to capture.
            default_filename: Suggested filename shown in the dialog.
            scale: Pixel scaling factor for higher-resolution output.
            parent: Optional parent widget for the dialog.

        Returns:
            True if the file was saved successfully, False otherwise.
        """
        if QFileDialog is None or widget is None:
            return False

        filepath, _ = QFileDialog.getSaveFileName(
            parent, "차트 이미지 저장", default_filename, "PNG (*.png)"
        )
        if not filepath:
            return False

        if not filepath.lower().endswith(".png"):
            filepath += ".png"

        pixmap = widget.grab()
        if scale > 1.0:
            w = int(pixmap.width() * scale)
            h = int(pixmap.height() * scale)
            pixmap = pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        return pixmap.save(filepath, "PNG", 95)
