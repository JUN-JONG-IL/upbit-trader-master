#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
앱 진입점(간단한 래퍼)

변경 요지:
- stdout/stderr를 devnull로 리다이렉트하는 'shim' 제거 (정석적 임포트 방식 사용)
- 콘솔 핸들러 레벨을 WARNING으로 낮추어 INFO 노이즈 차단
- QtLogHandler 추가: 통신 관련 INFO 로그를 UI 콜백으로 전달
- LOG_MINIMAL/LOG_LOGGERS/LOG_LEVEL/LOG_TZ 환경변수로 동작 제어
- bootstrap 모듈에서 StatusWidget 인스턴스를 자동으로 찾아 SettingsManager 주입 시도
- settings_manager 모듈은 안전하게 파일 경로로 로드(숫자로 시작하는 패키 네임 문��� 회피)
- 전역 TimescaleDB 연결 풀(init_global_pool)을 앱 초기화 전에 시도하도록 추가
- main 모듈을 'main' 별칭으로 등록하여 StatusWidget의 register_ui_log_consumer 탐색 실패 방지
- bootstrap.main 호출 직후 UI 등록 진단 로그 출력 (임시 디버그)
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import os
from pathlib import Path
import logging
from typing import Optional, Callable, List
from datetime import datetime, timezone, timedelta

# Ensure an early basic logging handler so propagated DEBUG logs have somewhere to go.
# This is diagnostic-only; you can remove or lower level after troubleshooting.
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(name)s] [%(levelname)s] %(message)s")

# Optional PyQt imports for QtLogHandler UI delivery
try:
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    _HAS_QT_FOR_LOG = True
except Exception:
    _HAS_QT_FOR_LOG = False

# ----------------------------
# 시간대 포맷 지원 포매터
# ----------------------------
class TZFormatter(logging.Formatter):
    """시간대(UTC/KST)를 반영한 formatTime 구현"""
    def __init__(self, fmt=None, datefmt=None, tz_name: str = "KST"):
        super().__init__(fmt=fmt, datefmt=datefmt)
        if tz_name and tz_name.upper() == "UTC":
            self._tz = timezone.utc
        else:
            self._tz = timezone(timedelta(hours=9))  # KST 기본

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=self._tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%H:%M:%S")

# ----------------------------
# 중복 억제 필터
# ----------------------------
class DedupFilter(logging.Filter):
    """
    동일한 (logger name, level, message) 조합이 반복되면 이후 것은 무시.
    """
    def __init__(self):
        super().__init__()
        self._seen = set()

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            key = (record.name, record.levelno, record.getMessage())
            if key in self._seen:
                return False
            self._seen.add(key)
            return True
        except Exception:
            return True

# ----------------------------
# UI 전달용 로깅 핸들러 (Qt-friendly)
# ----------------------------
_ui_log_consumers: List[Callable[[str, logging.LogRecord], None]] = []

def register_ui_log_consumer(fn: Callable[[str, logging.LogRecord], None]) -> None:
    """UI에서 호출: 문자열(포맷된), LogRecord 형태로 전달받을 콜백 등록"""
    if callable(fn):
        _ui_log_consumers.append(fn)

def unregister_ui_log_consumer(fn: Callable[[str, logging.LogRecord], None]) -> None:
    """UI 콜백 등록 해제"""
    try:
        _ui_log_consumers.remove(fn)
    except Exception:
        pass

class QtLogHandler(logging.Handler):
    """로그를 포맷해서 등록된 UI 콜백으로 전달하는 핸들러.

    전달 방식:
      - PyQt가 사용 가능하고 QApplication이 존재하면 QTimer.singleShot(0, ...)을 사용해
        메인(UI) 스레드에서 비동기 호출하도록 함.
      - 그렇지 않으면 동기 콜백 호출.
    """
    def __init__(self, level=logging.INFO, fmt: Optional[str] = None, datefmt: Optional[str] = None, tz_name: str = "KST"):
        super().__init__(level=level)
        fmt = fmt or "%(asctime)s %(levelname)s %(name)s: %(message)s"
        self._formatter = TZFormatter(fmt=fmt, datefmt=datefmt, tz_name=tz_name)
        self.addFilter(DedupFilter())

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self._formatter.format(record)
            # deliver to registered UI consumers
            if not _ui_log_consumers:
                return
            if _HAS_QT_FOR_LOG:
                try:
                    app = QApplication.instance()
                    if app is not None:
                        # schedule on UI thread
                        def _deliver():
                            for cb in list(_ui_log_consumers):
                                try:
                                    cb(msg, record)
                                except Exception:
                                    logger = logging.getLogger(__name__)
                                    logger.debug("UI log consumer raised", exc_info=True)
                        QTimer.singleShot(0, _deliver)
                        return
                except Exception:
                    pass
            # fallback synchronous delivery
            for cb in list(_ui_log_consumers):
                try:
                    cb(msg, record)
                except Exception:
                    logger = logging.getLogger(__name__)
                    logger.debug("UI log consumer raised", exc_info=True)
        except Exception:
            self.handleError(record)

