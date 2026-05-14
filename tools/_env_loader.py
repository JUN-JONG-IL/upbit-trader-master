# -*- coding: utf-8 -*-
"""
tools/_env_loader.py

tools/ 스크립트 직접 실행 시 레포 루트 .env를 자동 로드합니다.
기존 환경변수는 덮어쓰지 않습니다 (환경변수 > .env 우선순위 보장).

사용법:
    # tools 스크립트 최상단에 추가
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # tools 폴더 추가
    from _env_loader import load_env
    load_env()

구현 원칙:
    - python-dotenv 없이 순수 표준 라이브러리만 사용
    - os.environ.setdefault() 방식 사용 (기존 환경변수 덮어쓰기 방지)
    - .env 파일 없을 시 조용히 스킵 (예외 발생 금지)
    - 레포 루트 탐색: __file__ 기준으로 부모 디렉토리 순회하여 .env 찾기
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 레포 루트 탐색 시 최대 상위 디렉토리 탐색 단계 수
_MAX_REPO_ROOT_SEARCH_DEPTH: int = 10


def _find_repo_root(start: Path) -> Optional[Path]:
    """레포 루트 디렉토리를 탐색합니다.

    start 디렉토리에서 시작하여 상위로 올라가며 .env 또는 .git 이 있는
    디렉토리를 레포 루트로 판단합니다.

    Args:
        start: 탐색을 시작할 디렉토리 경로.

    Returns:
        레포 루트 Path 또는 None (탐색 실패 시).
    """
    current = start.resolve()
    for _ in range(_MAX_REPO_ROOT_SEARCH_DEPTH):  # 최대 탐색 단계 수
        if (current / ".env").exists() or (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _parse_env_line(line: str) -> Optional[tuple[str, str]]:
    """단일 .env 파일 라인을 파싱하여 (key, value) 쌍을 반환합니다.

    Args:
        line: .env 파일의 한 줄.

    Returns:
        (key, value) 튜플 또는 None (주석·빈 줄·파싱 불가 시).
    """
    stripped = line.strip()
    # 빈 줄 또는 주석 스킵
    if not stripped or stripped.startswith("#"):
        return None
    if "=" not in stripped:
        return None
    key, _, val = stripped.partition("=")
    key = key.strip()
    if not key:
        return None
    # 인라인 주석 제거 (따옴표 밖의 #)
    val = val.strip()
    if val and val[0] in ('"', "'"):
        quote = val[0]
        end = val.find(quote, 1)
        if end != -1:
            val = val[1:end]
    else:
        # 인라인 주석 제거
        hash_idx = val.find(" #")
        if hash_idx != -1:
            val = val[:hash_idx].strip()
    return key, val


def load_env(env_path: Optional[str] = None) -> int:
    """레포 루트 .env 파일을 환경변수에 로드합니다.

    이미 설정된 환경변수는 덮어쓰지 않습니다.
    파일이 없으면 조용히 스킵합니다.

    Args:
        env_path: .env 파일 경로. None이면 자동 탐색합니다.

    Returns:
        로드된 환경변수 개수 (기존 환경변수에 의해 스킵된 항목 제외).
    """
    path: Optional[Path] = None
    if env_path:
        path = Path(env_path)
    else:
        repo_root = _find_repo_root(Path(__file__).parent)
        if repo_root is not None:
            path = repo_root / ".env"

    if path is None or not path.exists():
        logger.debug("[env_loader] .env 파일을 찾을 수 없습니다 (path=%s) — 스킵", path)
        return 0

    loaded = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                result = _parse_env_line(line)
                if result is None:
                    continue
                key, val = result
                # setdefault: 기존 환경변수 덮어쓰기 방지
                # 키가 아직 설정되지 않은 경우에만 카운트
                if key not in os.environ:
                    os.environ[key] = val
                    loaded += 1
    except OSError as exc:
        logger.warning("[env_loader] .env 파일 읽기 실패: %s", exc)
        return 0

    logger.debug("[env_loader] .env 로드 완료: %d개 변수 설정 (path=%s)", loaded, path)
    return loaded
