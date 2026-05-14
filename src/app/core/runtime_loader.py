# -*- coding: utf-8 -*-
"""
런타임 모듈 로더
- static, RealtimeManager, Account 등 전역 객체 로드
"""
from __future__ import annotations

from types import SimpleNamespace

from .logger import SafeLogger
from .module_loader import try_import_names


def load_runtime_modules(static: SimpleNamespace, log: SafeLogger) -> None:
    """런타임 모듈 로드 (static, RealtimeManager, Account)"""
    global RealtimeManager, Account, SignalManager
    
    RealtimeManager = None
    Account = None
    SignalManager = None

    # server.static 로드
    server_candidates = (
        "src.11_server.app.static",
        "11_server.app.static",
        "11_server.app.static.__init__",
    )
    server_mod, attempts = try_import_names(server_candidates)
    if server_mod:
        # static 모듈을 전역 static으로 교체
        for attr in dir(server_mod):
            if not attr.startswith("_"):
                setattr(static, attr, getattr(server_mod, attr))
        
        srv_log = getattr(server_mod, "log", None)
        if srv_log:
            try:
                from .logger import SafeLogger
                log = SafeLogger(srv_log, name="server.static")
                log.debug("[bootstrap] adopted server logger")
            except Exception:
                pass
    else:
        log.debug("[bootstrap] server.static import attempts: %s", attempts)

    # utils 모듈 로드
    utils_candidates = ("src.11_server.utils", "11_server.utils", "src.app.utils", "app.utils", "utils")
    utils_mod, u_attempts = try_import_names(utils_candidates)
    if utils_mod:
        set_global = getattr(utils_mod, "set_windows_selector_event_loop_global", None)
        if callable(set_global):
            import builtins
            setattr(builtins, "set_windows_selector_event_loop_global", set_global)
        set_mp = getattr(utils_mod, "set_multiprocessing_context", None)
        if callable(set_mp):
            import builtins
            setattr(builtins, "set_multiprocessing_context", set_mp)
    else:
        log.debug("[bootstrap] utils import attempts: %s", u_attempts)

    # helpers 모듈 로드
    helper_candidates = (
        "src.app.utils.helpers",
        "app.utils.helpers",
        "01_core.utils.helpers",
        "src.01_core.utils.helpers",
        "11_server.utils.helpers",
        "src.11_server.utils.helpers",
        "utils.helpers",
        "data_01.timescale.utils.helpers",
        "data_01.utils.helpers",
    )
    helper_mod, h_attempts = try_import_names(helper_candidates)
    if helper_mod:
        RealtimeManager = getattr(helper_mod, "RealtimeManager", RealtimeManager)
        Account = getattr(helper_mod, "Account", Account)
        log.debug("[bootstrap] helpers module imported: %s", getattr(helper_mod, "__file__", None))
    else:
        log.debug("[bootstrap] helpers import attempts: %s", h_attempts)
        comp_candidates = (
            "src.11_server.component.component",
            "11_server.component.component",
            "11_server.component",
            "component",
            "component.component",
        )
        comp_mod, comp_attempts = try_import_names(comp_candidates)
        if comp_mod:
            if RealtimeManager is None:
                RealtimeManager = getattr(comp_mod, "RealtimeManager", RealtimeManager)
            if Account is None:
                Account = getattr(comp_mod, "Account", Account)
            log.debug("[bootstrap] component module used as fallback for RealtimeManager/Account -> %s", getattr(comp_mod, "__file__", None))
        else:
            log.debug("[bootstrap] component import attempts: %s", comp_attempts)

    # strategy 모듈 로드 시도
    try_import_names(("src.05_strategy", "05_strategy", "strategy"))
    
    # 전역 객체에 저장
    static.RealtimeManager = RealtimeManager
    static.Account = Account
    static.SignalManager = SignalManager
