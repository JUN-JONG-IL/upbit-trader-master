"""
[Purpose]
- WebSocket 湲곕컲 ?ㅼ떆媛??쒖옣 ?곗씠???섏쭛 紐⑤뱢

[Responsibilities]
- ?낅퉬??WebSocket ?곌껐 諛??곗씠???ㅽ듃由щ컢
- ?ㅼ떆媛?ticker/orderbook/trade ?곗씠???섏떊

[Usage]
    # 沅뚯옣: ?щ낵/?⑥닔???꾩슂????濡쒕뱶?⑸땲??
    from src.data_01.collectors import UpbitWebSocket
    from src.data_01.collectors import subscribe_ticker
"""
from __future__ import annotations

import importlib
import types
from typing import Any

__all__ = ["UpbitWebSocket", "subscribe_ticker"]

# ?대? 罹먯떆(泥??묎렐??紐⑤뱢???ㅼ젣濡?濡쒕뱶)
_loaded_mod: types.ModuleType | None = None

def _load_impl_module() -> types.ModuleType:
    global _loaded_mod
    if _loaded_mod is None:
        try:
            # ?ㅼ젣 援ы쁽 紐⑤뱢 ?대쫫/?꾩튂瑜??⑦궎吏 援ъ“??留욎떠 諛붽퓭二쇱꽭??
            # ?꾩옱 ?뚯씪??src/data_01/collectors/__init__.py??占쏙옙移섑븳?ㅺ퀬 媛?뺥븯硫?
            # 媛숈? ?⑦궎吏紐낆쓽 upbit_websocket 紐⑤뱢??濡쒕뱶?⑸땲??
            _loaded_mod = importlib.import_module(".upbit_websocket", package=__package__)
        except Exception as exc:
            # 移쒖젅???덉쇅 硫붿떆吏濡??붾쾭源낆쓣 ?뺤뒿?덈떎.
            raise ImportError(
                "Failed to import collectors.upbit_websocket implementation. "
                "Ensure dependencies (websockets, asyncpg, redis) are installed and "
                "that src/data_01/collectors/upbit_websocket.py exists. "
                f"Original error: {exc}"
            ) from exc
    return _loaded_mod

def __getattr__(name: str) -> Any:
    """
    Lazy-load attributes from the real implementation module.
    Allows: from src.data_01.collectors import UpbitWebSocket
    """
    mod = _load_impl_module()
    try:
        return getattr(mod, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

def __dir__() -> list[str]:
    # 湲곕낯 ?щ낵 + 援ы쁽 紐⑤뱢??怨듦컻 ?щ낵 ?⑹튇 由ъ뒪??諛섑솚
    mod = None
    try:
        mod = _load_impl_module()
    except Exception:
        pass
    names = list(globals().keys())
    if mod is not None:
        names.extend(getattr(mod, "__all__", [n for n in dir(mod) if not n.startswith("_")]))
    return sorted(set(names))
