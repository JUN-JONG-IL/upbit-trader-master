# -*- coding: utf-8 -*-
"""
Loaders ?⑦궎吏 珥덇린??(吏??濡쒕뱶, ?뚯씪-?덈꺼 ?대갚, shim ?쒓굅)

?ㅻ챸:
- create_data_manager / setup_pipeline ?⑥닔瑜??몄텧?????대??먯꽌 ?ㅼ젣 援ы쁽 紐⑤뱢???숈쟻?쇰줈 濡쒕뱶?⑸땲??
- ?ㅼ엫?ㅽ럹?댁뒪 import ?ㅽ뙣 ??src 猷⑦듃 諛묒쓽 ?뚯씪??吏곸젒 濡쒕뱶?섎뒗 ?뚯씪-?덈꺼 ?대갚???쒕룄?⑸땲??
- ?뚯씪濡?濡쒕뱶??紐⑤뱢? 媛?ν븳 ???뺤떇 ?⑦궎吏 ?ㅼ엫?ㅽ럹?댁뒪(?? app.loaders.datamanager_loader)濡?
  sys.modules???깅줉?섏뿬 'shim' 臾몄젣瑜??쒓굅?⑸땲??
- shim(?꾩떆 ?⑦궎吏/?뚯씪) ?앹꽦?대굹 ?뚯씪 ?대룞? ?덈? ?섏? ?딆뒿?덈떎.
- ?ㅽ뙣 ??媛?ν븳 紐⑤뱺 ?쒕룄 寃곌낵(紐⑤뱢 ?꾨낫, ?뚯씪 ?꾨낫, traceback)瑜??곸꽭??濡쒓퉭?⑸땲??
"""
from __future__ import annotations

import importlib
import importlib.util
import traceback
import os
import sys
from typing import Any, Optional, Iterable, List, Tuple

__all__ = ["create_data_manager", "setup_pipeline"]


def _log_static(static: Any, level: str, msg: str, *args) -> None:
    """
    static??log 媛앹껜媛 ?덉쑝硫??ъ슜, ?놁쑝硫?print濡??대갚.
    level: 'info', 'warning', 'error', 'debug'
    """
    try:
        logobj = getattr(static, "log", None)
        if logobj is not None and hasattr(logobj, level):
            getattr(logobj, level)(msg % args if args else msg)
            return
    except Exception:
        pass
    try:
        text = msg % args if args else msg
        if level == "info":
            print("[INFO] " + text)
        elif level == "warning":
            print("[WARN] " + text)
        elif level == "error":
            print("[ERROR] " + text)
        else:
            print("[DEBUG] " + text)
    except Exception:
        pass


def _find_src_root(start_path: Optional[str] = None) -> str:
    """
    start_path?먯꽌 ?꾨줈 ?щ씪媛硫?'src' ?대뜑瑜?李얜뒗?? 紐?李얠쑝硫?start_path ?곸쐞 3?④퀎瑜?諛섑솚.
    """
    if start_path is None:
        start_path = os.path.abspath(__file__)
    p = os.path.abspath(start_path)
    # if start_path is a file, start from its directory
    if os.path.isfile(p):
        p = os.path.dirname(p)
    for _ in range(6):
        candidate = os.path.join(p, "src")
        if os.path.isdir(candidate):
            return os.path.abspath(candidate)
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    # fallback: assume src is two levels up from this file's directory
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def _module_name_from_path(src_root: str, file_path: str) -> Optional[str]:
    """
    src_root 諛묒쓽 file_path濡쒕???紐⑤뱢 ?ㅼ엫?ㅽ럹?댁뒪(?꾪듃 ?쒓린)瑜??앹꽦?쒕떎.
    ?? /.../src/app/loaders/datamanager_loader.py -> 'app.loaders.datamanager_loader'
    諛섑솚 遺덇??ν븯硫?None.
    """
    try:
        src_root = os.path.abspath(src_root)
        fp = os.path.abspath(file_path)
        if not fp.startswith(src_root):
            return None
        rel = os.path.relpath(fp, src_root)
        # remove .py and replace path sep with dot
        if rel.endswith(".py"):
            rel = rel[:-3]
        parts = []
        for part in rel.split(os.path.sep):
            # ignore empty or current dir
            if part in ("", ".", ".."):
                continue
            parts.append(part)
        if not parts:
            return None
        return ".".join(parts)
    except Exception:
        return None


