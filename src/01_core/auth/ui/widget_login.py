# -*- coding: utf-8 -*-
"""
widget_login.py (완전한 모듈화 버전)

- UI 로드 / PreLogin 체크 / AutoBackfill 트리거의 연결 코드와
  MainWindow 로드 헬퍼를 포함한 전체 파일입니다.
- 의존: 같은 폴더에 async_utils.py, prelogin.py, backfill_loader.py 를 두고 사용하세요.
"""
from __future__ import annotations

import os
import sys
import logging
import traceback
import importlib
import importlib.util
import asyncio
from typing import Optional, Dict, TYPE_CHECKING, Any
from pathlib import Path

# qasync optional
try:
    import qasync as _qasync  # type: ignore
except Exception:
    _qasync = None  # type: ignore

# 타입 검사 전용 import (정적 타입 검사기용)
if TYPE_CHECKING:
    from .prelogin import PreLoginChecker  # type: ignore

# runtime import: 이름 충돌 방지 위해 별도 변수에 할당
try:
    from .async_utils import run_sync_callable, set_main_loop
except Exception:
    # fallback: 최소 구현
    def run_sync_callable(fn, *args, **kwargs):
        res = fn(*args, **kwargs)
        if asyncio.iscoroutine(res) or asyncio.iscoroutinefunction(fn):
            return asyncio.run(res)
        return res
    def set_main_loop(loop):
        pass

# runtime prelogin import into a different name to avoid Pylance confusion
try:
    from .prelogin import PreLoginChecker as _PreLoginCheckerRuntime  # type: ignore
except Exception:
    _PreLoginCheckerRuntime = None  # type: ignore

# runtime backfill loader import
try:
    from .backfill_loader import trigger_auto_backfill as _trigger_auto_backfill_runtime  # type: ignore
except Exception:
    _trigger_auto_backfill_runtime = None  # type: ignore

logger = logging.getLogger(__name__)

# PyQt5 imports
try:
    from PyQt5.QtCore import Qt, pyqtSignal, QCoreApplication
    from PyQt5.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QSizePolicy
    )
    from PyQt5 import uic
    _HAS_QT = True
except Exception as e:
    _HAS_QT = False
    logger.warning("[widget_login] PyQt5 import failed: %s", e)

_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_UI_FILE = os.path.join(_UI_DIR, "login.ui")