# ----------------------------
# 전역 로깅 구성 함수 (핵심 로그만 기본 허용)
# ----------------------------
def _configure_global_logging():
    """
    전역 로깅 구성:
      - 기본적으로 최소모드 활성화 (환경변수로 해제 가능)
      - LOG_MINIMAL: '0' 또는 'false'로 설정하면 전체 모드(기존 동작)
      - LOG_LOGGERS: 사용자 정의 허용 로거(콤마 구분)로 오버라이드 가능
      - LOG_UI_LOGGERS: UI로 보낼 로거 접두사(콤마 구분), 기본값은 통신 관련 접두사들
      - LOG_LEVEL: 전체 모드에서 적용되는 기본 레벨 (예: INFO, DEBUG)
      - LOG_TZ: 'UTC' 또는 'KST' (기본 KST)
    """
    root = logging.getLogger()
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # 기본: minimal mode ON unless user explicitly disables
    env_val = os.getenv("LOG_MINIMAL", None)
    if env_val is None:
        minimal_mode = True
    else:
        minimal_mode = str(env_val).lower() not in ("0", "false", "no", "")

    tz_name = os.getenv("LOG_TZ", "KST").upper()

    # 기본 루트 레벨 설정(전체 모드 대비)
    root.setLevel(level)

    # 콘솔 핸들러(중복 추가 방지) — 터미널에는 WARNING 이상만 출력 (요청 사항)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        ch = logging.StreamHandler()
        ch.setLevel(logging.WARNING)  # 변경: INFO -> WARNING (콘솔에 INFO 노이즈 차단)
        fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
        ch.setFormatter(TZFormatter(fmt=fmt, datefmt="%H:%M:%S", tz_name=tz_name))
        ch.addFilter(DedupFilter())
        root.addHandler(ch)
    else:
        for h in root.handlers:
            try:
                h.addFilter(DedupFilter())
            except Exception:
                pass

    if minimal_mode:
        # 1) 기본적으로 루트 WARNING 설정 -> 전역 노이즈 억제
        root.setLevel(logging.WARNING)

        # 2) 기본 허용 핵심 로거 목록 (권장 기본값)
        default_allowed = [
            "app.core.startup_validator",
            "data_01.mongodb.init_mongodb",
            "src.data_01.timescale.health_check",
            "data_01.timescale.operations.gap_finder",
            "01_core.auth.ui.widget_login",
            "data_01.core.data_manager",
            "static",
        ]

        # 사용자 정의 허용 로거(콤마 구분)로 오버라이드 가능
        loggers_env = os.getenv("LOG_LOGGERS", "")
        allowed = [s.strip() for s in loggers_env.split(",") if s.strip()] if loggers_env else default_allowed

        # 먼저 모든 known loggers를 WARNING으로 올려 노이즈 차단(명시적)
        manager = logging.Logger.manager
        for name, logger_obj in list(manager.loggerDict.items()):
            try:
                if isinstance(logger_obj, logging.Logger):
                    logger_obj.setLevel(logging.WARNING)
            except Exception:
                pass

        # 허용 목록(접두사 포함)만 INFO로 낮춤
        for allow in allowed:
            try:
                logging.getLogger(allow).setLevel(logging.INFO)
            except Exception:
                pass
            for name, logger_obj in list(manager.loggerDict.items()):
                try:
                    if isinstance(logger_obj, logging.Logger):
                        if name == allow or name.startswith(allow + ".") or name.startswith(allow):
                            logger_obj.setLevel(logging.INFO)
                except Exception:
                    pass
    else:
        noisy = ["tzlocal", "asyncio", "aiopyupbit", "websockets", "pymongo", "apscheduler.executors.default", "apscheduler.scheduler"]
        for nm in noisy:
            try:
                logging.getLogger(nm).setLevel(logging.WARNING)
            except Exception:
                pass

    # --- QtLogHandler 등록 (UI 용) ---
    try:
        ui_loggers_env = os.getenv("LOG_UI_LOGGERS", "")
        if ui_loggers_env:
            ui_prefixes = [s.strip() for s in ui_loggers_env.split(",") if s.strip()]
        else:
            ui_prefixes = ["timescale", "data_01", "o2_data", "websocket", "pipeline", "collectors", "gap_finder"]

        qt_handler = QtLogHandler(level=logging.INFO, fmt="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S", tz_name=tz_name)

        class UILogFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                try:
                    name = record.name or ""
                    for p in ui_prefixes:
                        if name == p or name.startswith(p + ".") or name.startswith(p):
                            # Only INFO/DEBUG/NOTICE are forwarded to UI; WARNING/ERROR remain for console too
                            return record.levelno <= logging.INFO
                    return False
                except Exception:
                    return False

        qt_handler.addFilter(UILogFilter())

        root_has_qt = any(isinstance(h, QtLogHandler) for h in root.handlers)
        if not root_has_qt:
            root.addHandler(qt_handler)
    except Exception:
        logging.getLogger(__name__).debug("Failed to install QtLogHandler (UI logging disabled)", exc_info=True)

