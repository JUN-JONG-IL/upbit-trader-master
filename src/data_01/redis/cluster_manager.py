#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis Cluster 슬롯/토폴로지 유틸 (개선판)

요지:
- redis client wrapper(low-level 또는 고수준) 모두 지원
- ADDSLOTS 전송은 청크 단위로 안전 전송
- RESP 소켓 전송/수신을 바이트 레벨로 견고하게 처리
- CLUSTER NODES 응답을 파싱해 슬롯 목록을 가공하여 반환
- 에러(예: cluster support disabled)는 raw 응답과 함께 반환하여 진단 용이
"""

from __future__ import annotations
import logging
import socket
from typing import List, Tuple, Optional, Any, Dict
import importlib.util
from pathlib import Path

logger = logging.getLogger("redis.cluster_manager")
if logger.level == logging.NOTSET:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(asctime)s] [cluster_manager] [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(ch)
logger.propagate = False

# 슬롯 범위 (총 16384개)
_SLOT_RANGES: List[Tuple[int, int]] = [
    (0, 5460),
    (5461, 10922),
    (10923, 16383),
]


# -------------------------
# 유틸: get_redis_client 팩토리(동적 로드)
# -------------------------
def _load_get_redis_client():
    """상대 임포트 실패시 파일 경로에서 동적으로 get_redis_client 로드 시도."""
    try:
        from .redis_client import get_redis_client  # type: ignore
        return get_redis_client
    except Exception:
        try:
            repo_root = Path(__file__).resolve().parents[3]
            candidate = repo_root / "src" / "data_01" / "redis" / "redis_client.py"
            if candidate.exists():
                spec = importlib.util.spec_from_file_location("redis_client_dynamic", str(candidate))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)  # type: ignore
                    return getattr(mod, "get_redis_client", None)
        except Exception:
            logger.debug("dynamic load of redis_client failed", exc_info=True)
    return None


_get_redis_client = _load_get_redis_client()


def _get_raw_client(client: Any) -> Any:
    """
    wrapper에서 raw client 추출: 흔한 속성 _client, client, redis 를 검사.
    없으면 client 자체를 반환.
    """
    if client is None:
        return None
    for attr in ("_client", "client", "redis"):
        try:
            raw = getattr(client, attr, None)
            if raw:
                return raw
        except Exception:
            continue
    return client


# -------------------------
# RESP 소켓 전송/수신
# -------------------------
def _build_resp_command(args: List[str]) -> bytes:
    """
    RESP array 포맷을 바이트로 생성.
    안전하게 바이트로 처리하여 인코딩 문제를 방지.
    """
    parts: List[bytes] = []
    parts.append(f"*{len(args)}\r\n".encode("utf-8"))
    for a in args:
        if isinstance(a, bytes):
            b = a
        else:
            b = str(a).encode("utf-8")
        parts.append(f"${len(b)}\r\n".encode("utf-8"))
        parts.append(b)
        parts.append(b"\r\n")
    return b"".join(parts)


def _recv_all(sock: socket.socket, timeout: float = 5.0) -> bytes:
    """
    소켓으로부터 가능한 응답을 수집.
    - socket.recv 타임아웃으로 종료를 허용.
    """
    data = bytearray()
    sock.settimeout(timeout)
    try:
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            data.extend(chunk)
            # 작은 청크가 오면 곧 끝날 가능성이 높음; 계속 수신하여 타임아웃으로 종료 허용
            if len(chunk) < 8192:
                # continue to read until timeout or closed
                pass
    except socket.timeout:
        # 읽기 타임아웃은 일반적인 종료 조건으로 간주
        pass
    return bytes(data)


def _send_redis_command_socket(host: str, port: int, args: List[str], timeout: float = 5.0) -> bytes:
    """
    RESP 명령을 소켓으로 전송하고 raw 응답 바이트를 반환.
    """
    cmd = _build_resp_command(args)
    data = b""
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(cmd)
            data = _recv_all(sock, timeout=timeout)
    except Exception as exc:
        logger.exception("_send_redis_command_socket 예외: %s", exc)
        raise
    return data


def _resp_to_text(resp: bytes) -> str:
    try:
        return resp.decode("utf-8", errors="replace")
    except Exception:
        return str(resp)


def _parse_slots_token(token: str) -> List[str]:
    """
    CLUSTER NODES/INFO에서 나오는 슬롯 토큰(예: '1-5460', '10923-16383', '5461')을
    사람이 읽기 좋은 문자열 리스트로 정리하여 반환.
    """
    out: List[str] = []
    parts = token.split()
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # 토큰이 '[..]' 같은 메타 정보를 포함할 수 있으므로 필터링
        if p.startswith("[") and p.endswith("]"):
            out.append(p)
            continue
        # 범위 또는 단일 번호 처리
        out.append(p)
    return out


# -------------------------
# 클러스터 초기화: 슬롯 분배 (ADDSLOTS)
# -------------------------
def init_cluster(nodes: List[Tuple[str, int]], chunk_size: int = 1000, timeout: float = 5.0, client: Optional[Any] = None) -> None:
    """
    제공된 nodes의 처음 3개를 마스터로 사용하여 슬롯을 할당합니다.
    - nodes: [(host,port), ...] (최소 3개)
    - chunk_size: 한 번에 전송할 슬롯 수 (기본 1000)
    - client: redis client wrapper 또는 low-level client (있으면 execute_command 사용)
    """
    masters = nodes[:3]
    if len(masters) < 3:
        raise ValueError(f"최소 3개의 마스터 노드가 필요합니다. 제공됨: {len(masters)}")

    raw_client = _get_raw_client(client) if client is not None else None

    for i, (host, port) in enumerate(masters):
        start, end = _SLOT_RANGES[i]
        slots = [str(s) for s in range(start, end + 1)]
        logger.info("노드 %s:%s 에 슬롯 %d~%d (총 %d개) 할당 시작", host, port, start, end, len(slots))

        for j in range(0, len(slots), chunk_size):
            chunk = slots[j : j + chunk_size]
            try:
                if raw_client is not None and hasattr(raw_client, "execute_command"):
                    # redis-py low-level client의 execute_command 사용 (빠름)
                    logger.debug("execute_command로 ADDSLOTS 전송: 노드=%s:%s chunk=%d", host, port, len(chunk))
                    raw_client.execute_command("CLUSTER", "ADDSLOTS", *chunk)
                else:
                    logger.debug("socket으로 ADDSLOTS 전송: 노드=%s:%s chunk=%d", host, port, len(chunk))
                    _send_redis_command_socket(host, port, ["CLUSTER", "ADDSLOTS", *chunk], timeout=timeout)
            except Exception as exc:
                logger.exception("노드 %s:%s 슬롯 할당 실패(청크 인덱스 %d): %s", host, port, j // chunk_size, exc)
                raise
        logger.info("노드 %s:%s 슬롯 할당 완료", host, port)


# -------------------------
# CLUSTER NODES 조회 및 파싱
# -------------------------
def get_cluster_nodes(host: str = "localhost", port: int = 6379, client: Optional[Any] = None, timeout: float = 5.0) -> List[Dict[str, Any]]:
    """
    CLUSTER NODES 실행 후 파싱하여 리스트 반환.
    - client가 주어지면 client.execute_command("CLUSTER","NODES")를 우선 시도
    - 실패하면 RESP 소켓 폴백
    - 반환: 정상 시 노드 dict 리스트, 에러 시 [{"error": <msg>, "raw": <raw_text>}]
    노드 dict 형식:
      { "id": "...", "addr": "host:port", "flags": "...", "role": "master|slave|unknown", "slots": ["1-5460", "5461", ...] }
    """
    raw_text = ""
    raw_client = _get_raw_client(client) if client is not None else None

    # 1) client.execute_command 시도
    if raw_client is not None and hasattr(raw_client, "execute_command"):
        try:
            resp = raw_client.execute_command("CLUSTER", "NODES")
            raw_text = resp.decode("utf-8", errors="replace") if isinstance(resp, (bytes, bytearray)) else str(resp)
        except Exception as exc:
            logger.debug("client.execute_command(CLUSTER NODES) 실패: %s", exc, exc_info=True)
            raw_text = ""

    # 2) 소켓 폴백
    if not raw_text:
        try:
            resp_bytes = _send_redis_command_socket(host, port, ["CLUSTER", "NODES"], timeout=timeout)
            raw_text = _resp_to_text(resp_bytes)
        except Exception as exc:
            logger.exception("CLUSTER NODES 조회 중 예외: %s", exc)
            return [{"error": "CLUSTER NODES 조회 실패", "raw": ""}]

    # 3) 에러 감지 (예: cluster support disabled)
    err_msg = None
    for line in raw_text.splitlines():
        s = line.strip()
        if not s:
            continue
        # RESP 오류 라인(-ERR ...) 혹은 명확한 문구 포함 여부 검사
        if s.startswith("-ERR") or s.startswith("-"):
            err_msg = s.lstrip("-ERR ").lstrip("-").strip()
            break
        if "cluster support disabled" in s.lower() or "cluster is disabled" in s.lower():
            err_msg = s
            break
    if err_msg:
        logger.debug("CLUSTER NODES 에러 감지: %s", err_msg)
        return [{"error": err_msg, "raw": raw_text}]

    # 4) 정상 응답 파싱
    nodes: List[Dict[str, Any]] = []
    try:
        for line in raw_text.splitlines():
            s = line.strip()
            if not s:
                continue
            # RESP 표기($, *) 제거 안전 처리
            if s.startswith("$") or s.startswith("*"):
                continue
            parts = s.split()
            if len(parts) < 2:
                continue
            node_id = parts[0]
            addr = parts[1].split("@")[0] if "@" in parts[1] else parts[1]
            flags = parts[2] if len(parts) > 2 else ""
            role = "master" if "master" in flags else "slave" if "slave" in flags else "unknown"
            # 슬롯 정보는 parts[8:] 이후에 나올 수 있음; 합쳐서 토큰화
            slots_token = parts[8:] if len(parts) > 8 else []
            slots: List[str] = []
            for tok in slots_token:
                # tok은 '1-5460' 또는 '5461' 또는 '[..]' 등의 형태
                slots.extend(_parse_slots_token(tok))
            nodes.append({
                "id": node_id[:8],
                "addr": addr,
                "flags": flags,
                "role": role,
                "slots": slots,
            })
        logger.debug("CLUSTER NODES 파싱 완료: %d 노드", len(nodes))
    except Exception as exc:
        logger.exception("CLUSTER NODES 파싱 실패: %s", exc)
        return [{"error": "파싱 실패", "raw": raw_text}]

    return nodes