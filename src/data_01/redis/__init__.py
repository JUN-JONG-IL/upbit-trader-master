# -*- coding: utf-8 -*-
"""
redis ?⑦궎吏 濡쒖뺄 health_check 濡쒕뜑

紐⑹쟻:
- ?꾨줈?앺듃 ?댁쓽 濡쒖뺄 援ы쁽(src/data_01/redis/health_check.py ?????곗꽑 濡쒕뱶?섍퀬,
  ?놁쓣 寃쎌슦 ?덉쟾???ㅽ뀅???쒓났?섏뿬 ?덉쇅 ?몄텧??諛⑹??⑸땲??
- 濡쒓퉭? 'shim'?대씪???좊ℓ???쒓린瑜??ъ슜?섏? ?딄퀬 紐낇솗??紐⑤뱢/?뚯씪 寃쎈줈? ?ㅻ쪟瑜??④퉩?덈떎.
"""
from __future__ import annotations

import importlib.util
import importlib
import logging
import os
from pathlib import Path
from typing import Dict, Optional

_log = logging.getLogger(__name__)

STATUS_GREEN = "green"
STATUS_RED = "red"
STATUS_GRAY = "gray"

# 湲곕낯 ?ㅽ뀅 援ы쁽 (濡쒖뺄 援ы쁽 ?놁쓣 ???ъ슜)
def _stub_check_redis_connection() -> str:
    # ?ㅼ젙???놁쓣 ???뚯깋(gray) 諛섑솚 ??UI?먯꽌 '誘몄꽕???쇰줈 蹂댁뿬二쇨린 ?꾪븿
    return STATUS_GRAY

def _stub_health_check() -> Dict[str, Optional[str]]:
    return {
        "status": STATUS_GRAY,
        "reason": "redis.health_check not available in project or site-packages",
        "host": None,
        "port": None,
        "impl": "stub",
    }

# 珥덇린 ?ъ씤?곕뒗 ?ㅽ뀅?쇰줈 ?ㅼ젙
_check_fn = _stub_check_redis_connection
_health_fn = _stub_health_check
_impl_name = "stub"

def _find_repo_root(start: Optional[str] = None) -> str:
    """
    ?꾩옱 ?뚯씪 ?꾩튂瑜?湲곗??쇰줈 媛?ν븳 repo 猷⑦듃瑜??먯깋?쒕떎.
    - 'src' ?대뜑瑜?諛쒓껄?섎㈃ 洹??곸쐞 ?붾젆?좊━瑜?repo root濡?媛꾩＜
    - '.git' ?붾젆?좊━媛 諛쒓껄?섎㈃ 洹??꾩튂瑜??ъ슜
    - ?ㅽ뙣 ??start ?먮뒗 cwd 諛섑솚
    """
    try:
        p = Path(start or __file__).resolve()
        # climb up searching for 'src' or '.git'
        for parent in [p] + list(p.parents):
            if (parent / "src").is_dir() or (parent / ".git").exists():
                return str(parent)
        # fallback: two levels up if we are under src/...
        for parent in p.parents:
            if parent.name == "src":
                return str(parent.parent)
    except Exception:
        pass
    return str(Path(start or ".").resolve())

