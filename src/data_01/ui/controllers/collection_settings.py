# -*- coding: utf-8 -*-
"""Tab 8 ?섏쭛 ?ㅼ젙 ?쒖뼱 濡쒖쭅"""
from __future__ import annotations
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = [1, 3, 7, 14, 30]
_COMPRESSION_DAYS = [0, 1, 7, 30]
_RETENTION_DAYS = [30, 90, 180, 365, 0]
_TF_WEIGHT = {"1m": 1.0, "5m": 0.2, "15m": 0.1, "1h": 0.05, "4h": 0.01, "1d": 0.005}

try:
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QMessageBox
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class CollectionSettings:
    """Tab 8 ?섏쭛 ?ㅼ젙 而⑦듃濡ㅻ윭"""

    LOOKBACK_DAYS = _LOOKBACK_DAYS
    COMPRESSION_DAYS = _COMPRESSION_DAYS
    RETENTION_DAYS = _RETENTION_DAYS
    TF_WEIGHT = _TF_WEIGHT

    def __init__(self, widget=None, mongo_client=None):
        self.widget = widget
        self._mongo_client = mongo_client  # pymongo MongoClient ?몄뒪?댁뒪 (?좏깮??

        # ?먮룞 ????붾컮?댁뒪 ??대㉧ (PyQt5 ?ъ슜 媛????
        if _HAS_QT:
            self._debounce_timer = QTimer()
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._auto_save)

        # ?꾩젽???덉쑝硫?利됱떆 ?쒓렇???곌껐
        self._connect_auto_save_signals()

    def _connect_auto_save_signals(self) -> None:
        """紐⑤뱺 UI ?꾩젽??auto-save ?쒓렇???곌껐"""
        if not _HAS_QT or self.widget is None:
            return

        # ??꾪봽?덉엫 泥댄겕諛뺤뒪 蹂寃????먮룞 ????덉빟
        for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
            w = self._w(f"chk_tf_{tf}")
            if w is not None:
                w.stateChanged.connect(self._schedule_auto_save)

        # 肄ㅻ낫諛뺤뒪 蹂寃????먮룞 ????덉빟
        for combo_name in ["combo_lookback_days", "combo_compression_days", "combo_retention_days"]:
            w = self._w(combo_name)
            if w is not None:
                w.currentIndexChanged.connect(self._schedule_auto_save)

    def _schedule_auto_save(self) -> None:
        """500ms ?붾컮?댁뒪濡??먮룞 ????덉빟 (?곗냽 蹂寃???留덉?留?媛믩쭔 ???"""
        if _HAS_QT and hasattr(self, "_debounce_timer"):
            self._debounce_timer.stop()
            self._debounce_timer.start(500)

    def _auto_save(self) -> None:
        """?먮룞 ????ㅽ뻾 (debounce ???몄텧)"""
        try:
            settings = self.collect_settings_from_ui()
            # UI 釉붾줈??諛⑹?瑜??꾪빐 蹂꾨룄 ?ㅻ젅?쒖뿉??MongoDB ???
            threading.Thread(
                target=self._save_to_mongo_sync,
                args=(settings,),
                daemon=True,
            ).start()
            logger.info("[?먮룞 ??? ?섏쭛 ?ㅼ젙 ????꾨즺")
        except Exception as exc:
            logger.error("[?먮룞 ??? ?ㅽ뙣: %s", exc)

    def _save_to_mongo_sync(self, settings: Dict[str, Any]) -> None:
        """MongoDB ?숆린 ???(蹂꾨룄 ?ㅻ젅?쒖뿉???ㅽ뻾)

        二쇱엯??mongo_client媛 ?덉쑝硫??ъ궗?? ?놁쑝硫????곌껐 ?앹꽦.
        """
        try:
            from pymongo import MongoClient  # type: ignore
            # 二쇱엯???대씪?댁뼵???ъ궗??(?곌껐 ?ㅻ쾭?ㅻ뱶 理쒖냼??
            if self._mongo_client is not None:
                client = self._mongo_client
            else:
                mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
                client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
            db = client["upbit_trader"]
            db.ui_settings.update_one(
                {"user_id": "default"},
                {
                    "$set": {
                        "collection_settings": settings,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
            logger.debug("[MongoDB ??? ?섏쭛 ?ㅼ젙 ????꾨즺")
        except Exception as exc:
            logger.error("[MongoDB ??? ?섏쭛 ?ㅼ젙 ????ㅽ뙣: %s", exc)

    def _w(self, name: str):
        """?꾩젽 ?띿꽦 ?덉쟾 議고쉶"""
        return getattr(self.widget, name, None) if self.widget else None

    def _is_checked(self, widget_name: str) -> bool:
        """泥댄겕諛뺤뒪 ?꾩젽??泥댄겕 ?곹깭瑜??덉쟾?섍쾶 諛섑솚?⑸땲??"""
        w = self._w(widget_name)
        return bool(w.isChecked()) if w is not None and hasattr(w, "isChecked") else False

    def init_tab(self) -> None:
        """Tab 8: ?섏쭛 ?ㅼ젙 珥덇린??- ?섍꼍蹂??湲곕낯媛믪쑝濡?UI ?명똿."""
        try:
            # ??꾪봽?덉엫 泥댄겕諛뺤뒪: ?섍꼍蹂??ENABLED_TIMEFRAMES 湲곗?
            enabled_raw = os.getenv("ENABLED_TIMEFRAMES", "1m,5m,1h")
            enabled_tfs = [tf.strip() for tf in enabled_raw.split(",") if tf.strip()]
            for tf_name in ("5m", "15m", "1h", "4h", "1d"):
                w = self._w(f"chk_tf_{tf_name}")
                if w is not None:
                    w.setChecked(tf_name in enabled_tfs)

            # 諛깊븘 湲곌컙: ?섍꼍蹂??FORCE_ENQUEUE_LOOKBACK_DAYS
            try:
                lb_days = int(os.getenv("FORCE_ENQUEUE_LOOKBACK_DAYS", "3"))
            except Exception:
                lb_days = 3
            combo_lb = self._w("combo_lookback_days")
            if combo_lb is not None:
                idx = self.LOOKBACK_DAYS.index(lb_days) if lb_days in self.LOOKBACK_DAYS else 1
                combo_lb.setCurrentIndex(idx)

            # ?뺤텞 ?쒖옉: ?섍꼍蹂??TIMESCALE_COMPRESSION_DAYS
            try:
                comp_days = int(os.getenv("TIMESCALE_COMPRESSION_DAYS", "1"))
            except Exception:
                comp_days = 1
            combo_comp = self._w("combo_compression_days")
            if combo_comp is not None:
                idx = self.COMPRESSION_DAYS.index(comp_days) if comp_days in self.COMPRESSION_DAYS else 1
                combo_comp.setCurrentIndex(idx)

            # 蹂댁〈 湲곌컙: ?섍꼍蹂??TIMESCALE_RETENTION_DAYS
            try:
                ret_days = int(os.getenv("TIMESCALE_RETENTION_DAYS", "90"))
            except Exception:
                ret_days = 90
            combo_ret = self._w("combo_retention_days")
            if combo_ret is not None:
                idx = self.RETENTION_DAYS.index(ret_days) if ret_days in self.RETENTION_DAYS else 1
                combo_ret.setCurrentIndex(idx)

            # ?덉긽 ?⑸웾 ?덉씠釉?珥덇린??
            self.update_estimated_size()
            # ?붿뒪???ъ슜??珥덇린 議고쉶
            self.refresh_disk_usage()

            logger.debug("[CollectionSettings] ?섏쭛 ?ㅼ젙 ??珥덇린???꾨즺")
        except Exception as exc:
            logger.debug("[CollectionSettings] ?섏쭛 ?ㅼ젙 ??珥덇린???ㅽ뙣: %s", exc)

    def update_estimated_size(self) -> None:
        """?덉긽 ?붿뒪???⑸웾 怨꾩궛 ??label_lookback_size ?낅뜲?댄듃."""
        try:
            combo_lb = self._w("combo_lookback_days")
            if combo_lb is None:
                return
            lookback_days = self.LOOKBACK_DAYS[combo_lb.currentIndex()]

            enabled_weight = sum(
                self.TF_WEIGHT.get(tf, 0.0)
                for tf, widget_name in [
                    ("1m", "chk_tf_1m"), ("5m", "chk_tf_5m"), ("15m", "chk_tf_15m"),
                    ("1h", "chk_tf_1h"), ("4h", "chk_tf_4h"), ("1d", "chk_tf_1d"),
                ]
                if self._is_checked(widget_name)
            )

            # 湲곗?: 1m+5m+1h, 7?? 130醫낅ぉ ??30GB
            base_size_gb = 30.0
            base_weight = self.TF_WEIGHT["1m"] + self.TF_WEIGHT["5m"] + self.TF_WEIGHT["1h"]
            estimated_gb = (lookback_days / 7.0) * (enabled_weight / max(base_weight, 0.001)) * base_size_gb

            lbl = self._w("label_lookback_size")
            if lbl is None:
                return
            lbl.setText(f"?덉긽 ?⑸웾: ~{estimated_gb:.1f} GB")

            if estimated_gb < 20:
                color = "#4CAF50"
            elif estimated_gb < 50:
                color = "#FF9800"
            else:
                color = "#F44336"
            lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        except Exception as exc:
            logger.debug("[CollectionSettings] ?덉긽 ?⑸웾 怨꾩궛 ?ㅽ뙣: %s", exc)

    def refresh_disk_usage(self) -> None:
        """?붿뒪??Redis/ClickHouse ?ъ슜???덉씠釉?媛깆떊."""
        try:
            import shutil
            total, used, _ = shutil.disk_usage("/")
            pct = int(used / total * 100)
            pb = self._w("progress_disk")
            if pb is not None:
                pb.setValue(pct)
        except Exception:
            pass

        try:
            import redis as _redis_mod
            rc = _redis_mod.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                socket_connect_timeout=1,
            )
            info = rc.info("memory")
            used_mb = int(info.get("used_memory", 0)) / (1024 * 1024)
            lbl = self._w("label_redis_size")
            if lbl is not None:
                lbl.setText(f"{used_mb:.0f} MB")
        except Exception:
            pass

    def collect_settings_from_ui(self) -> Dict[str, Any]:
        """?꾩옱 UI ?곹깭?먯꽌 ?섏쭛 ?ㅼ젙 ?뺤뀛?덈━瑜?鍮뚮뱶."""
        enabled_tfs = []
        for tf in ("1m", "5m", "15m", "1h", "4h", "1d"):
            w = self._w(f"chk_tf_{tf}")
            if w is not None and w.isChecked():
                enabled_tfs.append(tf)

        combo_lb = self._w("combo_lookback_days")
        lookback_days = self.LOOKBACK_DAYS[combo_lb.currentIndex()] if combo_lb else 3

        combo_comp = self._w("combo_compression_days")
        compression_days = self.COMPRESSION_DAYS[combo_comp.currentIndex()] if combo_comp else 1

        combo_ret = self._w("combo_retention_days")
        retention_days = self.RETENTION_DAYS[combo_ret.currentIndex()] if combo_ret else 90

        return {
            "enabled_timeframes": enabled_tfs,
            "lookback_days": lookback_days,
            "compression_days": compression_days,
            "retention_days": retention_days,
        }

    def apply_settings_to_ui(self, settings: Dict[str, Any]) -> None:
        """?ㅼ젙 ?뺤뀛?덈━瑜?UI ?꾩젽??諛섏쁺."""
        enabled_tfs = settings.get("enabled_timeframes", ["1m", "5m", "1h"])
        for tf in ("5m", "15m", "1h", "4h", "1d"):
            w = self._w(f"chk_tf_{tf}")
            if w is not None:
                w.setChecked(tf in enabled_tfs)

        lb_days = settings.get("lookback_days", 3)
        combo_lb = self._w("combo_lookback_days")
        if combo_lb is not None:
            idx = self.LOOKBACK_DAYS.index(lb_days) if lb_days in self.LOOKBACK_DAYS else 1
            combo_lb.setCurrentIndex(idx)

        comp_days = settings.get("compression_days", 1)
        combo_comp = self._w("combo_compression_days")
        if combo_comp is not None:
            idx = self.COMPRESSION_DAYS.index(comp_days) if comp_days in self.COMPRESSION_DAYS else 1
            combo_comp.setCurrentIndex(idx)

        ret_days = settings.get("retention_days", 90)
        combo_ret = self._w("combo_retention_days")
        if combo_ret is not None:
            idx = self.RETENTION_DAYS.index(ret_days) if ret_days in self.RETENTION_DAYS else 1
            combo_ret.setCurrentIndex(idx)

        self.update_estimated_size()

    def on_preset_save_disk(self) -> None:
        """?⑸웾 ?덉빟 紐⑤뱶 ?꾨━???곸슜."""
        try:
            self.apply_settings_to_ui({
                "enabled_timeframes": ["1m", "5m", "1h"],
                "lookback_days": 3,
                "compression_days": 1,
                "retention_days": 90,
            })
            if _HAS_QT and self.widget:
                QMessageBox.information(
                    self.widget, "?꾨━???곸슜",
                    "?뮶 ?⑸웾 ?덉빟 紐⑤뱶 ?ㅼ젙 ?꾨즺\n\n"
                    "??꾪봽?덉엫: 1m, 5m, 1h\n"
                    "諛깊븘 湲곌컙: 3??n"
                    "?뺤텞: 1????n"
                    "蹂닿?: 3媛쒖썡\n\n"
                    "?덉긽 ?붿뒪???덉빟: ??50%\n"
                    "?ㅼ젙???먮룞?쇰줈 ??λ맗?덈떎.",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] ?⑸웾 ?덉빟 ?꾨━???곸슜 ?ㅽ뙣: %s", exc)

    def on_preset_high_performance(self) -> None:
        """怨좎꽦??紐⑤뱶 ?꾨━???곸슜."""
        try:
            self.apply_settings_to_ui({
                "enabled_timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"],
                "lookback_days": 30,
                "compression_days": 30,
                "retention_days": 365,
            })
            if _HAS_QT and self.widget:
                QMessageBox.warning(
                    self.widget, "?꾨━???곸슜",
                    "?? 怨좎꽦??紐⑤뱶 ?ㅼ젙 ?꾨즺\n\n"
                    "?좑툘 二쇱쓽: ?붿뒪??100GB ?댁긽 ?꾩슂\n\n"
                    "??꾪봽?덉엫: ?꾩껜\n"
                    "諛깊븘 湲곌컙: 30??n"
                    "?뺤텞: 30????n"
                    "蹂닿?: 1??n\n"
                    "?ㅼ젙???먮룞?쇰줈 ??λ맗?덈떎.",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] 怨좎꽦???꾨━???곸슜 ?ㅽ뙣: %s", exc)

    def on_preset_default(self) -> None:
        """湲곕낯媛?蹂듭썝."""
        try:
            self.apply_settings_to_ui({
                "enabled_timeframes": ["1m", "5m", "1h"],
                "lookback_days": 3,
                "compression_days": 1,
                "retention_days": 90,
            })
            if _HAS_QT and self.widget:
                QMessageBox.information(
                    self.widget, "珥덇린???꾨즺",
                    "湲곕낯 ?ㅼ젙?쇰줈 蹂듭썝?섏뿀?듬땲??\n\n"
                    "?ㅼ젙???먮룞?쇰줈 ??λ맗?덈떎.",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] 湲곕낯媛?蹂듭썝 ?ㅽ뙣: %s", exc)

    def on_preset_indicator_minimum(self) -> None:
        """吏??理쒖냼 蹂듭썝 ?꾨━????RSI/MACD/BB ??湲곗닠 吏???뺥솗???뺣낫.

        DB?ㅺ퀎1.md 湲곗?:
          - RSI(14), MACD(26), BB(20) ?덉젙?붾? ?꾪빐 理쒖냼 7????0,080 1遺꾨큺) ?꾩슂
          - 1m + 5m + 1h, 7??諛깊븘, 3媛쒖썡 蹂닿?
        """
        try:
            self.apply_settings_to_ui({
                "enabled_timeframes": ["1m", "5m", "1h"],
                "lookback_days": 7,
                "compression_days": 1,
                "retention_days": 90,
            })
            if _HAS_QT and self.widget:
                QMessageBox.information(
                    self.widget, "吏??理쒖냼 蹂듭썝",
                    "吏??理쒖냼 蹂듭썝 ?ㅼ젙 ?곸슜\n\n"
                    "??꾪봽?덉엫: 1m, 5m, 1h\n"
                    "諛깊븘 湲곌컙: 7??(RSI14/MACD26/BB20 ?덉젙??\n"
                    "?뺤텞: 1????n"
                    "蹂닿?: 3媛쒖썡\n\n"
                    "?ㅼ젙???먮룞?쇰줈 ??λ맗?덈떎.",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] 吏??理쒖냼 蹂듭썝 ?꾨━???ㅽ뙣: %s", exc)

    def on_preset_aiml_minimum(self) -> None:
        """AI/ML 理쒖냼 蹂듭썝 ?꾨━?????숈뒿??異⑸텇??怨쇨굅 ?곗씠???뺣낫.

        DB?ㅺ퀎1.md 湲곗?:
          - Prophet/Transformer/XGBoost ?숈뒿: 理쒖냼 30???댁긽 ?꾩슂
          - ?꾩껜 ??꾪봽?덉엫, 30??諛깊븘, 1??蹂닿?
        """
        try:
            self.apply_settings_to_ui({
                "enabled_timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"],
                "lookback_days": 30,
                "compression_days": 7,
                "retention_days": 365,
            })
            if _HAS_QT and self.widget:
                QMessageBox.warning(
                    self.widget, "AI/ML 理쒖냼 蹂듭썝",
                    "AI/ML 理쒖냼 蹂듭썝 ?ㅼ젙 ?곸슜\n\n"
                    "二쇱쓽: ?붿뒪??50GB ?댁긽 ?꾩슂\n\n"
                    "??꾪봽?덉엫: ?꾩껜 (1m쨌5m쨌15m쨌1h쨌4h쨌1d)\n"
                    "諛깊븘 湲곌컙: 30??(Prophet/Transformer/XGBoost ?숈뒿)\n"
                    "?뺤텞: 7????n"
                    "蹂닿?: 1??n\n"
                    "?ㅼ젙???먮룞?쇰줈 ??λ맗?덈떎.",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] AI/ML 理쒖냼 蹂듭썝 ?꾨━???ㅽ뙣: %s", exc)

    def on_save(self) -> None:
        """?꾩옱 UI ?ㅼ젙??MongoDB????ν븯怨?TimescaleDB ?뺤콉??媛깆떊?쒕떎."""
        try:
            settings = self.collect_settings_from_ui()

            # MongoDB ???(鍮꾨룞湲?- 蹂꾨룄 ?ㅻ젅?쒖뿉???ㅽ뻾)
            self._save_settings_async(settings)

            # ?섍꼍蹂??利됱떆 諛섏쁺 (?꾩옱 ?꾨줈?몄뒪)
            os.environ["ENABLED_TIMEFRAMES"] = ",".join(settings["enabled_timeframes"])
            os.environ["FORCE_ENQUEUE_LOOKBACK_DAYS"] = str(settings["lookback_days"])
            os.environ["TIMESCALE_COMPRESSION_DAYS"] = str(settings["compression_days"])
            os.environ["TIMESCALE_RETENTION_DAYS"] = str(settings["retention_days"])

            enabled_str = ", ".join(settings["enabled_timeframes"])
            ret_label = "?곴뎄 蹂닿?" if settings["retention_days"] == 0 else f"{settings['retention_days']}??
            if _HAS_QT and self.widget:
                QMessageBox.information(
                    self.widget, "????꾨즺",
                    "???ㅼ젙????λ릺?덉뒿?덈떎.\n\n"
                    f"??꾪봽?덉엫: {enabled_str}\n"
                    f"諛깊븘 湲곌컙: {settings['lookback_days']}??n"
                    f"?뺤텞: {settings['compression_days']}????n"
                    f"蹂닿?: {ret_label}\n\n"
                    "?좑툘 Gap Detector ?뚯빱瑜??ъ떆?묓빐??????꾪봽?덉엫 ?ㅼ젙???꾩쟾???곸슜?⑸땲??",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] ?섏쭛 ?ㅼ젙 ????ㅽ뙣: %s", exc)
            if _HAS_QT and self.widget:
                QMessageBox.critical(self.widget, "????ㅽ뙣", f"?ㅼ젙 ???以??ㅻ쪟:\n{exc}")

    def _save_settings_async(self, settings: Dict[str, Any]) -> None:
        """MongoDB ?ㅼ젙 ??μ쓣 蹂꾨룄 ?ㅻ젅?쒖뿉??鍮꾨룞湲곕줈 ?ㅽ뻾."""
        import importlib as _importlib

        def _run() -> None:
            try:
                import asyncio
                from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore

                async def _save() -> None:
                    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader")
                    client = AsyncIOMotorClient(mongo_uri)
                    mgr_cls = None
                    for mod_name in (
                        "src.data_01.mongodb.collection_settings",
                        "mongodb.collection_settings",
                    ):
                        try:
                            mod = _importlib.import_module(mod_name)
                            mgr_cls = getattr(mod, "CollectionSettingsManager", None)
                            if mgr_cls is not None:
                                break
                        except Exception:
                            continue
                    if mgr_cls is None:
                        logger.warning("[CollectionSettings] CollectionSettingsManager import ?ㅽ뙣")
                        return
                    mgr = mgr_cls(client)
                    await mgr.save_settings(settings)
                    logger.info("[CollectionSettings] MongoDB ?섏쭛 ?ㅼ젙 ????꾨즺: %s", settings)

                asyncio.run(_save())
            except Exception as exc:
                logger.warning("[CollectionSettings] MongoDB ?ㅼ젙 ????ㅽ뙣 (鍮꾩튂紐낆쟻): %s", exc)

        t = threading.Thread(target=_run, daemon=True)
        t.start()

