#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
debug_pool_dump.py
- pool.py 파일을 파일경로로 직접 로드하여 pool 상태를 강제로 덤프합니다 (디버그 전용).
- 프로젝트 루트(레포지토리 최상위)에서 실행하거나 --pool-path 옵션으로 pool.py 경로를 지정하세요.
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Optional

# 로깅 설정 (간단)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("debug_pool_dump")


def _set_env_once(key: str, value: str) -> Optional[str]:
    """환경변수를 이 스크립트에서만 설정하고, 이전 값을 반환합니다."""
    prev = os.environ.get(key)
    os.environ[key] = value
    return prev


def _restore_env(key: str, prev: Optional[str]) -> None:
    """환경변수 복원(이전값 None이면 삭제)."""
    if prev is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = prev


def load_pool_by_path(pool_path: Optional[str] = None):
    """
    pool.py 파일을 동적 로드하여 모듈 객체를 반환합니다.
    기본 경로는 repo_root/src/data_01/timescale/pool.py 입니다.
    """
    # 현재 파일(스크립트) 위치를 기준으로 repo_root를 계산
    repo_root = Path(__file__).resolve().parent

    if pool_path:
        pool_path = Path(pool_path)
    else:
        pool_path = repo_root / "src" / "data_01" / "timescale" / "pool.py"

    pool_path = pool_path.resolve()
    if not pool_path.exists():
        raise FileNotFoundError(f"pool.py 파일을 찾을 수 없습니다: {pool_path}")

    # pool.py 내부에서 다른 프로젝트 모듈을 임포트할 가능성이 있으므로
    # repo의 src 디렉토리를 sys.path 앞에 추가한 뒤 로드하고, 이후 복구함.
    src_dir = repo_root / "src"
    added_to_syspath = False
    original_syspath0 = None
    try:
        if src_dir.exists():
            original_syspath0 = sys.path[0] if sys.path else None
            sys.path.insert(0, str(src_dir))
            added_to_syspath = True
            logger.debug("임시로 src 디렉터리를 sys.path에 추가: %s", str(src_dir))

        spec = importlib.util.spec_from_file_location("debug_timescale_pool", str(pool_path))
        if spec is None or spec.loader is None:
            raise ImportError("importlib spec 생성 실패")

        mod = importlib.util.module_from_spec(spec)
        # exec_module 실행 시 내부에서 상대임포트가 있을 경우 실패할 수 있으므로
        # 가능한 한 src가 sys.path에 등록된 상태에서 실행되도록 했음.
        spec.loader.exec_module(mod)  # type: ignore
        logger.info("pool 모듈을 성공적으로 로드했습니다: %s", str(pool_path))
        return mod
    finally:
        # sys.path 복구
        try:
            if added_to_syspath:
                # 가능하면 앞쪽에 넣었던 항목을 제거
                if sys.path and str(src_dir) == sys.path[0]:
                    sys.path.pop(0)
                else:
                    # 안전하게 전체에서 제거
                    try:
                        sys.path.remove(str(src_dir))
                    except ValueError:
                        pass
                logger.debug("sys.path 복구 완료")
        except Exception:
            logger.exception("sys.path 복구 중 예외 발생")


def detect_dump_path(pool_module) -> Path:
    """
    pool 모듈에서 덤프 파일 경로를 제공하면 우선 사용, 없으면 시스템 temp 경로의 기본 파일 사용.
    """
    # 모듈에 명시된 상수명들을 우선적으로 체크
    candidates = ["TIMESCALE_POOL_DUMP_PATH", "DUMP_FILE_PATH", "POOL_DUMP_PATH"]
    for name in candidates:
        if hasattr(pool_module, name):
            try:
                val = getattr(pool_module, name)
                path = Path(str(val)).expanduser()
                logger.info("pool 모듈에서 덤프 경로 발견 (%s) -> %s", name, str(path))
                return path
            except Exception:
                logger.debug("모듈 상수로부터 경로 변환 실패: %s", name)
                continue

    # 기본 파일명
    return Path(tempfile.gettempdir()) / "timescale_pool_status.json"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="pool 상태를 강제로 덤프하는 디버그 스크립트")
    parser.add_argument("--pool-path", help="pool.py 파일의 전체 경로 (옵션)")
    parser.add_argument("--verbose", action="store_true", help="상세 로그 출력")
    args = parser.parse_args(argv)

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # 이 세션에서만 모니터 활성화 (원래값을 복구하기 위해 저장)
    prev_pool_monitor = _set_env_once("POOL_MONITOR", "1")

    try:
        try:
            pool = load_pool_by_path(args.pool_path)
        except Exception as e:
            logger.error("pool 모듈 로드 실패: %s", e)
            traceback.print_exc()
            return 1

        # _get_state 존재 확인
        if not hasattr(pool, "_get_state") or not callable(getattr(pool, "_get_state")):
            logger.error("pool 모듈에 _get_state 함수가 없습니다. 모듈의 API를 확인하세요.")
            return 4

        try:
            state = pool._get_state()
        except Exception as e:
            logger.error("pool._get_state() 호출 실패: %s", e)
            traceback.print_exc()
            return 2

        # 강제 디버그 항목 추가 (덤프 조건 유도)
        try:
            key = f"debug-force-{int(time.time())}"
            if isinstance(state, dict):
                state.setdefault("_active", {})[key] = {
                    "acquired_at": time.time() - 120.0,
                    "stack": "DEBUG-FORCE",
                }
                if not state.get("maxconn"):
                    state["maxconn"] = 10
                logger.debug("디버그 강제 항목을 state에 추가했습니다: %s", key)
            else:
                logger.debug("state가 dict가 아니므로 강제 항목 추가를 건너뜁니다.")
        except Exception:
            logger.exception("state 강제 변경 중 예외 발생 (무시)")

        # _check_and_dump 존재 확인 및 호출
        if not hasattr(pool, "_check_and_dump") or not callable(getattr(pool, "_check_and_dump")):
            logger.error("pool 모듈에 _check_and_dump 함수가 없습니다. 덤프 호출을 수행할 수 없습니다.")
            return 5

        try:
            pool._check_and_dump(state)
            logger.info("pool._check_and_dump 호출을 완료했습니다.")
        except Exception as e:
            logger.error("pool._check_and_dump 호출 실패: %s", e)
            traceback.print_exc()
            return 3

        # 덤프 파일 읽기 (모듈 지정 경로 우선)
        fn = detect_dump_path(pool)
        logger.info("덤프 시도 완료. 예상 경로: %s", str(fn))
        if fn.exists():
            try:
                text = fn.read_text(encoding="utf-8")
                print("===== timescale_pool_status.json 내용 시작 =====")
                print(text)
                print("===== timescale_pool_status.json 내용 끝 =====")
            except Exception as e:
                logger.error("덤프 파일 읽기 실패: %s", e)
                traceback.print_exc()
                return 6
        else:
            logger.warning("덤프 파일이 생성되지 않았습니다. (POOL_MONITOR 설정/덤프 조건 확인 필요)")
            return 7

        return 0
    finally:
        # 환경 변수 원상복구
        try:
            _restore_env("POOL_MONITOR", prev_pool_monitor)
        except Exception:
            logger.exception("환경변수 복구 중 예외 발생")


if __name__ == "__main__":
    raise SystemExit(main())
