"""
[Purpose]
- WebSocket 기반 실시간 시장 데이터 수집 모듈

[Responsibilities]
- 업비트 WebSocket 연결 및 데이터 스트리밍
- 실시간 ticker/orderbook/trade 데이터 수신

[Usage]
    # 권장: 심볼/함수는 필요할 때 로드됩니다.
    from src.02_data.collectors import UpbitWebSocket
    from src.02_data.collectors import subscribe_ticker
"""
from __future__ import annotations

import importlib
import types
from typing import Any

__all__ = ["UpbitWebSocket", "subscribe_ticker"]

# 내부 캐시(첫 접근시 모듈을 실제로 로드)
_loaded_mod: types.ModuleType | None = None

def _load_impl_module() -> types.ModuleType:
    global _loaded_mod
    if _loaded_mod is None:
        try:
            # 실제 구현 모듈 이름/위치를 패키지 구조에 맞춰 바꿔주세요.
            # 현재 파일이 src/02_data/collectors/__init__.py에 ��치한다고 가정하면
            # 같은 패키지명의 upbit_websocket 모듈을 로드합니다.
            _loaded_mod = importlib.import_module(".upbit_websocket", package=__package__)
        except Exception as exc:
            # 친절한 예외 메시지로 디버깅을 돕습니다.
            raise ImportError(
                "Failed to import collectors.upbit_websocket implementation. "
                "Ensure dependencies (websockets, asyncpg, redis) are installed and "
                "that src/02_data/collectors/upbit_websocket.py exists. "
                f"Original error: {exc}"
            ) from exc
    return _loaded_mod

def __getattr__(name: str) -> Any:
    """
    Lazy-load attributes from the real implementation module.
    Allows: from src.02_data.collectors import UpbitWebSocket
    """
    mod = _load_impl_module()
    try:
        return getattr(mod, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

def __dir__() -> list[str]:
    # 기본 심볼 + 구현 모듈의 공개 심볼 합친 리스트 반환
    mod = None
    try:
        mod = _load_impl_module()
    except Exception:
        pass
    names = list(globals().keys())
    if mod is not None:
        names.extend(getattr(mod, "__all__", [n for n in dir(mod) if not n.startswith("_")]))
    return sorted(set(names))