# -*- coding: utf-8 -*-
"""Tab 8 수집 설정 제어 로직"""
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
    """Tab 8 수집 설정 컨트롤러"""

    LOOKBACK_DAYS = _LOOKBACK_DAYS
    COMPRESSION_DAYS = _COMPRESSION_DAYS
    RETENTION_DAYS = _RETENTION_DAYS
    TF_WEIGHT = _TF_WEIGHT

    def __init__(self, widget=None, mongo_client=None):
        self.widget = widget
        self._mongo_client = mongo_client  # pymongo MongoClient 인스턴스 (선택적)

        # 자동 저장 디바운스 타이머 (PyQt5 사용 가능 시)
        if _HAS_QT:
            self._debounce_timer = QTimer()
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._auto_save)

        # 위젯이 있으면 즉시 시그널 연결
        self._connect_auto_save_signals()

    def _connect_auto_save_signals(self) -> None:
        """모든 UI 위젯에 auto-save 시그널 연결"""
        if not _HAS_QT or self.widget is None:
            return

        # 타임프레임 체크박스 변경 시 자동 저장 예약
        for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
            w = self._w(f"chk_tf_{tf}")
            if w is not None:
                w.stateChanged.connect(self._schedule_auto_save)

        # 콤보박스 변경 시 자동 저장 예약
        for combo_name in ["combo_lookback_days", "combo_compression_days", "combo_retention_days"]:
            w = self._w(combo_name)
            if w is not None:
                w.currentIndexChanged.connect(self._schedule_auto_save)

    def _schedule_auto_save(self) -> None:
        """500ms 디바운스로 자동 저장 예약 (연속 변경 시 마지막 값만 저장)"""
        if _HAS_QT and hasattr(self, "_debounce_timer"):
            self._debounce_timer.stop()
            self._debounce_timer.start(500)

    def _auto_save(self) -> None:
        """자동 저장 실행 (debounce 후 호출)"""
        try:
            settings = self.collect_settings_from_ui()
            # UI 블로킹 방지를 위해 별도 스레드에서 MongoDB 저장
            threading.Thread(
                target=self._save_to_mongo_sync,
                args=(settings,),
                daemon=True,
            ).start()
            logger.info("[자동 저장] 수집 설정 저장 완료")
        except Exception as exc:
            logger.error("[자동 저장] 실패: %s", exc)

    def _save_to_mongo_sync(self, settings: Dict[str, Any]) -> None:
        """MongoDB 동기 저장 (별도 스레드에서 실행)

        주입된 mongo_client가 있으면 재사용, 없으면 새 연결 생성.
        """
        try:
            from pymongo import MongoClient  # type: ignore
            # 주입된 클라이언트 재사용 (연결 오버헤드 최소화)
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
            logger.debug("[MongoDB 저장] 수집 설정 저장 완료")
        except Exception as exc:
            logger.error("[MongoDB 저장] 수집 설정 저장 실패: %s", exc)

    def _w(self, name: str):
        """위젯 속성 안전 조회"""
        return getattr(self.widget, name, None) if self.widget else None

    def _is_checked(self, widget_name: str) -> bool:
        """체크박스 위젯의 체크 상태를 안전하게 반환합니다."""
        w = self._w(widget_name)
        return bool(w.isChecked()) if w is not None and hasattr(w, "isChecked") else False

    def init_tab(self) -> None:
        """Tab 8: 수집 설정 초기화 - 환경변수 기본값으로 UI 세팅."""
        try:
            # 타임프레임 체크박스: 환경변수 ENABLED_TIMEFRAMES 기준
            enabled_raw = os.getenv("ENABLED_TIMEFRAMES", "1m,5m,1h")
            enabled_tfs = [tf.strip() for tf in enabled_raw.split(",") if tf.strip()]
            for tf_name in ("5m", "15m", "1h", "4h", "1d"):
                w = self._w(f"chk_tf_{tf_name}")
                if w is not None:
                    w.setChecked(tf_name in enabled_tfs)

            # 백필 기간: 환경변수 FORCE_ENQUEUE_LOOKBACK_DAYS
            try:
                lb_days = int(os.getenv("FORCE_ENQUEUE_LOOKBACK_DAYS", "3"))
            except Exception:
                lb_days = 3
            combo_lb = self._w("combo_lookback_days")
            if combo_lb is not None:
                idx = self.LOOKBACK_DAYS.index(lb_days) if lb_days in self.LOOKBACK_DAYS else 1
                combo_lb.setCurrentIndex(idx)

            # 압축 시작: 환경변수 TIMESCALE_COMPRESSION_DAYS
            try:
                comp_days = int(os.getenv("TIMESCALE_COMPRESSION_DAYS", "1"))
            except Exception:
                comp_days = 1
            combo_comp = self._w("combo_compression_days")
            if combo_comp is not None:
                idx = self.COMPRESSION_DAYS.index(comp_days) if comp_days in self.COMPRESSION_DAYS else 1
                combo_comp.setCurrentIndex(idx)

            # 보존 기간: 환경변수 TIMESCALE_RETENTION_DAYS
            try:
                ret_days = int(os.getenv("TIMESCALE_RETENTION_DAYS", "90"))
            except Exception:
                ret_days = 90
            combo_ret = self._w("combo_retention_days")
            if combo_ret is not None:
                idx = self.RETENTION_DAYS.index(ret_days) if ret_days in self.RETENTION_DAYS else 1
                combo_ret.setCurrentIndex(idx)

            # 예상 용량 레이블 초기화
            self.update_estimated_size()
            # 디스크 사용량 초기 조회
            self.refresh_disk_usage()

            logger.debug("[CollectionSettings] 수집 설정 탭 초기화 완료")
        except Exception as exc:
            logger.debug("[CollectionSettings] 수집 설정 탭 초기화 실패: %s", exc)

    def update_estimated_size(self) -> None:
        """예상 디스크 용량 계산 후 label_lookback_size 업데이트."""
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

            # 기준: 1m+5m+1h, 7일, 130종목 ≈ 30GB
            base_size_gb = 30.0
            base_weight = self.TF_WEIGHT["1m"] + self.TF_WEIGHT["5m"] + self.TF_WEIGHT["1h"]
            estimated_gb = (lookback_days / 7.0) * (enabled_weight / max(base_weight, 0.001)) * base_size_gb

            lbl = self._w("label_lookback_size")
            if lbl is None:
                return
            lbl.setText(f"예상 용량: ~{estimated_gb:.1f} GB")

            if estimated_gb < 20:
                color = "#4CAF50"
            elif estimated_gb < 50:
                color = "#FF9800"
            else:
                color = "#F44336"
            lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        except Exception as exc:
            logger.debug("[CollectionSettings] 예상 용량 계산 실패: %s", exc)

    def refresh_disk_usage(self) -> None:
        """디스크/Redis/ClickHouse 사용량 레이블 갱신."""
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
        """현재 UI 상태에서 수집 설정 딕셔너리를 빌드."""
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
        """설정 딕셔너리를 UI 위젯에 반영."""
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
        """용량 절약 모드 프리셋 적용."""
        try:
            self.apply_settings_to_ui({
                "enabled_timeframes": ["1m", "5m", "1h"],
                "lookback_days": 3,
                "compression_days": 1,
                "retention_days": 90,
            })
            if _HAS_QT and self.widget:
                QMessageBox.information(
                    self.widget, "프리셋 적용",
                    "💾 용량 절약 모드 설정 완료\n\n"
                    "타임프레임: 1m, 5m, 1h\n"
                    "백필 기간: 3일\n"
                    "압축: 1일 후\n"
                    "보관: 3개월\n\n"
                    "예상 디스크 절약: 약 50%\n"
                    "설정이 자동으로 저장됩니다.",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] 용량 절약 프리셋 적용 실패: %s", exc)

    def on_preset_high_performance(self) -> None:
        """고성능 모드 프리셋 적용."""
        try:
            self.apply_settings_to_ui({
                "enabled_timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"],
                "lookback_days": 30,
                "compression_days": 30,
                "retention_days": 365,
            })
            if _HAS_QT and self.widget:
                QMessageBox.warning(
                    self.widget, "프리셋 적용",
                    "🚀 고성능 모드 설정 완료\n\n"
                    "⚠️ 주의: 디스크 100GB 이상 필요\n\n"
                    "타임프레임: 전체\n"
                    "백필 기간: 30일\n"
                    "압축: 30일 후\n"
                    "보관: 1년\n\n"
                    "설정이 자동으로 저장됩니다.",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] 고성능 프리셋 적용 실패: %s", exc)

    def on_preset_default(self) -> None:
        """기본값 복원."""
        try:
            self.apply_settings_to_ui({
                "enabled_timeframes": ["1m", "5m", "1h"],
                "lookback_days": 3,
                "compression_days": 1,
                "retention_days": 90,
            })
            if _HAS_QT and self.widget:
                QMessageBox.information(
                    self.widget, "초기화 완료",
                    "기본 설정으로 복원되었습니다.\n\n"
                    "설정이 자동으로 저장됩니다.",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] 기본값 복원 실패: %s", exc)

    def on_preset_indicator_minimum(self) -> None:
        """지표 최소 복원 프리셋 — RSI/MACD/BB 등 기술 지표 정확도 확보.

        DB설계1.md 기준:
          - RSI(14), MACD(26), BB(20) 안정화를 위해 최소 7일(≥10,080 1분봉) 필요
          - 1m + 5m + 1h, 7일 백필, 3개월 보관
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
                    self.widget, "지표 최소 복원",
                    "지표 최소 복원 설정 적용\n\n"
                    "타임프레임: 1m, 5m, 1h\n"
                    "백필 기간: 7일 (RSI14/MACD26/BB20 안정화)\n"
                    "압축: 1일 후\n"
                    "보관: 3개월\n\n"
                    "설정이 자동으로 저장됩니다.",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] 지표 최소 복원 프리셋 실패: %s", exc)

    def on_preset_aiml_minimum(self) -> None:
        """AI/ML 최소 복원 프리셋 — 학습용 충분한 과거 데이터 확보.

        DB설계1.md 기준:
          - Prophet/Transformer/XGBoost 학습: 최소 30일 이상 필요
          - 전체 타임프레임, 30일 백필, 1년 보관
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
                    self.widget, "AI/ML 최소 복원",
                    "AI/ML 최소 복원 설정 적용\n\n"
                    "주의: 디스크 50GB 이상 필요\n\n"
                    "타임프레임: 전체 (1m·5m·15m·1h·4h·1d)\n"
                    "백필 기간: 30일 (Prophet/Transformer/XGBoost 학습)\n"
                    "압축: 7일 후\n"
                    "보관: 1년\n\n"
                    "설정이 자동으로 저장됩니다.",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] AI/ML 최소 복원 프리셋 실패: %s", exc)

    def on_save(self) -> None:
        """현재 UI 설정을 MongoDB에 저장하고 TimescaleDB 정책을 갱신한다."""
        try:
            settings = self.collect_settings_from_ui()

            # MongoDB 저장 (비동기 - 별도 스레드에서 실행)
            self._save_settings_async(settings)

            # 환경변수 즉시 반영 (현재 프로세스)
            os.environ["ENABLED_TIMEFRAMES"] = ",".join(settings["enabled_timeframes"])
            os.environ["FORCE_ENQUEUE_LOOKBACK_DAYS"] = str(settings["lookback_days"])
            os.environ["TIMESCALE_COMPRESSION_DAYS"] = str(settings["compression_days"])
            os.environ["TIMESCALE_RETENTION_DAYS"] = str(settings["retention_days"])

            enabled_str = ", ".join(settings["enabled_timeframes"])
            ret_label = "영구 보관" if settings["retention_days"] == 0 else f"{settings['retention_days']}일"
            if _HAS_QT and self.widget:
                QMessageBox.information(
                    self.widget, "저장 완료",
                    "✅ 설정이 저장되었습니다.\n\n"
                    f"타임프레임: {enabled_str}\n"
                    f"백필 기간: {settings['lookback_days']}일\n"
                    f"압축: {settings['compression_days']}일 후\n"
                    f"보관: {ret_label}\n\n"
                    "⚠️ Gap Detector 워커를 재시작해야 새 타임프레임 설정이 완전히 적용됩니다.",
                )
        except Exception as exc:
            logger.error("[CollectionSettings] 수집 설정 저장 실패: %s", exc)
            if _HAS_QT and self.widget:
                QMessageBox.critical(self.widget, "저장 실패", f"설정 저장 중 오류:\n{exc}")

    def _save_settings_async(self, settings: Dict[str, Any]) -> None:
        """MongoDB 설정 저장을 별도 스레드에서 비동기로 실행."""
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
                        "src.02_data.mongodb.collection_settings",
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
                        logger.warning("[CollectionSettings] CollectionSettingsManager import 실패")
                        return
                    mgr = mgr_cls(client)
                    await mgr.save_settings(settings)
                    logger.info("[CollectionSettings] MongoDB 수집 설정 저장 완료: %s", settings)

                asyncio.run(_save())
            except Exception as exc:
                logger.warning("[CollectionSettings] MongoDB 설정 저장 실패 (비치명적): %s", exc)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
