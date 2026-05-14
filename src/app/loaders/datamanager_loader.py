#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DataManager ?숈쟻 濡쒕뜑 (媛뺥솕??

- ?⑦궎吏 ?ㅼ엫?ㅽ럹?댁뒪 ?꾨낫 ?쒖감 import
- ?뚯씪-?덈꺼 ?대갚(濡쒖뺄 ?뚯씪 諛?repo-wide 寃??
- factory ?⑥닔? ?대옒???앹꽦?먯뿉 ???媛?ν븳 ?쒓렇?덉쿂?ㅼ쓣 ??꼻寃??쒕룄
- ?뚯씪濡?濡쒕뱶??紐⑤뱢??sys.modules???깅줉?섏뿬 ?대? import媛 ?덉젙?곸쑝濡??숈옉?섎룄濡???- static 湲곕컲 濡쒓퉭 ?쇨???諛??곸꽭 ?덉쇅 濡쒓퉭
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import os
import sys
import traceback
from typing import Optional, Any, Dict, Iterable, List
from pathlib import Path

_logger = logging.getLogger("app.loaders.datamanager_loader")


def _log(static: Any, level: str, *args, **kwargs) -> None:
    """
    static.log 媛 ?덉쑝硫??ъ슜, ?꾨땲硫?紐⑤뱢 濡쒓굅 ?먮뒗 print 濡??대갚.
    """
    try:
        log_obj = getattr(static, "log", None)
        if log_obj is not None:
            getattr(log_obj, level)(*args, **kwargs)
            return
    except Exception:
        pass

    try:
        getattr(_logger, level)(*args, **kwargs)
        return
    except Exception:
        pass

    try:
        print(*args, **kwargs)
    except Exception:
        pass


# ------------------------------------------------------------------
# ?고??꾩뿉 src 諛?repo 猷⑦듃瑜?sys.path??異붽????덈? import('app...') 臾몄젣 ?꾪솕
# ------------------------------------------------------------------
def _ensure_package_paths(static: Any = None) -> None:
    """
    ??紐⑤뱢 ?뚯씪 ?꾩튂瑜?湲곗??쇰줈 ?곸쐞 寃쎈줈?먯꽌 'src' ?붾젆?좊━? repo 猷⑦듃瑜?異붿젙?섏뿬
    sys.path???덉쟾?섍쾶 異붽??⑸땲?? ?대? 異붽??섏뼱 ?덉쑝硫?以묐났 異붽??섏? ?딆뒿?덈떎.
    紐⑹쟻: bootstrap?먯꽌 'import app.loaders...' 媛숈? ?덈? import媛 ?ㅽ뙣?섎뒗 臾몄젣 ?꾪솕.
    """
    try:
        p = Path(__file__).resolve()
        # p.parents[0] -> loaders dir
        # p.parents[1] -> app dir
        # p.parents[2] -> src dir
        # p.parents[3] -> repo root (?遺遺?
        if len(p.parents) >= 3:
            src_dir = str(p.parents[2])
            repo_root = str(p.parents[3]) if len(p.parents) >= 4 else str(p.parents[2])

            # src 寃쎈줈 ?곗꽑 異붽? (?덈? import 'app'???꾪븳 寃쎈줈)
            if src_dir and src_dir not in sys.path:
                sys.path.insert(0, src_dir)
                _log(static, "debug", "[datamanager_loader] inserted src into sys.path: %s", src_dir)

            # repo root??異붽????뚯씪-?덈꺼 ?먯깋 寃쎌슦瑜??뺣뒗??
            if repo_root and repo_root not in sys.path:
                sys.path.insert(0, repo_root)
                _log(static, "debug", "[datamanager_loader] inserted repo_root into sys.path: %s", repo_root)
    except Exception:
        try:
            _logger.debug("failed to ensure package paths: %s", traceback.format_exc())
        except Exception:
            pass


# 紐⑤뱢 import ?쒖젏???ㅽ뻾?섏뿬 bootstrap ???ㅼ엫?ㅽ럹?댁뒪 臾몄젣瑜??꾪솕
_ensure_package_paths(None)


def _load_module_by_names(names: Iterable[str], static: Any = None) -> Optional[Any]:
    """二쇱뼱吏??ㅼ엫 紐⑸줉???쒖꽌?濡?import ?쒕룄, ?깃났??紐⑤뱢 諛섑솚. ?ㅽ뙣 濡쒓렇 ?④?."""
    for nm in names:
        try:
            mod = importlib.import_module(nm)
            _log(static, "debug", "[datamanager_loader] import success: %s -> %s", nm, getattr(mod, "__file__", None))
            return mod
        except Exception as e:
            _log(static, "debug", "[datamanager_loader] import %s failed: %s", nm, f"{type(e).__name__}: {e}")
    return None


def _load_module_from_file(path: str, alias: str, static: Any = None) -> Optional[Any]:
    """?뚯씪 寃쎈줈?먯꽌 紐⑤뱢 濡쒕뱶(?뚯씪??議댁옱?섎㈃ 濡쒕뱶?섍퀬 sys.modules???깅줉)."""
    try:
        if not os.path.isfile(path):
            _log(static, "debug", "[datamanager_loader] file not found: %s", path)
            return None
        spec = importlib.util.spec_from_file_location(alias, path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception as e:
                _log(static, "debug", "[datamanager_loader] exec_module failed for %s: %s", path, traceback.format_exc())
                return None
            # ensure available under a deterministic key
            try:
                sys.modules[alias] = mod
            except Exception:
                pass
            _log(static, "debug", "[datamanager_loader] file-loaded module %s from %s", alias, path)
            return mod
    except Exception:
        _log(static, "debug", "[datamanager_loader] file load failed for %s: %s", path, traceback.format_exc())
    return None


def _search_repo_for_file(repo_root: str, filename_part: str, max_results: int = 10) -> List[str]:
    """
    repo_root ?꾨옒?먯꽌 filename_part瑜??ы븿???뚯씪?ㅼ쓣 ?ш? 寃??
    ex) filename_part='data_manager'
    """
    matches: List[str] = []
    for root, dirs, files in os.walk(repo_root):
        # skip some common heavy dirs
        if any(skip in root for skip in (os.path.join(repo_root, ".git"), "venv", "env", "__pycache__", "node_modules")):
            continue
        for f in files:
            if filename_part.lower() in f.lower() and f.lower().endswith(".py"):
                matches.append(os.path.join(root, f))
                if len(matches) >= max_results:
                    return matches
    return matches


def _extract_config_values(static: Any) -> Dict[str, Any]:
    """
    static ?먮뒗 static.config(媛앹껜 ?먮뒗 dict)?먯꽌 媛?ν븳 DB 愿???ㅻ? 李얠븘 ?뺤뀛?덈━濡?諛섑솚.
    """
    out: Dict[str, Any] = {}

    keys = [
        "mongo_uri", "MONGO_URI", "mongo_url", "db_uri", "db_url",
        "mongo_host", "mongo_ip", "mongo_port", "mongo_user", "mongo_username", "mongo_id",
        "mongo_password", "mongo_pwd",
        "EXTERNAL_TIMEOUT", "INTERNAL_TIMEOUT", "REQUEST_LIMIT",
        "request_limit", "external_timeout", "internal_timeout",
    ]

    cfg = getattr(static, "config", None)
    if cfg is not None:
        for k in keys:
            try:
                if hasattr(cfg, k):
                    out[k] = getattr(cfg, k)
                elif isinstance(cfg, dict) and k in cfg:
                    out[k] = cfg[k]
            except Exception:
                continue

    for k in keys:
        if k in out:
            continue
        try:
            if hasattr(static, k):
                out[k] = getattr(static, k)
            elif isinstance(static, dict) and k in static:
                out[k] = static[k]
        except Exception:
            continue

    normalized: Dict[str, Any] = {}
    for cand in ("mongo_uri", "MONGO_URI", "mongo_url", "db_uri", "db_url"):
        if cand in out and out[cand]:
            normalized["mongo_uri"] = out[cand]
            break

    for host_key in ("mongo_host", "mongo_ip"):
        if host_key in out and out[host_key]:
            normalized["host"] = out[host_key]
            break
    for port_key in ("mongo_port",):
        if port_key in out and out[port_key] is not None:
            try:
                normalized["port"] = int(out[port_key])
            except Exception:
                normalized["port"] = out[port_key]
            break
    for user_key in ("mongo_user", "mongo_username", "mongo_id"):
        if user_key in out and out[user_key]:
            normalized["user"] = out[user_key]
            break
    for pwd_key in ("mongo_password", "mongo_pwd"):
        if pwd_key in out and out[pwd_key]:
            normalized["password"] = out[pwd_key]
            break

    for key in ("EXTERNAL_TIMEOUT", "external_timeout"):
        if key in out and out[key] is not None:
            normalized["external_timeout"] = out[key]
            break
    for key in ("INTERNAL_TIMEOUT", "internal_timeout"):
        if key in out and out[key] is not None:
            normalized["internal_timeout"] = out[key]
            break
    for key in ("REQUEST_LIMIT", "request_limit"):
        if key in out and out[key] is not None:
            normalized["request_limit"] = out[key]
            break

    return normalized


def _instantiate_class_with_best_args(cls: Any, cfg: Dict[str, Any], static: Any) -> Optional[Any]:
    """
    cls ???앹꽦???쒓렇?덉쿂瑜??뺤씤?섍퀬 cfg?먯꽌 ?쒓났??媛믪쑝濡?媛?ν븳 ?몄옄瑜?留ㅽ븨???몄뒪?댁뒪???쒕룄.
    """
    try:
        sig = inspect.signature(cls)
    except Exception:
        try:
            return cls()
        except Exception:
            return None

    params = sig.parameters
    kwargs = {}

    uri_keys = {"uri", "mongo_uri", "db_uri", "mongodb_uri", "connection_string"}
    for p in params:
        if p in uri_keys and "mongo_uri" in cfg:
            kwargs[p] = cfg["mongo_uri"]

    if any(n in params for n in ("host", "hostname", "mongo_host", "mongo_ip")):
        if "host" in cfg:
            for p in ("host", "hostname", "mongo_host", "mongo_ip"):
                if p in params:
                    kwargs[p] = cfg.get("host")
    if any(n in params for n in ("port", "mongo_port")) and "port" in cfg:
        for p in ("port", "mongo_port"):
            if p in params:
                kwargs[p] = cfg.get("port")
    if any(n in params for n in ("user", "username", "mongo_user", "mongo_id")) and "user" in cfg:
        for p in ("user", "username", "mongo_user", "mongo_id"):
            if p in params:
                kwargs[p] = cfg.get("user")
    if any(n in params for n in ("password", "pwd", "mongo_password")) and "password" in cfg:
        for p in ("password", "pwd", "mongo_password"):
            if p in params:
                kwargs[p] = cfg.get("password")

    for mapping in (("external_timeout", "external_timeout"), ("internal_timeout", "internal_timeout"), ("request_limit", "request_limit")):
        key, cfg_key = mapping
        if cfg_key in cfg:
            if key in params:
                kwargs[key] = cfg[cfg_key]
            elif cfg_key in params:
                kwargs[cfg_key] = cfg[cfg_key]

    for p in ("config", "cfg", "settings"):
        if p in params:
            kwargs[p] = getattr(static, "config", None) or static
            break

    try:
        _log(static, "debug", "[datamanager_loader] attempting instantiate %s with kwargs=%s", getattr(cls, "__name__", repr(cls)), {k: (type(v).__name__ if v is not None else None) for k, v in kwargs.items()})
        if kwargs:
            return cls(**kwargs)
        else:
            try:
                return cls()
            except TypeError:
                try:
                    return cls(static)
                except Exception:
                    try:
                        return cls(getattr(static, "config", None))
                    except Exception:
                        return None
    except Exception:
        _log(static, "debug", "[datamanager_loader] instantiate failed for %s: %s", getattr(cls, "__name__", repr(cls)), traceback.format_exc())
        return None


def _call_factory_with_best_args(factory: Any, cfg_values: Dict[str, Any], static: Any) -> Optional[Any]:
    """
    factory ?⑥닔???쒓렇?덉쿂瑜?蹂닿퀬 媛?ν븳 ?몄옄瑜??꾨떖?섏뿬 ?몄텧 ?쒕룄.
    """
    try:
        sig = inspect.signature(factory)
    except Exception:
        try:
            return factory()
        except Exception:
            return None

    params = sig.parameters
    # try several invocation patterns in order of preference
    tries = []

    # 1) factory(static)
    if "static" in params:
        tries.append(("static", (static, ), {}))
    # 2) factory(config) or factory(static.config)
    if "config" in params or "cfg" in params:
        tries.append(("config", (getattr(static, "config", None), ), {}))
    # 3) factory(**cfg_values) if parameters match
    if cfg_values:
        # filter cfg_values by params
        kwargs = {k: v for k, v in cfg_values.items() if k in params}
        if kwargs:
            tries.append(("cfg_kwargs", (), kwargs))
    # 4) no-arg
    tries.append(("no_args", (), {}))

    for name, args, kwargs in tries:
        try:
            _log(static, "debug", "[datamanager_loader] calling factory %s with try=%s args=%s kwargs_keys=%s", getattr(factory, "__name__", repr(factory)), name, ("(static)" if args else "()"), list(kwargs.keys()))
            res = factory(*args, **kwargs)
            _log(static, "debug", "[datamanager_loader] factory %s returned %s", getattr(factory, "__name__", repr(factory)), type(res).__name__)
            return res
        except TypeError as e:
            _log(static, "debug", "[datamanager_loader] factory try=%s TypeError: %s", name, e)
            continue
        except Exception:
            _log(static, "debug", "[datamanager_loader] factory try=%s exception: %s", name, traceback.format_exc())
            # try next
            continue

    return None


def create_data_manager(static: Any) -> Optional[Any]:
    """
    DataManager ?몄뒪?댁뒪瑜??앹꽦?섏뿬 諛섑솚. ?ㅽ뙣?섎㈃ None 諛섑솚.
    """
    _log(static, "info", "[datamanager_loader] create_data_manager invoked")

    module_candidates = [
        "data_01.core.data_manager",
        "src.data_01.core.data_manager",
        "src._data_01.core.data_manager",
        "data_01.core",
        "data_01.core.data_manager_v2",
        "data.core.data_manager",
        "src.data.core.data_manager",
    ]

    server_mod = _load_module_by_names(module_candidates, static)

    if server_mod is None:
        legacy = [
            "server.server", "src.server.server", "11_server.app.server", "11_server.server.server"
        ]
        server_mod = _load_module_by_names(legacy, static)

    # file-level fallbacks relative to repo
    if server_mod is None:
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            file_candidates = [
                os.path.join(base_dir, "data_01", "core", "data_manager.py"),
                os.path.join(base_dir, "src", "data_01", "core", "data_manager.py"),
                os.path.join(base_dir, "data_01", "core", "data_manager_local.py"),
                os.path.join(base_dir, "..", "data_01", "core", "data_manager.py"),
            ]
            for p in file_candidates:
                mod = _load_module_from_file(p, alias=f"datamanager_file_{os.path.basename(p)}", static=static)
                if mod is not None:
                    server_mod = mod
                    break

            # repo-wide search as last resort
            if server_mod is None:
                repo_root = os.path.abspath(os.path.join(base_dir, "..", "..")) if os.path.basename(base_dir) == "app" else os.path.abspath(os.path.join(base_dir, ".."))
                repo_root = os.path.abspath(repo_root)
                _log(static, "debug", "[datamanager_loader] repo root computed as %s", repo_root)
                found = _search_repo_for_file(repo_root, "data_manager", max_results=8)
                _log(static, "debug", "[datamanager_loader] repo search candidates: %s", found)
                for f in found:
                    mod = _load_module_from_file(f, alias=f"repo_datamanager_{os.path.basename(f)}", static=static)
                    if mod is not None:
                        server_mod = mod
                        break
        except Exception:
            _log(static, "debug", "[datamanager_loader] file-level fallbacks failed: %s", traceback.format_exc())

    if server_mod is None:
        _log(static, "warning", "[datamanager_loader] DataManager module not found among candidates")
        return None

    # resolve candidates
    DataManagerCandidate = getattr(server_mod, "DataManager", None)
    create_fn = getattr(server_mod, "create_data_manager", None) or getattr(server_mod, "get_data_manager", None)

    # try other common factory names
    if DataManagerCandidate is None and create_fn is None:
        for nm in ("make_data_manager", "build_data_manager", "factory"):
            if hasattr(server_mod, nm):
                create_fn = getattr(server_mod, nm)
                break

    cfg_values = _extract_config_values(static)
    _log(static, "debug", "[datamanager_loader] cfg_values extracted: %s", cfg_values)

    # 1) factory function preferred
    if callable(create_fn):
        try:
            res = _call_factory_with_best_args(create_fn, cfg_values, static)
            if res is not None:
                _log(static, "info", "[datamanager_loader] factory created data_manager: %s", type(res))
                return res
        except Exception:
            _log(static, "error", "[datamanager_loader] create_data_manager factory raised:\n%s", traceback.format_exc())

    # 2) class instantiation attempts
    if DataManagerCandidate is not None and inspect.isclass(DataManagerCandidate):
        _log(static, "info", "[datamanager_loader] DataManager class found, attempting instantiation")
        inst = _instantiate_class_with_best_args(DataManagerCandidate, cfg_values, static)
        if inst is not None:
            _log(static, "info", "[datamanager_loader] DataManager instance created: %s", type(inst))
            return inst
        # try alternate invocation patterns
        try:
            _log(static, "debug", "[datamanager_loader] trying fallback constructors for DataManager")
            try:
                inst = DataManagerCandidate(static)
                _log(static, "info", "[datamanager_loader] DataManager(static) succeeded")
                return inst
            except Exception:
                _log(static, "debug", "[datamanager_loader] DataManager(static) failed: %s", traceback.format_exc())
            try:
                inst = DataManagerCandidate(getattr(static, "config", None))
                _log(static, "info", "[datamanager_loader] DataManager(config) succeeded")
                return inst
            except Exception:
                _log(static, "debug", "[datamanager_loader] DataManager(config) failed: %s", traceback.format_exc())
        except Exception:
            _log(static, "debug", "[datamanager_loader] fallback constructor attempts raised: %s", traceback.format_exc())

    # 3) last-resort: any callable attribute in module
    for attr_name in ("DataManager", "data_manager", "Data_Manager"):
        try:
            attr = getattr(server_mod, attr_name, None)
            if callable(attr):
                _log(static, "info", "[datamanager_loader] trying fallback callable %s()", attr_name)
                try:
                    res = attr()
                    _log(static, "info", "[datamanager_loader] fallback callable %s() returned %s", attr_name, type(res))
                    return res
                except Exception:
                    _log(static, "debug", "[datamanager_loader] fallback callable %s() failed: %s", attr_name, traceback.format_exc())
        except Exception:
            continue

    _log(static, "warning", "[datamanager_loader] Could not instantiate DataManager from module %s", getattr(server_mod, "__file__", "<module>"))
    return None
