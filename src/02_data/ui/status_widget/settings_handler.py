# -*- coding: utf-8 -*-
"""
설정 핸들러 Mixin (settings_handler.py)

개선 요약:
- autosave 디바운스(500ms) 및 주기 저장(10s)
- QTimer를 UI 위젯(self)를 부모로 하여 UI 스레드에 바인딩 보장
- 저장 동작을 백그라운드 스레드로 수행(기본), sync=True로 동기 저장 가능
- 변경 감지: 이전과 동일하면 저장 생략
- 팝업(다이얼로그) 닫힘 시 저장 연결 지원 (register_dialog_for_save)
- start_settings_handling 엔트리포인트 추가 — StatusWidget에서 UI 로드 직후 호출 권장
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QTimer, QCoreApplication
    from PyQt5.QtWidgets import QDialog
    _HAS_QT = True
except Exception:
    _HAS_QT = False

# 기본 UI 설정 (기본값)
DEFAULT_UI_SETTINGS = {
    "schema_version": 1,
    "chk_log_websocket": True,
    "chk_log_pipeline": True,
    "chk_log_gap": False,
    "chk_show_warnings": False,
    "combo_log_level": "전체",
    "chk_autoscroll": True,
    "sb_max_rows": 500,
    "le_log_search": "",
    "last_active_tab_index": 0,
}

# debounce 및 periodic interval
AUTOSAVE_DEBOUNCE_MS = 500
PERIODIC_SAVE_MS = 10_000  # 10 seconds

# 설정 스키마 버전 (향후 마이그레이션 용)
SETTINGS_SCHEMA_VERSION = 1


class SettingsHandlerMixin:
    """설정 핸들러 Mixin.

    사용��(권장):
    - StatusWidget에서 UI 로드 직후: self.start_settings_handling(mongo_client=self._mongo_client, collection_name="ui_status")
    - 다이얼로그를 닫을 때 저장하고 싶으면: self.register_dialog_for_save(dialog_instance)
    """

    _LOCAL_SETTINGS_FILENAME = os.path.join(os.path.expanduser("~"), ".upbit_trader_ui_settings.json")

    def __init_mixin_settings(self) -> None:
        """내부 상태 초기화(타이머/락 등)."""
        if not hasattr(self, "_settings_manager"):
            self._settings_manager: Optional[object] = None
        if not hasattr(self, "_settings_collection_name"):
            self._settings_collection_name = "default"
        if not hasattr(self, "_autosave_timer"):
            self._autosave_timer = None
        if not hasattr(self, "_periodic_save_timer"):
            self._periodic_save_timer = None
        if not hasattr(self, "_settings_save_lock"):
            self._settings_save_lock = threading.Lock()
        if not hasattr(self, "_last_save_ts"):
            self._last_save_ts = 0.0
        if not hasattr(self, "_last_saved_settings"):
            self._last_saved_settings: Optional[Dict[str, Any]] = None

    # -----------------------
    # QTimer 생성 보증 (UI 스레드에서 호출되어야 함)
    # -----------------------
    def _ensure_timers(self) -> None:
        """QTimer를 lazy로 생성. 반드시 UI(메인) 스레드에서 호출하세요."""
        self.__init_mixin_settings()
        if not _HAS_QT:
            return

        # autosave 타이머: singleShot 디바운스
        if getattr(self, "_autosave_timer", None) is None:
            try:
                self._autosave_timer = QTimer(self)
                self._autosave_timer.setSingleShot(True)
                self._autosave_timer.setInterval(AUTOSAVE_DEBOUNCE_MS)
                self._autosave_timer.timeout.connect(lambda: self.save_settings())
                logger.debug("[Settings] autosave_timer 생성(parent=self) interval=%dms", AUTOSAVE_DEBOUNCE_MS)
            except Exception as exc:
                logger.debug("[Settings] autosave_timer 생성 실패: %s", exc)

        # periodic 저장 타이머: 안정성 보장용
        if getattr(self, "_periodic_save_timer", None) is None:
            try:
                self._periodic_save_timer = QTimer(self)
                self._periodic_save_timer.setSingleShot(False)
                self._periodic_save_timer.setInterval(PERIODIC_SAVE_MS)
                self._periodic_save_timer.timeout.connect(lambda: self.save_settings())
                logger.debug("[Settings] periodic_save_timer 생성(parent=self) interval=%dms", PERIODIC_SAVE_MS)
            except Exception as exc:
                logger.debug("[Settings] periodic_save_timer 생성 실패: %s", exc)

    # -----------------------
    # 외부 주입 / 시작 엔트리포인트
    # -----------------------
    def set_settings_manager(self, manager: object, collection_name: str = "default") -> None:
        """외부에서 SettingsManager 객체를 주입합니다."""
        try:
            self.__init_mixin_settings()
            self._settings_manager = manager
            self._settings_collection_name = collection_name
            logger.debug("[Settings] SettingsManager 주입: collection=%s", collection_name)
        except Exception as exc:
            logger.debug("[Settings] set_settings_manager 실패: %s", exc)

    def start_settings_handling(self, mongo_client: object = None, collection_name: str = "default") -> None:
        """
        UI가 로드된 직후 호출하세요(예: StatusWidget UI 로드 성공 후).
        - SettingsManager 자동 초기화(내부 import 시도)
        - 설정 로드 및 UI 복원
        - autosave 바인딩 시작
        - app.aboutToQuit 에 동기 저장 연결 (마지막 저장 보증)
        """
        try:
            self.__init_mixin_settings()
            self._settings_collection_name = collection_name

            # 가능한 경우 매니저 초기화 시도
            if getattr(self, "_settings_manager", None) is None and mongo_client is not None:
                try:
                    from ...mongodb.settings_manager import SettingsManager as _UISettingsManager  # type: ignore
                    self._settings_manager = _UISettingsManager(mongo_client)
                    logger.info("[Settings] SettingsManager 생성(주입된 mongo_client 사용)")
                except Exception as exc:
                    logger.warning("[Settings] SettingsManager 생성 실패(주입된 mongo_client 사용): %s", exc)

            # 설정 로드 및 UI 복원
            try:
                self.load_and_restore_settings(mongo_client=mongo_client)
            except Exception as exc:
                logger.warning("[Settings] load_and_restore_settings 실패: %s", exc)

            # autosave 바인딩 및 타이머 생성
            try:
                self._setup_autosave_bindings()
            except Exception as exc:
                logger.debug("[Settings] _setup_autosave_bindings 호출 실패: %s", exc)

            # aboutToQuit 시 동기 저장 연결 (종료 시 설정 유실 방지)
            if _HAS_QT:
                try:
                    app = QCoreApplication.instance()
                    if app is not None:
                        def _on_app_quit():
                            try:
                                self.save_settings(sync=True)
                            except Exception:
                                logger.debug("[Settings] aboutToQuit 동기 저장 실패", exc_info=True)

                        try:
                            app.aboutToQuit.connect(_on_app_quit)
                            logger.debug("[Settings] aboutToQuit에 동기 저장 핸들러 연결됨")
                        except Exception as exc:
                            logger.debug("[Settings] aboutToQuit 연결 실패: %s", exc)
                except Exception as exc:
                    logger.debug("[Settings] aboutToQuit 연결 과정 오류: %s", exc)
        except Exception as exc:
            logger.debug("[Settings] start_settings_handling 실패: %s", exc)

    # -----------------------
    # 로드/복원
    # -----------------------
    def load_and_restore_settings(self, mongo_client: object = None) -> None:
        """설정 로드(우선 DB, 실패 시 파일) 및 UI에 적용."""
        try:
            self.__init_mixin_settings()

            # 파일 복원 ��로 (Mongo 미사용)
            if mongo_client is None and getattr(self, "_settings_manager", None) is None:
                logger.debug("[Settings] MongoDB 클라이언트 미제공 - 파일 기반 복원 시도")
                settings = self._load_settings_from_file()
                self._apply_ui_settings_safe(settings)
                self._last_saved_settings = settings.copy() if isinstance(settings, dict) else None
                return

            # SettingsManager가 없으면 내부 초기화 시도
            if getattr(self, "_settings_manager", None) is None:
                try:
                    from ...mongodb.settings_manager import SettingsManager as _UISettingsManager  # type: ignore
                    mgr = _UISettingsManager(mongo_client)
                    self._settings_manager = mgr
                    logger.info("[Settings] SettingsManager 초기화 완료 (내부)")
                except Exception as exc:
                    logger.warning("[Settings] SettingsManager 초기화 실패, 파일 복원 시도: %s", exc)
                    settings = self._load_settings_from_file()
                    self._apply_ui_settings_safe(settings)
                    self._last_saved_settings = settings.copy() if isinstance(settings, dict) else None
                    return

            # DB에서 로드 시도 (실패 시 파일 복원)
            try:
                settings = getattr(self._settings_manager, "load_settings")(self._settings_collection_name)
                if not isinstance(settings, dict):
                    raise ValueError("loaded settings is not a dict")
                logger.info("[Settings] MongoDB에서 UI 설정 로드 완료")
            except Exception as exc:
                logger.warning("[Settings] MongoDB에서 UI 설정 로드 실패, 파일 복원 시도: %s", exc)
                settings = self._load_settings_from_file()

            self._apply_ui_settings_safe(settings)
            self._last_saved_settings = settings.copy() if isinstance(settings, dict) else None
        except Exception as exc:
            logger.debug("[Settings] load_and_restore_settings 실패: %s", exc)

    # aliases
    restore_settings = load_and_restore_settings
    load_settings = load_and_restore_settings
    _restore_settings = load_and_restore_settings
    _load_settings = load_and_restore_settings
    restore_ui_settings = load_and_restore_settings

    # -----------------------
    # 저장 API (비동기 기본) — 변경감지 포함
    # -----------------------
    def save_settings(self, sync: bool = False) -> None:
        """
        설정 저장 진입점.
        - 기본: 비동기 저장(백그라운드 쓰레드)
        - sync=True: 호출 스레드에서 동기적으로 저장(종료 시 사용 권장)
        """
        try:
            self.__init_mixin_settings()
            data = self._gather_ui_settings()
            data.setdefault("schema_version", SETTINGS_SCHEMA_VERSION)

            # 변경 감지: 마지막으로 저장된 값과 동일하면 저장 건너뜀
            last = getattr(self, "_last_saved_settings", None)
            try:
                if isinstance(last, dict) and last == data:
                    logger.debug("[Settings] 변경 없음 ��� 저장 생략")
                    return
            except Exception:
                logger.debug("[Settings] 변경 감지 비교 중 오류", exc_info=True)

            # debug: 저장 시 주요 키 로그
            try:
                sample_keys = ", ".join(list(data.keys())[:12])
            except Exception:
                sample_keys = "(keys unavailable)"
            logger.debug("[Settings] save_settings 호출 - keys: %s", sample_keys)

            if sync:
                self._save_settings_sync(data)
                try:
                    self._last_saved_settings = data.copy()
                except Exception:
                    pass
                return

            # 비동기 저장(백그라운드 쓰레드)
            try:
                t = threading.Thread(target=self._save_settings_async, args=(data,), daemon=True)
                t.start()
                logger.debug("[Settings] 설정 저장을 백그라운드 쓰레드로 위임")
            except Exception as exc:
                logger.debug("[Settings] ���그라운드 저장 스레드 생성 실패, 동기 저장 시도: %s", exc)
                try:
                    self._save_settings_sync(data)
                    try:
                        self._last_saved_settings = data.copy()
                    except Exception:
                        pass
                except Exception as exc2:
                    logger.error("[Settings] 동기 저장도 실패: %s", exc2)
        except Exception as exc:
            logger.debug("[Settings] save_settings 실패: %s", exc)

    _save_settings = save_settings
    persist_settings = save_settings
    _persist_settings = save_settings
    store_settings = save_settings

    def _save_settings_async(self, data: Dict[str, Any]) -> None:
        """실제 저장 로직: DB 우선, 실패 시 파일 저장. 백그라운드에서 실행됨."""
        try:
            with self._settings_save_lock:  # type: ignore[attr-defined]
                now = time.time()
                if now - getattr(self, "_last_save_ts", 0.0) < 0.05:
                    logger.debug("[Settings] 너무 잦은 저장 요청 무시")
                    return
                self._last_save_ts = now

                mgr = getattr(self, "_settings_manager", None)
                last_exc = None
                saved = False
                if mgr is not None:
                    try:
                        if hasattr(mgr, "save_settings"):
                            try:
                                getattr(mgr, "save_settings")(data)
                                logger.info("[Settings] 설정 저장 성공 (to DB) via save_settings(data)")
                                saved = True
                            except TypeError:
                                try:
                                    getattr(mgr, "save_settings")(self._settings_collection_name, data)
                                    logger.info("[Settings] 설정 저장 성공 (to DB) via save_settings(name,data)")
                                    saved = True
                                except Exception as exc:
                                    last_exc = exc
                        if not saved and hasattr(mgr, "set_settings"):
                            try:
                                getattr(mgr, "set_settings")(self._settings_collection_name, data)
                                logger.info("[Settings] 설정 저장 성공 (to DB) via set_settings(name,data)")
                                saved = True
                            except Exception as exc:
                                last_exc = exc
                        if not saved and hasattr(mgr, "upsert"):
                            try:
                                getattr(mgr, "upsert")(self._settings_collection_name, data)
                                logger.info("[Settings] 설정 저장 성공 (to DB) via upsert(name,data)")
                                saved = True
                            except Exception as exc:
                                last_exc = exc
                        if not saved and hasattr(mgr, "save"):
                            try:
                                getattr(mgr, "save")(self._settings_collection_name, data)
                                logger.info("[Settings] 설정 저장 성공 (to DB) via save(name,data)")
                                saved = True
                            except Exception as exc:
                                last_exc = exc
                        if not saved and isinstance(mgr, dict):
                            try:
                                mgr[self._settings_collection_name] = data
                                logger.info("[Settings] 설정 저장 성공 (to dict mgr)")
                                saved = True
                            except Exception as exc:
                                last_exc = exc
                    except Exception as exc:
                        last_exc = exc

                if saved:
                    try:
                        self._last_saved_settings = data.copy()
                    except Exception:
                        pass
                    return

                # DB 저장 실패 시 파일로 폴백
                logger.warning("[Settings] DB 저장 실패 또는 매니저 없음, 로컬 파일로 저장 시도 (%s)", last_exc)
                try:
                    self._save_settings_to_file(data)
                    logger.info("[Settings] 설정 로컬 파일 저장 성공: %s", self._LOCAL_SETTINGS_FILENAME)
                    try:
                        self._last_saved_settings = data.copy()
                    except Exception:
                        pass
                    return
                except Exception as exc:
                    logger.error("[Settings] 로컬 파일 저장 실패: %s", exc)
        except Exception as exc:
            logger.debug("[Settings] _save_settings_async 내부 오류: %s", exc)

    def _save_settings_sync(self, data: Dict[str, Any]) -> None:
        """동기 저장(종료 시 사용). DB에 실패하면 파일로 폴백 — 호출 스레드에서 실행됨."""
        try:
            mgr = getattr(self, "_settings_manager", None)
            last_exc = None
            saved = False
            if mgr is not None:
                try:
                    if hasattr(mgr, "save_settings"):
                        try:
                            getattr(mgr, "save_settings")(data)
                            logger.info("[Settings] 설정 동기 저장 성공 (to DB) via save_settings(data)")
                            saved = True
                        except TypeError:
                            try:
                                getattr(mgr, "save_settings")(self._settings_collection_name, data)
                                logger.info("[Settings] 설정 동기 저장 성공 (to DB) via save_settings(name,data)")
                                saved = True
                            except Exception as exc:
                                last_exc = exc
                    if not saved and hasattr(mgr, "set_settings"):
                        try:
                            getattr(mgr, "set_settings")(self._settings_collection_name, data)
                            logger.info("[Settings] 설정 동기 저장 성공 (to DB) via set_settings")
                            saved = True
                        except Exception as exc:
                            last_exc = exc
                    if not saved and hasattr(mgr, "upsert"):
                        try:
                            getattr(mgr, "upsert")(self._settings_collection_name, data)
                            logger.info("[Settings] 설정 동기 저장 성공 (to DB) via upsert")
                            saved = True
                        except Exception as exc:
                            last_exc = exc
                except Exception as exc:
                    last_exc = exc

            if saved:
                try:
                    self._last_saved_settings = data.copy()
                except Exception:
                    pass
                return

            # DB 저장 불가 → 파일 저장
            try:
                self._save_settings_to_file(data)
                logger.info("[Settings] 설정 동기 로컬 파일 저장 성공: %s", self._LOCAL_SETTINGS_FILENAME)
                try:
                    self._last_saved_settings = data.copy()
                except Exception:
                    pass
            except Exception as exc:
                logger.error("[Settings] 설정 동기 파일 저장 실패: %s", exc)
        except Exception as exc:
            logger.debug("[Settings] _save_settings_sync 내부 오류: %s", exc)

    # -----------------------
    # UI 상태 수집/적용
    # -----------------------
    def _gather_ui_settings(self) -> Dict[str, Any]:
        """현재 UI 위젯 상태를 수집하여 딕셔너리로 반환."""
        settings: Dict[str, Any] = {}
        try:
            settings.update(DEFAULT_UI_SETTINGS)
            for name in ("chk_log_websocket", "chk_log_pipeline", "chk_log_gap", "chk_show_warnings", "chk_autoscroll"):
                try:
                    w = getattr(self, name, None)
                    if w is not None and hasattr(w, "isChecked"):
                        settings[name] = bool(w.isChecked())
                except Exception:
                    logger.debug("[Settings] 체크박스 수집 실패: %s", name)
            try:
                cb = getattr(self, "combo_log_level", None)
                if cb is not None and hasattr(cb, "currentText"):
                    settings["combo_log_level"] = str(cb.currentText())
            except Exception:
                logger.debug("[Settings] combo_log_level 수집 실패")
            try:
                sb = getattr(self, "sb_max_rows", None)
                if sb is not None and hasattr(sb, "value"):
                    settings["sb_max_rows"] = int(sb.value())
            except Exception:
                logger.debug("[Settings] sb_max_rows 수집 실패")
            try:
                le = getattr(self, "le_log_search", None)
                if le is not None and hasattr(le, "text"):
                    settings["le_log_search"] = str(le.text())
            except Exception:
                logger.debug("[Settings] le_log_search 수집 실패")
            try:
                tabw = getattr(self, "tabWidget", None)
                if tabw is not None and hasattr(tabw, "currentIndex"):
                    settings["last_active_tab_index"] = int(tabw.currentIndex())
            except Exception:
                logger.debug("[Settings] tabWidget index 수집 실패")
        except Exception as exc:
            logger.debug("[Settings] _gather_ui_settings 실패: %s", exc)
        return settings

    def _apply_ui_settings_safe(self, settings: Optional[Dict[str, Any]], source: str = "file") -> None:
        """UI 적용을 안전하게 예약합니다(메인 스레드에서 실행)."""
        try:
            if not isinstance(settings, dict):
                settings = {}
            merged = DEFAULT_UI_SETTINGS.copy()
            merged.update(settings)
            if _HAS_QT:
                try:
                    QTimer.singleShot(0, lambda: self._apply_ui_settings(merged))
                    logger.debug("[Settings] UI 설정 적용 예약 (source=%s)", source)
                    return
                except Exception:
                    logger.debug("[Settings] QTimer.singleShot 예약 실패", exc_info=True)
            self._apply_ui_settings(merged)
        except Exception as exc:
            logger.debug("[Settings] _apply_ui_settings_safe 실패: %s", exc)

    def _apply_ui_settings(self, settings: Dict[str, Any]) -> None:
        """실제 UI에 설정을 적용합니다(동기)."""
        try:
            for name in ("chk_log_websocket", "chk_log_pipeline", "chk_log_gap", "chk_show_warnings", "chk_autoscroll"):
                try:
                    if name in settings:
                        val = bool(settings.get(name))
                        w = getattr(self, name, None)
                        if w is not None and hasattr(w, "setChecked"):
                            try:
                                w.setChecked(val)
                            except Exception:
                                logger.debug("[Settings] 체크박스 적용 실패: %s", name)
                except Exception:
                    logger.debug("[Settings] 체크박스 적용 중 예외: %s", name)
            try:
                if "combo_log_level" in settings:
                    val = settings.get("combo_log_level")
                    cb = getattr(self, "combo_log_level", None)
                    if cb is not None:
                        try:
                            if hasattr(cb, "setCurrentText"):
                                cb.setCurrentText(str(val))
                            else:
                                idx = cb.findText(str(val)) if hasattr(cb, "findText") else -1
                                if idx is not None and idx >= 0:
                                    cb.setCurrentIndex(idx)
                        except Exception:
                            logger.debug("[Settings] combo_log_level 적용 실패")
            except Exception:
                logger.debug("[Settings] combo_log_level 처리 오류")
            try:
                if "sb_max_rows" in settings:
                    val = int(settings.get("sb_max_rows", DEFAULT_UI_SETTINGS["sb_max_rows"]))
                    sb = getattr(self, "sb_max_rows", None)
                    if sb is not None and hasattr(sb, "setValue"):
                        try:
                            sb.setValue(val)
                        except Exception:
                            logger.debug("[Settings] sb_max_rows 적용 실패")
            except Exception:
                logger.debug("[Settings] sb_max_rows 처리 오류")
            try:
                if "le_log_search" in settings:
                    val = str(settings.get("le_log_search", ""))
                    le = getattr(self, "le_log_search", None)
                    if le is not None and hasattr(le, "setText"):
                        try:
                            le.setText(val)
                        except Exception:
                            logger.debug("[Settings] le_log_search 적용 실패")
            except Exception:
                logger.debug("[Settings] le_log_search 처리 오류")
            try:
                if "last_active_tab_index" in settings:
                    idx = int(settings.get("last_active_tab_index", 0))
                    tabw = getattr(self, "tabWidget", None)
                    if tabw is not None and hasattr(tabw, "setCurrentIndex"):
                        try:
                            tabw.setCurrentIndex(max(0, idx))
                        except Exception:
                            logger.debug("[Settings] tabWidget index 적용 실패")
            except Exception:
                logger.debug("[Settings] tabWidget 처리 오류")
            logger.info("[Settings] UI 설정 적용 완료")
        except Exception as exc:
            logger.debug("[Settings] _apply_ui_settings 실패: %s", exc)

    # -----------------------
    # 파일 저장/로드 헬퍼
    # -----------------------
    def _load_settings_from_file(self) -> Dict[str, Any]:
        """로컬 파일에서 설정을 읽어 반환 (실패 시 DEFAULT 반환)."""
        try:
            if os.path.exists(self._LOCAL_SETTINGS_FILENAME):
                try:
                    with open(self._LOCAL_SETTINGS_FILENAME, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            logger.debug("[Settings] local settings 파일 로드 완료: %s", self._LOCAL_SETTINGS_FILENAME)
                            return data
                except Exception as exc:
                    logger.warning("[Settings] local settings 파일 읽기 실패: %s", exc)
        except Exception as exc:
            logger.debug("[Settings] _load_settings_from_file 예외: %s", exc)
        return DEFAULT_UI_SETTINGS.copy()

    def _save_settings_to_file(self, data: Dict[str, Any]) -> None:
        """로컬 파일로 설정을 저장 (동기)."""
        try:
            safe_data = {}
            for k, v in data.items():
                try:
                    json.dumps(v)
                    safe_data[k] = v
                except Exception:
                    try:
                        safe_data[k] = str(v)
                    except Exception:
                        safe_data[k] = None
            d = os.path.dirname(self._LOCAL_SETTINGS_FILENAME)
            if d and not os.path.exists(d):
                try:
                    os.makedirs(d, exist_ok=True)
                except Exception as exc:
                    logger.debug("[Settings] 디렉토리 생성 실패: %s", exc)
            with open(self._LOCAL_SETTINGS_FILENAME, "w", encoding="utf-8") as f:
                json.dump(safe_data, f, indent=2, ensure_ascii=False)
            logger.debug("[Settings] local settings 파일 저장됨: %s", self._LOCAL_SETTINGS_FILENAME)
        except Exception as exc:
            logger.error("[Settings] _save_settings_to_file 실패: %s", exc)

    # -----------------------
    # autosave 바인딩
    # -----------------------
    def _setup_autosave_bindings(self) -> None:
        """주요 UI 컨트롤에 대해 변경 시그널을 autosave에 연결합니다. UI가 준비된 후 호출하세요."""
        try:
            self.__init_mixin_settings()
            self._ensure_timers()

            # 체크박스
            for name in ("chk_log_websocket", "chk_log_pipeline", "chk_log_gap", "chk_show_warnings", "chk_autoscroll"):
                w = getattr(self, name, None)
                if w is not None:
                    try:
                        if hasattr(w, "toggled"):
                            w.toggled.connect(lambda _checked, s=name: self._schedule_autosave())
                        elif hasattr(w, "clicked"):
                            w.clicked.connect(lambda _checked, s=name: self._schedule_autosave())
                    except Exception as exc:
                        logger.debug("[Settings] 체크박스 바인딩 실패(%s): %s", name, exc)

            # 콤보박스
            cb = getattr(self, "combo_log_level", None)
            if cb is not None:
                try:
                    if hasattr(cb, "currentIndexChanged"):
                        cb.currentIndexChanged.connect(lambda _idx: self._schedule_autosave())
                    elif hasattr(cb, "currentTextChanged"):
                        cb.currentTextChanged.connect(lambda _text: self._schedule_autosave())
                except Exception as exc:
                    logger.debug("[Settings] combo 바인딩 실패: %s", exc)

            # spinbox
            sb = getattr(self, "sb_max_rows", None)
            if sb is not None:
                try:
                    if hasattr(sb, "valueChanged"):
                        sb.valueChanged.connect(lambda _v: self._schedule_autosave())
                except Exception as exc:
                    logger.debug("[Settings] spinbox 바인딩 실패: %s", exc)

            # lineedit
            le = getattr(self, "le_log_search", None)
            if le is not None:
                try:
                    if hasattr(le, "textChanged"):
                        le.textChanged.connect(lambda _t: self._schedule_autosave())
                except Exception as exc:
                    logger.debug("[Settings] lineedit 바인딩 실패: %s", exc)

            # tab widget index change
            tabw = getattr(self, "tabWidget", None)
            if tabw is not None:
                try:
                    if hasattr(tabw, "currentChanged"):
                        tabw.currentChanged.connect(lambda _i: self._schedule_autosave())
                except Exception as exc:
                    logger.debug("[Settings] tabWidget 바인딩 실패: %s", exc)

            # periodic timer 자동 시작
            try:
                t = getattr(self, "_periodic_save_timer", None)
                if t is not None and not t.isActive():
                    t.start()
                    logger.debug("[Settings] periodic_save_timer 시작 (interval=%dms)", PERIODIC_SAVE_MS)
            except Exception as exc:
                logger.debug("[Settings] periodic_save_timer 시작 실패: %s", exc)

            logger.debug("[Settings] autosave 바인딩 완료")
        except Exception as exc:
            logger.debug("[Settings] _setup_autosave_bindings 실패: %s", exc)

    def _schedule_autosave(self) -> None:
        """자동 저장 타이머 재시작(디바운스)."""
        try:
            self.__init_mixin_settings()
            self._ensure_timers()
            t = getattr(self, "_autosave_timer", None)
            if t is None:
                self.save_settings()
                return
            if t.isActive():
                t.stop()
            t.start()
        except Exception as exc:
            logger.debug("[Settings] _schedule_autosave 실패: %s", exc)

    # -----------------------
    # 팝업(다이얼로그) 닫힘 시 저장 헬퍼
    # -----------------------
    def register_dialog_for_save(self, dialog: "QDialog") -> None:
        """
        다이얼로그가 닫힐 때 설정을 저장하도록 연결합니다.
        사용 예: self.register_dialog_for_save(someDialog)
        """
        if not _HAS_QT or dialog is None:
            return
        try:
            if hasattr(dialog, "finished"):
                dialog.finished.connect(lambda _code: self.save_settings())
            if hasattr(dialog, "accepted"):
                dialog.accepted.connect(lambda: self.save_settings())
            if hasattr(dialog, "rejected"):
                dialog.rejected.connect(lambda: self.save_settings())
            logger.debug("[Settings] 다이얼로그 저장 연결 설정됨")
        except Exception as exc:
            logger.debug("[Settings] register_dialog_for_save 연결 실패: %s", exc)