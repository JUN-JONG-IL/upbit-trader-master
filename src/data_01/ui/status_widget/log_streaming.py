# -*- coding: utf-8 -*-
"""
?ㅼ떆媛?濡쒓렇 ?ㅽ듃由щ컢 Mixin (log_streaming.py)

QtLogHandler, MonitoringWorker ?대옒?ㅼ?
?ㅼ떆媛?濡쒓렇 ?ㅽ듃由щ컢 ?ㅼ젙/?쒖옉/?섏떊 硫붿꽌?쒕? ?ы븿?⑸땲??

CHANGELOG:
    v6.0 (2026-04-28) | Copilot | status_widget.py ???⑦궎吏 ?꾩쟾 紐⑤뱢??

?섏젙 (2026-05-10):
- UI ?뺤콉???곕씪 ?듭떊 愿??INFO/DEBUG 濡쒓렇??UI???쒖떆?섎룄濡??몃뱾???덈꺼??INFO濡??ㅼ젙.
- WARNING/ERROR/CRITICAL 濡쒓렇??肄섏넄 ?꾩슜?쇰줈 痍④툒?섏뿬 UI?먮뒗 ?쒖떆?섏? ?딆쓬.
- _should_show_log??議곗젙?섏뿬 combo媛 ?놁쓣 ??INFO/DEBUG ?쒖떆 ?덉슜.
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QObject, QThread, Qt, QMetaObject, Q_ARG, pyqtSignal, pyqtSlot
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if TYPE_CHECKING:
    pass

if _HAS_QT:
    class QtLogHandler(logging.Handler, QObject):
        """濡쒓렇瑜?Qt ?쒓렇?먮줈 emit?섎뒗 ?몃뱾??

        logging.Handler? QObject瑜??ㅼ쨷 ?곸냽?섏뿬
        Python 濡쒓렇 ?덉퐫?쒕? Qt ?쒓렇?먮줈 蹂?섑빀?덈떎.
        """

        log_signal = pyqtSignal(str, str)

        def __init__(self) -> None:
            logging.Handler.__init__(self)
            QObject.__init__(self)

        def emit(self, record: logging.LogRecord) -> None:
            """濡쒓렇 ?덉퐫?쒕? Qt ?쒓렇?먮줈 諛쒗뻾.

            Args:
                record: Python 濡쒓렇 ?덉퐫??
            """
            try:
                msg = self.format(record)
                self.log_signal.emit(record.levelname, msg)
            except Exception as exc:
                logger.debug("[QtLogHandler] 濡쒓렇 emit ?ㅽ뙣: %s", exc)

    class MonitoringWorker(QThread):
        """諛깃렇?쇱슫???쒖뒪??紐⑤땲?곕쭅 ?ㅻ젅??

        psutil???ъ슜?섏뿬 CPU, 硫붾え由? ?붿뒪???ъ슜瑜좎쓣 ?섏쭛?섍퀬
        stats_updated ?쒓렇?먮줈 硫붿씤 ?ㅻ젅?쒖뿉 ?꾨떖?⑸땲??
        """

        stats_updated = pyqtSignal(dict)

        def __init__(self, parent: object = None) -> None:
            super().__init__(parent)
            self._running = True
            self._stop_event = threading.Event()

        def run(self) -> None:
            """紐⑤땲?곕쭅 猷⑦봽 ?ㅽ뻾."""
            while self._running:
                try:
                    stats = self._collect_stats()
                    self.stats_updated.emit(stats)
                except Exception as exc:
                    logger.error("[MonitoringWorker] ?ㅻ쪟: %s", exc)
                    self._stop_event.wait(timeout=5)
                    if not self._running:
                        break
                    continue
                self._stop_event.wait(timeout=1)

        def _collect_stats(self) -> dict:
            """?쒖뒪???듦퀎 ?섏쭛.

            Returns:
                cpu_percent, mem_percent, mem_used_gb, disk_percent瑜??댁? dict
            """
            stats: dict = {}
            try:
                import psutil  # type: ignore
                stats["cpu_percent"] = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory()
                stats["mem_percent"] = mem.percent
                stats["mem_used_gb"] = mem.used / (1024 ** 3)
                disk = psutil.disk_usage("/")
                stats["disk_percent"] = disk.percent
            except ImportError:
                pass
            except Exception as exc:
                logger.debug("[MonitoringWorker] ?곹깭 ?섏쭛 ?ㅽ뙣: %s", exc)
            return stats

        def stop(self) -> None:
            """紐⑤땲?곕쭅 猷⑦봽瑜??뺤??섍퀬 ?ㅻ젅?쒕? 醫낅즺?⑸땲??"""
            self._running = False
            self._stop_event.set()
            self.wait()

    class LogStreamingMixin:
        """?ㅼ떆媛?濡쒓렇 ?ㅽ듃由щ컢 Mixin.

        QtLogHandler, MonitoringWorker 湲곕컲???ㅼ떆媛?濡쒓렇 ?ㅽ듃由щ컢
        ?ㅼ젙怨?硫붿떆吏 ?섏떊 ?щ’???ы븿?⑸땲??
        """

        def _setup_realtime_log_streaming(self) -> None:
            """?ㅼ떆媛?濡쒓렇 ?ㅽ듃由щ컢 ?ㅼ젙.

            Statistics ??쓽 text_log ?꾩젽??WebSocket/Pipeline 濡쒓굅瑜??곌껐?섏뿬
            ?ㅼ떆媛꾩쑝濡?濡쒓렇瑜??쒖떆?⑸땲??
            """
            try:
                if self._tab_statistics is None:
                    logger.debug("[StatusWidget] Statistics ???놁쓬 ??濡쒓렇 ?ㅽ듃由щ컢 ?ㅽ궢")
                    return

                log_widget = getattr(self._tab_statistics, "text_log", None)
                if log_widget is None:
                    logger.debug("[StatusWidget] text_log ?꾩젽 ?놁쓬 ??濡쒓렇 ?ㅽ듃由щ컢 ?ㅽ궢")
                    return

                class RealtimeLogStreamHandler(logging.Handler):
                    """text_log ?꾩젽??濡쒓렇瑜??ㅽ듃由щ컢?섎뒗 ?몃뱾??"""

                    def __init__(self, text_widget: object) -> None:
                        super().__init__()
                        self.text_widget = text_widget
                        # We want communication logs (INFO/DEBUG) streamed
                        self.setLevel(logging.DEBUG)
                        self.setFormatter(logging.Formatter(
                            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%H:%M:%S"
                        ))

                    def emit(self, record: logging.LogRecord) -> None:
                        """濡쒓렇瑜?硫붿씤 ?ㅻ젅??append濡??꾩젽???쒖떆."""
                        try:
                            msg = self.format(record)
                            QMetaObject.invokeMethod(
                                self.text_widget,
                                "append",
                                Qt.QueuedConnection,
                                Q_ARG(str, msg)
                            )
                        except Exception:
                            pass

                # Register handlers for key loggers (WebSocket + Pipeline)
                try:
                    ws_logger = logging.getLogger("data_01.collectors.websocket_manager")
                    ws_handler = RealtimeLogStreamHandler(log_widget)
                    ws_logger.addHandler(ws_handler)
                    self._realtime_log_handlers.append(
                        ("data_01.collectors.websocket_manager", ws_handler)
                    )
                except Exception:
                    logger.debug("[LogStreaming] ws realtime handler registration failed", exc_info=True)

                try:
                    pipeline_logger = logging.getLogger("data_01.pipeline")
                    pipeline_handler = RealtimeLogStreamHandler(log_widget)
                    pipeline_logger.addHandler(pipeline_handler)
                    self._realtime_log_handlers.append(("data_01.pipeline", pipeline_handler))
                except Exception:
                    logger.debug("[LogStreaming] pipeline realtime handler registration failed", exc_info=True)

                logger.info("[StatusWidget] ???ㅼ떆媛?濡쒓렇 ?ㅽ듃由щ컢 ?깅줉 ?꾨즺 (WebSocket + Pipeline)")

            except Exception as exc:
                logger.error("[StatusWidget] ???ㅼ떆媛?濡쒓렇 ?ㅽ듃由щ컢 ?ㅼ젙 ?ㅽ뙣: %s", exc)

        def _start_monitoring_worker(self) -> None:
            """紐⑤땲?곕쭅 ?뚯빱 ?쒖옉.

            MonitoringWorker ?ㅻ젅?쒖? QtLogHandler瑜?珥덇린?뷀븯怨??쒖옉?⑸땲??

            蹂寃? INFO ?덈꺼遺??UI???몃뱾?ш? ?대깽?몃? 諛쏅룄濡??ㅼ젙?⑸땲??
            WARNING/ERROR/CRITICAL ? UI???쒖떆?섏? ?딅룄濡?_on_log_message?먯꽌 李⑤떒?⑸땲??
            """
            try:
                self._monitoring_worker = MonitoringWorker(self)
                self._monitoring_worker.stats_updated.connect(self._on_monitoring_stats)
                self._monitoring_worker.start()

                self._qt_log_handler = QtLogHandler()
                # 蹂寃? INFO ?댁긽??UI ?꾩넚 ??곸쑝濡??섏뿬 ?듭떊 濡쒓렇(INFO)??UI???꾨떖?섎룄濡???
                self._qt_log_handler.setLevel(logging.INFO)
                self._qt_log_handler.log_signal.connect(self._on_log_message)
                logging.getLogger().addHandler(self._qt_log_handler)
                logger.debug("[StatusWidget] QtLogHandler added (level=INFO)")
            except Exception as exc:
                logger.warning("[StatusWidget] 紐⑤땲?곕쭅 ?뚯빱 ?쒖옉 ?ㅽ뙣: %s", exc)

        @pyqtSlot(dict)
        def _on_monitoring_stats(self, stats: dict) -> None:
            """紐⑤땲?곕쭅 ?듦퀎 ?섏떊 ?щ’.

            Args:
                stats: cpu_percent, mem_percent ???쒖뒪???듦퀎 dict
            """
            # ?듦퀎???ㅻⅨ 誘뱀뒪???? UIUpdaters)?먯꽌 ?쒖슜?섎룄濡??쒓렇?먮줈 ?꾨떖??
            pass

        @pyqtSlot(str, str)
        def _on_log_message(self, level: str, msg: str) -> None:
            """濡쒓렇 硫붿떆吏 ?섏떊 ?щ’.

            Args:
                level: 濡쒓렇 ?덈꺼 臾몄옄??("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
                msg: ?щ㎎??濡쒓렇 硫붿떆吏 臾몄옄??

            ?뺤콉:
            - WARNING/ERROR/CRITICAL 硫붿떆吏??肄섏넄 ?꾩슜 (UI???쒖떆?섏? ?딆쓬)
            - INFO/DEBUG 硫붿떆吏??UI??text_log??append (?? _should_show_log瑜??듦낵?댁빞 ??
            """
            try:
                # 1) ?덈꺼 湲곕컲 李⑤떒: WARNING ?댁긽? UI???쒖떆?섏? ?딆쓬 (肄섏넄 ?꾩슜)
                try:
                    lvl = (level or "").upper()
                except Exception:
                    lvl = ""

                if lvl in ("WARNING", "ERROR", "CRITICAL"):
                    # Do not display warnings/errors in the UI - they remain in console logs.
                    return

                # 2) ?ъ슜???ㅼ젙(肄ㅻ낫 諛뺤뒪)???덉슜?섎뒗吏 ?뺤씤
                if not self._should_show_log(level):
                    return

                # 3) ?덉쟾?섍쾶 UI??append
                if self._tab_statistics is not None and hasattr(self._tab_statistics, "text_log"):
                    try:
                        self._tab_statistics.text_log.append(f"[{level}] {msg}")
                    except Exception:
                        logger.debug("[StatusWidget] text_log append failed", exc_info=True)
            except Exception as exc:
                logger.debug("[StatusWidget] 濡쒓렇 硫붿떆吏 泥섎━ ?ㅽ뙣: %s", exc)

        def _should_show_log(self, level: str) -> bool:
            """濡쒓렇 ?덈꺼 ?꾪꽣.

            Args:
                level: 濡쒓렇 ?덈꺼 臾몄옄??

            Returns:
                True?대㈃ ?쒖떆, False?대㈃ ?④?

            ?숈옉:
            - combo_log_level ?꾩젽???놁쑝硫?湲곕낯?곸쑝濡?INFO/DEBUG瑜??쒖떆.
            - combo_log_level???덉쑝硫??ъ슜?먭? ?좏깮??媛믪뿉 ?곕씪 寃곗젙?섎릺,
              WARNING/ERROR/CRITICAL? UI ?뺤콉???쒖떆?섏? ?딆쓬(?꾩뿉???대? 李⑤떒).
            """
            try:
                combo = getattr(self, "combo_log_level", None)
            except Exception:
                combo = None

            lvl = (level or "").upper()
            # If combo not present, allow INFO/DEBUG
            if combo is None:
                return lvl in ("DEBUG", "INFO")

            # If combo present, respect selection.
            try:
                filter_text = combo.currentText()
            except Exception:
                filter_text = "?꾩껜"

            if filter_text == "?꾩껜":
                # Even when "?꾩껜" selected, WARNING+ are blocked earlier.
                return True
            elif filter_text == "?먮윭留?:
                return lvl in ("ERROR", "CRITICAL")
            elif filter_text == "寃쎄퀬 ?댁긽":
                return lvl in ("WARNING", "ERROR", "CRITICAL")
            return False

else:
    class QtLogHandler(logging.Handler):  # type: ignore[no-redef]
        """PyQt5 誘몄꽕移????ъ슜?섎뒗 ?붾? QtLogHandler."""

        def emit(self, record: logging.LogRecord) -> None:
            """?붾? emit."""
            pass

    class MonitoringWorker:  # type: ignore[no-redef]
        """PyQt5 誘몄꽕移????ъ슜?섎뒗 ?붾? MonitoringWorker."""

        def __init__(self, parent: object = None) -> None:
            pass

        def start(self) -> None:
            """?붾? start."""
            pass

        def stop(self) -> None:
            """?붾? stop."""
            pass

    class LogStreamingMixin:  # type: ignore[no-redef]
        """PyQt5 誘몄꽕移????ъ슜?섎뒗 ?붾? LogStreamingMixin."""

        def _setup_realtime_log_streaming(self) -> None:
            """?붾? 濡쒓렇 ?ㅽ듃由щ컢 ?ㅼ젙."""
            pass

        def _start_monitoring_worker(self) -> None:
            """?붾? 紐⑤땲?곕쭅 ?뚯빱 ?쒖옉."""
            pass

        def _on_monitoring_stats(self, stats: dict) -> None:
            """?붾? 紐⑤땲?곕쭅 ?듦퀎 ?섏떊."""
            pass

        def _on_log_message(self, level: str, msg: str) -> None:
            """?붾? 濡쒓렇 硫붿떆吏 ?섏떊."""
            pass

        def _should_show_log(self, level: str) -> bool:
            """?붾? 濡쒓렇 ?꾪꽣."""
            return False
