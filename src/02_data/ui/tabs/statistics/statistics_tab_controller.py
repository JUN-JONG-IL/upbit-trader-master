# -*- coding: utf-8 -*-
"""
분리된 컴포넌트(Persistence, BufferManager, ForwardingRegistrar)를 사용하도록
간결히 재작성된 컨트롤러입니다.
- 실제 로직(필요시) 위 컴포넌트로 위임합니다.
- 뷰는 가능한 경우에만 생성(lazy)하며, 테스트/비-GUI 환경에서 None으로 둘 수 있습니다.
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

if _HAS_QT and Persistence is not None and BufferManager is not None and ForwardingRegistrar is not None:
    class StatisticsTabController(QObject):
        """간결 컨트롤러: 컴포넌트를 조합하여 뷰와 연결"""

        def __init__(self, view: Optional["StatisticsTab"] = None, parent=None, create_view_if_missing: bool = True):
            """
            생성자 변경 사항:
            - view 인스턴스가 전달되면 이를 사용합니다.
            - 전달되지 않았고 create_view_if_missing이 True이면 StatisticsTab 클래스가 사용 가능한 경우에만 뷰를 생성합니다.
            - create_view_if_missing=False 또는 StatisticsTab 클래스가 없으면 self.view는 None으로 남아 비-GUI/테스트 환경에서 안전합니다.
            """
            super().__init__(parent)

            # 뷰 인스턴스 처리: 전달된 뷰 우선, 없으면 옵션에 따라 지연 생성
            if view is not None:
                self.view = view
            else:
                if create_view_if_missing and StatisticsTab is not None:
                    try:
                        self.view = StatisticsTab(parent=parent)
                    except Exception as exc:
                        # 뷰 생성에 실패하면 None으로 두고 로그만 남김
                        logger.debug("[Controller] StatisticsTab 생성 실패: %s", exc)
                        self.view = None
                else:
                    self.view = None

            # 컴포넌트 초기화
            self.persistence = Persistence()
            self.buffer = BufferManager(max_pending=int(self.persistence.settings.get("max_pending", 100000)))
            self.forwarding = ForwardingRegistrar()
            if bool(self.persistence.settings.get("enable_forwarding", True)):
                # forwarding은 뷰와 독립적으로 동작하므로 등록 시점에 뷰 필요 없음
                self.forwarding.register(self.add_log_entry)

            # 타이머 (flush)
            # QTimer는 QObject를 상속하므로 self(Controller)가 QObject일 때만 생성
            self._timer: Optional[QTimer] = None
            try:
                self._timer = QTimer(self)
                self._timer.setInterval(int(self.persistence.settings.get("flush_interval_ms", 200)))
                self._timer.timeout.connect(self._on_timer_flush)
            except Exception as exc:
                logger.debug("[Controller] QTimer 초기화 실패: %s", exc)
                self._timer = None

            # view 연결 (간단) — view가 None인 경우 연결을 건너뜀
            if self.view is not None:
                try:
                    self.view.load_history_requested.connect(lambda p: self.load_history(path=p or None))
                    self.view.pause_toggled.connect(self._on_pause_toggled)
                    self.view.manual_refresh_requested.connect(lambda: self._do_rebuild_table_for_tab(self.view.get_active_tab()))
                except Exception as exc:
                    logger.debug("[Controller] view 시그널 연결 실패: %s", exc)

            # 자동 타이머 시작 (타이머가 존재할 때만)
            try:
                if self._timer is not None and bool(self.persistence.settings.get("autostart_timer", True)):
                    self._timer.start()
            except Exception as exc:
                logger.debug("[Controller] 타이머 자동 시작 실패: %s", exc)

        # 최소한의 구현(나머지는 기존 컴포넌트에 위임)
        def add_log_entry(self, entry):
            try:
                ts = entry.get("time")
                level = (entry.get("level") or "INFO").upper()
                module = (entry.get("module") or "") or entry.get("logger", "")
                msg = (entry.get("message") or "") or entry.get("msg", "")
                item = {"time": ts, "level": level, "category": "", "module": module, "message": msg}
                self.buffer.append(item)
            except Exception as e:
                logger.debug("[Controller] add_log_entry failed: %s", e)

        def _on_timer_flush(self):
            # 간단히 버퍼에서 배치 추출 후 뷰에 전달(뷰가 없으면 버퍼를 비우기만 함)
            batch_size = int(self.persistence.settings.get("flush_batch", 200))
            batch = self.buffer.pop_batch(batch_size)
            if not batch:
                if self.view is not None:
                    try:
                        self.view.set_status_text("상태: 대기")
                    except Exception:
                        pass
                return

            # 뷰가 없으면 로그를 버리는 대신 버퍼에서 꺼낸 항목을 별도로 처리할 수 있음
            if self.view is None:
                logger.debug("[Controller] view 없음: 버퍼에서 꺼낸 %d 건 처리하지 않음", len(batch))
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
                if self._timer is not None and self._timer.isActive():
                    self._timer.stop()
                    if self.view is not None:
                        self.view.set_status_text("상태: 일시정지")
                        self.view.set_pause_button_text("재개")
                else:
                    if self._timer is not None:
                        self._timer.start()
                    if self.view is not None:
                        self.view.set_status_text("상태: 수신 대기")
                        self.view.set_pause_button_text("일시정지")
            except Exception:
                pass

        def load_history(self, path: Optional[str] = None, max_lines: int = 1000):
            # 기존 컨트롤러의 load_history를 그대로 호출하거나 필요한 로직을 여기에 추가하세요.
            try:
                # Persistence의 설정 사용
                max_lines = int(self.persistence.settings.get("history_max_lines", max_lines))
                if self.view is not None:
                    # 실제 파일 읽기/뷰 업데이트는 기존 구현을 복사하여 사용하면 됩니다.
                    self.view.set_status_text("히스토리 로드 중...")
                else:
                    logger.debug("[Controller] load_history 요청이지만 view가 없습니다 (path=%s)", path)
            except Exception as exc:
                logger.debug("[Controller] load_history 실패: %s", exc)

        # 내부에서 뷰가 필요한 추가 메서드를 호출할 때는 항상 self.view가 None인지 검사해야 함.
        # 예: _do_rebuild_table_for_tab, _export_tab_to_path 등은 view 존재 여부를 체크하도록 구현 필요.

else:
    class StatisticsTabController:
        def __init__(self, *a, **k):
            raise RuntimeError("PyQt5 또는 분리 모듈이 없습니다; Controller를 생성할 수 없습니다.")