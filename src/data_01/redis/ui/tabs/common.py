# 怨듯넻 ?좏떥: RESP ?대갚, timescale get_client ?숈쟻 濡쒕뱶, ?뚯떛 ?좏떥, SCAN 湲곕컲 ?덉쟾 移댁슫????# ?쒓? 二쇱꽍?쇰줈 ?숈옉 ?ㅻ챸 ?ы븿

from __future__ import annotations
import importlib.util
import logging
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------
# timescale_redis.get_client ?숈쟻 濡쒕뱶 (?덉쑝硫??곗꽑 ?ъ슜)
# ---------------------------
def _load_timescale_module() -> Optional[object]:
    """
    ?덊룷 ?대???src/data_01/timescale/timescale_redis.py瑜??쒕룄 濡쒕뱶?섍퀬
    get_client ?⑥닔媛 ?덉쑝硫?紐⑤뱢??諛섑솚?⑸땲?? ?ㅽ뙣?대룄 None 諛섑솚.
    """
    try:
        base = Path(__file__).resolve()
        p = base
        # src/data_01 源뚯? ?щ씪媛???timescale ?붾젆?좊━ 李얘린
        while p and p.name != "data_01":
            p = p.parent
        if not p:
            return None
        candidate = p / "timescale" / "timescale_redis.py"
        if not candidate.exists():
            return None
        spec = importlib.util.spec_from_file_location("timescale_redis_local", str(candidate))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            return mod
    except Exception as exc:
        logger.debug("[common] timescale 紐⑤뱢 濡쒕뱶 ?ㅽ뙣: %s", exc, exc_info=True)
    return None

_timescale_mod = _load_timescale_module()
_get_client_fn = None
if _timescale_mod is not None:
    try:
        _get_client_fn = getattr(_timescale_mod, "get_client", None)
    except Exception:
        _get_client_fn = None

def get_client_if_available():
    """timescale 紐⑤뱢??get_client()瑜??덉쟾???몄텧?댁꽌 ?대씪?댁뼵?몃? ?살뒿?덈떎. ?ㅽ뙣 ??None."""
    try:
        if _get_client_fn:
            return _get_client_fn()
    except Exception as exc:
        logger.debug("[common] get_client ?몄텧 ?ㅽ뙣: %s", exc, exc_info=True)
    return None

# ---------------------------
# RESP ?뚯폆 ?대갚 援ы쁽 (redis-py媛 ?놁쓣 ?뚮룄 ?숈옉 媛?ν븯寃?
# ---------------------------
def _resp_send(host: str, port: int, password: Optional[str], timeout: float, *args: Any) -> bytes:
    """
    媛꾨떒??RESP 吏곸넚 ?ы띁.
    - AUTH 吏??    - 紐낅졊 ?꾩넚 ???대━?ㅽ떛?쇰줈 ?묐떟 醫낅즺 ?먮떒
    ?ㅽ뙣 ??鍮?bytes 諛섑솚(?몄텧?먯뿉???덉쇅/鍮덇컪 泥섎━)
    """
    try:
        parts = [str(a) for a in args]
        lines = [f"*{len(parts)}\r\n"]
        for p in parts:
            b = p.encode("utf-8")
            lines.append(f"${len(b)}\r\n{p}\r\n")
        cmd = "".join(lines).encode("utf-8")
        with socket.create_connection((host, port), timeout=timeout) as sock:
            if password:
                pw_bytes = password.encode("utf-8")
                auth_cmd = (
                    b"*2\r\n$4\r\nAUTH\r\n$"
                    + str(len(pw_bytes)).encode()
                    + b"\r\n"
                    + pw_bytes
                    + b"\r\n"
                )
                sock.sendall(auth_cmd)
                resp = sock.recv(64).decode(errors="replace").strip()
                if not resp.startswith("+OK"):
                    raise ConnectionError(f"Redis AUTH ?ㅽ뙣: {resp}")
            sock.sendall(cmd)
            sock.settimeout(timeout)
            data = b""
            try:
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                    if _resp_complete(data):
                        break
            except socket.timeout:
                # ??꾩븘????遺遺??묐떟?대씪??諛섑솚
                pass
            return data
    except Exception as exc:
        logger.debug("[common] RESP ?꾩넚 ?ㅽ뙣: %s", exc, exc_info=True)
        return b""

