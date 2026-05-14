# -*- coding: utf-8 -*-
"""
분리된 컴포넌트(Persistence, BufferManager, ForwardingRegistrar)를 사용하도록
간결히 재작성된 컨트롤러입니다.
- 실제 로직(필요시) 위 컴포넌트로 위임합니다.
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QObject, QTimer
    _HAS_QT = True
except Exception:
    _HAS_QT = False

# 상대 경로로 분리된 모듈 import
try:
    from .statistics_tab_persistence import Persistence
    from .statistics_tab_buffer import BufferManager
    from .statistics_tab_forwarding import ForwardingRegistrar
except Exception:
    Persistence = None
    BufferManager = None
    ForwardingRegistrar = None

try:
    from .statistics_tab import StatisticsTab
except Exception:
    StatisticsTab = None

if _HAS_QT and StatisticsTab is not None and Persistence is not None and BufferManager is not None and ForwardingRegistrar is not None:
    class StatisticsTabController(QObject):
        """간결 컨트롤러: 컴포넌트를 조합하여 뷰와 연결"""

        def __init__(self, view: Optional[StatisticsTab] = None, parent=None):
            super().__init__(parent)
            self.view = view or StatisticsTab(parent=parent)

            # 컴포넌트 초기화
            self.persistence = Persistence()
            self.buffer = BufferManager(max_pending=int(self.persistence.settings.get("max_pending", 100000)))
            self.forwarding = ForwardingRegistrar()
            if bool(self.persistence.settings.get("enable_forwarding", True)):
                self.forwarding.register(self.add_log_entry)

            # 타이머 (flush)
            self._timer = QTimer(self)
            self._timer.setInterval(int(self.persistence.settings.get("flush_interval_ms", 200)))
            self._timer.timeout.connect(self._on_timer_flush)

            # view 연결 (간단)
            try:
                self.view.load_history_requested.connect(lambda p: self.load_history(path=p or None))
                self.view.pause_toggled.connect(self._on_pause_toggled)
                self.view.manual_refresh_requested.connect(lambda: self._do_rebuild_table_for_tab(self.view.get_active_tab()))
            except Exception:
                pass

            # 자동 타이머 시작
            if bool(self.persistence.settings.get("autostart_timer", True)):
                self._timer.start()

        # 최소한의 구현(나머지는 기존 컴포넌트에 위임)
        def add_log_entry(self, entry):
            try:
                ts = entry.get("time")
                level = entry.get("level", "INFO").upper()
                module = entry.get("module", "") or entry.get("logger", "")
                msg = entry.get("message", "") or entry.get("msg", "")
                item = {"time": ts, "level": level, "category": "", "module": module, "message": msg}
                self.buffer.append(item)
            except Exception as e:
                logger.debug("[Controller] add_log_entry failed: %s", e)

        def _on_timer_flush(self):
            # 간단히 버퍼에서 배치 추출 후 뷰에 전달(기존 로직을 재사용)
            batch_size = int(self.persistence.settings.get("flush_batch", 200))
            batch = self.buffer.pop_batch(batch_size)
            if not batch:
                try:
                    self.view.set_status_text("상태: 대기")
                except Exception:
                    pass
                return
            # 기존의 뷰 삽입 로직 호출(컨트롤러의 세부 처리는 변경하지 않음)
            for item in batch:
                try:
                    t = self.view.get_active_tab()
                    self.view.insert_table_row(t, [item.get("time", ""), item.get("level", ""), "", item.get("module", ""), item.get("message", "")])
                except Exception:
                    pass
            try:
                self.view.set_status_text(f"상태: 수신 {len(batch)}건")
            except Exception:
                pass

        # 나머지 메서드는 기존 컨트롤러 구현을 참고하여 필요 시 확장
        def _on_pause_toggled(self):
            try:
                if self._timer.isActive():
                    self._timer.stop()
                    self.view.set_status_text("상태: 일시정지")
                    self.view.set_pause_button_text("재개")
                else:
                    self._timer.start()
                    self.view.set_status_text("상태: 수신 대기")
                    self.view.set_pause_button_text("일시정지")
            except Exception:
                pass

        def load_history(self, path: Optional[str] = None, max_lines: int = 1000):
            # 기존 컨트롤러의 load_history를 그대로 호출하거나 필요한 로직을 여기에 추가하세요.
            try:
                # 간단 팩: Persistence의 설정 사용
                max_lines = int(self.persistence.settings.get("history_max_lines", max_lines))
                # 실제 파일 읽기/뷰 업데이트는 기존 구현을 복사하여 사용하면 됩니다.
                self.view.set_status_text("히스토리 로드 중...")
            except Exception:
                pass

else:
    class StatisticsTabController:
        def __init__(self, *a, **k):
            raise RuntimeError("PyQt5 또는 분리 모듈이 없습니다; Controller를 생성할 수 없습니다.")