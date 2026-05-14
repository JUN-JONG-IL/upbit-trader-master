# -*- coding: utf-8 -*-
"""
而⑦듃濡ㅻ윭 珥덇린??諛?WebSocket 愿由?Mixin (controller_manager.py)

CHANGELOG:
    v6.1 (2026-04-28) | Copilot |
        - _find_ws_manager_in_modules(): sys.modules 愿묒뿭 ?ㅼ틪 ?ы띁 異붽?
        - _start_ws_discovery_timer(): 5珥?媛꾧꺽 ?먮룞 ?먯깋 ??대㉧ 異붽?
        - _on_ws_discovery_tick(): ?먯깋 ?깍옙占쏙옙 ???대쭅 ?먮룞 ?쒖옉
        - _connect_runtime_callbacks(): ???ы띁 湲곕컲?쇰줈 援먯껜
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

# WebSocket Manager ?먮퀎???뱀쭠 ?띿꽦 紐⑸줉
_WS_MANAGER_ATTRS = (
    "recv_count", "_stats", "is_running", "subscriptions",
    "_ws_count", "message_count", "_last_symbol", "connections",
)

if _HAS_QT:
    class ControllerManagerMixin:
        """而⑦듃濡ㅻ윭 珥덇린??諛?WebSocket 愿由?Mixin."""

        # ------------------------------------------------------------------
        # 而⑦듃濡ㅻ윭 珥덇린??
        # ------------------------------------------------------------------

        def _init_controllers(self) -> None:
            """而⑦듃濡ㅻ윭 珥덇린??"""
            try:
                from ..controllers import (
                    HealthChecker, MetricsUpdater, RealtimeLogHandler,
                    WebSocketController, CollectionSettings, DBPopupManager,
                )
                _has_controllers = True
            except ImportError as exc:
                logger.warning("[StatusWidget] 而⑦듃濡ㅻ윭 ?꾪룷???ㅽ뙣: %s", exc)
                _has_controllers = False

            if not _has_controllers:
                return

            try:
                # ?ъ뒪泥댄겕 諛?硫뷀듃由?뒪 珥덇린??
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
                # 濡쒓렇 ?몃뱾??珥덇린??(蹂寃?
                # ---------------------------
                import logging as _logging
                # 湲곕낯 RealtimeLogHandler ?몄뒪?댁뒪 ?앹꽦 (湲곗〈 ?숈옉 ?좎?)
                self._log_handler = RealtimeLogHandler(max_logs=1000)

                # ?듭떖 蹂寃? 紐⑤뱺 濡쒓렇瑜?UI濡?蹂댁씠寃??섎젮硫?collect_all??耳?땲??
                # ?덉쟾??湲곕낯? False??쇰굹 UI?먯꽌 ?꾩껜 濡쒓렇瑜??뺤씤?섎젮硫?True濡??ㅼ젙.
                try:
                    # ?고??꾩뿉???ъ슜?????덈룄濡??ㅼ젙
                    if hasattr(self._log_handler, "set_collect_all"):
                        self._log_handler.set_collect_all(True)
                    else:
                        # ?댁쟾 援ы쁽?대씪硫??泥대줈 ?대? 紐⑤뱺 濡쒓렇瑜?諛쏄퀬 ?덉????딆쓬.
                        pass
                except Exception:
                    logger.debug("[StatusWidget] _log_handler.set_collect_all ?몄텧 ?ㅽ뙣", exc_info=True)

                # 沅뚯옣: UILogBridge 瑜??ъ슜??Qt-safe ?쒓렇??釉뚮━吏 援ъ꽦
                # (src/data_01/ui/controllers/uilog_bridge.py ?뚯씪???꾨줈?앺듃??異붽??댁빞 ??
                try:
                    from ..controllers.uilog_bridge import UILogBridge  # ?덈줈 異붽???紐⑤뱢
                    # 釉뚮━吏 ?앹꽦 (handler 二쇱엯)
                    self._uilog_bridge = UILogBridge(self._log_handler)
                    # 釉뚮━吏媛 猷⑦듃 濡쒓굅???몃뱾?щ? ?깅줉?섎룄濡??붿껌 (?좏깮??
                    try:
                        self._uilog_bridge.install_into_root_logger()
                    except Exception:
                        logger.debug("[StatusWidget] UILogBridge.install_into_root_logger ?ㅽ뙣", exc_info=True)

                    # StatisticsTab ?먮뒗 釉뚮━吏瑜??꾨떖 (StatisticsTab.set_log_handler ??釉뚮━吏/?몃뱾??紐⑤몢 ?섏슜?댁빞 ??
                    if self._tab_statistics is not None:
                        try:
                            self._tab_statistics.set_log_handler(self._uilog_bridge)
                        except Exception:
                            # ?대갚: 湲곗〈 ?몃뱾??吏곸젒 ?꾨떖
                            self._tab_statistics.set_log_handler(self._log_handler)
                    logger.info("[StatusWidget] UILogBridge濡??ㅼ떆媛?濡쒓렇 ?듯빀 ?꾨즺")
                except Exception as exc:
                    # UILogBridge 紐⑤뱢???녾굅???앹꽦 ?ㅽ뙣?섎㈃ 湲곗〈 ?숈옉(吏곸젒 ?몃뱾???깅줉)?쇰줈 ?대갚
                    logger.debug("[StatusWidget] UILogBridge 濡쒕뱶/?앹꽦 ?ㅽ뙣: %s; 湲곗〈 ?몃뱾?щ줈 ?대갚", exc, exc_info=True)
                    try:
                        _logging.getLogger().addHandler(self._log_handler)
                    except Exception:
                        logger.debug("[StatusWidget] 猷⑦듃 濡쒓굅???몃뱾??異붽? ?ㅽ뙣", exc_info=True)
                    if self._tab_statistics is not None:
                        try:
                            self._tab_statistics.set_log_handler(self._log_handler)
                        except Exception:
                            logger.debug("[StatusWidget] stats_tab.set_log_handler(?몃뱾?? ?ㅽ뙣", exc_info=True)

                # ---------------------------
                # 湲곗〈 WebSocket 珥덇린??怨꾩냽
                # ---------------------------
                self._ws_controller = WebSocketController(self)
                self._ws_controller.websocket_started.connect(self._on_websocket_started)

                self._db_popup_manager = DBPopupManager(parent=self)
                self._collection_settings_ctrl = CollectionSettings(widget=None)

                if self._tab_websocket is not None:
                    try:
                        # bootstrap 紐⑤뱢?먯꽌 WebSocketManager ?곗꽑 ?먯깋
                        bootstrap_mod = None
                        for mod_name in ("app.bootstrap", "src.app.bootstrap", "bootstrap"):
                            if mod_name in sys.modules:
                                bootstrap_mod = sys.modules[mod_name]
                                logger.debug("[StatusWidget] ??bootstrap 紐⑤뱢 諛쒓껄: %s", mod_name)
                                break

                        ws_manager = None
                        if bootstrap_mod:
                            static = getattr(bootstrap_mod, "static", None)
                            ws_manager = getattr(static, "websocket_manager", None) if static else None

                        if ws_manager is None:
                            # 愿묒뿭 ?ㅼ틪 1???좎젣 ?쒕룄
                            ws_manager = self._find_ws_manager_in_modules()

                        if ws_manager is not None:
                            self._ws_manager_ref = ws_manager
                            if hasattr(self._tab_websocket, "set_websocket_manager"):
                                self._tab_websocket.set_websocket_manager(ws_manager)
                            logger.info("[StatusWidget] ??WebSocket ??manager ?곕룞 ?꾨즺")
                        else:
                            logger.warning(
                                "[StatusWidget] ?좑툘 WebSocketManager 誘몃컻寃????먮룞 ?먯깋 ??대㉧ ?쒖옉"
                            )

                        self._setup_realtime_log_streaming()
                        self._connect_runtime_callbacks()

                    except Exception as exc:
                        logger.error("[StatusWidget] ??WebSocket ???곕룞 ?ㅽ뙣: %s", exc)

                logger.info("[StatusWidget] 而⑦듃濡ㅻ윭 珥덇린???꾨즺")

                if self._mongo_client is not None:
                    try:
                        self.load_and_restore_settings(self._mongo_client)
                    except Exception as exc:
                        logger.error("[StatusWidget] ??UI ?ㅼ젙 濡쒕뱶 ?ㅽ뙣: %s", exc)

            except Exception as exc:
                logger.exception("[StatusWidget] 而⑦듃濡ㅻ윭 珥덇린???ㅽ뙣: %s", exc)

        # ------------------------------------------------------------------
        # WebSocket Manager 愿묒뿭 ?먯깋 ?ы띁
        # ------------------------------------------------------------------

        def _find_ws_manager_in_modules(self) -> Optional[object]:
            """sys.modules ?꾩껜?먯꽌 WebSocket Manager 媛앹껜瑜?愿묒뿭 ?먯깋.

            ?먯깋 ?꾨왂:
            1) ?뚮젮吏?紐⑤뱢 寃쎈줈 吏곸젒 ?뺤씤
            2) sys.modules ?꾩껜 ?ㅼ틪 ???대쫫??'websocket'/'collector' ?ы븿 ???몃? ?먯깋

            Returns:
                ws_manager 媛앹껜 ?먮뒗 None
            """
            # ?? 1?④퀎: ?뚮젮吏?寃쎈줈 吏곸젒 ?먯깋 ????????????????????????
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
                # 吏곸젒 ?띿꽦
                for attr in candidate_attrs:
                    candidate = getattr(mod, attr, None)
                    if candidate is not None and any(
                        hasattr(candidate, a) for a in _WS_MANAGER_ATTRS
                    ):
                        logger.debug(
                            "[StatusWidget] ws_manager 諛쒓껄(?뚮젮吏꾧꼍濡?: %s.%s", mod_name, attr
                        )
                        return candidate
                # bootstrap.static 以묒꺽
                static = getattr(mod, "static", None)
                if static is not None:
                    for attr in candidate_attrs:
                        candidate = getattr(static, attr, None)
                        if candidate is not None and any(
                            hasattr(candidate, a) for a in _WS_MANAGER_ATTRS
                        ):
                            logger.debug(
                                "[StatusWidget] ws_manager 諛쒓껄(static以묒꺽): %s.static.%s",
                                mod_name, attr,
                            )
                            return candidate

            # ?? 2?④퀎: sys.modules ?꾩껜 ?ㅼ틪 ?????????????????????????
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
                # ?몄뒪?댁뒪 ?띿꽦 ?먯깋
                for attr in ("_instance", "manager", "_manager", "instance") + candidate_attrs:
                    obj = getattr(mod, attr, None)
                    if obj is not None and any(hasattr(obj, a) for a in _WS_MANAGER_ATTRS):
                        logger.debug(
                            "[StatusWidget] ws_manager 諛쒓껄(愿묒뿭?ㅼ틪): %s.%s", mod_key, attr
                        )
                        return obj
                # 紐⑤뱢 ?먯껜媛 manager ??븷??寃쎌슦
                if any(hasattr(mod, a) for a in _WS_MANAGER_ATTRS):
                    logger.debug("[StatusWidget] ws_manager 諛쒓껄(紐⑤뱢?먯껜): %s", mod_key)
                    return mod

            return None

        # ------------------------------------------------------------------
        # WebSocket Manager ?먮룞 ?먯깋 ??대㉧
        # ------------------------------------------------------------------

        def _start_ws_discovery_timer(self) -> None:
            """5珥?媛꾧꺽 WebSocket Manager ?먮룞 ?먯깋 ??대㉧ ?쒖옉 (理쒕? 120珥?.

            ws_manager 諛쒓껄 利됱떆 ?대쭅 ??대㉧瑜??쒖옉?섍퀬 ?먯깋 ??대㉧瑜?以묒??⑸땲??
            """
            self._ws_discovery_attempts: int = 0
            self._ws_discovery_max: int = 24  # 24 횞 5珥?= 120珥?
            self._ws_discovery_timer = QTimer(self)
            self._ws_discovery_timer.setInterval(5_000)
            self._ws_discovery_timer.timeout.connect(self._on_ws_discovery_tick)
            self._ws_discovery_timer.start()
            logger.debug("[StatusWidget] WebSocket ?먮룞 ?먯깋 ??대㉧ ?쒖옉 (5珥?媛꾧꺽, 理쒕? 120珥?")

        def _on_ws_discovery_tick(self) -> None:
            """WebSocket Manager ?먯깋 ????諛쒓껄 ???대쭅 ?쒖옉."""
            self._ws_discovery_attempts = getattr(self, "_ws_discovery_attempts", 0) + 1
            if self._ws_discovery_attempts > getattr(self, "_ws_discovery_max", 24):
                if hasattr(self, "_ws_discovery_timer"):
                    self._ws_discovery_timer.stop()
                logger.debug(
                    "[StatusWidget] WebSocket ?먯깋 ??꾩븘??(%d???쒕룄)", self._ws_discovery_attempts
                )
                return

            # ?대? ?곌껐??寃쎌슦 以묐났 泥섎━ 諛⑹?
            if getattr(self, "_ws_manager_ref", None) is not None:
                if hasattr(self, "_ws_discovery_timer"):
                    self._ws_discovery_timer.stop()
                return

            ws_manager = self._find_ws_manager_in_modules()
            if ws_manager is None:
                return

            # ?? ws_manager 諛쒓껄 ??????????????????????????????????????
            self._ws_manager_ref = ws_manager
            logger.info(
                "[StatusWidget] ??WebSocket Manager ?먮룞 諛쒓껄 (?쒕룄 %d??",
                self._ws_discovery_attempts,
            )

            # WebSocket ???곕룞
            if self._tab_websocket is not None and hasattr(
                self._tab_websocket, "set_websocket_manager"
            ):
                try:
                    self._tab_websocket.set_websocket_manager(ws_manager)
                    logger.info("[StatusWidget] ??WebSocket ??manager ?ъ뿰???꾨즺")
                except Exception as exc:
                    logger.warning("[StatusWidget] WebSocket ???ъ뿰???ㅽ뙣: %s", exc)

            # ?대쭅 ??대㉧ ?쒖옉 (1珥?
            if not hasattr(self, "_ws_poll_timer") or self._ws_poll_timer is None:
                self._ws_poll_timer = QTimer(self)
                self._ws_poll_timer.setInterval(1_000)
                self._ws_poll_timer.timeout.connect(self._poll_ws_manager)
                self._ws_poll_timer.start()
                logger.info("[StatusWidget] ??WebSocket Manager ?대쭅 ??대㉧ ?쒖옉 (1珥?")

            # ?먯깋 ??대㉧ 醫낅즺
            if hasattr(self, "_ws_discovery_timer"):
                self._ws_discovery_timer.stop()

        # ------------------------------------------------------------------
        # 湲곗〈 ?ъ떆??濡쒖쭅 (?섏쐞 ?명솚 ?좎?)
        # ------------------------------------------------------------------

        def _retry_websocket_connection(self) -> None:
            """WebSocketManager ?ъ떆??(T+10珥???1?????섏쐞 ?명솚)."""
            try:
                ws_manager = self._find_ws_manager_in_modules()
                if ws_manager is not None and self._tab_websocket is not None:
                    if hasattr(self._tab_websocket, "set_websocket_manager"):
                        self._tab_websocket.set_websocket_manager(ws_manager)
                        self._ws_manager_ref = ws_manager
                        logger.info("[StatusWidget] ??WebSocket ???ъ뿰寃??깃났")
                else:
                    logger.warning("[StatusWidget] ?좑툘 WebSocketManager ?ъ쟾???놁쓬")
            except Exception as exc:
                logger.error("[StatusWidget] ??WebSocket ?ъ뿰寃??ㅽ뙣: %s", exc)
            self._connect_runtime_callbacks()

        # ------------------------------------------------------------------
        # ?고???肄쒕갚 ?곌껐 (?대쭅 + ?뚯씠?꾨씪??
        # ------------------------------------------------------------------

        def _connect_runtime_callbacks(self) -> None:
            """WebSocket/Pipeline ?고???肄쒕갚 ?곌껐.

            ws_manager 誘몃컻寃????먮룞 ?먯깋 ??대㉧(_start_ws_discovery_timer)瑜??쒖옉?⑸땲??
            """
            try:
                # ?? 1. ?대? 諛쒓껄??ref ?쒖슜 ??????????????????????????
                ws_manager = getattr(self, "_ws_manager_ref", None)

                # ?? 2. 愿묒뿭 ?ㅼ틪 ??????????????????????????????????????
                if ws_manager is None:
                    ws_manager = self._find_ws_manager_in_modules()

                if ws_manager is not None:
                    self._ws_manager_ref = ws_manager
                    if not hasattr(self, "_ws_poll_timer") or self._ws_poll_timer is None:
                        self._ws_poll_timer = QTimer(self)
                        self._ws_poll_timer.setInterval(1_000)
                        self._ws_poll_timer.timeout.connect(self._poll_ws_manager)
                        self._ws_poll_timer.start()
                        logger.info("[StatusWidget] ??WebSocketManager ?대쭅 ??대㉧ ?쒖옉")
                else:
                    # ?? ws_manager 誘몃컻寃????먮룞 ?먯깋 ??대㉧ ?쒖옉 ????
                    logger.debug("[StatusWidget] WebSocketManager 誘몃컻寃????먮룞 ?먯깋 ??대㉧ ?쒖옉")
                    self._start_ws_discovery_timer()

                # ?? 3. Pipeline 肄쒕갚 ??????????????????????????????????
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
                        logger.debug("[StatusWidget] ?뚯씠?꾨씪??肄쒕갚 ?ㅽ뙣: %s", cb_exc)

                if hasattr(processor, "add_on_processed"):
                    processor.add_on_processed(_on_pipeline_processed)
                    logger.info("[StatusWidget] ??Pipeline on_processed 肄쒕갚 ?깅줉")
                elif hasattr(processor, "_on_processed_callbacks"):
                    processor._on_processed_callbacks.append(_on_pipeline_processed)
                    logger.info("[StatusWidget] ??Pipeline on_processed 肄쒕갚 ?깅줉")

            except Exception as exc:
                logger.debug("[StatusWidget] ?고???肄쒕갚 ?곌껐 ?ㅽ뙣: %s", exc)

        def _find_static_module(self) -> Optional[object]:
            """static 紐⑤뱢??sys.modules?먯꽌 ?먯깋?섎뒗 ?ы띁."""
            known = (
                "static-fallback", "11_server.app.static",
                "src.11_server.app.static", "server.static",
            )
            for mod_name in known:
                if mod_name in sys.modules:
                    return sys.modules[mod_name]

            # bootstrap.static 以묒꺽
            for boot_name in ("app.bootstrap", "src.app.bootstrap", "bootstrap"):
                boot_mod = sys.modules.get(boot_name)
                if boot_mod is not None:
                    _s = getattr(boot_mod, "static", None)
                    if _s is not None:
                        return _s
            return None

        # ------------------------------------------------------------------
        # WebSocket Manager ?대쭅
        # ------------------------------------------------------------------

        def _poll_ws_manager(self) -> None:
            """WebSocketManager ?섏떊 ?듦퀎 ?대쭅 (1珥덈쭏??."""
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
                        "websocket", f"?섏떊 以?.. ({last_symbol or 'active'})"
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
                        logger.debug("[StatusWidget] WebSocket 吏??湲곕줉 ?ㅽ뙣: %s", ws_exc)

            except Exception as exc:
                logger.debug("[StatusWidget] WebSocketManager ?대쭅 ?ㅽ뙣: %s", exc)

else:
    class ControllerManagerMixin:  # type: ignore[no-redef]
        """PyQt5 誘몄꽕移????ъ슜?섎뒗 ?붾? ControllerManagerMixin."""

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
