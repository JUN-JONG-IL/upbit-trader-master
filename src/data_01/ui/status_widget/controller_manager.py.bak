# -*- coding: utf-8 -*-
"""
컨트롤러 초기화 및 WebSocket 관리 Mixin (controller_manager.py)

CHANGELOG:
    v6.1 (2026-04-28) | Copilot |
        - _find_ws_manager_in_modules(): sys.modules 광역 스캔 헬퍼 추가
        - _start_ws_discovery_timer(): 5초 간격 자동 탐색 타이머 추가
        - _on_ws_discovery_tick(): 탐색 성��� 시 폴링 자동 시작
        - _connect_runtime_callbacks(): 새 헬퍼 기반으로 교체
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QTimer, Qt, QMetaObject, Q_ARG
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if TYPE_CHECKING:
    pass

# WebSocket Manager 판별용 특징 속성 목록
_WS_MANAGER_ATTRS = (
    "recv_count", "_stats", "is_running", "subscriptions",
    "_ws_count", "message_count", "_last_symbol", "connections",
)

if _HAS_QT:
    class ControllerManagerMixin:
        """컨트롤러 초기화 및 WebSocket 관리 Mixin."""

        # ------------------------------------------------------------------
        # 컨트롤러 초기화
        # ------------------------------------------------------------------

        def _init_controllers(self) -> None:
            """컨트롤러 초기화."""
            try:
                from ..controllers import (
                    HealthChecker, MetricsUpdater, RealtimeLogHandler,
                    WebSocketController, CollectionSettings, DBPopupManager,
                )
                _has_controllers = True
            except ImportError as exc:
                logger.warning("[StatusWidget] 컨트롤러 임포트 실패: %s", exc)
                _has_controllers = False

            if not _has_controllers:
                return

            try:
                # 헬스체크 및 메트릭스 초기화
                self._health_checker = HealthChecker(self)
                self._health_checker.health_updated.connect(self._on_health_updated)
                self._health_checker.run_check()

                self._health_timer = QTimer(self)
                self._health_timer.setInterval(3000)
                self._health_timer.timeout.connect(
                    lambda: self._health_checker.run_check()
                    if self._health_checker is not None else None
                )
                self._health_timer.start()

                self._metrics_updater = MetricsUpdater(self)
                self._metrics_updater.metrics_updated.connect(self._on_metrics_updated)
                self._metrics_updater.start()

                # ---------------------------
                # 로그 핸들러 초기화 (변경)
                # ---------------------------
                import logging as _logging
                # 기본 RealtimeLogHandler 인스턴스 생성 (기존 동작 유지)
                self._log_handler = RealtimeLogHandler(max_logs=1000)

                # 핵심 변경: 모든 로그를 UI로 보이게 하려면 collect_all을 켭니다.
                # 안전상 기본은 False였으나 UI에서 전체 로그를 확인하려면 True로 설정.
                try:
                    # 런타임에서 사용할 수 있도록 설정
                    if hasattr(self._log_handler, "set_collect_all"):
                        self._log_handler.set_collect_all(True)
                    else:
                        # 이전 구현이라면 대체로 이미 모든 로그를 받고 있지는 않음.
                        pass
                except Exception:
                    logger.debug("[StatusWidget] _log_handler.set_collect_all 호출 실패", exc_info=True)

                # 권장: UILogBridge 를 사용해 Qt-safe 시그널 브리지 구성
                # (src/02_data/ui/controllers/uilog_bridge.py 파일을 프로젝트에 추가해야 함)
                try:
                    from ..controllers.uilog_bridge import UILogBridge  # 새로 추가할 모듈
                    # 브리지 생성 (handler 주입)
                    self._uilog_bridge = UILogBridge(self._log_handler)
                    # 브리지가 루트 로거에 핸들러를 등록하도록 요청 (선택적)
                    try:
                        self._uilog_bridge.install_into_root_logger()
                    except Exception:
                        logger.debug("[StatusWidget] UILogBridge.install_into_root_logger 실패", exc_info=True)

                    # StatisticsTab 에는 브리지를 전달 (StatisticsTab.set_log_handler 는 브리지/핸들러 모두 수용해야 함)
                    if self._tab_statistics is not None:
                        try:
                            self._tab_statistics.set_log_handler(self._uilog_bridge)
                        except Exception:
                            # 폴백: 기존 핸들러 직접 전달
                            self._tab_statistics.set_log_handler(self._log_handler)
                    logger.info("[StatusWidget] UILogBridge로 실시간 로그 통합 완료")
                except Exception as exc:
                    # UILogBridge 모듈이 없거나 생성 실패하면 기존 동작(직접 핸들러 등록)으로 폴백
                    logger.debug("[StatusWidget] UILogBridge 로드/생성 실패: %s; 기존 핸들러로 폴백", exc, exc_info=True)
                    try:
                        _logging.getLogger().addHandler(self._log_handler)
                    except Exception:
                        logger.debug("[StatusWidget] 루트 로거에 핸들러 추가 실패", exc_info=True)
                    if self._tab_statistics is not None:
                        try:
                            self._tab_statistics.set_log_handler(self._log_handler)
                        except Exception:
                            logger.debug("[StatusWidget] stats_tab.set_log_handler(핸들러) 실패", exc_info=True)

                # ---------------------------
                # 기존 WebSocket 초기화 계속
                # ---------------------------
                self._ws_controller = WebSocketController(self)
                self._ws_controller.websocket_started.connect(self._on_websocket_started)

                self._db_popup_manager = DBPopupManager(parent=self)
                self._collection_settings_ctrl = CollectionSettings(widget=None)

                if self._tab_websocket is not None:
                    try:
                        # bootstrap 모듈에서 WebSocketManager 우선 탐색
                        bootstrap_mod = None
                        for mod_name in ("app.bootstrap", "src.app.bootstrap", "bootstrap"):
                            if mod_name in sys.modules:
                                bootstrap_mod = sys.modules[mod_name]
                                logger.debug("[StatusWidget] ✅ bootstrap 모듈 발견: %s", mod_name)
                                break

                        ws_manager = None
                        if bootstrap_mod:
                            static = getattr(bootstrap_mod, "static", None)
                            ws_manager = getattr(static, "websocket_manager", None) if static else None

                        if ws_manager is None:
                            # 광역 스캔 1회 선제 시도
                            ws_manager = self._find_ws_manager_in_modules()

                        if ws_manager is not None:
                            self._ws_manager_ref = ws_manager
                            if hasattr(self._tab_websocket, "set_websocket_manager"):
                                self._tab_websocket.set_websocket_manager(ws_manager)
                            logger.info("[StatusWidget] ✅ WebSocket 탭 manager 연동 완료")
                        else:
                            logger.warning(
                                "[StatusWidget] ⚠️ WebSocketManager 미발견 — 자동 탐색 타이머 시작"
                            )

                        self._setup_realtime_log_streaming()
                        self._connect_runtime_callbacks()

                    except Exception as exc:
                        logger.error("[StatusWidget] ❌ WebSocket 탭 연동 실패: %s", exc)

                logger.info("[StatusWidget] 컨트롤러 초기화 완료")

                if self._mongo_client is not None:
                    try:
                        self.load_and_restore_settings(self._mongo_client)
                    except Exception as exc:
                        logger.error("[StatusWidget] ❌ UI 설정 로드 실패: %s", exc)

            except Exception as exc:
                logger.exception("[StatusWidget] 컨트롤러 초기화 실패: %s", exc)

        # ------------------------------------------------------------------
        # WebSocket Manager 광역 탐색 헬퍼
        # ------------------------------------------------------------------

        def _find_ws_manager_in_modules(self) -> Optional[object]:
            """sys.modules 전체에서 WebSocket Manager 객체를 광역 탐색.

            탐색 전략:
            1) 알려진 모듈 경로 직접 확인
            2) sys.modules 전체 스캔 — 이름에 'websocket'/'collector' 포함 시 세부 탐색

            Returns:
                ws_manager 객체 또는 None
            """
            # ── 1단계: 알려진 경로 직접 탐색 ────────────────────────
            known_roots = (
                "static-fallback", "11_server.app.static",
                "src.11_server.app.static", "server.static",
                "app.bootstrap", "src.app.bootstrap", "bootstrap",
                "app.static", "src.app.static",
            )
            candidate_attrs = (
                "websocket_manager", "ws_manager", "_ws_manager",
                "WebSocketManager", "websocket",
            )
            for mod_name in known_roots:
                mod = sys.modules.get(mod_name)
                if mod is None:
                    continue
                # 직접 속성
                for attr in candidate_attrs:
                    candidate = getattr(mod, attr, None)
                    if candidate is not None and any(
                        hasattr(candidate, a) for a in _WS_MANAGER_ATTRS
                    ):
                        logger.debug(
                            "[StatusWidget] ws_manager 발견(알려진경로): %s.%s", mod_name, attr
                        )
                        return candidate
                # bootstrap.static 중첩
                static = getattr(mod, "static", None)
                if static is not None:
                    for attr in candidate_attrs:
                        candidate = getattr(static, attr, None)
                        if candidate is not None and any(
                            hasattr(candidate, a) for a in _WS_MANAGER_ATTRS
                        ):
                            logger.debug(
                                "[StatusWidget] ws_manager 발견(static중첩): %s.static.%s",
                                mod_name, attr,
                            )
                            return candidate

            # ── 2단계: sys.modules 전체 스캔 ─────────────────────────
            for mod_key, mod in list(sys.modules.items()):
                if mod is None:
                    continue
                key_lower = mod_key.lower()
                is_candidate = (
                    "websocket" in key_lower
                    or "ws_manager" in key_lower
                    or "collector" in key_lower
                )
                if not is_candidate:
                    continue
                # 인스턴스 속성 탐색
                for attr in ("_instance", "manager", "_manager", "instance") + candidate_attrs:
                    obj = getattr(mod, attr, None)
                    if obj is not None and any(hasattr(obj, a) for a in _WS_MANAGER_ATTRS):
                        logger.debug(
                            "[StatusWidget] ws_manager 발견(광역스캔): %s.%s", mod_key, attr
                        )
                        return obj
                # 모듈 자체가 manager 역할인 경우
                if any(hasattr(mod, a) for a in _WS_MANAGER_ATTRS):
                    logger.debug("[StatusWidget] ws_manager 발견(모듈자체): %s", mod_key)
                    return mod

            return None

        # ------------------------------------------------------------------
        # WebSocket Manager 자동 탐색 타이머
        # ------------------------------------------------------------------

        def _start_ws_discovery_timer(self) -> None:
            """5초 간격 WebSocket Manager 자동 탐색 타이머 시작 (최대 120초).

            ws_manager 발견 즉시 폴링 타이머를 시작하고 탐색 타이머를 중지합니다.
            """
            self._ws_discovery_attempts: int = 0
            self._ws_discovery_max: int = 24  # 24 × 5초 = 120초
            self._ws_discovery_timer = QTimer(self)
            self._ws_discovery_timer.setInterval(5_000)
            self._ws_discovery_timer.timeout.connect(self._on_ws_discovery_tick)
            self._ws_discovery_timer.start()
            logger.debug("[StatusWidget] WebSocket 자동 탐색 타이머 시작 (5초 간격, 최대 120초)")

        def _on_ws_discovery_tick(self) -> None:
            """WebSocket Manager 탐색 틱 — 발견 시 폴링 시작."""
            self._ws_discovery_attempts = getattr(self, "_ws_discovery_attempts", 0) + 1
            if self._ws_discovery_attempts > getattr(self, "_ws_discovery_max", 24):
                if hasattr(self, "_ws_discovery_timer"):
                    self._ws_discovery_timer.stop()
                logger.debug(
                    "[StatusWidget] WebSocket 탐색 타임아웃 (%d회 시도)", self._ws_discovery_attempts
                )
                return

            # 이미 연결된 경우 중복 처리 방지
            if getattr(self, "_ws_manager_ref", None) is not None:
                if hasattr(self, "_ws_discovery_timer"):
                    self._ws_discovery_timer.stop()
                return

            ws_manager = self._find_ws_manager_in_modules()
            if ws_manager is None:
                return

            # ── ws_manager 발견 ──────────────────────────────────────
            self._ws_manager_ref = ws_manager
            logger.info(
                "[StatusWidget] ✅ WebSocket Manager 자동 발견 (시도 %d회)",
                self._ws_discovery_attempts,
            )

            # WebSocket 탭 연동
            if self._tab_websocket is not None and hasattr(
                self._tab_websocket, "set_websocket_manager"
            ):
                try:
                    self._tab_websocket.set_websocket_manager(ws_manager)
                    logger.info("[StatusWidget] ✅ WebSocket 탭 manager 재연동 완료")
                except Exception as exc:
                    logger.warning("[StatusWidget] WebSocket 탭 재연동 실패: %s", exc)

            # 폴링 타이머 시작 (1초)
            if not hasattr(self, "_ws_poll_timer") or self._ws_poll_timer is None:
                self._ws_poll_timer = QTimer(self)
                self._ws_poll_timer.setInterval(1_000)
                self._ws_poll_timer.timeout.connect(self._poll_ws_manager)
                self._ws_poll_timer.start()
                logger.info("[StatusWidget] ✅ WebSocket Manager 폴링 타이머 시작 (1초)")

            # 탐색 타이머 종료
            if hasattr(self, "_ws_discovery_timer"):
                self._ws_discovery_timer.stop()

        # ------------------------------------------------------------------
        # 기존 재시도 로직 (하위 호환 유지)
        # ------------------------------------------------------------------

        def _retry_websocket_connection(self) -> None:
            """WebSocketManager 재시도 (T+10초 후 1회 — 하위 호환)."""
            try:
                ws_manager = self._find_ws_manager_in_modules()
                if ws_manager is not None and self._tab_websocket is not None:
                    if hasattr(self._tab_websocket, "set_websocket_manager"):
                        self._tab_websocket.set_websocket_manager(ws_manager)
                        self._ws_manager_ref = ws_manager
                        logger.info("[StatusWidget] ✅ WebSocket 탭 재연결 성공")
                else:
                    logger.warning("[StatusWidget] ⚠️ WebSocketManager 여전히 없음")
            except Exception as exc:
                logger.error("[StatusWidget] ❌ WebSocket 재연결 실패: %s", exc)
            self._connect_runtime_callbacks()

        # ------------------------------------------------------------------
        # 런타임 콜백 연결 (폴링 + 파이프라인)
        # ------------------------------------------------------------------

        def _connect_runtime_callbacks(self) -> None:
            """WebSocket/Pipeline 런타임 콜백 연결.

            ws_manager 미발견 시 자동 탐색 타이머(_start_ws_discovery_timer)를 시작합니다.
            """
            try:
                # ── 1. 이미 발견된 ref 활용 ──────────────────────────
                ws_manager = getattr(self, "_ws_manager_ref", None)

                # ── 2. 광역 스캔 ──────────────────────────────────────
                if ws_manager is None:
                    ws_manager = self._find_ws_manager_in_modules()

                if ws_manager is not None:
                    self._ws_manager_ref = ws_manager
                    if not hasattr(self, "_ws_poll_timer") or self._ws_poll_timer is None:
                        self._ws_poll_timer = QTimer(self)
                        self._ws_poll_timer.setInterval(1_000)
                        self._ws_poll_timer.timeout.connect(self._poll_ws_manager)
                        self._ws_poll_timer.start()
                        logger.info("[StatusWidget] ✅ WebSocketManager 폴링 타이머 시작")
                else:
                    # ── ws_manager 미발견 → 자동 탐색 타이머 시작 ────
                    logger.debug("[StatusWidget] WebSocketManager 미발견 — 자동 탐색 타이머 시작")
                    self._start_ws_discovery_timer()

                # ── 3. Pipeline 콜백 ──────────────────────────────────
                static_mod = self._find_static_module()
                if static_mod is None:
                    return

                processor = getattr(static_mod, "processor", None)
                if processor is None:
                    return

                def _on_pipeline_processed(symbol: str, timeframe: str, result: dict) -> None:
                    try:
                        if self._metrics_updater is not None:
                            self._metrics_updater.record_pipeline_event()
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        QMetaObject.invokeMethod(
                            self, "_pipeline_callback_slot",
                            Qt.QueuedConnection,
                            Q_ARG(str, now), Q_ARG(str, symbol),
                        )
                    except Exception as cb_exc:
                        logger.debug("[StatusWidget] 파이프라인 콜백 실패: %s", cb_exc)

                if hasattr(processor, "add_on_processed"):
                    processor.add_on_processed(_on_pipeline_processed)
                    logger.info("[StatusWidget] ✅ Pipeline on_processed 콜백 등록")
                elif hasattr(processor, "_on_processed_callbacks"):
                    processor._on_processed_callbacks.append(_on_pipeline_processed)
                    logger.info("[StatusWidget] ✅ Pipeline on_processed 콜백 등록")

            except Exception as exc:
                logger.debug("[StatusWidget] 런타임 콜백 연결 실패: %s", exc)

        def _find_static_module(self) -> Optional[object]:
            """static 모듈을 sys.modules에서 탐색하는 헬퍼."""
            known = (
                "static-fallback", "11_server.app.static",
                "src.11_server.app.static", "server.static",
            )
            for mod_name in known:
                if mod_name in sys.modules:
                    return sys.modules[mod_name]

            # bootstrap.static 중첩
            for boot_name in ("app.bootstrap", "src.app.bootstrap", "bootstrap"):
                boot_mod = sys.modules.get(boot_name)
                if boot_mod is not None:
                    _s = getattr(boot_mod, "static", None)
                    if _s is not None:
                        return _s
            return None

        # ------------------------------------------------------------------
        # WebSocket Manager 폴링
        # ------------------------------------------------------------------

        def _poll_ws_manager(self) -> None:
            """WebSocketManager 수신 통계 폴링 (1초마다)."""
            try:
                ws_manager = getattr(self, "_ws_manager_ref", None)
                if ws_manager is None:
                    return

                recv_count = (
                    getattr(ws_manager, "recv_count", None)
                    or getattr(ws_manager, "_stats", {}).get("message_count", 0)
                    or 0
                )
                last_symbol = (
                    getattr(ws_manager, "last_symbol", None)
                    or getattr(ws_manager, "_last_symbol", "")
                    or ""
                )

                if recv_count and int(recv_count) > 0:
                    self.update_flow_status(
                        "websocket", f"수신 중... ({last_symbol or 'active'})"
                    )
                    prev_count = getattr(self, "_ws_poll_last_recv_count", -1)
                    current_count = int(recv_count)
                    if current_count != prev_count:
                        self._ws_poll_last_recv_count = current_count
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        display_symbol = last_symbol or "WS"
                        self.add_comm_row(
                            now, "WS", display_symbol, f"recv={current_count}", "-"
                        )

                if self._metrics_updater is not None and recv_count:
                    try:
                        self._metrics_updater.record_ws_event(last_symbol or "WS")
                    except Exception as ws_exc:
                        logger.debug("[StatusWidget] WebSocket 지표 기록 실패: %s", ws_exc)

            except Exception as exc:
                logger.debug("[StatusWidget] WebSocketManager 폴링 실패: %s", exc)

else:
    class ControllerManagerMixin:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 ControllerManagerMixin."""

        def _init_controllers(self) -> None:
            pass

        def _find_ws_manager_in_modules(self) -> None:
            return None

        def _start_ws_discovery_timer(self) -> None:
            pass

        def _on_ws_discovery_tick(self) -> None:
            pass

        def _retry_websocket_connection(self) -> None:
            pass

        def _connect_runtime_callbacks(self) -> None:
            pass

        def _find_static_module(self) -> None:
            return None

        def _poll_ws_manager(self) -> None:
            pass