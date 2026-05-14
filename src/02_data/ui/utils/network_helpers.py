# -*- coding: utf-8 -*-
"""
네트워크 유틸리티 (TCP/HTTP probe)
"""
from __future__ import annotations
import logging
import socket
import urllib.request
import urllib.error
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def tcp_probe(host: str, port: int, timeout: float = 2.0) -> bool:
    """TCP 연결 프로브 — 연결 가능 여부만 확인합니다."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as e:
        logger.debug("[network_helpers] TCP probe 실패 %s:%s -> %s", host, port, e)
        return False


def http_probe(host: str, port: int, path: str = "/", timeout: float = 2.0) -> Tuple[bool, Optional[int]]:
    """HTTP GET 프로브 — 응답 여부와 상태 코드를 반환합니다."""
    url = f"http://{host}:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return True, getattr(resp, "status", None)
    except urllib.error.HTTPError as he:
        logger.debug("[network_helpers] HTTPError %s for %s", he.code, url)
        return True, getattr(he, "code", None)
    except Exception as e:
        logger.debug("[network_helpers] HTTP probe 실패 %s -> %s", url, e)
        return False, None


def parse_hostport(hostport: str, default_port: int) -> Tuple[str, int]:
    """'host:port' 문자열을 (host, port) 튜플로 파싱합니다."""
    if not hostport or hostport.strip() in ("--", "", "host:port"):
        return ("127.0.0.1", default_port)
    s = hostport.strip()
    if ":" in s:
        h, p = s.split(":", 1)
        try:
            return (h.strip(), int(p.strip()))
        except Exception:
            return (h.strip(), default_port)
    return (s, default_port)
