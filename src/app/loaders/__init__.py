# -*- coding: utf-8 -*-
"""
Loaders ?¨í‚¤ì§€ ì´ˆê¸°??(ì§€??ë¡œë“œ, ?Œì¼-?ˆë²¨ ?´ë°±, shim ?œê±°)

?¤ëª…:
- create_data_manager / setup_pipeline ?¨ìˆ˜ë¥??¸ì¶œ?????´ë??ì„œ ?¤ì œ êµ¬í˜„ ëª¨ë“ˆ???™ì ?¼ë¡œ ë¡œë“œ?©ë‹ˆ??
- ?¤ì„?¤í˜?´ìŠ¤ import ?¤íŒ¨ ??src ë£¨íŠ¸ ë°‘ì˜ ?Œì¼??ì§ì ‘ ë¡œë“œ?˜ëŠ” ?Œì¼-?ˆë²¨ ?´ë°±???œë„?©ë‹ˆ??
- ?Œì¼ë¡?ë¡œë“œ??ëª¨ë“ˆ?€ ê°€?¥í•œ ???•ì‹ ?¨í‚¤ì§€ ?¤ì„?¤í˜?´ìŠ¤(?? app.loaders.datamanager_loader)ë¡?
  sys.modules???±ë¡?˜ì—¬ 'shim' ë¬¸ì œë¥??œê±°?©ë‹ˆ??
- shim(?„ì‹œ ?¨í‚¤ì§€/?Œì¼) ?ì„±?´ë‚˜ ?Œì¼ ?´ë™?€ ?ˆë? ?˜ì? ?ŠìŠµ?ˆë‹¤.
- ?¤íŒ¨ ??ê°€?¥í•œ ëª¨ë“  ?œë„ ê²°ê³¼(ëª¨ë“ˆ ?„ë³´, ?Œì¼ ?„ë³´, traceback)ë¥??ì„¸??ë¡œê¹…?©ë‹ˆ??
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
    static??log ê°ì²´ê°€ ?ˆìœ¼ë©??¬ìš©, ?†ìœ¼ë©?printë¡??´ë°±.
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
    start_path?ì„œ ?„ë¡œ ?¬ë¼ê°€ë©?'src' ?´ë”ë¥?ì°¾ëŠ”?? ëª?ì°¾ìœ¼ë©?start_path ?ìœ„ 3?¨ê³„ë¥?ë°˜í™˜.
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
    src_root ë°‘ì˜ file_pathë¡œë???ëª¨ë“ˆ ?¤ì„?¤í˜?´ìŠ¤(?„íŠ¸ ?œê¸°)ë¥??ì„±?œë‹¤.
    ?? /.../src/app/loaders/datamanager_loader.py -> 'app.loaders.datamanager_loader'
    ë°˜í™˜ ë¶ˆê??¥í•˜ë©?None.
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
    ?Œì¼ ê²½ë¡œ?ì„œ ëª¨ë“ˆ???ˆì „?˜ê²Œ ë¡œë“œ (importlib.util).
    - ê°€?¥í•œ ê²½ìš° ?•ì‹ ?¨í‚¤ì§€ ?¤ì„?¤í˜?´ìŠ¤ë¡?sys.modules???±ë¡?˜ì—¬ shim ?ì„±??ë°©ì?.
    - alias: ?„ì‹œ alias (?? 'file_loaded__...') ???´ë? ì°¸ì¡°??
    - src_root: src ë£¨íŠ¸ ê²½ë¡œë¥?ì£¼ë©´, src_root ?˜ìœ„?¼ë©´ ?¨í‚¤ì§€ ?¤ì„?¤í˜?´ìŠ¤ë¡??±ë¡???œë„.
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
    - candidates: ?¤ì„?¤í˜?´ìŠ¤ ?„ë³´(importlib.import_moduleë¡??œë„)
    - file_candidates: ?Œì¼ ê²½ë¡œ ?„ë³´(?„ë¡œ?íŠ¸ src ë£¨íŠ¸ ê¸°ì? ?ë? ê²½ë¡œ ?ëŠ” ?ˆë?ê²½ë¡œ)
    - desc: ë¡œê¹…???¤ëª… ('datamanager_loader' ?ëŠ” 'pipeline_loader' ??
    ë°˜í™˜: (module_or_None, attempts_list)
    attempts_list: [(kind, name, result_str), ...] where kind='import'|'file'
    """
    attempts: List[Tuple[str, str, str]] = []

    # 1) namespace imports (?•ì‹ ?¨í‚¤ì§€ ê²½ë¡œ ?°ì„ )
    for nm in candidates:
        try:
            mod = importlib.import_module(nm)
            attempts.append(("import", nm, "ok"))
            _log_static(static, "debug", "[loaders] %s import success: %s -> %s", desc, nm, getattr(mod, "__file__", None))
            return mod, attempts
        except Exception as e:
            attempts.append(("import", nm, f"{type(e).__name__}: {e}"))
            _log_static(static, "debug", "[loaders] %s import failed: %s -> %s", desc, nm, f"{type(e).__name__}: {e}")

    # 2) file-level load from src root (?•ì„???°ì„ )
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
    datamanager_loader.create_data_manager ë¥?ì§€??ë¡œë“œ?˜ì—¬ ?¸ì¶œ.
    - ?±ê³µ: DataManager ?¸ìŠ¤?´ìŠ¤ ë°˜í™˜
    - ?¤íŒ¨: RuntimeError ë°œìƒ (?¸ì¶œ?ì—??catch ?˜ì—¬ ì²˜ë¦¬)
    """
    desc = "datamanager_loader"
    # ?¤ì„?¤í˜?´ìŠ¤ ?„ë³´??
    ns_candidates = [
        "app.loaders.datamanager_loader",
        "app.loaders.datamanager_loader",  # duplicate safe
        "data_01.core.data_manager",
        "src.app.loaders.datamanager_loader",
        "app.datamanager_loader",
    ]
    # ?Œì¼ ?„ë³´ (src ë£¨íŠ¸ ê¸°ì? ?ë? ê²½ë¡œ)
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
    pipeline_loader.setup_pipeline ë¥?ì§€??ë¡œë“œ?˜ì—¬ ?¸ì¶œ.
    - ?¤ì„?¤í˜?´ìŠ¤ import ?¤íŒ¨ ??src ?˜ìœ„???Œì¼??ì§ì ‘ ë¡œë“œ?˜ëŠ” ?´ë°±???œë„?©ë‹ˆ??
    - ?¤íŒ¨ ??RuntimeError ë°œìƒ.
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
