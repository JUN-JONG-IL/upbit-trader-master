# -*- coding: utf-8 -*-
"""
Loaders 패키지 초기화 (지연 로드, 파일-레벨 폴백, shim 제거)

설명:
- create_data_manager / setup_pipeline 함수를 호출할 때 내부에서 실제 구현 모듈을 동적으로 로드합니다.
- 네임스페이스 import 실패 시 src 루트 밑의 파일을 직접 로드하는 파일-레벨 폴백을 시도합니다.
- 파일로 로드한 모듈은 가능한 한 정식 패키지 네임스페이스(예: app.loaders.datamanager_loader)로
  sys.modules에 등록하여 'shim' 문제를 제거합니다.
- shim(임시 패키지/파일) 생성이나 파일 이동은 절대 하지 않습니다.
- 실패 시 가능한 모든 시도 결과(모듈 후보, 파일 후보, traceback)를 상세히 로깅합니다.
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
    static에 log 객체가 있으면 사용, 없으면 print로 폴백.
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
    start_path에서 위로 올라가며 'src' 폴더를 찾는다. 못 찾으면 start_path 상위 3단계를 반환.
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
    src_root 밑의 file_path로부터 모듈 네임스페이스(도트 표기)를 생성한다.
    예: /.../src/app/loaders/datamanager_loader.py -> 'app.loaders.datamanager_loader'
    반환 불가능하면 None.
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
    파일 경로에서 모듈을 안전하게 로드 (importlib.util).
    - 가능한 경우 정식 패키지 네임스페이스로 sys.modules에 등록하여 shim 생성을 방지.
    - alias: 임시 alias (예: 'file_loaded__...') — 내부 참조용.
    - src_root: src 루트 경로를 주면, src_root 하위라면 패키지 네임스페이스로 등록을 시도.
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
    - candidates: 네임스페이스 후보(importlib.import_module로 시도)
    - file_candidates: 파일 경로 후보(프로젝트 src 루트 기준 상대 경로 또는 절대경로)
    - desc: 로깅용 설명 ('datamanager_loader' 또는 'pipeline_loader' 등)
    반환: (module_or_None, attempts_list)
    attempts_list: [(kind, name, result_str), ...] where kind='import'|'file'
    """
    attempts: List[Tuple[str, str, str]] = []

    # 1) namespace imports (정식 패키지 경로 우선)
    for nm in candidates:
        try:
            mod = importlib.import_module(nm)
            attempts.append(("import", nm, "ok"))
            _log_static(static, "debug", "[loaders] %s import success: %s -> %s", desc, nm, getattr(mod, "__file__", None))
            return mod, attempts
        except Exception as e:
            attempts.append(("import", nm, f"{type(e).__name__}: {e}"))
            _log_static(static, "debug", "[loaders] %s import failed: %s -> %s", desc, nm, f"{type(e).__name__}: {e}")

    # 2) file-level load from src root (정석적 우선)
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
    datamanager_loader.create_data_manager 를 지연 로드하여 호출.
    - 성공: DataManager 인스턴스 반환
    - 실패: RuntimeError 발생 (호출자에서 catch 하여 처리)
    """
    desc = "datamanager_loader"
    # 네임스페이스 후보들
    ns_candidates = [
        "app.loaders.datamanager_loader",
        "app.loaders.datamanager_loader",  # duplicate safe
        "data_01.core.data_manager",
        "src.app.loaders.datamanager_loader",
        "app.datamanager_loader",
    ]
    # 파일 후보 (src 루트 기준 상대 경로)
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
    pipeline_loader.setup_pipeline 를 지연 로드하여 호출.
    - 네임스페이스 import 실패 시 src 하위의 파일을 직접 로드하는 폴백을 시도합니다.
    - 실패 시 RuntimeError 발생.
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