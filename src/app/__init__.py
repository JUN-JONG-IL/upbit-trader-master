# 레포 루트에 위치시킬 패키지 shim
# 목적: 레포의 src/app 패키지를 "app" 네임스페이스로 노출시켜
# import app.* 형태가 동작하도록 합니다.
# 이 파일은 매우 작고 안전한 shim이며, 문제 해결 후 유지해도 무방합니다.

from __future__ import annotations

import os
import sys
from pathlib import Path

# 로깅은 선택사항 (안정성 위해 예외 발생 시 무시)
try:
    import logging
    _log = logging.getLogger("app.shim")
except Exception:
    _log = None

try:
    _repo_root = Path(__file__).parent.resolve()
    _src_app = _repo_root / "src" / "app"
    _src = _repo_root / "src"

    # 우선 순위: src/app 디렉토리를 package __path__ 에 추가
    if _src_app.exists() and _src_app.is_dir():
        sp = str(_src_app)
        if sp not in __path__:
            __path__.insert(0, sp)
            if _log:
                _log.debug("app shim: inserted src/app to __path__: %s", sp)
    else:
        # fallback: src 전체를 sys.path에 추가 (다른 import 경로와의 호환성 확보)
        s = str(_src)
        if _src.exists() and s not in sys.path:
            sys.path.insert(0, s)
            if _log:
                _log.debug("app shim: inserted src to sys.path: %s", s)
except Exception:
    # 절대 실패해선 안되므로 예외는 조용히 무시
    try:
        if _log:
            _log.exception("app shim: failed to configure path")
    except Exception:
        pass

# 공개 API 표기 (필요시 확장)
__all__ = []