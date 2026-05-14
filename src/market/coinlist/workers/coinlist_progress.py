"""
[Purpose]
- 코인리스트 진행 상태(프로그레스바/상태 라벨)를 큐 기반으로 관리한다.

[User Options]
- enabled: progress 표시 사용/미사용
- always_show: 빠른 작업도 항상 표시
- min_show_seconds: 빠른 작업 숨김 지연(초). always_show=True면 무시.

[Stability]
- shutdown 지원(삭제된 위젯 접근 방지)
"""

from __future__ import annotations

import time
from collections import deque

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QTimer


class ProgressController:
    def __init__(self, widget):
        self.widget = widget
        self._closed = False

        self.progress_animation = QPropertyAnimation(self.widget.progress_bar, b"value")
        self.progress_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.progress_animation.setDuration(250)

        self.progress_queue = deque(maxlen=10)

        self.current_progress = 0
        self.current_total = 0
        self.current_status = ""
        self.current_step = 0

        # options (default: 부드러움 우선)
        self.enabled = True
        self.always_show = False
        self.min_show_seconds = 0.20

        # perf throttle
        self._min_update_interval = 0.08
        self._job_started_at = 0.0
        self._last_ui_update_at = 0.0
        self._visible = False

    def set_options(self, *, enabled: bool | None = None, always_show: bool | None = None, min_show_seconds: float | None = None):
        if enabled is not None:
            self.enabled = bool(enabled)
        if always_show is not None:
            self.always_show = bool(always_show)
        if min_show_seconds is not None:
            self.min_show_seconds = max(0.0, float(min_show_seconds))

        # 옵션이 꺼지면 즉시 숨김/정리
        if self._can_touch_ui() and not self.enabled:
            try:
                self.progress_queue.clear()
                self.progress_animation.stop()
                self.widget.progress_bar.setVisible(False)
                self.widget.status_label.setVisible(False)
            except Exception:
                pass

    def shutdown(self):
        self._closed = True
        try:
            self.progress_queue.clear()
        except Exception:
            pass
        try:
            self.progress_animation.stop()
        except Exception:
            pass
        self.widget = None

    def _can_touch_ui(self) -> bool:
        return (not self._closed) and (self.widget is not None)

    def set_idle_status(self):
        if not self._can_touch_ui() or not self.enabled:
            return
        if not self.progress_queue and self.current_status == "":
            self.widget.status_label.setText("상태: 준비됨")
            self.widget.progress_bar.setValue(0)
            self._visible = False

    def start_progress(self, status: str, total_steps: int):
        if not self._can_touch_ui() or not self.enabled:
            return

        self.progress_queue.append((status, max(1, int(total_steps))))
        if len(self.progress_queue) == 1:
            self._process_progress_queue()

    def _process_progress_queue(self):
        if not self._can_touch_ui() or not self.enabled:
            return
        if not self.progress_queue:
            return

        self.current_status, self.current_total = self.progress_queue[0]
        self.current_progress = 0
        self.current_step = 0

        self._job_started_at = time.monotonic()
        self._last_ui_update_at = 0.0
        self._visible = False

        # 시작은 숨김(always_show면 즉시 보임)
        if self.always_show:
            self._ensure_visible()
        else:
            self.widget.progress_bar.setVisible(False)
            self.widget.status_label.setVisible(False)

    def _ensure_visible(self):
        if not self._can_touch_ui() or not self.enabled:
            return
        if self._visible:
            return
        self.widget.progress_bar.setVisible(True)
        self.widget.status_label.setVisible(True)
        self.widget.progress_bar.setRange(0, 100)
        self.widget.progress_bar.setValue(0)
        self._visible = True

    def _ensure_visible_if_needed(self):
        if self.always_show:
            self._ensure_visible()
            return
        if self._visible:
            return
        if (time.monotonic() - self._job_started_at) >= self.min_show_seconds:
            self._ensure_visible()

    def update_status_text(self):
        if not self._can_touch_ui() or not self.enabled:
            return

        now = time.monotonic()
        if (now - self._last_ui_update_at) < self._min_update_interval:
            return

        self._ensure_visible_if_needed()
        if not self._visible:
            return

        percent = min(100, int((self.current_step / self.current_total) * 100 if self.current_total > 0 else 0))
        self.widget.status_label.setText(f"{self.current_status} ({percent}%)")
        self._last_ui_update_at = now

    def update_progress(self, step: int):
        if not self._can_touch_ui() or not self.enabled:
            return

        self.current_step = step
        self.update_status_text()

        if self.current_total <= 0:
            return

        self._ensure_visible_if_needed()
        if not self._visible:
            return

        new_progress = min(100, int((step / self.current_total) * 100))
        if new_progress == self.current_progress:
            return

        self.progress_animation.stop()
        self.progress_animation.setStartValue(self.current_progress)
        self.progress_animation.setEndValue(new_progress)
        self.progress_animation.start()
        self.current_progress = new_progress

    def end_progress(self):
        if not self._can_touch_ui() or not self.enabled:
            return

        if not self._visible:
            self._finish_progress()
            return

        self.progress_animation.stop()
        self.progress_animation.setStartValue(self.current_progress)
        self.progress_animation.setEndValue(100)
        self.progress_animation.start()
        QTimer.singleShot(self.progress_animation.duration(), self._finish_progress)

    def _finish_progress(self):
        if not self._can_touch_ui() or not self.enabled:
            return

        if self.progress_queue:
            self.progress_queue.popleft()

        if self.progress_queue:
            self._process_progress_queue()
        else:
            self.current_status = ""
            self.current_total = 0
            self.current_progress = 0
            self.current_step = 0
            self.set_idle_status()