def _resp_complete(data: bytes) -> bool:
    """媛꾨떒??RESP ?묐떟 ?꾨즺 ?대━?ㅽ떛"""
    if not data:
        return False
    try:
        first = chr(data[0])
    except Exception:
        return False
    if first in ("+", "-", ":"):
        return b"\r\n" in data
    if first in ("$", "*"):
        return data.endswith(b"\r\n")
    return True

# ---------------------------
# RESP ?뚯떛 ?좏떥
# ---------------------------
def _parse_integer(data: bytes) -> Optional[int]:
    try:
        text = data.decode(errors="replace").strip()
        if text.startswith(":"):
            return int(text[1:])
    except Exception:
        pass
    return None

def _parse_bulk_array(data: bytes) -> List[str]:
    items: List[str] = []
    try:
        text = data.decode(errors="replace")
        lines = text.split("\r\n")
        if not lines:
            return items
        # ?⑥닚 ?뚯떛: 泥?以?"*N" ?뺤씤 ??"$len" ?ㅼ쓬 以??ы븿 諛⑹떇 泥섎━
        if lines[0].startswith("*"):
            i = 1
            while i < len(lines):
                line = lines[i]
                if line.startswith("$"):
                    i += 1
                    if i < len(lines):
                        items.append(lines[i])
                elif line.startswith(":"):
                    items.append(line[1:])
                else:
                    # 湲고???臾댁떆
                    pass
                i += 1
    except Exception as exc:
        logger.debug("[common] 諛곗뿴 ?뚯떛 ?ㅽ뙣: %s", exc, exc_info=True)
    return items

