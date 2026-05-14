# -*- coding: utf-8 -*-
"""
모듈 로더 - import 헬퍼 함수들
- try_import_names: 여러 이름으로 import 시도
- load_module_from_file_abs: 파일 경로로 직접 로드
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import traceback
from types import ModuleType
from typing import Iterable, List, Optional, Tuple

from .logger import create_safe_logger, mark_module_imported

log = create_safe_logger("module_loader")


def get_src_root() -> str:
    """src 루트 경로 반환"""
    src_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not os.path.isdir(os.path.join(src_root, "app")):
        cur = os.path.abspath(__file__)
        for _ in range(6):
            cur = os.path.dirname(cur)
            candidate_src = os.path.join(cur, "src")
            if os.path.isdir(os.path.join(candidate_src, "app")):
                src_root = candidate_src
                break
    return os.path.abspath(src_root)


SRC_ROOT = get_src_root()


def ensure_src_root_on_path() -> str:
    """src 루트를 sys.path 맨 앞에 추가"""
    if SRC_ROOT not in sys.path:
        sys.path.insert(0, SRC_ROOT)
        log.debug("[module_loader] Inserted src root to sys.path: %s", SRC_ROOT)
    importlib.invalidate_caches()
    return SRC_ROOT


def module_has_source_under_src(import_name: str) -> bool:
    """모듈이 src 하위에 소스 파일로 존재하는지 확인"""
    try:
        if not import_name or not isinstance(import_name, str):
            return False
        parts = import_name.split(".")
        candidate1 = os.path.join(SRC_ROOT, *parts) + ".py"
        if os.path.isfile(candidate1):
            return True
        candidate2 = os.path.join(SRC_ROOT, *parts, "__init__.py")
        if os.path.isfile(candidate2):
            return True
        if parts and parts[0] == "src":
            parts2 = parts[1:]
            candidate3 = os.path.join(SRC_ROOT, *parts2) + ".py"
            if os.path.isfile(candidate3):
                return True
            candidate4 = os.path.join(SRC_ROOT, *parts2, "__init__.py")
            if os.path.isfile(candidate4):
                return True
    except Exception:
        pass
    return False


def load_module_from_file_abs(path: str, module_name: str) -> Optional[ModuleType]:
    """파일 경로로 모듈 로드"""
    try:
        if not path or not os.path.isfile(path):
            return None
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        log.debug("[module_loader] file-loaded module %s from %s", module_name, path)
        return mod
    except Exception:
        try:
            if module_name in sys.modules:
                del sys.modules[module_name]
        except Exception:
            pass
        log.debug("[module_loader] file load failed for %s: %s", path, traceback.format_exc())
        return None


def try_import_names(names: Iterable[str]) -> Tuple[Optional[object], List[Tuple[str, str]]]:
    """여러 모듈명으로 import 시도 (우선순위: src 하위 소스 파일)"""
    attempts: List[Tuple[str, str]] = []
    if not names:
        return None, attempts
    
    tried = set()
    candidates = list(names)
    prioritized: List[str] = []
    others: List[str] = []
    
    for nm in candidates:
        if not nm or nm in tried:
            continue
        if module_has_source_under_src(nm):
            prioritized.append(nm)
        else:
            others.append(nm)
        tried.add(nm)
    
    ordered = prioritized + others
    for nm in ordered:
        try:
            importlib.invalidate_caches()
            mod = importlib.import_module(nm)
            
            # 중복 로그 방지
            if mark_module_imported(nm):
                log.debug("[module_loader] imported module %s -> %s", nm, getattr(mod, "__file__", None))
            return mod, attempts
        except Exception as e:
            attempts.append((nm, f"{type(e).__name__}: {e}"))
            log.debug("[module_loader] import %s failed: %s", nm, f"{type(e).__name__}: {e}")
            continue
    
    return None, attempts


def import_module_with_file_fallback(import_name: str, file_relpaths: Iterable[str]) -> Optional[ModuleType]:
    """import 실패 시 파일 경로로 폴백"""
    try:
        importlib.invalidate_caches()
        mod = importlib.import_module(import_name)
        log.debug("[module_loader] import success: %s -> %s", import_name, getattr(mod, "__file__", None))
        return mod
    except Exception as e:
        log.debug("[module_loader] import %s failed: %s", import_name, f"{type(e).__name__}: {e}")
        for rel in file_relpaths:
            try:
                if not rel:
                    continue
                abs_path = rel if os.path.isabs(rel) else os.path.join(SRC_ROOT, rel)
                if not os.path.isfile(abs_path):
                    log.debug("[module_loader] file candidate missing: %s", abs_path)
                    continue
                mod = load_module_from_file_abs(abs_path, import_name)
                if mod is not None:
                    log.debug("[module_loader] file fallback loaded %s from %s", import_name, abs_path)
                    return mod
            except Exception:
                log.debug("[module_loader] file fallback attempt failed for %s: %s", rel, traceback.format_exc())
        return None


def try_load_from_files(candidates: Iterable[str], alias_prefix: str = "bootstrap_fallback") -> Tuple[Optional[object], List[Tuple[str, str]]]:
    """파일 경로들로 모듈 로드 시도"""
    attempts: List[Tuple[str, str]] = []
    for p_str in candidates:
        try:
            if not p_str:
                continue
            abs_path = p_str if os.path.isabs(p_str) else os.path.join(SRC_ROOT, p_str)
            if not os.path.isfile(abs_path):
                attempts.append((abs_path, "missing"))
                continue
            mod = load_module_from_file_abs(abs_path, f"{alias_prefix}_{os.path.basename(abs_path)}")
            if mod:
                return mod, attempts
            else:
                attempts.append((abs_path, "load_failed"))
        except Exception as e:
            attempts.append((p_str, f"{type(e).__name__}: {e}"))
            log.debug("[module_loader] file fallback exception for %s: %s", p_str, traceback.format_exc())
    return None, attempts