# 즉시 로깅 구성
try:
    _configure_global_logging()
except Exception:
    pass

# --- 핵심 추가: 이 모듈을 'main' 별칭으로도 등록하여 StatusWidget가 안정적으로 main 모듈을 찾도록 함 ---
sys.modules.setdefault("main", sys.modules.get(__name__, sys.modules.get("__main__")))

# After configuring global logging, make sure our diagnostic loggers will output DEBUG.
for _diag in ("timescale_pool", "timescale_db"):
    try:
        lg = logging.getLogger(_diag)
        lg.setLevel(logging.DEBUG)
        lg.propagate = True
        for h in list(lg.handlers):
            try:
                h.setLevel(logging.DEBUG)
            except Exception:
                pass
    except Exception:
        pass

_log = logging.getLogger(__name__)

# ----------------------------
# repo 루트 / src 경로 sys.path 선행 추가 (원본 로직 유지)
# ----------------------------
try:
    _this_file = Path(__file__).resolve()
    _repo_root: Optional[Path] = None
    for p in _this_file.parents:
        if p.name == "src":
            _repo_root = p.parent
            break
    if _repo_root is None:
        _repo_root = _this_file.parents[2] if len(_this_file.parents) >= 3 else _this_file.parent

    _src_path = str(_repo_root / "src")
    _repo_root_str = str(_repo_root)

    if _src_path not in sys.path:
        sys.path.insert(0, _src_path)
    if _repo_root_str not in sys.path:
        sys.path.insert(0, _repo_root_str)

    _log.debug("main_entry: prepended paths: %s, %s", _src_path, _repo_root_str)
except Exception as _e:
    _log.debug("main_entry: path prepending failed: %s", _e)

# ----------------------------
# 전역 TimescaleDB 풀 초기화 시도 (앱 시작 직전에 수행)
# ----------------------------
def _init_global_pool_from_env(minconn: int = 10, maxconn: int = 100) -> None:
    try:
        dsn = os.getenv("TIMESCALE_DSN") or os.getenv("DATABASE_URL")
        if not dsn:
            _log.debug("[main] No TIMESCALE_DSN or DATABASE_URL env var found; skipping global pool init")
            return

        try:
            src_root = Path(_repo_root) / "src" if "_repo_root" in globals() else Path(__file__).resolve().parents[2] / "src"
        except Exception:
            src_root = Path(__file__).resolve().parents[2] / "src"

        pool_path = src_root / "data_01" / "timescale" / "pool.py"
        if not pool_path.exists():
            _log.debug("[main] pool.py not found at expected path: %s", pool_path)
            return

        spec = importlib.util.spec_from_file_location("_timescale_pool_file", str(pool_path))
        if spec is None or spec.loader is None:
            _log.debug("[main] pool.py spec creation failed: %s", pool_path)
            return
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)  # type: ignore
        except Exception as e_load:
            _log.debug("[main] pool.py module load failed: %s", e_load, exc_info=True)
            return

        init_fn = getattr(mod, "init_global_pool", None)
        if not callable(init_fn):
            _log.debug("[main] init_global_pool not found in pool.py: %s", pool_path)
            return

        try:
            init_fn(dsn, minconn=minconn, maxconn=maxconn)
            _log.info("[main] _init_global_pool: pool init succeeded (minconn=%d,maxconn=%d)", minconn, maxconn)
            try:
                plog = logging.getLogger("timescale_pool")
                plog.setLevel(logging.DEBUG)
                plog.propagate = True
                for h in list(plog.handlers):
                    try:
                        h.setLevel(logging.DEBUG)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception as e_init:
            _log.warning("[main] init_global_pool failed: %s", e_init, exc_info=True)
    except Exception as _ex:
        _log.debug("[main] Unexpected error in _init_global_pool_from_env: %s", _ex, exc_info=True)

