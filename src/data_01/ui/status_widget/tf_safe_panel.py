# -*- coding: utf-8 -*-
"""
TF ?ˆì „ê¶?ì§„í–‰ë¥??¨ë„ Mixin (tf_safe_panel.py)

[ì±…ìž„]
    StatusWidget ??``status_widget.ui`` ??ì¶”ê???``groupBox_tf_safe`` /
    ``widget_tf_progress_host`` ë¥??´ì•„?ˆëŠ” ?„ì ¯?¼ë¡œ ë§Œë“¤ê¸??„í•œ ?¨ì¼ ì±…ìž„
    Mixin. ???™ìž‘ ì¤‘ì¸ ``UIUpdatersMixin`` / ``SignalHandlersMixin`` ??ê¸°ì¡´
    Mixin ??ì½”ë“œ???¼ì²´ ê±´ë“œë¦¬ì? ?ŠëŠ”??

[?œê³µ ê¸°ëŠ¥]
    - ``_init_tf_safe_panel()``  : ``TFProgressWidget`` ?¸ìŠ¤?´ìŠ¤ë¥?placeholder
      ???„í‚¹?˜ê³ , ë³„ë„ 15ì´?``QTimer`` ë¥??œìž‘?œë‹¤.
    - ``_refresh_tf_safe_panel()`` : ê¸°ë³¸ ?¬ë³¼(``KRW-BTC``) ??6ê°?TF ???€??
      ``MetadataManager.compute_safe_zone_pct()`` ë¥?ë¹„ë™ê¸°ë¡œ ?¸ì¶œ, ê²°ê³¼ë¥?
      ?„ì ¯???¸ì‹œ?œë‹¤. ?¸ì¶œ?€ ì§§ì? lifecycle ??``QThread`` ?Œì»¤?ì„œ ?˜í–‰
      ?˜ë?ë¡?GUI ?¤ë ˆ?œë? ë¸”ë¡œ?¹í•˜ì§€ ?ŠëŠ”??
    - ``_set_tf_safe_symbol(symbol)`` : ?œì‹œ ?€???¬ë³¼ ë³€ê²??„ìš” ???¸ë? ?¸ì¶œ).

[ë¹„íŒŒê´?ë³´ìž¥]
    - placeholder (``widget_tf_progress_host``) ê°€ ?†ìœ¼ë©?ì¡°ìš©??noop.
    - PyQt5 / MetadataManager ê°€ ?†ëŠ” ?˜ê²½?ì„œ??import ë§??˜ë„ë¡?ê°€??
    - ê¸°ì¡´ ?€?´ë¨¸/?´ë²¤??ë£¨í”„ ë³€ê²??†ìŒ ???´ë? ?„ìš© ``QTimer`` 1ê°œë§Œ ì¶”ê?.

[?±ëŠ¥ / ??ë°©ì?]
    - ê°±ì‹  ì£¼ê¸° 15ì´?(`_TF_SAFE_REFRESH_MS`) ??ë©”ëª¨ë¦?ë£°ê³¼ ?¼ì¹˜.
    - ?Œì»¤ ``isRunning()`` ê°€????ì¤‘ë³µ ?¤í–‰ ì°¨ë‹¨ (ë©”ëª¨ë¦?ë£?'performance').
    - ê²°ê³¼ ?¼ë²¨?€ GUI ?¤ë ˆ?œì—?œë§Œ ê°±ì‹  (Qt ?œê·¸???¬ìš©).
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal
    from PyQt5.QtWidgets import QVBoxLayout, QWidget
    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False


_TF_SAFE_REFRESH_MS = 15_000  # 15s ?œì? ?´ë§ (ë©”ëª¨ë¦?ë£?'performance')
_DEFAULT_TFS = ["1m", "5m", "15m", "1h", "4h", "1d"]
_DEFAULT_SYMBOL = os.environ.get("STATUSWIDGET_TF_SAFE_SYMBOL", "KRW-BTC")


# ---------------------------------------------------------------------------
# ë¹„ë™ê¸??Œì»¤ ??MetadataManager.compute_safe_zone_pct N???¸ì¶œ
# ---------------------------------------------------------------------------

if _HAS_QT:

    class _TFSafeWorker(QThread):
        """ì§§ì? ?˜ëª…???Œì»¤ ??1???¤í–‰ ??ì¢…ë£Œ.

        ê¸°ë³¸ ?´ë²¤??ë£¨í”„ ?„ì— ??``asyncio.run`` ???„ì›Œ ``compute_safe_zone_pct``
        ë¥?Nê°?TF ???€??ë³‘ë ¬ ?¸ì¶œ(``asyncio.gather``) ?œë‹¤. ê²°ê³¼??
        ``finished_results(dict)`` ?œê·¸?ë¡œ ë³´ë‚¸??
        """

        finished_results = pyqtSignal(str, dict)  # (symbol, results)

        def __init__(self, symbol: str, timeframes: List[str], parent: Optional[QObject] = None) -> None:
            super().__init__(parent)
            self._symbol = symbol
            self._tfs = list(timeframes)

        def run(self) -> None:  # noqa: D401
            """?Œì»¤ ë³¸ì²´ ????asyncio ë£¨í”„?ì„œ ``compute_safe_zone_pct`` ë¥?Nê°?TF??
            ?€???™ì‹œ ?¸ì¶œ(``asyncio.gather``) ????``finished_results(symbol, dict)``
            ?œê·¸?ë¡œ GUI ?¤ë ˆ?œì— ê²°ê³¼ë¥??„ë‹¬?œë‹¤.
            """
            try:
                import asyncio

                async def _gather_all() -> Dict[str, Dict[str, Any]]:
                    mgr = self._resolve_metadata_manager()
                    if mgr is None:
                        return {}
                    coros = [
                        mgr.compute_safe_zone_pct(self._symbol, tf)
                        for tf in self._tfs
                    ]
                    raw = await asyncio.gather(*coros, return_exceptions=True)
                    out: Dict[str, Dict[str, Any]] = {}
                    for tf, val in zip(self._tfs, raw):
                        if isinstance(val, dict):
                            out[tf] = val
                    return out

                try:
                    results = asyncio.run(_gather_all())
                except RuntimeError:
                    # ?´ë? ë£¨í”„ê°€ ?œì„±?”ëœ ?˜ê²½ ?´ë°± ????ë£¨í”„ë¥??ì„±
                    loop = asyncio.new_event_loop()
                    try:
                        results = loop.run_until_complete(_gather_all())
                    finally:
                        loop.close()
                self.finished_results.emit(self._symbol, results or {})
            except Exception as exc:
                logger.debug("[TFSafeWorker] ?¤í–‰ ?¤íŒ¨: %s", exc)
                self.finished_results.emit(self._symbol, {})

        # ------------------------------------------------------------------
        @staticmethod
        def _resolve_metadata_manager() -> Optional[Any]:
            """?„ë¡œ?¸ìŠ¤ ?´ì—???¬ìš© ê°€?¥í•œ ``MetadataManager`` ë¥?ì°¾ëŠ”??

            ``data_01`` ?¨í‚¤ì§€ëª…ì´ ?«ìžë¡??œìž‘???¼ë°˜ ``import_module`` ê°€ ë¶ˆê??˜ë?ë¡?
            ?Œì¼ ê¸°ë°˜ ``importlib.util`` ?´ë°±???¬ìš©?œë‹¤ (``pipeline_loader`` ?¨í„´).
            """
            # 1) sys.modules ???´ë? ë¡œë“œ??ëª¨ë“ˆ???ˆë‹¤ë©??°ì„  ?œìš©
            for name, mod in list(sys.modules.items()):
                if mod is None:
                    continue
                if not name.endswith("metadata_manager"):
                    continue
                factory = getattr(mod, "create_metadata_manager", None) or getattr(
                    mod, "get_metadata_manager", None
                )
                if callable(factory):
                    try:
                        return factory()
                    except Exception:
                        pass
                cls = getattr(mod, "MetadataManager", None)
                if cls is not None:
                    try:
                        return cls()
                    except Exception:
                        pass

            # 2) ?Œì¼ ê¸°ë°˜ ?™ì  ë¡œë“œ (digit-prefix ?¨í‚¤ì§€ ?¸í™˜)
            try:
                import importlib.util
                import pathlib

                here = pathlib.Path(__file__).resolve()
                # tf_safe_panel.py: src/data_01/ui/status_widget/  ?? parents[3] == src/
                src_root = here.parents[3]
                mm_path = src_root / "data_01" / "mongodb" / "metadata_manager.py"
                if not mm_path.exists():
                    return None
                spec = importlib.util.spec_from_file_location(
                    "_tf_safe_metadata_manager", str(mm_path)
                )
                if spec is None or spec.loader is None:
                    return None
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                factory = getattr(mod, "create_metadata_manager", None) or getattr(
                    mod, "get_metadata_manager", None
                )
                if callable(factory):
                    try:
                        return factory()
                    except Exception:
                        pass
                cls = getattr(mod, "MetadataManager", None)
                if cls is not None:
                    try:
                        return cls()
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[TFSafeWorker] file-based metadata ë¡œë“œ ?¤íŒ¨: %s", exc)
            return None


    class TFSafePanelMixin:
        """``status_widget.ui`` ??TF ?ˆì „ê¶?ì§„í–‰ë¥??¨ë„ ?¼ì´?„ì‚¬?´í´ Mixin."""

        # ------------------------------------------------------------------
        def _init_tf_safe_panel(self) -> None:
            """``widget_tf_progress_host`` ??TFProgressWidget ?„í‚¹ + ?€?´ë¨¸ ?œìž‘.

            placeholder ê°€ ì¡´ìž¬?˜ì? ?Šê±°??PyQt5/?„ì ¯ ëª¨ë“ˆ ë¡œë“œê°€ ?¤íŒ¨?˜ë©´
            ?„ë¬´ ê²ƒë„ ?˜ì? ?ŠëŠ”???„ì „ ë¹„íŒŒê´?.
            """
            self._tf_safe_widget: Optional[Any] = None
            self._tf_safe_timer: Optional[QTimer] = None
            self._tf_safe_worker: Optional[_TFSafeWorker] = None
            self._tf_safe_symbol: str = _DEFAULT_SYMBOL
            self._tf_safe_tfs: List[str] = list(_DEFAULT_TFS)

            host = getattr(self, "widget_tf_progress_host", None)
            if host is None:
                logger.debug("[TFSafePanel] placeholder ?†ìŒ ??ë¹„í™œ??)
                return

            try:
                # PyQt5 ?„ì ¯??`data_01` ?”ì????„ë¦¬?½ìŠ¤ ?¨í‚¤ì§€ ?ˆì— ?ˆì–´
                # ?œì? `import` ê°€ ???˜ë?ë¡??Œì¼ ê¸°ë°˜ ?™ì  ë¡œë“œ
                import importlib.util
                import pathlib

                here = pathlib.Path(__file__).resolve()
                src_root = here.parents[3]  # src/
                tfp_path = src_root / "data_01" / "ui" / "widgets" / "tf_progress_widget.py"
                if not tfp_path.exists():
                    raise FileNotFoundError(str(tfp_path))
                _key = "_tf_progress_widget"
                if _key in sys.modules:
                    tfp_mod = sys.modules[_key]
                else:
                    spec = importlib.util.spec_from_file_location(_key, str(tfp_path))
                    if spec is None or spec.loader is None:
                        raise ImportError("spec load ?¤íŒ¨")
                    tfp_mod = importlib.util.module_from_spec(spec)
                    sys.modules[_key] = tfp_mod
                    spec.loader.exec_module(tfp_mod)
                TFProgressWidget = getattr(tfp_mod, "TFProgressWidget")
            except Exception as exc:
                logger.debug("[TFSafePanel] TFProgressWidget ë¡œë“œ ?¤íŒ¨: %s", exc)
                return

            try:
                widget = TFProgressWidget(timeframes=self._tf_safe_tfs, title=None, parent=host)
                lay = host.layout()
                if lay is None:
                    lay = QVBoxLayout(host)
                    lay.setContentsMargins(0, 0, 0, 0)
                lay.addWidget(widget)
                self._tf_safe_widget = widget
            except Exception as exc:
                logger.debug("[TFSafePanel] ?„ì ¯ ?„í‚¹ ?¤íŒ¨: %s", exc)
                return

            # ?¬ë³¼ ?¼ë²¨ ê°±ì‹ 
            self._set_tf_safe_symbol(self._tf_safe_symbol)

            # ?˜ì§‘ ?¤ì •?ì„œ ? íƒ??TF ë¡œë“œ ???„ì ¯??ê°•ì¡° ?œì‹œ ?„ë‹¬
            try:
                selected = self._load_selected_timeframes()
                if selected and hasattr(widget, "set_selected_timeframes"):
                    widget.set_selected_timeframes(selected)
            except Exception as exc:
                logger.debug("[TFSafePanel] ? íƒ TF ë¡œë“œ ?¤íŒ¨: %s", exc)

            # ?„ìš© ?€?´ë¨¸ (ë©”ì¸ _timer ?€ ë¶„ë¦¬, 15s)
            try:
                self._tf_safe_timer = QTimer(self)  # type: ignore[arg-type]
                self._tf_safe_timer.setInterval(_TF_SAFE_REFRESH_MS)
                self._tf_safe_timer.timeout.connect(self._refresh_tf_safe_panel)
                self._tf_safe_timer.start()
                # ì¦‰ì‹œ 1??ê°±ì‹ 
                QTimer.singleShot(500, self._refresh_tf_safe_panel)
            except Exception as exc:
                logger.debug("[TFSafePanel] ?€?´ë¨¸ ?œìž‘ ?¤íŒ¨: %s", exc)

        # ------------------------------------------------------------------
        def _set_tf_safe_symbol(self, symbol: str) -> None:
            """?œì‹œ ?€???¬ë³¼ ë³€ê²?(?„ì²´ TF ì§„í–‰ë¥?ê¸°ì?)."""
            if not symbol:
                return
            self._tf_safe_symbol = str(symbol)
            lbl = getattr(self, "label_tf_safe_symbol", None)
            if lbl is not None:
                try:
                    lbl.setText(
                        f"?„ì²´ TF ?ˆì •ê¶?ì§„í–‰ë¥?(?€?œì‹¬ë³? {self._tf_safe_symbol})"
                    )
                except Exception:
                    pass

        # ------------------------------------------------------------------
        def _load_selected_timeframes(self) -> List[str]:
            """MongoDB ``ui_settings.collection_settings.timeframes`` ?ì„œ ?¬ìš©?ê?
            ?˜ì§‘ ?¤ì •??ì²´í¬??TF ë¦¬ìŠ¤?¸ë? ?™ê¸°?ìœ¼ë¡?ë¡œë“œ?œë‹¤.

            ?¤íŠ¸?Œí¬/DB ?¤íŒ¨ ??ë¹?ë¦¬ìŠ¤?¸ë? ë°˜í™˜ ???¸ì¶œë¶€?ì„œ noop ì²˜ë¦¬.
            """
            try:
                import os as _os

                from pymongo import MongoClient  # type: ignore

                mongo_uri = _os.environ.get(
                    "MONGO_URI", "mongodb://localhost:27017/upbit_trader"
                )
                client = MongoClient(
                    mongo_uri,
                    serverSelectionTimeoutMS=1500,
                    directConnection=True,
                )
                try:
                    db_name = mongo_uri.rstrip("/").rsplit("/", 1)[-1] or "upbit_trader"
                    doc = (
                        client[db_name]["ui_settings"].find_one({"user_id": "default"})
                        or {}
                    )
                    col = doc.get("collection_settings", {}) or {}
                    tfs = col.get("timeframes") or col.get("collected_timeframes")
                    if isinstance(tfs, (list, tuple)) and tfs:
                        return [str(t) for t in tfs if t]
                finally:
                    try:
                        client.close()
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[TFSafePanel] collection_settings ë¡œë“œ ?¤íŒ¨: %s", exc)
            return []

        # ------------------------------------------------------------------
        def _refresh_tf_safe_panel(self) -> None:
            """?Œì»¤ isRunning ê°€??+ ???Œì»¤ 1???¤í–‰."""
            if getattr(self, "_tf_safe_widget", None) is None:
                return
            worker = getattr(self, "_tf_safe_worker", None)
            if worker is not None and worker.isRunning():
                return  # ì¤‘ë³µ ?¤í–‰ ì°¨ë‹¨
            try:
                worker = _TFSafeWorker(
                    symbol=self._tf_safe_symbol,
                    timeframes=self._tf_safe_tfs,
                    parent=self,  # type: ignore[arg-type]
                )
                worker.finished_results.connect(self._on_tf_safe_results)
                worker.start()
                self._tf_safe_worker = worker
            except Exception as exc:
                logger.debug("[TFSafePanel] ?Œì»¤ ?œìž‘ ?¤íŒ¨: %s", exc)

        # ------------------------------------------------------------------
        def _on_tf_safe_results(self, symbol: str, results: Dict[str, Dict[str, Any]]) -> None:
            """?Œì»¤ ì¢…ë£Œ ??ê²°ê³¼ë¥??„ì ¯??ë°˜ì˜(GUI ?¤ë ˆ??."""
            widget = getattr(self, "_tf_safe_widget", None)
            if widget is None:
                return
            try:
                widget.update_from_results(results or {})
            except Exception as exc:
                logger.debug("[TFSafePanel] update_from_results ?¤íŒ¨: %s", exc)

else:  # pragma: no cover
    class TFSafePanelMixin:  # type: ignore[no-redef]
        def _init_tf_safe_panel(self) -> None:
            return

        def _set_tf_safe_symbol(self, symbol: str) -> None:
            return

        def _refresh_tf_safe_panel(self) -> None:
            return

        def _on_tf_safe_results(self, *args, **kwargs) -> None:
            return


__all__ = ["TFSafePanelMixin"]

