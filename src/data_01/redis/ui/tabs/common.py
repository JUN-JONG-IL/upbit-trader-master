# ê³µí†µ ? í‹¸: RESP ?´ë°±, timescale get_client ?™ì  ë¡œë“œ, ?Œì‹± ? í‹¸, SCAN ê¸°ë°˜ ?ˆì „ ì¹´ìš´????# ?œê? ì£¼ì„?¼ë¡œ ?™ì‘ ?¤ëª… ?¬í•¨

from __future__ import annotations
import importlib.util
import logging
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------
# timescale_redis.get_client ?™ì  ë¡œë“œ (?ˆìœ¼ë©??°ì„  ?¬ìš©)
# ---------------------------
def _load_timescale_module() -> Optional[object]:
    """
    ?ˆí¬ ?´ë???src/data_01/timescale/timescale_redis.pyë¥??œë„ ë¡œë“œ?˜ê³ 
    get_client ?¨ìˆ˜ê°€ ?ˆìœ¼ë©?ëª¨ë“ˆ??ë°˜í™˜?©ë‹ˆ?? ?¤íŒ¨?´ë„ None ë°˜í™˜.
    """
    try:
        base = Path(__file__).resolve()
        p = base
        # src/data_01 ê¹Œì? ?¬ë¼ê°???timescale ?”ë ‰? ë¦¬ ì°¾ê¸°
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
        logger.debug("[common] timescale ëª¨ë“ˆ ë¡œë“œ ?¤íŒ¨: %s", exc, exc_info=True)
    return None

_timescale_mod = _load_timescale_module()
_get_client_fn = None
if _timescale_mod is not None:
    try:
        _get_client_fn = getattr(_timescale_mod, "get_client", None)
    except Exception:
        _get_client_fn = None

def get_client_if_available():
    """timescale ëª¨ë“ˆ??get_client()ë¥??ˆì „???¸ì¶œ?´ì„œ ?´ë¼?´ì–¸?¸ë? ?»ìŠµ?ˆë‹¤. ?¤íŒ¨ ??None."""
    try:
        if _get_client_fn:
            return _get_client_fn()
    except Exception as exc:
        logger.debug("[common] get_client ?¸ì¶œ ?¤íŒ¨: %s", exc, exc_info=True)
    return None

# ---------------------------
# RESP ?Œì¼“ ?´ë°± êµ¬í˜„ (redis-pyê°€ ?†ì„ ?Œë„ ?™ì‘ ê°€?¥í•˜ê²?
# ---------------------------
def _resp_send(host: str, port: int, password: Optional[str], timeout: float, *args: Any) -> bytes:
    """
    ê°„ë‹¨??RESP ì§ì†¡ ?¬í¼.
    - AUTH ì§€??    - ëª…ë ¹ ?„ì†¡ ???´ë¦¬?¤í‹±?¼ë¡œ ?‘ë‹µ ì¢…ë£Œ ?ë‹¨
    ?¤íŒ¨ ??ë¹?bytes ë°˜í™˜(?¸ì¶œ?ì—???ˆì™¸/ë¹ˆê°’ ì²˜ë¦¬)
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
                    raise ConnectionError(f"Redis AUTH ?¤íŒ¨: {resp}")
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
                # ?€?„ì•„????ë¶€ë¶??‘ë‹µ?´ë¼??ë°˜í™˜
                pass
            return data
    except Exception as exc:
        logger.debug("[common] RESP ?„ì†¡ ?¤íŒ¨: %s", exc, exc_info=True)
        return b""

def _resp_complete(data: bytes) -> bool:
    """ê°„ë‹¨??RESP ?‘ë‹µ ?„ë£Œ ?´ë¦¬?¤í‹±"""
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
# RESP ?Œì‹± ? í‹¸
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
        # ?¨ìˆœ ?Œì‹±: ì²?ì¤?"*N" ?•ì¸ ??"$len" ?¤ìŒ ì¤??¬í•¨ ë°©ì‹ ì²˜ë¦¬
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
                    # ê¸°í???ë¬´ì‹œ
                    pass
                i += 1
    except Exception as exc:
        logger.debug("[common] ë°°ì—´ ?Œì‹± ?¤íŒ¨: %s", exc, exc_info=True)
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
        logger.debug("[common] INFO ?Œì‹± ?¤íŒ¨: %s", exc, exc_info=True)
    return result

# ---------------------------
# ?¸ì˜ ?¨ìˆ˜: ?´ë¼?´ì–¸???°ì„ , ?´ë°± RESP ?¬ìš©
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
    ë°˜í™˜: [(member, score), ...] (score?€ str)
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
    """?ë¬¸ ?ìŠ¤??ë°˜í™˜(?Œì‹±?€ ?¸ì¶œ?ì—???˜í–‰)"""
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
# ?ˆì „??SCAN ê¸°ë°˜ ??ì¹´ìš´??# ---------------------------
def scan_count(host: str, port: int, password: Optional[str], timeout: float, pattern: str, client=None, max_scan: int = 200000) -> int:
    """
    SCAN ê¸°ë°˜?¼ë¡œ ?¨í„´??ë§¤ì¹­?˜ëŠ” ??ê°œìˆ˜(ê·¼ì‚¬)ë¥??ˆì „?˜ê²Œ ?‰ë‹ˆ??
    - clientê°€ redis-py ?¸ìŠ¤?´ìŠ¤ë©?scan_iter ?¬ìš© (ë¹„ì°¨??.
    - max_scan: ?ˆì „?¥ì¹˜(ìµœë? ?¤ìº” ???? ??ë§¤ìš° ??DB?ì„œ ê³¼ë„???¤ìº” ë°©ì?.
    - ?´ë°±: client ë¯¸ì¡´???¹ì? scan_iter ?¤íŒ¨ ??ê¸°ì¡´ keys() ê²°ê³¼??ê¸¸ì´ë¥?ë°˜í™˜.
    """
    try:
        if client:
            # redis-py ?´ë¼?´ì–¸?¸ë¼ë©?scan_iter ?œë„
            try:
                cnt = 0
                for _ in client.scan_iter(match=pattern, count=1000):
                    cnt += 1
                    if cnt >= max_scan:
                        break
                return cnt
            except Exception:
                # scan_iter ?¬ìš© ë¶ˆê?ë©??´ë°±?¼ë¡œ ?˜ì–´ê°?                logger.debug("[common] client.scan_iter ?¬ìš© ë¶ˆê?, ?´ë°±?¼ë¡œ keys ?¬ìš©")
        # ?´ë°±: ê¸°ì¡´ keys() ?¬ìš© (?•ìƒ ?˜ê²½?ì„œ?????™ì‘?˜ì?ë§??´ì˜?ì„œ??SCAN ê¶Œì¥)
        keys_list = keys(host, port, password, timeout, pattern, client=client)
        return len(keys_list)
    except Exception as exc:
        logger.debug("[common] scan_count ?¤íŒ¨: %s", exc, exc_info=True)
        return 0