try:
    _init_global_pool_from_env(minconn=10, maxconn=100)
except Exception:
    _log.debug("[main] Global pool init attempt raised unexpected exception", exc_info=True)

# ----------------------------
# bootstrap import (정석적 임포트 방식)
# ----------------------------
_bootstrap = None
_try_names = ("src.app.bootstrap", "app.bootstrap", "bootstrap")

def _import_bootstrap(minimal_mode: bool):
    global _bootstrap
    for name in _try_names:
        try:
            _bootstrap = importlib.import_module(name)
            _log.debug("bootstrap imported via name: %s", name)
            return
        except Exception:
            continue

    here = os.path.dirname(os.path.abspath(__file__))
    fp = os.path.join(here, "bootstrap.py")
    if os.path.isfile(fp):
        try:
            spec = importlib.util.spec_from_file_location("app.bootstrap", fp)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                _bootstrap = mod
                _log.debug("bootstrap loaded from file: %s", fp)
                return
        except Exception as e:
            _log.debug("bootstrap load from file failed: %s", e, exc_info=True)

env_val = os.getenv("LOG_MINIMAL", None)
minimal_now = True if env_val is None else (str(env_val).lower() not in ("0", "false", "no", ""))
_import_bootstrap(minimal_now)

if _bootstrap is None:
    raise RuntimeError("bootstrap module could not be imported")

# ----------------------------
# main_entry 래퍼
# ----------------------------
def _find_settings_manager_file(src_root: Path) -> Optional[Path]:
    try:
        for p in src_root.rglob("settings_manager.py"):
            if "mongodb" in p.parts:
                return p
        matches = list(src_root.rglob("settings_manager.py"))
        return matches[0] if matches else None
    except Exception:
        return None

def _load_module_from_path(module_name: str, path: Path):
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            return mod
    except Exception:
        return None
    return None