def _load_module_from_file(path: str, alias: Optional[str] = None, src_root: Optional[str] = None):
    """
    ?뚯씪 寃쎈줈?먯꽌 紐⑤뱢???덉쟾?섍쾶 濡쒕뱶 (importlib.util).
    - 媛?ν븳 寃쎌슦 ?뺤떇 ?⑦궎吏 ?ㅼ엫?ㅽ럹?댁뒪濡?sys.modules???깅줉?섏뿬 shim ?앹꽦??諛⑹?.
    - alias: ?꾩떆 alias (?? 'file_loaded__...') ???대? 李몄“??
    - src_root: src 猷⑦듃 寃쎈줈瑜?二쇰㈃, src_root ?섏쐞?쇰㈃ ?⑦궎吏 ?ㅼ엫?ㅽ럹?댁뒪濡??깅줉???쒕룄.
    """
    try:
        if not os.path.isfile(path):
            return None
        spec = importlib.util.spec_from_file_location(alias or path, path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            # Register module in sys.modules under best-effort package names
            registered_names = []
            try:
                # 1) If src_root provided and path under it, compute canonical module name
                if src_root:
                    mname = _module_name_from_path(src_root, path)
                    if mname:
                        # only register if not already present
                        if mname not in sys.modules:
                            sys.modules[mname] = mod
                            registered_names.append(mname)
                # 2) also register alias if provided and not present
                if alias:
                    if alias not in sys.modules:
                        sys.modules[alias] = mod
                        registered_names.append(alias)
            except Exception:
                # best-effort registration; continue even if fails
                pass

            # Execute module
            spec.loader.exec_module(mod)
            # Ensure module is accessible under at least one name
            if not registered_names:
                # fallback: ensure a simple alias is present
                try:
                    fallback = alias or f"file_loaded__{os.path.basename(path)}"
                    sys.modules.setdefault(fallback, mod)
                except Exception:
                    pass
            return mod
    except Exception:
        # Do not raise here; caller will log attempts
        return None
    return None


def _try_import_candidates(
    candidates: Iterable[str],
    file_candidates: Iterable[str],
    static: Any,
    desc: str,
):
    """
    - candidates: ?ㅼ엫?ㅽ럹?댁뒪 ?꾨낫(importlib.import_module濡??쒕룄)
    - file_candidates: ?뚯씪 寃쎈줈 ?꾨낫(?꾨줈?앺듃 src 猷⑦듃 湲곗? ?곷? 寃쎈줈 ?먮뒗 ?덈?寃쎈줈)
    - desc: 濡쒓퉭???ㅻ챸 ('datamanager_loader' ?먮뒗 'pipeline_loader' ??
    諛섑솚: (module_or_None, attempts_list)
    attempts_list: [(kind, name, result_str), ...] where kind='import'|'file'
    """
    attempts: List[Tuple[str, str, str]] = []

    # 1) namespace imports (?뺤떇 ?⑦궎吏 寃쎈줈 ?곗꽑)
    for nm in candidates:
        try:
            mod = importlib.import_module(nm)
            attempts.append(("import", nm, "ok"))
            _log_static(static, "debug", "[loaders] %s import success: %s -> %s", desc, nm, getattr(mod, "__file__", None))
            return mod, attempts
        except Exception as e:
            attempts.append(("import", nm, f"{type(e).__name__}: {e}"))
            _log_static(static, "debug", "[loaders] %s import failed: %s -> %s", desc, nm, f"{type(e).__name__}: {e}")

    # 2) file-level load from src root (?뺤꽍???곗꽑)
    src_root = _find_src_root(os.path.dirname(os.path.abspath(__file__)))
    for fp in file_candidates:
        try:
            if not fp:
                continue
            # If fp is relative path, make absolute relative to src_root
            if not os.path.isabs(fp):
                fp_abs = os.path.normpath(os.path.join(src_root, fp))
            else:
                fp_abs = fp
            exists = os.path.isfile(fp_abs)
            attempts.append(("file", fp_abs, "exists" if exists else "missing"))
            _log_static(static, "debug", "[loaders] %s file candidate: %s exists=%s", desc, fp_abs, exists)
            if exists:
                # compute a canonical module name if possible (to avoid shim)
                canon_name = _module_name_from_path(src_root, fp_abs)
                alias = f"file_loaded__{os.path.basename(fp_abs)}"
                mod = _load_module_from_file(fp_abs, alias=alias, src_root=src_root)
                if mod is not None:
                    if canon_name and canon_name not in sys.modules:
                        # if _load_module_from_file didn't register canon_name earlier, set it now
                        try:
                            sys.modules[canon_name] = mod
                        except Exception:
                            pass
                    attempts.append(("file", fp_abs, "loaded"))
                    _log_static(static, "info", "[loaders] %s file-loaded module: %s as %s", desc, fp_abs, canon_name or alias)
                    return mod, attempts
                else:
                    attempts.append(("file", fp_abs, "load_failed"))
                    _log_static(static, "debug", "[loaders] %s file load failed: %s", desc, fp_abs)
        except Exception as e:
            attempts.append(("file", fp, f"{type(e).__name__}: {e}"))
            _log_static(static, "debug", "[loaders] %s file attempt exception for %s: %s", desc, fp, f"{type(e).__name__}: {e}")

    _log_static(static, "debug", "[loaders] %s: all candidates tried: %s", desc, attempts)
    return None, attempts


def create_data_manager(static: Any) -> Optional[Any]:
    """
    datamanager_loader.create_data_manager 瑜?吏??濡쒕뱶?섏뿬 ?몄텧.
    - ?깃났: DataManager ?몄뒪?댁뒪 諛섑솚
    - ?ㅽ뙣: RuntimeError 諛쒖깮 (?몄텧?먯뿉??catch ?섏뿬 泥섎━)
    """
    desc = "datamanager_loader"
    # ?ㅼ엫?ㅽ럹?댁뒪 ?꾨낫??
    ns_candidates = [
        "app.loaders.datamanager_loader",
        "app.loaders.datamanager_loader",  # duplicate safe
        "data_01.core.data_manager",
        "src.app.loaders.datamanager_loader",
        "app.datamanager_loader",
    ]
    # ?뚯씪 ?꾨낫 (src 猷⑦듃 湲곗? ?곷? 寃쎈줈)
    file_candidates = [
        os.path.join("app", "loaders", "datamanager_loader.py"),
        os.path.join("app", "core", "datamanager_loader.py"),
        os.path.join("data_01", "core", "data_manager.py"),
    ]

    mod, attempts = _try_import_candidates(ns_candidates, file_candidates, static, desc)
    if mod is None:
        _log_static(static, "debug", "[loaders] create_data_manager: %s not found; attempts=%s", desc, attempts)
        raise RuntimeError("datamanager_loader not available. Ensure src/app/loaders/datamanager_loader.py exists and is importable.") from None

    create_fn = getattr(mod, "create_data_manager", None)
    if not callable(create_fn):
        _log_static(static, "debug", "[loaders] create_data_manager: create_data_manager factory not found in %s; public attrs: %s", desc, ", ".join([a for a in dir(mod) if not a.startswith("_")]) )
        raise RuntimeError("datamanager_loader missing create_data_manager factory")

    try:
        return create_fn(static)
    except Exception as e:
        _log_static(static, "error", "[loaders] create_data_manager: creation failed: %s", str(e))
        _log_static(static, "debug", "[loaders] create_data_manager traceback:\n%s", traceback.format_exc())
        raise


def setup_pipeline(static: Any) -> None:
    """
    pipeline_loader.setup_pipeline 瑜?吏??濡쒕뱶?섏뿬 ?몄텧.
    - ?ㅼ엫?ㅽ럹?댁뒪 import ?ㅽ뙣 ??src ?섏쐞???뚯씪??吏곸젒 濡쒕뱶?섎뒗 ?대갚???쒕룄?⑸땲??
    - ?ㅽ뙣 ??RuntimeError 諛쒖깮.
    """
    desc = "pipeline_loader"
    ns_candidates = [
        "app.loaders.pipeline_loader",
        "src.app.loaders.pipeline_loader",
        "app.pipeline_loader",
    ]
    file_candidates = [
        os.path.join("app", "loaders", "pipeline_loader.py"),
        os.path.join("data_01", "pipeline", "processor.py"),
        os.path.join("data_01", "timescale", "operations", "candle_writer.py"),
        os.path.join("app", "pipeline_loader.py"),
    ]

    mod, attempts = _try_import_candidates(ns_candidates, file_candidates, static, desc)
    if mod is None:
        _log_static(static, "debug", "[loaders] setup_pipeline: %s not found; attempts=%s", desc, attempts)
        raise RuntimeError("pipeline_loader not available. Ensure src/app/loaders/pipeline_loader.py exists and is importable.") from None

    # Prefer explicit setup_pipeline symbol; fallback to factory names
    setup_fn = getattr(mod, "setup_pipeline", None)
    if not callable(setup_fn):
        setup_fn = getattr(mod, "setup", None) or getattr(mod, "create_pipeline", None) or getattr(mod, "create_processor", None) or getattr(mod, "create_processor_instance", None)

    if not callable(setup_fn):
        _log_static(static, "debug", "[loaders] setup_pipeline: setup function not found in module; public attrs: %s", ", ".join([a for a in dir(mod) if not a.startswith("_")]))
        raise RuntimeError("pipeline_loader missing setup_pipeline or compatible factory")

    try:
        setup_fn(static)
    except Exception as e:
        _log_static(static, "error", "[loaders] setup_pipeline: setup failed: %s", str(e))
        _log_static(static, "debug", "[loaders] setup_pipeline traceback:\n%s", traceback.format_exc())
        raise
