# 클러스터 노드 파싱 (빈/단독 인스턴스/에러 처리 강화)
from __future__ import annotations
from typing import List, Tuple, Optional, Any
from . import common
import logging

logger = logging.getLogger(__name__)

def _short_id(node_id: str) -> str:
    """노드 id를 화면 용으로 축약 (8자 초과 시 생략부호 추가)."""
    if not node_id:
        return "-"
    return (node_id[:8] + "…") if len(node_id) > 8 else node_id

def _normalize_address(addr: str) -> str:
    """
    주소 정리:
    - 'ip:port@cport' 형태에서는 '@' 뒤 제거
    - IPv6 형태 처리(대괄호 포함 등)
    """
    if not addr:
        return "-"
    if "@" in addr:
        addr = addr.split("@", 1)[0]
    return addr

def fetch_cluster(host: str, port: int, password: Optional[str], timeout: float, client: Optional[Any]=None) -> Tuple[List[Tuple[str,str,str,str,str]], str]:
    """
    클러스터 노드 정보를 파싱하여 반환합니다.
    반환값:
      - node_rows: [(node_id, role, address, slots, state), ...]
      - status_msg: 설명 문자열 (예: '클러스터 모드 아님 (단독 인스턴스)' 또는 '총 N개 노드')
    개선사항:
      - common.cluster_nodes()의 다양한 응답 포맷(에러, RESP 라인, 빈값)을 견고히 처리
      - 화면에 표시할 최소한의 안전한 값들로 구성
    """
    node_rows: List[Tuple[str,str,str,str,str]] = []
    status_msg = "클러스터 정보 없음"
    try:
        raw = common.cluster_nodes(host, port, password, timeout, client=client)

        # 빈 응답: 단독 인스턴스(클러스터 아님)
        if not raw:
            return node_rows, "클러스터 모드 아님 (단독 인스턴스)"

        # raw가 바이트 또는 그 외 타입일 수 있으므로 문자열화
        if isinstance(raw, bytes):
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                text = str(raw)
        else:
            text = str(raw)

        text_strip = text.strip()
        if not text_strip:
            return node_rows, "클러스터 모드 아님 (단독 인스턴스)"

        # 에러 응답 처리: RESP 오류 줄 또는 redis 오류 프리픽스('-ERR' / '-')
        first_line = text_strip.splitlines()[0].strip()
        if first_line.startswith("-ERR") or first_line.startswith("-"):
            # 에러 메시지를 status_msg로 전달(뷰에서 '연결 오류'로 표시 가능)
            msg = first_line.lstrip("-ERR ").lstrip("-").strip()
            logger.debug("[cluster] cluster_nodes returned error: %s", msg or first_line)
            return [], f"클러스터 조회 오류: {msg or first_line}"

        # CLUSTER NODES 형태로 응답이 온 경우 라인 단위 파싱
        # 일부 구현에서 RESP array 표기나 다른 선행 라인이 포함될 수 있어 필터링
        lines = []
        for l in text.splitlines():
            if not l:
                continue
            s = l.strip()
            # RESP/멀티라인 표기($, *) 등은 무시
            if s.startswith("$") or s.startswith("*"):
                continue
            # 가끔 서버가 에러/응답 텍스트 대신 '-ERR '를 포함한 라인도 보낼 수 있으므로 다시 체크
            if s.startswith("-ERR") or s.startswith("-"):
                # 에러가 섞여 있다면 전체를 실패로 처리
                logger.debug("[cluster] skipping error-like line in cluster_nodes response: %s", s)
                return [], f"클러스터 조회 오류: {s}"
            lines.append(s)

        node_count = 0
        for line in lines:
            # 일반적인 CLUSTER NODES 한 줄 예:
            # <id> <ip:port@cport> <flags> <master> <ping> <pong> <epoch> <connected> [slots...]
            parts = line.split()
            if len(parts) < 2:
                # 의미없는 라인 무시
                continue

            # 기본 필드 안전 추출
            raw_id = parts[0]
            raw_addr = parts[1] if len(parts) > 1 else "-"
            flags = parts[2] if len(parts) > 2 else ""
            # 역할 판단
            role = "master" if "master" in flags else ("slave" if "slave" in flags else flags or "unknown")
            # 상태 판단 (fail 키워드 포함 시 FAIL)
            state = "FAIL" if ("fail" in flags or "fail?" in flags) else "ok"
            # 슬롯 정보: 보통 8번째 인덱스(0-based)부터 존재하지만 일부 포맷은 길이가 다름 -> 안전하게 slice
            slots = "-"
            if len(parts) >= 9:
                # parts[8:] 는 슬롯 목록/범위(또는 여러 토큰)일 수 있음
                try:
                    slots_part = parts[8:]
                    # join하지만 길이가 너무 길면 축약
                    slots = " ".join(slots_part) if slots_part else "-"
                except Exception:
                    slots = "-"
            else:
                slots = "-"

            node_id = _short_id(raw_id)
            address = _normalize_address(raw_addr)

            node_rows.append((node_id, role, address, slots, state))
            node_count += 1

        status_msg = f"총 {node_count}개 노드" if node_count > 0 else "클러스터 모드 아님 (단독 인스턴스)"
        return node_rows, status_msg

    except Exception as exc:
        logger.exception("[cluster] fetch failed: %s", exc)
        return [], "클러스터 정보 조회 실패"