def main_entry(gui: bool = True) -> None:
    try:
        try:
            _load_runtime = getattr(_bootstrap, "_load_runtime_modules", None)
            if callable(_load_runtime):
                _load_runtime()
        except Exception:
            _log.debug("bootstrap._load_runtime_modules failed (continuing)", exc_info=True)

        init_fn = getattr(_bootstrap, "init", None)
        if not callable(init_fn):
            _log.error("bootstrap.init not callable")
            raise RuntimeError("bootstrap.init not callable")

        init_ok = False
        try:
            init_ok = bool(init_fn())
        except Exception:
            _log.exception("bootstrap.init raised an exception")
            init_ok = False

        if init_ok:
            _gui_flag = True
            try:
                _gui_flag = getattr(_bootstrap.static.config, "gui", True)
                if _gui_flag is None:
                    _gui_flag = True
            except Exception:
                _gui_flag = True

            if "--nogui" in sys.argv or os.getenv("NOGUI", "").lower() in ("1", "true", "yes"):
                _gui_flag = False

            try:
                main_fn = getattr(_bootstrap, "main", None)
                if not callable(main_fn):
                    _log.error("bootstrap.main not callable")
                    raise RuntimeError("bootstrap.main not callable")
                # QApplication 생성(bootstrap.init 내부) 이후에 메타타입을 등록합니다.
                try:
                    from PyQt5.QtCore import qRegisterMetaType
                    qRegisterMetaType("QVector<int>")
                    qRegisterMetaType("QTextCursor")
                except Exception:
                    pass

                # call main (this typically creates UI and StatusWidget instance)
                main_fn(gui=_gui_flag)

                # ------------------------------
                # 임시 진단: register_ui_log_consumer 제공 모듈과 main._ui_log_consumers 카운트 출력
                # (재현/디버그 용; 필요 시 제거)
                # ------------------------------
                try:
                    import sys as _sys
                    mods_with_api = []
                    for _n, _m in list(_sys.modules.items()):
                        try:
                            if _m is None:
                                continue
                            if callable(getattr(_m, "register_ui_log_consumer", None)):
                                mods_with_api.append(_n)
                        except Exception:
                            continue
                    _log.info("[main] modules that expose register_ui_log_consumer: %s", mods_with_api)
                    try:
                        _count = len(_ui_log_consumers)  # main module의 리스트 확인
                        _log.info("[main] current _ui_log_consumers count in main module: %d", _count)
                    except Exception:
                        _log.debug("[main] cannot read _ui_log_consumers from main module", exc_info=True)
                except Exception:
                    _log.debug("[main] UI registration diagnostic block failed", exc_info=True)

                # -----------------------------------------------------------------
                # 부트스트랩이 main() 실행 후 StatusWidget 인스턴스를 노출하면,
                # 여기서 SettingsManager를 생성하여 주입하고 복원 시도합니다.
                # 안전성: pymongo가 없거나 bootstrap에서 인스턴스를 찾지 못하면 건너뜁니다.
                # -----------------------------------------------------------------
                try:
                    sw = None
                    for attr in ("status_widget", "StatusWidgetInstance", "status_widget_instance", "statuswindow"):
                        if hasattr(_bootstrap, attr):
                            sw = getattr(_bootstrap, attr)
                            break

                    if sw is None:
                        for parent_attr in ("ui", "app", "widgets"):
                            parent = getattr(_bootstrap, parent_attr, None)
                            if parent is None:
                                continue
                            for attr in ("status_widget", "status_widget_instance", "StatusWidget"):
                                if hasattr(parent, attr):
                                    sw = getattr(parent, attr)
                                    break
                            if sw is not None:
                                break

                    if sw is None:
                        for name, val in vars(_bootstrap).items():
                            try:
                                if hasattr(val, "set_settings_manager") and hasattr(val, "restore_settings"):
                                    sw = val
                                    break
                            except Exception:
                                continue

                    if sw is not None:
                        try:
                            import pymongo
                            mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
                            client = pymongo.MongoClient(mongo_uri, maxPoolSize=10)
                            dbname = os.getenv("UPBIT_DB", "upbit_trader")
                            db = client.get_database(dbname)

                            settings_mod = None
                            try:
                                src_root = Path(_repo_root) / "src" if "_repo_root" in globals() else Path(__file__).resolve().parents[2] / "src"
                            except Exception:
                                src_root = Path(__file__).resolve().parents[2] / "src"

                            settings_path = _find_settings_manager_file(Path(src_root))
                            if settings_path is not None:
                                settings_mod = _load_module_from_path("ui_settings_manager", settings_path)

                            if settings_mod is None:
                                _log.debug("SettingsManager module loaded from file: %s", settings_path if settings_path is not None else "NOT_FOUND")

                            SettingsManager = None
                            if settings_mod is not None:
                                SettingsManager = getattr(settings_mod, "SettingsManager", None)

                            if SettingsManager is None:
                                try:
                                    for candidate in ("app.mongodb.settings_manager", "mongodb.settings_manager", "src.app.mongodb.settings_manager"):
                                        try:
                                            mod = importlib.import_module(candidate)
                                            SettingsManager = getattr(mod, "SettingsManager", None)
                                            if SettingsManager:
                                                _log.debug("Imported SettingsManager from %s", candidate)
                                                break
                                        except Exception:
                                            continue
                                except Exception:
                                    pass

                            if SettingsManager is not None:
                                settings_mgr = SettingsManager(db)
                                try:
                                    sw.set_settings_manager(settings_mgr)
                                    try:
                                        if hasattr(sw, "restore_settings"):
                                            sw.restore_settings()
                                        elif hasattr(sw, "load_and_restore_settings"):
                                            sw.load_and_restore_settings(db)
                                    except Exception:
                                        _log.debug("status_widget.restore_settings failed", exc_info=True)
                                    _log.info("[main] SettingsManager injected into StatusWidget and restore attempted")
                                except Exception:
                                    _log.debug("[main] Failed to set SettingsManager on detected StatusWidget", exc_info=True)
                            else:
                                _log.debug("[main] SettingsManager class not found via file import; skipping injection")
                        except Exception:
                            _log.debug("[main] SettingsManager injection skipped (pymongo missing or connection failed)", exc_info=True)
                    else:
                        _log.debug("[main] No StatusWidget instance found in bootstrap to inject SettingsManager")
                except Exception:
                    _log.debug("SettingsManager injection check failed", exc_info=True)

            except Exception:
                _log.exception("bootstrap.main raised an exception")
        else:
            _log.error("bootstrap.init returned falsy result; aborting start")
    except Exception:
        _log.exception("Unexpected error in main_entry")

if __name__ == "__main__":
    main_entry()
