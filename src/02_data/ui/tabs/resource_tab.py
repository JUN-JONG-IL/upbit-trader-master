# -*- coding: utf-8 -*-
"""Tab 6: 시스템 리소스 제어 로직"""
from __future__ import annotations
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:
    class ResourceTab(QWidget):
        """Tab 6: 시스템 리소스 — uic.loadUi() 기반 자립형 위젯"""

        def __init__(self, parent=None):
            super().__init__(parent)
            ui_path = os.path.join(os.path.dirname(__file__), "resource_tab.ui")
            try:
                uic.loadUi(ui_path, self)
            except Exception as exc:
                logger.warning("[ResourceTab] UI 파일 로드 실패: %s", exc)

            self._timer = QTimer(self)
            self._timer.setInterval(3000)
            self._timer.timeout.connect(self._update_ui)

        def start_updates(self, interval_ms: int = 3000) -> None:
            self._timer.setInterval(max(1000, int(interval_ms)))
            self._timer.start()
            self._update_ui()  # 즉시 1회 갱신

        def stop_updates(self) -> None:
            self._timer.stop()

        def _update_ui(self) -> None:
            """1초마다 psutil 기반 시스템 리소스 갱신"""
            try:
                import psutil  # type: ignore
                cpu_pct = psutil.cpu_percent(interval=None)
                if hasattr(self, "progress_cpu"):
                    self.progress_cpu.setValue(int(cpu_pct))
                if hasattr(self, "label_cpu_value"):
                    self.label_cpu_value.setText(f"{cpu_pct:.1f} %")
                mem = psutil.virtual_memory()
                mem_pct = mem.percent
                if hasattr(self, "progress_memory"):
                    self.progress_memory.setValue(int(mem_pct))
                if hasattr(self, "label_memory_value"):
                    self.label_memory_value.setText(f"{mem_pct:.1f} %")
                disk = psutil.disk_usage("/")
                disk_pct = disk.percent
                if hasattr(self, "progress_disk"):
                    self.progress_disk.setValue(int(disk_pct))
                if hasattr(self, "label_disk_value"):
                    self.label_disk_value.setText(f"{disk_pct:.1f} %")
                net = psutil.net_io_counters()
                if hasattr(self, "label_network_value"):
                    self.label_network_value.setText(
                        f"송신: {net.bytes_sent // 1024} KB | 수신: {net.bytes_recv // 1024} KB"
                    )
                proc = psutil.Process()
                if hasattr(self, "label_pid_value"):
                    self.label_pid_value.setText(str(proc.pid))
                if hasattr(self, "label_threads_value"):
                    self.label_threads_value.setText(str(proc.num_threads()))
            except Exception as exc:
                logger.debug("[ResourceTab] 시스템 리소스 갱신 실패: %s", exc)

else:
    class ResourceTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""
        def __init__(self, parent=None):
            pass
        def start_updates(self, interval_ms: int = 3000) -> None:
            pass
        def stop_updates(self) -> None:
            pass