if _HAS_QT:
    class LoginWidget(QDialog):
        # 타입 주석은 TYPE_CHECKING에서 선언된 PreLoginChecker 이름(문자열 포워드) 사용
        _prelogin_checker: Optional["PreLoginChecker"]

        backfill_finished = pyqtSignal(bool)

        def __init__(self, parent=None):
            super().__init__(parent)
            # 런타임 변수는 _PreLoginCheckerRuntime 을 사용
            self._prelogin_checker = None
            self._auto_backfill_mgr = None
            self._backfill_running = False
            self._last_prelogin_status: Dict[str, bool] = {}
            self._setup_ui()
            self._set_default_credentials()
            self.backfill_finished.connect(self._on_backfill_complete_ui)
            self._start_prelogin_checks()

        def _setup_ui(self):
            if os.path.exists(_UI_FILE):
                try:
                    uic.loadUi(_UI_FILE, self)
                    try:
                        self.setMinimumSize(900, 600)
                        self.resize(1100, 700)
                    except Exception:
                        pass
                    try:
                        self.setStyleSheet("font-size:11px;")
                    except Exception:
                        pass
                    # connect signals if present
                    btn = getattr(self, "pushButton_connect", None)
                    if btn:
                        try:
                            btn.clicked.connect(self._on_login)
                            btn.setEnabled(False)
                        except Exception:
                            pass
                    if not hasattr(self, "label_hint"):
                        self.label_hint = QLabel("", self)
                except Exception:
                    logger.warning("[LoginWidget] uic.loadUi failed; using fallback")
                    self._create_fallback_ui()
            else:
                self._create_fallback_ui()

        def _create_fallback_ui(self):
            try:
                self.setMinimumSize(900, 640)
                self.resize(960, 640)
            except Exception:
                pass
            layout = QVBoxLayout()
            title = QLabel("Upbit Trader 로그인")
            title.setAlignment(Qt.AlignCenter)
            try:
                title.setStyleSheet("font-size:16px; font-weight:bold;")
            except Exception:
                pass
            layout.addWidget(title)
            self.lineEdit_access = QLineEdit()
            self.lineEdit_access.setPlaceholderText("아이디 (테스트: 0000)")
            layout.addWidget(self.lineEdit_access)
            self.lineEdit_secret = QLineEdit()
            self.lineEdit_secret.setPlaceholderText("비밀번호 (테스트: 0000)")
            self.lineEdit_secret.setEchoMode(QLineEdit.Password)
            layout.addWidget(self.lineEdit_secret)
            self.pushButton_connect = QPushButton("로그인")
            try:
                self.pushButton_connect.setEnabled(False)
            except Exception:
                pass
            self.pushButton_connect.clicked.connect(self._on_login)
            layout.addWidget(self.pushButton_connect)
            skip_btn = QPushButton("건너뛰기 (개발용)")
            skip_btn.clicked.connect(self._on_skip)
            layout.addWidget(skip_btn)
            self.label_hint = QLabel("시스템 상태: 초기화 중...")
            self.label_hint.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            layout.addWidget(self.label_hint)
            self.setLayout(layout)

        def _set_default_credentials(self):
            try:
                access = getattr(self, "lineEdit_access", None)
                if access is not None:
                    access.setText("0000")
                secret = getattr(self, "lineEdit_secret", None)
                if secret is not None:
                    secret.setText("0000")
            except Exception:
                pass

        def _start_prelogin_checks(self):
            try:
                if hasattr(self, "label_hint"):
                    try:
                        self.label_hint.setText("시스템 상태 확인 중... 잠시만 기다려 주세요.")
                    except Exception:
                        pass
                if _PreLoginCheckerRuntime is None:
                    logger.debug("[LoginWidget] PreLoginChecker not available (module missing)")
                    return
                # Use runtime class reference
                self._prelogin_checker = _PreLoginCheckerRuntime(self)
                self._prelogin_checker.sig_status.connect(self._on_prelogin_status)
                self._prelogin_checker.finished.connect(self._on_prelogin_finished)
                self._prelogin_checker.start()
                logger.info("[LoginWidget] PreLoginChecker started")
            except Exception:
                logger.exception("[LoginWidget] PreLoginChecker start failed")

        def _on_prelogin_status(self, status: dict):
            try:
                if isinstance(status, dict):
                    self._last_prelogin_status.update(status)
                parts = []
                for k, v in (status.items() if isinstance(status, dict) else []):
                    parts.append(f"{k}: {'OK' if v else 'FAIL'}")
                st = " | ".join(parts) if parts else "대기중"
                if hasattr(self, "label_hint"):
                    try:
                        self.label_hint.setText(f"시스템 상태: {st}")
                    except Exception:
                        pass
            except Exception:
                logger.exception("[LoginWidget] _on_prelogin_status failed")

        def _on_prelogin_finished(self):
            try:
                if hasattr(self, "pushButton_connect"):
                    try:
                        self.pushButton_connect.setEnabled(True)
                    except Exception:
                        pass
                status_dict = getattr(self, "_last_prelogin_status", {}) or {}
                found_fail = any(v is False for k, v in status_dict.items() if k != "gap_hint")
                gap_hint_present = bool(status_dict.get("gap_hint", False))
                auto_backfill_env = os.getenv("AUTO_BACKFILL_ON_STARTUP", "1")
                auto_backfill_on_startup = str(auto_backfill_env).lower() not in ("0", "false", "no", "")
                enable_ai_env = os.getenv("ENABLE_AI", "0")
                ai_enabled = str(enable_ai_env).lower() not in ("0", "false", "no", "")
                if found_fail:
                    logger.warning("[LoginWidget] PreLogin found failures: %s", status_dict)
                    if not ai_enabled:
                        # AutoBackfill는 백그라운드/비동기일 수 있으므로 run_sync_callable으로 안전 호출
                        try:
                            run_sync_callable(lambda: trigger_auto_backfill_wrapper(self))
                        except Exception:
                            logger.exception("[LoginWidget] trigger_auto_backfill_wrapper failed")
                else:
                    logger.info("[LoginWidget] PreLogin all services OK")
                    if auto_backfill_on_startup and not ai_enabled:
                        try:
                            run_sync_callable(lambda: trigger_auto_backfill_wrapper(self))
                        except Exception:
                            logger.exception("[LoginWidget] trigger_auto_backfill_wrapper failed")
            except Exception:
                logger.exception("[LoginWidget] _on_prelogin_finished failed")

        def _on_backfill_complete_ui(self, success: bool):
            try:
                self._backfill_running = False
                msg = "백필 완료: 성공" if success else "백필 완료: 실패(상세 로그 확인)"
                if hasattr(self, "label_hint"):
                    try:
                        self.label_hint.setText((self.label_hint.text() or "") + "\n" + msg)
                    except Exception:
                        pass
                logger.info("[LoginWidget] Backfill finished: %s", success)
            except Exception:
                logger.exception("[LoginWidget] _on_backfill_complete_ui failed")

        def _on_login(self):
            access = getattr(self, "lineEdit_access", None)
            secret = getattr(self, "lineEdit_secret", None)
            user_id = access.text().strip() if access is not None else ""
            password = secret.text().strip() if secret is not None else ""
            if user_id == "0000" and password == "0000":
                logger.info("[LoginWidget] Test login accepted")
                self.accept()
                return
            if not user_id or not password:
                QMessageBox.warning(self, "입력 오류", "아이디와 비밀번호를 입력해 주세요.")
                return
            QMessageBox.warning(self, "로그인 실패", "아이디 또는 비밀번호가 올바르지 않습니다.\n(테스트 계정: 0000 / 0000)")

        def _on_skip(self):
            logger.info("[LoginWidget] Login skipped (dev mode)")
            self.accept()

    # wrapper that the widget calls via run_sync_callable to keep responsibilities separated
    def trigger_auto_backfill_wrapper(widget: LoginWidget):
        """
        호출 시:
        - trigger_auto_backfill() 를 실행하고 결과를 reflected to widget (label + signal)
        """
        try:
            if _trigger_auto_backfill_runtime is None:
                logger.debug("[trigger_auto_backfill_wrapper] trigger_auto_backfill module missing")
                return None
            mgr, started, reason = _trigger_auto_backfill_runtime(cb=lambda s: widget.backfill_finished.emit(bool(s)))
            if started:
                widget._backfill_running = True
                if hasattr(widget, "label_hint"):
                    try:
                        widget.label_hint.setText((widget.label_hint.text() or "") + "\n백필 작업을 시작했습니다.")
                    except Exception:
                        pass
            else:
                if hasattr(widget, "label_hint") and reason:
                    try:
                        widget.label_hint.setText((widget.label_hint.text() or "") + f"\n(백필 시작 안됨: {reason})")
                    except Exception:
                        pass
            return mgr
        except Exception:
            logger.exception("[trigger_auto_backfill_wrapper] failed")
            return None