def _try_load_module_from_file(path: str, alias: str):
    """吏???뚯씪?먯꽌 紐⑤뱢??濡쒕뱶?섏뿬 諛섑솚; ?ㅿ옙占쏀븯硫?None."""
    try:
        spec = importlib.util.spec_from_file_location(alias, path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    except Exception as e:
        _log.debug("[redis] file-load failed for %s: %s", path, e)
    return None

# ?꾨낫 寃쎈줈(?곗꽑?쒖쐞) ?먯깋 諛?濡쒕뱶 ?쒕룄
try:
    repo_root = _find_repo_root()
    here = os.path.dirname(__file__)  # ?⑦궎吏 ?붾젆?좊━ (?? .../src/data_01/redis)
    candidates = []

    # 1) same package sibling file (媛???곗꽑)
    candidates.append(os.path.join(here, "health_check.py"))

    # 2) common project locations relative to repo_root
    #    ?꾨줈?앺듃 援ъ“???곕씪 ?щ윭 ?꾨낫瑜??쒕룄 (src/data_01/redis, src/redis, redis/)
    candidates.extend([
        os.path.join(repo_root, "src", "data_01", "redis", "health_check.py"),
        os.path.join(repo_root, "src", "data_01", "redis", "health_check.py"),  # duplicate safe
        os.path.join(repo_root, "src", "redis", "health_check.py"),
        os.path.join(repo_root, "redis", "health_check.py"),
        os.path.join(repo_root, "src", "data_01", "redis", "health_check.py"),
    ])

    # 3) site-packages style import attempt: try to import well-known package names
    import_attempts = ["src.data_01.redis.health_check", "data_01.redis.health_check", "redis.health_check"]

    loaded = False
    # 癒쇱? ?쒕룄: ?뚯씪 ?덈꺼 ?꾨낫??
    for cand in candidates:
        try:
            if cand and os.path.isfile(cand):
                mod = _try_load_module_from_file(cand, alias=f"project_redis_health_check_{os.path.basename(cand)}")
                if mod is not None:
                    # discover functions
                    if hasattr(mod, "check_redis_connection"):
                        _check_fn = getattr(mod, "check_redis_connection")
                    if hasattr(mod, "health_check"):
                        _health_fn = getattr(mod, "health_check")
                    _impl_name = f"project:{os.path.relpath(cand, repo_root)}"
                    _log.debug("[redis] loaded local health_check from %s", cand)
                    loaded = True
                    break
        except Exception as e:
            _log.debug("[redis] failed loading candidate file %s: %s", cand, e)

    # ?뚯씪 ?꾨낫?먯꽌 紐?李얠븯?쇰㈃ 紐⑤뱢 ?꾪룷???쒕룄
    if not loaded:
        for modname in import_attempts:
            try:
                mod = importlib.import_module(modname)
                if mod:
                    if hasattr(mod, "check_redis_connection"):
                        _check_fn = getattr(mod, "check_redis_connection")
                    if hasattr(mod, "health_check"):
                        _health_fn = getattr(mod, "health_check")
                    _impl_name = f"module:{modname}"
                    _log.debug("[redis] imported health_check module %s -> %s", modname, getattr(mod, "__file__", None))
                    loaded = True
                    break
            except Exception as e:
                _log.debug("[redis] import attempt %s failed: %s", modname, e)

    if not loaded:
        _log.debug("[redis] no local health_check implementation found; using stub")
except Exception as e:
    _log.debug("[redis] discovery failed: %s", e)

# ?몃????몄텧???덉쟾???⑥닔??
def check_redis_connection() -> str:
    """'green'|'red'|'gray' 以??섎굹 諛섑솚. ?덉쇅 諛쒖깮 ??'red'濡?泥섎━."""
    try:
        return _check_fn()
    except Exception as e:
        _log.debug("[redis] check_redis_connection exception: %s", e)
        return STATUS_RED

def health_check() -> Dict[str, Optional[str]]:
    """援ъ“?붾맂 health-check 寃곌낵瑜?諛섑솚?쒕떎. impl ?꾨뱶瑜?蹂닿컯?쒕떎."""
    try:
        res = _health_fn()
        if isinstance(res, dict):
            res.setdefault("impl", _impl_name)
            return res
        return {"status": STATUS_GRAY, "reason": "invalid health_check return", "host": None, "port": None, "impl": _impl_name}
    except Exception as e:
        _log.debug("[redis] health_check exception: %s", e)
        return {"status": STATUS_RED, "reason": "exception during health_check", "host": None, "port": None, "impl": _impl_name}

__all__ = ["check_redis_connection", "health_check", "STATUS_GREEN", "STATUS_RED", "STATUS_GRAY"]