def _parse_info(data: bytes) -> Dict[str, str]:
    result: Dict[str, str] = {}
    try:
        text = data.decode(errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                result[k.strip()] = v.strip()
    except Exception as exc:
        logger.debug("[common] INFO ?뚯떛 ?ㅽ뙣: %s", exc, exc_info=True)
    return result

# ---------------------------
# ?몄쓽 ?⑥닔: ?대씪?댁뼵???곗꽑, ?대갚 RESP ?ъ슜
# ---------------------------
def keys(host: str, port: int, password: Optional[str], timeout: float, pattern: str, client=None) -> List[str]:
    if client:
        try:
            res = client.keys(pattern) or []
            return [k.decode() if isinstance(k, (bytes, bytearray)) else str(k) for k in res]
        except Exception:
            pass
    data = _resp_send(host, port, password, timeout, "KEYS", pattern)
    return _parse_bulk_array(data)

def info_section(host: str, port: int, password: Optional[str], timeout: float, section: str, client=None) -> Dict[str, str]:
    if client:
        try:
            info = client.info(section=section)
            return {k: str(v) for k, v in (info or {}).items()}
        except Exception:
            pass
    data = _resp_send(host, port, password, timeout, "INFO", section)
    return _parse_info(data)

def zcard(host: str, port: int, password: Optional[str], timeout: float, key: str, client=None) -> Optional[int]:
    if client:
        try:
            return int(client.zcard(key) or 0)
        except Exception:
            pass
    data = _resp_send(host, port, password, timeout, "ZCARD", key)
    return _parse_integer(data)

def zrevrange_withscores(host: str, port: int, password: Optional[str], timeout: float, key: str, start: int, stop: int, client=None) -> List[Tuple[str, str]]:
    """
    諛섑솚: [(member, score), ...] (score? str)
    """
    if client:
        try:
            items = client.zrevrange(key, start, stop, withscores=True) or []
            out = []
            for member, score in items:
                m = member.decode() if isinstance(member, (bytes, bytearray)) else str(member)
                out.append((m, str(score)))
            return out
        except Exception:
            pass
    data = _resp_send(host, port, password, timeout, "ZREVRANGE", key, str(start), str(stop), "WITHSCORES")
    flat = _parse_bulk_array(data)
    out: List[Tuple[str, str]] = []
    i = 0
    while i + 1 < len(flat):
        out.append((flat[i], flat[i + 1]))
        i += 2
    return out

def pubsub_channels(host: str, port: int, password: Optional[str], timeout: float, pattern: str, client=None) -> List[str]:
    if client:
        try:
            return client.execute_command("PUBSUB", "CHANNELS", pattern) or []
        except Exception:
            pass
    data = _resp_send(host, port, password, timeout, "PUBSUB", "CHANNELS", pattern)
    return _parse_bulk_array(data)

def pubsub_numsub(host: str, port: int, password: Optional[str], timeout: float, channel: str, client=None) -> str:
    if client:
        try:
            arr = client.execute_command("PUBSUB", "NUMSUB", channel) or []
            if len(arr) > 1:
                val = arr[1]
                return str(val)
            return "0"
        except Exception:
            pass
    data = _resp_send(host, port, password, timeout, "PUBSUB", "NUMSUB", channel)
    flat = _parse_bulk_array(data)
    return flat[1] if len(flat) > 1 else "0"

def ttl(host: str, port: int, password: Optional[str], timeout: float, key: str, client=None) -> Optional[int]:
    if client:
        try:
            t = client.ttl(key)
            return int(t) if t is not None else None
        except Exception:
            pass
    data = _resp_send(host, port, password, timeout, "TTL", key)
    return _parse_integer(data)

def delete(host: str, port: int, password: Optional[str], timeout: float, *keys_to_del: str, client=None) -> bool:
    if client:
        try:
            client.delete(*keys_to_del)
            return True
        except Exception:
            pass
    _resp_send(host, port, password, timeout, "DEL", *keys_to_del)
    return True

def cluster_nodes(host: str, port: int, password: Optional[str], timeout: float, client=None) -> str:
    """?먮Ц ?띿뒪??諛섑솚(?뚯떛? ?몄텧?먯뿉???섑뻾)"""
    if client:
        try:
            raw = client.execute_command("CLUSTER", "NODES")
            if isinstance(raw, (bytes, bytearray)):
                return raw.decode(errors="replace")
            return str(raw)
        except Exception:
            pass
    data = _resp_send(host, port, password, timeout, "CLUSTER", "NODES")
    return data.decode(errors="replace") if data else ""

def sentinel_masters(host: str, port: int, password: Optional[str], timeout: float, client=None) -> List[str]:
    if client:
        try:
            arr = client.execute_command("SENTINEL", "masters") or []
            return [a.decode() if isinstance(a, (bytes,bytearray)) else str(a) for a in arr]
        except Exception:
            pass
    data = _resp_send(host, port, password, timeout, "SENTINEL", "masters")
    return _parse_bulk_array(data)

def sentinel_sentinels(host: str, port: int, password: Optional[str], timeout: float, master_name: str, client=None) -> List[str]:
    if client:
        try:
            arr = client.execute_command("SENTINEL", "sentinels", master_name) or []
            return [a.decode() if isinstance(a, (bytes,bytearray)) else str(a) for a in arr]
        except Exception:
            pass
    data = _resp_send(host, port, password, timeout, "SENTINEL", "sentinels", master_name)
    return _parse_bulk_array(data)

# ---------------------------
# ?덉쟾??SCAN 湲곕컲 ??移댁슫??# ---------------------------
def scan_count(host: str, port: int, password: Optional[str], timeout: float, pattern: str, client=None, max_scan: int = 200000) -> int:
    """
    SCAN 湲곕컲?쇰줈 ?⑦꽩??留ㅼ묶?섎뒗 ??媛쒖닔(洹쇱궗)瑜??덉쟾?섍쾶 ?됰땲??
    - client媛 redis-py ?몄뒪?댁뒪硫?scan_iter ?ъ슜 (鍮꾩감??.
    - max_scan: ?덉쟾?μ튂(理쒕? ?ㅼ틪 ???? ??留ㅼ슦 ??DB?먯꽌 怨쇰룄???ㅼ틪 諛⑹?.
    - ?대갚: client 誘몄〈???뱀? scan_iter ?ㅽ뙣 ??湲곗〈 keys() 寃곌낵??湲몄씠瑜?諛섑솚.
    """
    try:
        if client:
            # redis-py ?대씪?댁뼵?몃씪硫?scan_iter ?쒕룄
            try:
                cnt = 0
                for _ in client.scan_iter(match=pattern, count=1000):
                    cnt += 1
                    if cnt >= max_scan:
                        break
                return cnt
            except Exception:
                # scan_iter ?ъ슜 遺덇?硫??대갚?쇰줈 ?섏뼱媛?                logger.debug("[common] client.scan_iter ?ъ슜 遺덇?, ?대갚?쇰줈 keys ?ъ슜")
        # ?대갚: 湲곗〈 keys() ?ъ슜 (?뺤긽 ?섍꼍?먯꽌?????숈옉?섏?留??댁쁺?먯꽌??SCAN 沅뚯옣)
        keys_list = keys(host, port, password, timeout, pattern, client=client)
        return len(keys_list)
    except Exception as exc:
        logger.debug("[common] scan_count ?ㅽ뙣: %s", exc, exc_info=True)
        return 0
