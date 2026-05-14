# 공통 유틸: RESP 폴백, timescale get_client 동적 로드, 파싱 유틸, SCAN 기반 안전 카운트 등
# 한글 주석으로 동작 설명 포함

from __future__ import annotations
import importlib.util
import logging
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------
# timescale_redis.get_client 동적 로드 (있으면 우선 사용)
# ---------------------------
def _load_timescale_module() -> Optional[object]:
    """
    레포 내부의 src/data_01/timescale/timescale_redis.py를 시도 로드하고
    get_client 함수가 있으면 모듈을 반환합니다. 실패해도 None 반환.
    """
    try:
        base = Path(__file__).resolve()
        p = base
        # src/data_01 까지 올라간 뒤 timescale 디렉토리 찾기
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
        logger.debug("[common] timescale 모듈 로드 실패: %s", exc, exc_info=True)
    return None

_timescale_mod = _load_timescale_module()
_get_client_fn = None
if _timescale_mod is not None:
    try:
        _get_client_fn = getattr(_timescale_mod, "get_client", None)
    except Exception:
        _get_client_fn = None

def get_client_if_available():
    """timescale 모듈의 get_client()를 안전히 호출해서 클라이언트를 얻습니다. 실패 시 None."""
    try:
        if _get_client_fn:
            return _get_client_fn()
    except Exception as exc:
        logger.debug("[common] get_client 호출 실패: %s", exc, exc_info=True)
    return None

# ---------------------------
# RESP 소켓 폴백 구현 (redis-py가 없을 때도 동작 가능하게)
# ---------------------------
def _resp_send(host: str, port: int, password: Optional[str], timeout: float, *args: Any) -> bytes:
    """
    간단한 RESP 직송 헬퍼.
    - AUTH 지원
    - 명령 전송 후 휴리스틱으로 응답 종료 판단
    실패 시 빈 bytes 반환(호출자에서 예외/빈값 처리)
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
                    raise ConnectionError(f"Redis AUTH 실패: {resp}")
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
                # 타임아웃 시 부분 응답이라도 반환
                pass
            return data
    except Exception as exc:
        logger.debug("[common] RESP 전송 실패: %s", exc, exc_info=True)
        return b""

def _resp_complete(data: bytes) -> bool:
    """간단한 RESP 응답 완료 휴리스틱"""
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
# RESP 파싱 유틸
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
        # 단순 파싱: 첫 줄 "*N" 확인 후 "$len" 다음 줄 포함 방식 처리
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
                    # 기타는 무시
                    pass
                i += 1
    except Exception as exc:
        logger.debug("[common] 배열 파싱 실패: %s", exc, exc_info=True)
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
        logger.debug("[common] INFO 파싱 실패: %s", exc, exc_info=True)
    return result

# ---------------------------
# 편의 함수: 클라이언트 우선, 폴백 RESP 사용
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
    반환: [(member, score), ...] (score은 str)
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
    """원문 텍스트 반환(파싱은 호출자에서 수행)"""
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
# 안전한 SCAN 기반 키 카운터
# ---------------------------
def scan_count(host: str, port: int, password: Optional[str], timeout: float, pattern: str, client=None, max_scan: int = 200000) -> int:
    """
    SCAN 기반으로 패턴에 매칭되는 키 개수(근사)를 안전하게 셉니다.
    - client가 redis-py 인스턴스면 scan_iter 사용 (비차단).
    - max_scan: 안전장치(최대 스캔 키 수) — 매우 큰 DB에서 과도한 스캔 방지.
    - 폴백: client 미존재 혹은 scan_iter 실패 시 기존 keys() 결과의 길이를 반환.
    """
    try:
        if client:
            # redis-py 클라이언트라면 scan_iter 시도
            try:
                cnt = 0
                for _ in client.scan_iter(match=pattern, count=1000):
                    cnt += 1
                    if cnt >= max_scan:
                        break
                return cnt
            except Exception:
                # scan_iter 사용 불가면 폴백으로 넘어감
                logger.debug("[common] client.scan_iter 사용 불가, 폴백으로 keys 사용")
        # 폴백: 기존 keys() 사용 (정상 환경에서는 잘 동작하지만 운영에서는 SCAN 권장)
        keys_list = keys(host, port, password, timeout, pattern, client=client)
        return len(keys_list)
    except Exception as exc:
        logger.debug("[common] scan_count 실패: %s", exc, exc_info=True)
        return 0