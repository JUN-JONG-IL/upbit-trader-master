# -*- coding: utf-8 -*-
"""
TF ?덉쟾沅?吏꾪뻾瑜??⑤꼸 Mixin (tf_safe_panel.py)

[梨낆엫]
    StatusWidget ??``status_widget.ui`` ??異붽???``groupBox_tf_safe`` /
    ``widget_tf_progress_host`` 瑜??댁븘?덈뒗 ?꾩젽?쇰줈 留뚮뱾湲??꾪븳 ?⑥씪 梨낆엫
    Mixin. ???숈옉 以묒씤 ``UIUpdatersMixin`` / ``SignalHandlersMixin`` ??湲곗〈
    Mixin ??肄붾뱶???쇱껜 嫄대뱶由ъ? ?딅뒗??

[?쒓났 湲곕뒫]
    - ``_init_tf_safe_panel()``  : ``TFProgressWidget`` ?몄뒪?댁뒪瑜?placeholder
      ???꾪궧?섍퀬, 蹂꾨룄 15珥?``QTimer`` 瑜??쒖옉?쒕떎.
    - ``_refresh_tf_safe_panel()`` : 湲곕낯 ?щ낵(``KRW-BTC``) ??6媛?TF ?????
      ``MetadataManager.compute_safe_zone_pct()`` 瑜?鍮꾨룞湲곕줈 ?몄텧, 寃곌낵瑜?
      ?꾩젽???몄떆?쒕떎. ?몄텧? 吏㏃? lifecycle ??``QThread`` ?뚯빱?먯꽌 ?섑뻾
      ?섎?濡?GUI ?ㅻ젅?쒕? 釉붾줈?뱁븯吏 ?딅뒗??
    - ``_set_tf_safe_symbol(symbol)`` : ?쒖떆 ????щ낵 蹂寃??꾩슂 ???몃? ?몄텧).

[鍮꾪뙆愿?蹂댁옣]
    - placeholder (``widget_tf_progress_host``) 媛 ?놁쑝硫?議곗슜??noop.
    - PyQt5 / MetadataManager 媛 ?녿뒗 ?섍꼍?먯꽌??import 留??섎룄濡?媛??
    - 湲곗〈 ??대㉧/?대깽??猷⑦봽 蹂寃??놁쓬 ???대? ?꾩슜 ``QTimer`` 1媛쒕쭔 異붽?.

[?깅뒫 / ??諛⑹?]
    - 媛깆떊 二쇨린 15珥?(`_TF_SAFE_REFRESH_MS`) ??硫붾え由?猷곌낵 ?쇱튂.
    - ?뚯빱 ``isRunning()`` 媛????以묐났 ?ㅽ뻾 李⑤떒 (硫붾え由?猷?'performance').
    - 寃곌낵 ?쇰꺼? GUI ?ㅻ젅?쒖뿉?쒕쭔 媛깆떊 (Qt ?쒓렇???ъ슜).
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


_TF_SAFE_REFRESH_MS = 15_000  # 15s ?쒖? ?대쭅 (硫붾え由?猷?'performance')
_DEFAULT_TFS = ["1m", "5m", "15m", "1h", "4h", "1d"]
_DEFAULT_SYMBOL = os.environ.get("STATUSWIDGET_TF_SAFE_SYMBOL", "KRW-BTC")


# ---------------------------------------------------------------------------
# 鍮꾨룞湲??뚯빱 ??MetadataManager.compute_safe_zone_pct N???몄텧
# ---------------------------------------------------------------------------

if _HAS_QT:

    class _TFSafeWorker(QThread):
        """吏㏃? ?섎챸???뚯빱 ??1???ㅽ뻾 ??醫낅즺.

        湲곕낯 ?대깽??猷⑦봽 ?꾩뿉 ??``asyncio.run`` ???꾩썙 ``compute_safe_zone_pct``
        瑜?N媛?TF ?????蹂묐젹 ?몄텧(``asyncio.gather``) ?쒕떎. 寃곌낵??
        ``finished_results(dict)`` ?쒓렇?먮줈 蹂대궦??
        """

        finished_results = pyqtSignal(str, dict)  # (symbol, results)

        def __init__(self, symbol: str, timeframes: List[str], parent: Optional[QObject] = None) -> None:
            super().__init__(parent)
            self._symbol = symbol
            self._tfs = list(timeframes)

        def run(self) -> None:  # noqa: D401
            """?뚯빱 蹂몄껜 ????asyncio 猷⑦봽?먯꽌 ``compute_safe_zone_pct`` 瑜?N媛?TF??
            ????숈떆 ?몄텧(``asyncio.gather``) ????``finished_results(symbol, dict)``
            ?쒓렇?먮줈 GUI ?ㅻ젅?쒖뿉 寃곌낵瑜??꾨떖?쒕떎.
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
                    # ?대? 猷⑦봽媛 ?쒖꽦?붾맂 ?섍꼍 ?대갚 ????猷⑦봽瑜??앹꽦
                    loop = asyncio.new_event_loop()
                    try:
                        results = loop.run_until_complete(_gather_all())
                    finally:
                        loop.close()
                self.finished_results.emit(self._symbol, results or {})
            except Exception as exc:
                logger.debug("[TFSafeWorker] ?ㅽ뻾 ?ㅽ뙣: %s", exc)
                self.finished_results.emit(self._symbol, {})

        # ------------------------------------------------------------------
        @staticmethod
        def _resolve_metadata_manager() -> Optional[Any]:
            """?꾨줈?몄뒪 ?댁뿉???ъ슜 媛?ν븳 ``MetadataManager`` 瑜?李얜뒗??

            ``data_01`` ?⑦궎吏紐낆씠 ?レ옄濡??쒖옉???쇰컲 ``import_module`` 媛 遺덇??섎?濡?
            ?뚯씪 湲곕컲 ``importlib.util`` ?대갚???ъ슜?쒕떎 (``pipeline_loader`` ?⑦꽩).
            """
            # 1) sys.modules ???대? 濡쒕뱶??紐⑤뱢???덈떎硫??곗꽑 ?쒖슜
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

            # 2) ?뚯씪 湲곕컲 ?숈쟻 濡쒕뱶 (digit-prefix ?⑦궎吏 ?명솚)
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
                logger.debug("[TFSafeWorker] file-based metadata 濡쒕뱶 ?ㅽ뙣: %s", exc)
            return None


    class TFSafePanelMixin:
        """``status_widget.ui`` ??TF ?덉쟾沅?吏꾪뻾瑜??⑤꼸 ?쇱씠?꾩궗?댄겢 Mixin."""

        # ------------------------------------------------------------------
        def _init_tf_safe_panel(self) -> None:
            """``widget_tf_progress_host`` ??TFProgressWidget ?꾪궧 + ??대㉧ ?쒖옉.

            placeholder 媛 議댁옱?섏? ?딄굅??PyQt5/?꾩젽 紐⑤뱢 濡쒕뱶媛 ?ㅽ뙣?섎㈃
            ?꾨Т 寃껊룄 ?섏? ?딅뒗???꾩쟾 鍮꾪뙆愿?.
            """
            self._tf_safe_widget: Optional[Any] = None
            self._tf_safe_timer: Optional[QTimer] = None
            self._tf_safe_worker: Optional[_TFSafeWorker] = None
            self._tf_safe_symbol: str = _DEFAULT_SYMBOL
            self._tf_safe_tfs: List[str] = list(_DEFAULT_TFS)

            host = getattr(self, "widget_tf_progress_host", None)
            if host is None:
                logger.debug("[TFSafePanel] placeholder ?놁쓬 ??鍮꾪솢??)
                return

            try:
                # PyQt5 ?꾩젽??`data_01` ?붿????꾨━?쎌뒪 ?⑦궎吏 ?덉뿉 ?덉뼱
                # ?쒖? `import` 媛 ???섎?濡??뚯씪 湲곕컲 ?숈쟻 濡쒕뱶
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
                        raise ImportError("spec load ?ㅽ뙣")
                    tfp_mod = importlib.util.module_from_spec(spec)
                    sys.modules[_key] = tfp_mod
                    spec.loader.exec_module(tfp_mod)
                TFProgressWidget = getattr(tfp_mod, "TFProgressWidget")
            except Exception as exc:
                logger.debug("[TFSafePanel] TFProgressWidget 濡쒕뱶 ?ㅽ뙣: %s", exc)
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
                logger.debug("[TFSafePanel] ?꾩젽 ?꾪궧 ?ㅽ뙣: %s", exc)
                return

            # ?щ낵 ?쇰꺼 媛깆떊
            self._set_tf_safe_symbol(self._tf_safe_symbol)

            # ?섏쭛 ?ㅼ젙?먯꽌 ?좏깮??TF 濡쒕뱶 ???꾩젽??媛뺤“ ?쒖떆 ?꾨떖
            try:
                selected = self._load_selected_timeframes()
                if selected and hasattr(widget, "set_selected_timeframes"):
                    widget.set_selected_timeframes(selected)
            except Exception as exc:
                logger.debug("[TFSafePanel] ?좏깮 TF 濡쒕뱶 ?ㅽ뙣: %s", exc)

            # ?꾩슜 ??대㉧ (硫붿씤 _timer ? 遺꾨━, 15s)
            try:
                self._tf_safe_timer = QTimer(self)  # type: ignore[arg-type]
                self._tf_safe_timer.setInterval(_TF_SAFE_REFRESH_MS)
                self._tf_safe_timer.timeout.connect(self._refresh_tf_safe_panel)
                self._tf_safe_timer.start()
                # 利됱떆 1??媛깆떊
                QTimer.singleShot(500, self._refresh_tf_safe_panel)
            except Exception as exc:
                logger.debug("[TFSafePanel] ??대㉧ ?쒖옉 ?ㅽ뙣: %s", exc)

        # ------------------------------------------------------------------
        def _set_tf_safe_symbol(self, symbol: str) -> None:
            """?쒖떆 ????щ낵 蹂寃?(?꾩껜 TF 吏꾪뻾瑜?湲곗?)."""
            if not symbol:
                return
            self._tf_safe_symbol = str(symbol)
            lbl = getattr(self, "label_tf_safe_symbol", None)
            if lbl is not None:
                try:
                    lbl.setText(
                        f"?꾩껜 TF ?덉젙沅?吏꾪뻾瑜?(??쒖떖蹂? {self._tf_safe_symbol})"
                    )
                except Exception:
                    pass

        # ------------------------------------------------------------------
        def _load_selected_timeframes(self) -> List[str]:
            """MongoDB ``ui_settings.collection_settings.timeframes`` ?먯꽌 ?ъ슜?먭?
            ?섏쭛 ?ㅼ젙??泥댄겕??TF 由ъ뒪?몃? ?숆린?곸쑝濡?濡쒕뱶?쒕떎.

            ?ㅽ듃?뚰겕/DB ?ㅽ뙣 ??鍮?由ъ뒪?몃? 諛섑솚 ???몄텧遺?먯꽌 noop 泥섎━.
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
                logger.debug("[TFSafePanel] collection_settings 濡쒕뱶 ?ㅽ뙣: %s", exc)
            return []

        # ------------------------------------------------------------------
        def _refresh_tf_safe_panel(self) -> None:
            """?뚯빱 isRunning 媛??+ ???뚯빱 1???ㅽ뻾."""
            if getattr(self, "_tf_safe_widget", None) is None:
                return
            worker = getattr(self, "_tf_safe_worker", None)
            if worker is not None and worker.isRunning():
                return  # 以묐났 ?ㅽ뻾 李⑤떒
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
                logger.debug("[TFSafePanel] ?뚯빱 ?쒖옉 ?ㅽ뙣: %s", exc)

        # ------------------------------------------------------------------
        def _on_tf_safe_results(self, symbol: str, results: Dict[str, Dict[str, Any]]) -> None:
            """?뚯빱 醫낅즺 ??寃곌낵瑜??꾩젽??諛섏쁺(GUI ?ㅻ젅??."""
            widget = getattr(self, "_tf_safe_widget", None)
            if widget is None:
                return
            try:
                widget.update_from_results(results or {})
            except Exception as exc:
                logger.debug("[TFSafePanel] update_from_results ?ㅽ뙣: %s", exc)

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