# === MainWindow loader helpers ===
def _load_class_from_file(candidate: str, class_name: str):
    """파일에서 지정 클래스 로드(원본 구현 호환)."""
    try:
        if not candidate or not os.path.isfile(candidate):
            return None
        spec = importlib.util.spec_from_file_location(f"project_module_{os.path.basename(candidate)}", candidate)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            cls = getattr(mod, class_name, None)
            return cls
    except Exception as e:
        logger.debug("[widget_login] file-load %s failed: %s", candidate, e)
    return None


def _launch_main_window(app: "QApplication") -> None:
    """
    MainWindow 로더:
    - 패키지 모듈 경로 우선 탐색
    - 파일 폴백 탐색
    - 최종 폴백은 간단한 QMainWindow
    """
    main_window = None
    tried_sources = []
    module_candidates = [
        "src.app.ui.window_main",
        "app.ui.window_main",
        "src.app.ui.windows.main_window",
        "app.ui.windows.main_window",
    ]
    for modname in module_candidates:
        try:
            tried_sources.append(f"module:{modname}")
            mod = importlib.import_module(modname)
            MainWindow = getattr(mod, "MainWindow", None)
            if MainWindow:
                try:
                    main_window = MainWindow()
                    logger.info("[widget_login] MainWindow loaded from module %s", modname)
                    break
                except Exception as e:
                    logger.debug("[widget_login] Instantiation of MainWindow from %s failed: %s", modname, e)
        except Exception as e:
            logger.debug("[widget_login] import %s failed: %s", modname, e)

    if main_window is None:
        try:
            here = Path(__file__).resolve()
            repo_root = here.parents[2] if len(here.parents) >= 3 else here.parent
        except Exception:
            repo_root = Path(os.getcwd())
        file_candidates = [
            repo_root / "src" / "app" / "ui" / "window_main.py",
            repo_root / "src" / "app" / "ui" / "windows" / "main_window.py",
            repo_root / "src" / "app" / "ui" / "windows" / "window_main.py",
            repo_root / "src" / "app" / "ui" / "main_window.py",
        ]
        for cand in file_candidates:
            try:
                tried_sources.append(f"file:{cand}")
                cls = _load_class_from_file(str(cand), "MainWindow")
                if cls:
                    try:
                        main_window = cls()
                        logger.info("[widget_login] MainWindow loaded from file %s", cand)
                        break
                    except Exception as e:
                        logger.debug("[widget_login] Instantiation of MainWindow from %s failed: %s", cand, e)
            except Exception as e:
                logger.debug("[widget_login] file candidate %s check failed: %s", cand, e)

    if main_window is None:
        try:
            from PyQt5.QtWidgets import QMainWindow, QLabel
            class _FallbackMainWindow(QMainWindow):
                def __init__(self):
                    super().__init__()
                    self.setWindowTitle("Upbit Trader")
                    # 대형 화면에 적절한 기본 크기
                    self.setGeometry(100, 100, 1400, 900)
                    label = QLabel("Upbit Trader (개발 중)", self)
                    label.setAlignment(Qt.AlignCenter)
                    self.setCentralWidget(label)
            main_window = _FallbackMainWindow()
            logger.warning("[widget_login] Using fallback MainWindow; tried: %s", tried_sources)
        except Exception as e:
            logger.error(f"[widget_login] Cannot create MainWindow: {e}")
            traceback.print_exc()
            return

    # show and run
    if main_window is not None:
        main_window.show()
        # try init_data if present (best-effort)
        if hasattr(main_window, "init_data"):
            try:
                main_window.init_data()
            except Exception as e:
                logger.warning("[gui_main] init_data failed (ignored): %s", e)
        try:
            if QApplication.instance() is app:
                try:
                    if _qasync is not None:
                        loop = asyncio.get_event_loop()
                        # qasync loop handling: if qasync loop was set, run it
                        if isinstance(loop, _qasync.QEventLoop):
                            with loop:
                                loop.run_forever()
                            return
                except Exception:
                    pass
                sys.exit(app.exec_())
            else:
                app.exec_()
        except Exception as e:
            logger.exception("[widget_login] app.exec_ failed: %s", e)


# gui_main
def gui_main():
    if not _HAS_QT:
        logger.error("[gui_main] PyQt5 is not installed; cannot start GUI.")
        print("[gui_main] PyQt5 is not installed; cannot start GUI.")
        return
    try:
        try:
            QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
            QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        except Exception:
            pass

        app = QApplication.instance() or QApplication(sys.argv)

        # qasync integration
        if _qasync is not None:
            try:
                loop = _qasync.QEventLoop(app)
                asyncio.set_event_loop(loop)
                try:
                    set_main_loop(loop)
                except Exception:
                    pass
            except Exception:
                logger.debug("[gui_main] qasync init failed, using default loop")
        else:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    try:
                        set_main_loop(loop)
                    except Exception:
                        pass
            except Exception:
                pass

        login = LoginWidget()
        result = login.exec_()
        if result == QDialog.Accepted:
            logger.info("[gui_main] Login accepted — launching MainWindow")
            try:
                _launch_main_window(app)
            except Exception:
                logger.debug("[gui_main] _launch_main_window missing or failed", exc_info=True)
        else:
            logger.info("[gui_main] Login cancelled")
    except Exception:
        logger.exception("[gui_main] unexpected error")