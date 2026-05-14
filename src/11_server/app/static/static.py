#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Static 전역 설정 및 전역 싱글톤(로그/설정/전역 인스턴스)을 초기화합니다.
- 다양한 실행 환경에서 Config 클래스를 안정적으로 확보하도록 후보 탐색/로딩을 견고화합니다.
- 디버그 모드가 아닐 경우 불필요한 스택트레이스/출력을 억제하여 VS 디버깅 로그를 간결하게 유지합니다.
"""

from __future__ import annotations

import sys
import os
import logging
import importlib
import importlib.util
from pathlib import Path
from typing import Optional, Any

# ----------------------------
# utils 모듈 안전 로드 (플레이스홀더 제공)
# ----------------------------
try:
    import utils  # 프로젝트 제공 get_logger 등 기대
except Exception:
    class _StubUtils:
        """간단한 스텁 로거 생성기 (프로덕션용 아님, 최소한의 완화 목적)"""
        def get_logger(self, *args, **kwargs):
            logger = logging.getLogger("stub")
            if not logger.handlers:
                h = logging.StreamHandler(sys.stdout)
                h.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s', datefmt='%H:%M:%S'))
                logger.addHandler(h)
                logger.setLevel(logging.INFO)
            return logger
    utils = _StubUtils()

# ----------------------------
# Config 모듈 탐색/로딩 (견고화)
# ----------------------------

def _debug_mode_from_env() -> bool:
    """환경변수 기반 임시 debug 판단 (config 로드 이전의 최소 기준)."""
    v = os.environ.get("UPBIT_TRADER_DEBUG", "") or os.environ.get("DEBUG", "")
    if str(v).lower() in ("1", "true", "yes", "on"):
        return True
    return False

_INITIAL_DEBUG = _debug_mode_from_env()

def _try_import_module_by_name(name: str) -> Optional[Any]:
    try:
        mod = importlib.import_module(name)
        return mod
    except Exception:
        return None

def _try_load_module_from_path(path: str, name_hint: str = "app_config_fallback") -> Optional[Any]:
    try:
        spec = importlib.util.spec_from_file_location(name_hint, path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    except Exception:
        # 디버그 모드인 경우만 상세 출력
        if _INITIAL_DEBUG:
            import traceback
            print(f"[STATIC DEBUG] failed to load config file: {path}", file=sys.stderr)
            traceback.print_exc()
    return None

def _find_config_module() -> Optional[Any]:
    """
    다음 우선순위로 Config 제공 모듈을 찾습니다:
    1) 패키지 모듈들: 'src.01_core.config.config', '01_core.config.config', '01_core.config', 'src.01_core.config'
    2) 최상위 'config'
    3) 파일 경로 후보(프로젝트 src 루트 기준)
    """
    candidate_names = [
        "src.01_core.config.config",
        "01_core.config.config",
        "01_core.config",
        "src.01_core.config",
        "config",
    ]

    for nm in candidate_names:
        mod = _try_import_module_by_name(nm)
        if mod is not None:
            if hasattr(mod, "Config"):
                return mod
            # 때때로 모듈 자체가 Config 인스턴스를 노출할 수 있음 (예: config = Config())
            # 그 경우 'Config' 속성이 없더라도 모듈 자체가 구성 객체일 가능성 감지
            # (모듈 안에 설정 dict/객체가 있는지 확인)
            for attr in ("config", "CONFIG", "AppConfig"):
                if hasattr(mod, attr):
                    return mod

    # 파일 경로 기반 후보 (src 루트 기준)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))  # 프로젝트 src/11_server/... 에서 src 루트로
    candidate_paths = [
        os.path.join(src_dir, "01_core", "config", "config.py"),
        os.path.join(src_dir, "01_core", "config.py"),
        os.path.join(src_dir, "config.py"),
    ]

    for p in candidate_paths:
        if os.path.isfile(p):
            mod = _try_load_module_from_path(p)
            if mod is not None:
                if hasattr(mod, "Config") or any(hasattr(mod, a) for a in ("config", "CONFIG", "AppConfig")):
                    return mod
    return None

cf_module_or_obj = _find_config_module()

# ----------------------------
# Config 미발견 시 최소 스텁 제공 (조용히)
# ----------------------------
if cf_module_or_obj is None:
    if _INITIAL_DEBUG:
        print("[STATIC] Config 모듈을 찾지 못했습니다. 스텁 Config를 사용합니다.", file=sys.stderr)
    class _StubConfig:
        def __init__(self):
            self.log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            self.log_save = False
            self.log_path = "upbit-trader.log"
            self.log_print = True
            self.log_level = "INFO"
            self.debug_mode = False
            self.gui = True
            # DB 기본값 (안정성 용)
            self.mongo_ip = "localhost"
            self.mongo_port = 27017
            self.mongo_id = None
            self.mongo_password = None

        def load(self):
            return None
    cf = _StubConfig()
else:
    cf = cf_module_or_obj

# ----------------------------
# config 객체/인스턴스화: 모듈 내 Config 클래스 또는 모듈 자체 인스턴스 대응
# ----------------------------
config = None
try:
    # 모듈이 Config 클래스를 제공하면 인스턴스화
    if hasattr(cf, "Config") and callable(getattr(cf, "Config")):
        try:
            config = cf.Config()  # 타입은 모듈의 Config 클래스 인스턴스
            # load 메서드가 있다면 안전하게 호출
            if hasattr(config, "load") and callable(getattr(config, "load")):
                try:
                    config.load()
                except Exception:
                    # 로드 실패는 치명적이지 않으므로 조용히 무시(디버그 시엔 출력)
                    if getattr(config, "debug_mode", False) or _INITIAL_DEBUG:
                        import traceback
                        print("[STATIC DEBUG] config.load() failed:", file=sys.stderr)
                        traceback.print_exc()
        except Exception:
            # 인스턴스화가 실패하면 모듈 자체가 설정 오브젝트일 가능성 확인
            config = cf
    else:
        # 모듈 자체가 설정 인스턴스(예: config = Config()) 또는 dict 형태일 수 있음
        config = cf
except Exception:
    # 극단적 실패시 방어적 스텁
    class _FinalStubConfig:
        def __init__(self):
            self.log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            self.log_save = False
            self.log_path = "upbit-trader.log"
            self.log_print = True
            self.log_level = "INFO"
            self.debug_mode = False
            self.gui = True
            self.mongo_ip = "localhost"
            self.mongo_port = 27017
            self.mongo_id = None
            self.mongo_password = None
        def load(self): pass
    config = _FinalStubConfig()

# ----------------------------
# 로거 생성: utils.get_logger 서명 차이 대응
# ----------------------------
def _create_logger_from_utils(cfg) -> logging.Logger:
    """utils.get_logger가 다양한 서명을 가질 수 있으므로 안전하게 호출합니다."""
    try:
        # 시도: (print_format=..., print=..., save=..., save_path=...)
        return utils.get_logger(
            print_format=getattr(cfg, "log_format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
            print=getattr(cfg, "log_print", True),
            save=getattr(cfg, "log_save", False),
            save_path=getattr(cfg, "log_path", "upbit-trader.log")
        )
    except TypeError:
        try:
            # 대체 서명: fmt, console, persist
            return utils.get_logger(
                fmt=getattr(cfg, "log_format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
                console=getattr(cfg, "log_print", True),
                persist=getattr(cfg, "log_save", False),
                path=getattr(cfg, "log_path", "upbit-trader.log")
            )
        except Exception:
            # 실패 시 기본 로거로 폴백
            logging.basicConfig(stream=sys.stdout, level=logging.INFO)
            return logging.getLogger("static-fallback")
    except Exception:
        logging.basicConfig(stream=sys.stdout, level=logging.INFO)
        return logging.getLogger("static-fallback")

try:
    log = _create_logger_from_utils(config)
except Exception:
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    log = logging.getLogger("static-fallback")

# ----------------------------
# 로그 레벨 및 콘솔 핸들러 세팅 (루트 로거에 추가, 중복 방지)
# ----------------------------
log_level_str = getattr(config, "log_level", "INFO").upper()
_level_map = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}
root_level = _level_map.get(log_level_str, logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(root_level)

# 콘솔 핸들러가 루트에 없으면 추가
if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(max(root_level, logging.INFO))
    ch.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s', datefmt='%H:%M:%S'))
    root_logger.addHandler(ch)

# 초기화 간결 출력 (중복을 피하기 위해 print 최소화)
root_logger.info("=" * 60)
root_logger.info("[STATIC] Module initialization started")
root_logger.info(f"[STATIC] Log print: {getattr(config, 'log_print', True)}")
root_logger.info(f"[STATIC] Log save: {getattr(config, 'log_save', False)}")
root_logger.info(f"[STATIC] Log path: {getattr(config, 'log_path', 'upbit-trader.log')}")
root_logger.info(f"[STATIC] Log level: {log_level_str}")
root_logger.info("=" * 60)

# 특정 noisy 로거 억제
for noisy in ('websockets', 'websockets.protocol', 'websockets.client',
              'aiopyupbit', 'PyQt5.uic', 'matplotlib', 'pymongo'):
    logging.getLogger(noisy).setLevel(logging.WARNING)
root_logger.info("[STATIC] Reduced noisy logger verbosity (websockets/aiopyupbit/PyQt5.uic/pymongo)")

# ----------------------------
# 상수 / 전역 변수
# ----------------------------
MIN_TRADE_PRICE = 5000
FEES = 0.0005
FIAT = "KRW"
BASE_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
UPBIT_TIME_FORMAT = '%Y-%m-%dT%H:%M:%S'
STRATEGY_DAILY_FINISH_TIME = 9
EXTERNAL_TIMEOUT = 60
INTERNAL_TIMEOUT = 1
REQUEST_LIMIT = 5
PING_INTERVAL = 60

# 전역 인스턴스(초기값)
upbit = None
chart = None
account = None
signal_manager = None
signal_queue = None
strategy = None
data_manager = None
compute_process = None
settings_start = False

# 디버그 모드 플래그
DEBUG_MODE = getattr(config, "debug_mode", False) or _INITIAL_DEBUG

# ----------------------------
# matplotlib 한글 폰트 설정 (부수 기능, 실패시 조용히 무시)
# ----------------------------
def setup_matplotlib_korean_font():
    try:
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm

        font_candidates = [
            'Malgun Gothic', 'NanumGothic', 'AppleGothic',
            'NanumBarunGothic', 'DejaVu Sans'
        ]
        available = {f.name for f in fm.fontManager.ttflist}
        for f in font_candidates:
            if f in available:
                plt.rcParams['font.family'] = f
                plt.rcParams['axes.unicode_minus'] = False
                root_logger.info(f"[STATIC] matplotlib font set: {f}")
                return True
        root_logger.debug("[STATIC] No suitable Korean font found for matplotlib (fallback may miss glyphs)")
        return False
    except Exception:
        root_logger.debug("[STATIC] matplotlib not available or font setup failed")
        return False

setup_matplotlib_korean_font()

root_logger.info("=" * 60)

# ----------------------------
# RealtimeManager 전역 등록 (UI에서 접근 가능하도록)
# ----------------------------
realtime_manager = None  # 초기화 시점에 외부에서 설정됨