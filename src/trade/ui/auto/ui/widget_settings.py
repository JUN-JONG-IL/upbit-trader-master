# -*- coding: utf-8 -*-
"""
SettingsWidget (방어적 로딩/폴백 포함)

변경 요지:
- static 및 전략/매니저 모듈을 여러 후보 네임스페이스에서 안전하게 탐색하여 로드합니다.
- static 또는 static.config가 없을 때 안전한 DefaultConfig 폴백을 제공하여 예외 방지.
- UI 요소 접근을 방어적으로 처리하여 .ui 파일이 변경되어 일부 위젯이 없어도 크래시가 나지 않음.
- 시작/중지 버튼 동작시 의존성 부족(예: SignalManager 없음)시 사용자에게 안내하고 중단.
"""
from __future__ import annotations

import importlib as _il
import importlib.util
import os
import logging
from types import SimpleNamespace
from typing import Optional

# PyQt imports (필요 최소한만)
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QMessageBox
from PyQt5 import uic

logger = logging.getLogger(__name__)


# ---------------------------
# 유틸: 안전한 모듈/심볼 탐색
# ---------------------------
def _try_import_module(names):
    """
    names: iterable of module name candidates (str)
    반환: 모듈 또는 None
    """
    for nm in names:
        if not nm:
            continue
        try:
            mod = _il.import_module(nm)
            logger.debug("[SettingsWidget] imported module %s -> %s", nm, getattr(mod, "__file__", None))
            return mod
        except Exception:
            continue
    return None


def _try_get_attr_from_modules(module_candidates, attr_name):
    """
    여러 모듈 후보에서 attr_name 심볼을 찾아 반환 (첫 발견)
    """
    for mod_name in module_candidates:
        try:
            mod = _try_import_module((mod_name,))
            if not mod:
                continue
            val = getattr(mod, attr_name, None)
            if val is not None:
                return val
        except Exception:
            continue
    return None


# ---------------------------
# 안전한 static 탐색/폴백
# ---------------------------
def _discover_static():
    """
    가능한 static 모듈/객체 후보를 탐색하여 반환.
    실패 시 None 반환 (호출부에서 폴백 처리).
    """
    candidates = (
        "src.server.app.static",
        "server.app.static",
        "src.app.static",
        "app.static",
        "static",
    )
    for c in candidates:
        try:
            mod = _try_import_module((c,))
            if mod is None:
                continue
            # static may be module having config attr OR module itself is static object
            if hasattr(mod, "config") or hasattr(mod, "signal_queue"):
                return mod
            # some code expose as package attribute 'static' (rare)
            maybe = getattr(mod, "static", None)
            if maybe is not None:
                return maybe
        except Exception:
            continue
    return None


class DefaultConfig:
    """
    최소한의 속성만 제공하는 폴백 config 객체.
    실제 실행 환경에서는 real static.config가 필요합니다.
    """
    def __init__(self):
        self.settings_auto_trading = False
        self.strategy_type = "VariousIndicator"
        # Mongo 관련 기본값 (사용 시 유효하지 않을 수 있음)
        self.mongo_ip = "127.0.0.1"
        self.mongo_port = 27017
        self.mongo_id = ""
        self.mongo_password = ""

    def save(self):
        logger.warning("[SettingsWidget] DefaultConfig.save() called — no-op in fallback environment")


# ---------------------------
# 전략/매니저 로드
# ---------------------------
def _discover_strategy_and_manager():
    """
    SignalManager, VariousIndicatorStrategy, VolatilityBreakoutStrategy 를 안전하게 찾아 반환 (없으면 None).
    """
    # 시도 후보 모듈 목록 (우선 src 네임스페이스)
    candidates_manager = ("src.strategy.core.signal_manager", "strategy.core.signal_manager", "strategy.core.signal_manager", "strategy")
    candidates_various = ("src.strategy.strategies.various_indicator", "strategy.strategies.various_indicator", "strategy.strategies.various_indicator", "strategy.strategies.various_indicator")
    candidates_volatility = ("src.strategy.strategies.volatility_breakout", "strategy.strategies.volatility_breakout", "strategy.strategies.volatility_breakout")

    SignalManager = _try_get_attr_from_modules(candidates_manager, "SignalManager")
    VariousIndicatorStrategy = _try_get_attr_from_modules(candidates_various, "VariousIndicatorStrategy")
    VolatilityBreakoutStrategy = _try_get_attr_from_modules(candidates_volatility, "VolatilityBreakoutStrategy")

    # 마지막으로 legacy fallback 이름으로 시도
    if SignalManager is None:
        try:
            mod = _try_import_module(("strategy",))
            if mod:
                SignalManager = getattr(mod, "SignalManager", None)
        except Exception:
            pass

    return SignalManager, VariousIndicatorStrategy, VolatilityBreakoutStrategy


# ---------------------------
# SettingsWidget
# ---------------------------
def _ui_file_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), filename)


class SettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # static 탐색 (폴백 처리)
        self.static = _discover_static()
        if self.static is None:
            logger.warning("[SettingsWidget] static 모듈/객체를 찾을 수 없습니다. 폴백 DefaultConfig 사용 (기능 제한).")
            # 최소한의 구조를 제공하는 폴백 static 객체 생성
            fb = SimpleNamespace()
            fb.config = DefaultConfig()
            fb.signal_queue = []  # 폴백 큐 (실무에선 반드시 교체 필요)
            fb.settings_start = False
            fb.signal_manager = None
            fb.strategy = None
            self.static = fb

        # 전략/매니저 발견
        SignalManager, VariousIndicatorStrategy, VolatilityBreakoutStrategy = _discover_strategy_and_manager()
        self._SignalManager = SignalManager
        self._VariousIndicatorStrategy = VariousIndicatorStrategy
        self._VolatilityBreakoutStrategy = VolatilityBreakoutStrategy

        # .ui 로드 (실패 시 예외 방지)
        ui_path = _ui_file_path("settings.ui")
        if os.path.exists(ui_path):
            try:
                uic.loadUi(ui_path, self)
            except Exception as e:
                logger.exception("[SettingsWidget] settings.ui 로드 실패 — 폴백 동작으로 전환: %s", e)
                # 간단한 폴백 UI 생성(위젯 팝업이나 최소 버튼만 필요하면 확장 가능)
                self._create_basic_ui()
        else:
            logger.warning("[SettingsWidget] UI 파일이 없습니다: %s (폴백 UI 생성)", ui_path)
            self._create_basic_ui()

        # UI 컴포넌트 존재 여부 확인/초기화 (안전모드)
        self._safe_connect_ui()

        # 초기 상태 반영 (config 기반)
        try:
            cfg = getattr(self.static, "config", None)
            if cfg is None:
                cfg = DefaultConfig()
                setattr(self.static, "config", cfg)
            # 시작/중지 버튼 초기 스타일/활성화
            if getattr(cfg, "settings_auto_trading", False) is False:
                if hasattr(self, "stop"):
                    try:
                        self.stop.setStyleSheet("QPushButton { color: #eff0f1; background-color: #757575; }")
                        self.stop.setEnabled(False)
                    except Exception:
                        pass
            else:
                if hasattr(self, "start"):
                    try:
                        self.start.setStyleSheet("QPushButton { color: #eff0f1; background-color: #757575; }")
                        self.start.setEnabled(False)
                    except Exception:
                        pass
                if hasattr(self, "RSI"):
                    try:
                        self.RSI.setEnabled(False)
                    except Exception:
                        pass
                if hasattr(self, "Volatility"):
                    try:
                        self.Volatility.setEnabled(False)
                    except Exception:
                        pass
            # 전략 라디오 상태 초기화
            stype = getattr(cfg, "strategy_type", None)
            if stype == "VariousIndicator":
                if hasattr(self, "RSI"):
                    try:
                        self.RSI.setChecked(True)
                    except Exception:
                        pass
                cfg.strategy_type = "VariousIndicator"
            else:
                if hasattr(self, "Volatility"):
                    try:
                        self.Volatility.setChecked(True)
                    except Exception:
                        pass
                cfg.strategy_type = "VolatilityBreakout"
        except Exception:
            logger.exception("[SettingsWidget] 초기 상태 반영 중 예외 발생")

        # 드래그 이동 이벤트 바인딩 (타이틀 라벨이 존재할 때만)
        try:
            if hasattr(self, "toplabel_title"):
                # MouseLeftClick Event Listener
                def mousePressEvent(event):
                    if event.buttons() == Qt.LeftButton:
                        self.dragPos = event.globalPos()
                        event.accept()

                # MouseClickMove Event Listener
                def moveWindow(event):
                    if getattr(self, "status", 0) == 1:
                        try:
                            self.status = 0
                            self.showNormal()
                        except Exception:
                            pass
                    if event.buttons() == Qt.LeftButton:
                        try:
                            self.move(self.pos() + event.globalPos() - self.dragPos)
                            self.dragPos = event.globalPos()
                            event.accept()
                        except Exception:
                            pass

                self.toplabel_title.mousePressEvent = mousePressEvent  # type: ignore[attr-defined]
                self.toplabel_title.mouseMoveEvent = moveWindow  # type: ignore[attr-defined]
        except Exception:
            logger.debug("[SettingsWidget] toplabel_title 드래그 바인딩 실패 (무시)")

    # -------------------
    def _create_basic_ui(self):
        """
        최소 폴백 UI: 빠르게 파일이 없을 때 크래시를 막기 위해 버튼/라디오 등의 속성만 생성.
        (실무에서는 settings.ui를 제공하는 것이 권장됨)
        """
        try:
            from PyQt5.QtWidgets import QVBoxLayout, QPushButton, QRadioButton, QLabel
            layout = QVBoxLayout()
            # 간단한 컨트롤만 생성
            self.toplabel_title = QLabel("Settings")
            layout.addWidget(self.toplabel_title)
            self.RSI = QRadioButton("VariousIndicator")
            self.Volatility = QRadioButton("VolatilityBreakout")
            layout.addWidget(self.RSI)
            layout.addWidget(self.Volatility)
            self.start = QPushButton("Start")
            self.stop = QPushButton("Stop")
            layout.addWidget(self.start)
            layout.addWidget(self.stop)
            self.setLayout(layout)
        except Exception:
            logger.exception("[SettingsWidget] _create_basic_ui 실패")

    # -------------------
    def _safe_connect_ui(self):
        """
        UI 속성이 있을 때만 시그널을 연결. 없는 경우 무시.
        """
        try:
            if hasattr(self, "close_btn"):
                try:
                    self.close_btn.clicked.connect(self.close_btn_click)
                except Exception:
                    logger.debug("[SettingsWidget] close_btn 연결 실패")
            if hasattr(self, "minimize_btn"):
                try:
                    self.minimize_btn.clicked.connect(lambda: self.showMinimized())
                except Exception:
                    logger.debug("[SettingsWidget] minimize_btn 연결 실패")
            if hasattr(self, "start"):
                try:
                    self.start.clicked.connect(self.clicked_start)
                except Exception:
                    logger.debug("[SettingsWidget] start 버튼 연결 실패")
            if hasattr(self, "stop"):
                try:
                    self.stop.clicked.connect(self.clicked_stop)
                except Exception:
                    logger.debug("[SettingsWidget] stop 버튼 연결 실패")
            # Frameless flag는 안전하게 설정
            try:
                self.setWindowFlag(Qt.FramelessWindowHint)
            except Exception:
                pass
        except Exception:
            logger.exception("[SettingsWidget] _safe_connect_ui 실패")

    # -------------------
    def close_btn_click(self):
        try:
            setattr(self.static, "settings_start", False)
        except Exception:
            pass
        try:
            self.close()
        except Exception:
            pass

    # -------------------
    def clicked_start(self):
        """
        Start 클릭 처리 — 필요한 의존성( SignalManager, strategy 클래스, signal_queue 등 )이
        준비되어 있는지 확인하고 없으면 사용자에게 알림 후 중단.
        """
        cfg = getattr(self.static, "config", None)
        if cfg is None:
            QMessageBox.warning(self, "설정 오류", "config가 준비되지 않았습니다. 설정을 확인하세요.")
            logger.warning("[SettingsWidget] clicked_start aborted: static.config missing")
            return

        # SignalManager 유무 확인
        if self._SignalManager is None:
            QMessageBox.warning(self, "설정 오류", "SignalManager 모듈을 찾을 수 없습니다. 시작할 수 없습니다.")
            logger.warning("[SettingsWidget] clicked_start aborted: SignalManager not available")
            return

        # 전략 클래스 확인
        use_various = hasattr(self, "RSI") and getattr(self, "RSI").isChecked() if hasattr(self, "RSI") else (cfg.strategy_type == "VariousIndicator")
        if use_various:
            if self._VariousIndicatorStrategy is None:
                QMessageBox.warning(self, "설정 오류", "VariousIndicatorStrategy를 찾을 수 없습니다.")
                logger.warning("[SettingsWidget] clicked_start aborted: VariousIndicatorStrategy not available")
                return
        else:
            if self._VolatilityBreakoutStrategy is None:
                QMessageBox.warning(self, "설정 오류", "VolatilityBreakoutStrategy를 찾을 수 없습니다.")
                logger.warning("[SettingsWidget] clicked_start aborted: VolatilityBreakoutStrategy not available")
                return

        # signal_queue 유효성 확인
        queue = getattr(self.static, "signal_queue", None)
        if queue is None:
            QMessageBox.warning(self, "설정 오류", "signal_queue가 준비되지 않았습니다.")
            logger.warning("[SettingsWidget] clicked_start aborted: signal_queue missing")
            return

        # SignalManager 인스턴스 생성
        try:
            self.static.signal_manager = self._SignalManager(
                config=self.static.config,
                db_ip=getattr(self.static.config, "mongo_ip", "127.0.0.1"),
                db_port=getattr(self.static.config, "mongo_port", 27017),
                db_id=getattr(self.static.config, "mongo_id", ""),
                db_password=getattr(self.static.config, "mongo_password", ""),
                queue=queue,
            )
        except Exception:
            logger.exception("[SettingsWidget] SignalManager 인스턴스 생성 실패")
            QMessageBox.warning(self, "시작 실패", "SignalManager 생성 중 오류가 발생했습니다. 로그를 확인하세요.")
            return

        # 전략 인스턴스 생성
        try:
            if use_various:
                self.static.config.strategy_type = "VariousIndicator"
                self.static.strategy = self._VariousIndicatorStrategy(queue=queue)
            else:
                self.static.config.strategy_type = "VolatilityBreakout"
                self.static.strategy = self._VolatilityBreakoutStrategy(queue=queue)
        except Exception:
            logger.exception("[SettingsWidget] Strategy 인스턴스 생성 실패")
            QMessageBox.warning(self, "시작 실패", "전략 생성 중 오류가 발생했습니다. 로그를 확인하세요.")
            return

        # 설정 저장 및 시작
        try:
            self.static.config.settings_auto_trading = True
            # settings_start 플래그는 외부에서 쓰는 코드가 있으면 업데이트
            try:
                setattr(self.static, "settings_start", True)
            except Exception:
                pass
            # save 가능하면 호출
            save_fn = getattr(self.static.config, "save", None)
            if callable(save_fn):
                try:
                    save_fn()
                except Exception:
                    logger.debug("[SettingsWidget] config.save() 실패 (무시)")

            # start managers
            try:
                if hasattr(self.static, "signal_manager") and getattr(self.static, "signal_manager") is not None:
                    try:
                        self.static.signal_manager.start()
                    except Exception:
                        logger.exception("[SettingsWidget] signal_manager.start() 예외")
                if hasattr(self.static, "strategy") and getattr(self.static, "strategy") is not None:
                    try:
                        self.static.strategy.start()
                    except Exception:
                        logger.exception("[SettingsWidget] strategy.start() 예외")
            except Exception:
                logger.exception("[SettingsWidget] start 호출 중 예외")

            # UI 닫기
            try:
                self.close()
            except Exception:
                pass

        except Exception:
            logger.exception("[SettingsWidget] clicked_start 처리 중 예외")
            QMessageBox.warning(self, "시작 실패", "설정 적용 중 오류가 발생했습니다. 로그를 확인하세요.")

    # -------------------
    def clicked_stop(self):
        """
        Stop 클릭 처리 — 실행중이면 종료 시도하고 설정을 저장.
        """
        try:
            cfg = getattr(self.static, "config", None)
            if cfg is not None:
                cfg.settings_auto_trading = False
            try:
                setattr(self.static, "settings_start", False)
            except Exception:
                pass
            # save 가능하면 호출
            save_fn = getattr(cfg, "save", None) if cfg else None
            if callable(save_fn):
                try:
                    save_fn()
                except Exception:
                    logger.debug("[SettingsWidget] config.save() 실패 (무시)")
            # 종료 시도
            try:
                if getattr(self.static, "strategy", None):
                    try:
                        # terminate/stop API가 다를 수 있으니 안전하게 호출
                        term = getattr(self.static.strategy, "terminate", None) or getattr(self.static.strategy, "stop", None)
                        if callable(term):
                            term()
                    except Exception:
                        logger.exception("[SettingsWidget] strategy 종료 중 예외")
                if getattr(self.static, "signal_manager", None):
                    try:
                        term2 = getattr(self.static.signal_manager, "terminate", None) or getattr(self.static.signal_manager, "stop", None)
                        if callable(term2):
                            term2()
                    except Exception:
                        logger.exception("[SettingsWidget] signal_manager 종료 중 예외")
            except Exception:
                logger.exception("[SettingsWidget] 종료 시도 중 예외")

        except Exception:
            logger.exception("[SettingsWidget] clicked_stop 처리 중 예외")
        finally:
            try:
                self.close()
            except Exception:
                pass