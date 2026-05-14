#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- DataManager: MongoDB 연결 및 기본 CRUD 를 제공하는 경량 데이터 관리자.
- FastAPI/uvicorn 의존성 없이 단독 임포트가 가능하도록 설계됨.
- server.py 의 전체 DataManager 가 임포트 불가능한 환경(의존 패키지 미설치 등)에서
  폴백으로 사용된다.

[추가 변경]
- Timescale(Postgres) 커넥터/풀을 최선의 노력으로 탐색하여
  self.timescale_connector, self.pg_pool 속성으로 노출하도록 보강했습니다.
  이는 pipeline_loader가 pg_pool을 자동 탐지하여 CandleWriter 등을 활성화할 수 있게 합니다.
- 탐색은 여러 네임스페이스 후보와 repo 파일 검색을 사용하며, 발견 시 디버그 로그를 남깁니다.
- 가능한 한 부작용을 줄이도록 connect()를 강제로 호출하지 않고, connector의 공개 속성을 우선 사용합니다.
"""
from __future__ import annotations

import logging
import os
import sys
import importlib
import importlib.util
from typing import Optional, Any, Dict, List

logger = logging.getLogger(__name__)

# pymongo 는 선택적 의존성 — 없어도 클래스 정의는 가능
try:
    import pymongo
    _HAS_PYMONGO = True
except ImportError:
    _HAS_PYMONGO = False
    logger.warning("[DataManager] pymongo not installed; MongoDB features disabled")


class DataManager:
    """
    경량 데이터 관리자 (MongoDB CRUD 래퍼).

    server.py 의 전체 DataManager 를 임포트할 수 없는 환경(의존 패키지 미설치 등)에서
    폴백으로 사용되는 최소 구현입니다.
    """

    def __init__(
        self,
        db_ip: Optional[str] = None,
        db_port: Optional[int] = None,
        db_id: Optional[str] = None,
        db_password: Optional[str] = None,
        db_name: Optional[str] = None,
        external_timeout: int = 60,
        internal_timeout: int = 1,
        request_limit: int = 10,
        **kwargs: Any,
    ) -> None:
        self.db_ip: str = db_ip or "localhost"
        self.db_port: int = int(db_port or 27017)
        self.db_id: str = db_id or "admin"
        self.db_password: str = db_password or "password"
        self.db_name: str = db_name or "upbit_trader"
        self.external_timeout: int = external_timeout
        self.internal_timeout: int = internal_timeout
        self.request_limit: int = request_limit

        self.client: Optional[Any] = None
        self.db: Optional[Any] = None

        # ----------------------------
        # Timescale 관련 탐색/노출 속성
        # ----------------------------
        # timescale 커넥터 인스턴스 (발견 시)
        self.timescale_connector: Optional[Any] = None
        # pipeline_loader가 찾는 표준 이름들 중 하나로 pool/engine 객체를 노출
        self.pg_pool: Optional[Any] = None

        # 탐색 시도 (최선의 노력으로 설정; 실패 시 None)
        try:
            self._discover_timescale_connector()
        except Exception:
            logger.debug("[DataManager] timescale discovery raised unexpected error", exc_info=True)

        logger.info(
            f"[DataManager] Initialized (MongoDB {self.db_ip}:{self.db_port})"
        )

    # ----------------------------
    # Timescale 탐색 로직 (최선의 노력)
    # ----------------------------
    def _search_repo_for_file(self, repo_root: str, filename_part: str, max_results: int = 10) -> List[str]:
        matches: List[str] = []
        for root, dirs, files in os.walk(repo_root):
            # skip heavy dirs
            if any(skip in root for skip in (os.path.join(repo_root, ".git"), "venv", "env", "__pycache__", "node_modules")):
                continue
            for f in files:
                if filename_part.lower() in f.lower() and f.lower().endswith(".py"):
                    matches.append(os.path.join(root, f))
                    if len(matches) >= max_results:
                        return matches
        return matches

    def _discover_timescale_connector(self) -> None:
        """
        여러 후보 네임스페이스와 repo 파일 검색을 통해 Timescale 커넥터/풀을 발견하려 시도합니다.
        발견 시 self.timescale_connector 및 self.pg_pool을 설정합니다.
        """
        tried: List[str] = []

        # 후보 모듈 네임 (유사한 패턴 포함)
        candidates = (
            "src.02_data.timescale.timescale_db",
            "02_data.timescale.timescale_db",
            "src.02_data.timescale.timescale_connector",
            "02_data.timescale.timescale_connector",
            "src.02_data.timescale.timescale_db.timescale_db",
            "src.02_data.timescale.timescale_db",
            "src.timescale.timescale_db",
            "timescale.timescale_db",
            "src.timescale_db",
            "timescale_db",
        )

        connector_cls = None
        connector_mod = None

        for name in candidates:
            try:
                tried.append(f"module:{name}")
                mod = importlib.import_module(name)
                connector_mod = mod
                # 일반적으로 TimescaleConnector 라는 클래스명을 사용함
                if hasattr(mod, "TimescaleConnector"):
                    connector_cls = getattr(mod, "TimescaleConnector")
                # 또는 timescale_db 모듈이 connector factory 함수를 가질 수 있음
                elif hasattr(mod, "get_timescale_connector"):
                    connector_cls = getattr(mod, "get_timescale_connector")
                if connector_cls:
                    if logger:
                        logger.debug(f"[DataManager] Found timescale module {name} -> {getattr(mod, '__file__', None)}")
                    break
            except Exception as e:
                # 모듈 import 실패는 디버그로 기록
                if logger:
                    logger.debug(f"[DataManager] import {name} failed: {type(e).__name__}: {e}")

        # repo 파일 검색 (마지막 수단)
        if connector_cls is None and connector_mod is None:
            try:
                here = os.path.dirname(os.path.abspath(__file__))
                repo_root = os.path.abspath(os.path.join(here, "..", ".."))  # src/02_data/core -> src
            except Exception:
                repo_root = os.path.abspath(os.getcwd())

            file_candidates = self._search_repo_for_file(repo_root, "timescale", max_results=20)
            if file_candidates:
                for fpath in file_candidates:
                    try:
                        tried.append(f"file:{fpath}")
                        alias = f"timescale_file_{os.path.basename(fpath)}"
                        spec = importlib.util.spec_from_file_location(alias, fpath)
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(mod)
                            # register to sys.modules for stability
                            try:
                                sys.modules[alias] = mod
                            except Exception:
                                pass
                            if hasattr(mod, "TimescaleConnector"):
                                connector_cls = getattr(mod, "TimescaleConnector")
                                connector_mod = mod
                                if logger:
                                    logger.debug(f"[DataManager] Loaded Timescale connector from file {fpath}")
                                break
                            # fallback: module may provide engine/pool directly as top-level var
                            if hasattr(mod, "engine") or hasattr(mod, "pg_pool") or hasattr(mod, "pool"):
                                connector_mod = mod
                                if logger:
                                    logger.debug(f"[DataManager] Found timescale variables in file {fpath}")
                                break
                    except Exception as e:
                        if logger:
                            logger.debug(f"[DataManager] file-load {fpath} failed: {type(e).__name__}: {e}")

        # connector_cls 또는 connector_mod를 바탕으로 인스턴스/풀 생성 시도
        try:
            if connector_cls:
                # connector_cls가 클래스이면 인스턴스 시도 (가능하면 인자 없이)
                try:
                    inst = connector_cls()
                except TypeError:
                    # 시그니처가 다를 수 있음(예: config 인자), 그러면 생성하지 않고 클래스 자체를 보관
                    inst = None
                if inst is not None:
                    self.timescale_connector = inst
                    # 가능한 pool/engine 속성 검색
                    for attr in ("pg_pool", "pool", "engine", "get_pool", "get_engine"):
                        try:
                            if hasattr(inst, attr):
                                val = getattr(inst, attr)
                                # get_* 함수이면 호출 시도(부작용 가능성 있음; 호출 전에 먼저 확인)
                                if callable(val) and attr.startswith("get_"):
                                    try:
                                        pool_candidate = val()
                                        if pool_candidate:
                                            self.pg_pool = pool_candidate
                                            if logger:
                                                logger.info(f"[DataManager] pg_pool discovered via connector.{attr}()")
                                            break
                                    except Exception:
                                        # 호출 실패 시 무시
                                        continue
                                else:
                                    if val:
                                        self.pg_pool = val
                                        if logger:
                                            logger.info(f"[DataManager] pg_pool discovered via connector.{attr}")
                                        break
                        except Exception:
                            continue
                else:
                    # 클래스만 찾았고 인스턴스화 실패한 경우, 보수적으로 클래스 정보만 보관
                    self.timescale_connector = connector_cls
            elif connector_mod:
                # 모듈 수준에서 pool/engine을 노출했을 수 있음
                for name in ("pg_pool", "pool", "engine", "get_pool", "get_engine"):
                    try:
                        if hasattr(connector_mod, name):
                            val = getattr(connector_mod, name)
                            if callable(val) and name.startswith("get_"):
                                try:
                                    pool_candidate = val()
                                    if pool_candidate:
                                        self.pg_pool = pool_candidate
                                        if logger:
                                            logger.info(f"[DataManager] pg_pool discovered via module.{name}()")
                                        break
                                except Exception:
                                    continue
                            else:
                                if val:
                                    self.pg_pool = val
                                    if logger:
                                        logger.info(f"[DataManager] pg_pool discovered via module.{name}")
                                    break
                    except Exception:
                        continue
        except Exception:
            if logger:
                logger.debug("[DataManager] timescale connector inspection failed", exc_info=True)

        if logger:
            logger.debug(f"[DataManager] timescale discovery finished; tried={tried}; pg_pool={'present' if self.pg_pool else 'none'}")

    # ── MongoDB 연결 관리 ─────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """MongoDB 에 연결을 시도합니다. 성공 여부를 반환합니다."""
        if not _HAS_PYMONGO:
            logger.warning("[DataManager] pymongo not available; skipping connect")
            return False
        try:
            uri = (
                f"mongodb://{self.db_id}:{self.db_password}"
                f"@{self.db_ip}:{self.db_port}/?authSource=admin"
            )
            self.client = pymongo.MongoClient(
                uri,
                serverSelectionTimeoutMS=self.external_timeout * 1000,
            )
            # 연결 확인 (ping)
            self.client.admin.command("ping")
            self.db = self.client.get_default_database(default=self.db_name)
            logger.info("[DataManager] MongoDB connection established")
            return True
        except Exception as e:
            logger.error(f"[DataManager] MongoDB connection failed: {e}")
            return False

    def disconnect(self) -> None:
        """MongoDB 연결을 종료합니다."""
        if self.client is not None:
            try:
                self.client.close()
                logger.info("[DataManager] MongoDB connection closed")
            except Exception as e:
                logger.warning(f"[DataManager] disconnect error: {e}")
            finally:
                self.client = None
                self.db = None

    # ── 기본 CRUD ─────────────────────────────────────────────────────────────

    def insert_one(self, collection: str, document: Dict[str, Any]) -> Optional[str]:
        """단일 문서를 삽입하고 삽입된 _id 문자열을 반환합니다."""
        if self.db is None:
            logger.warning("[DataManager] insert_one: not connected")
            return None
        try:
            result = self.db[collection].insert_one(document)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"[DataManager] insert_one error: {e}")
            return None

    def find_many(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """쿼리 조건에 맞는 문서 목록을 반환합니다."""
        if self.db is None:
            logger.warning("[DataManager] find_many: not connected")
            return []
        try:
            cursor = self.db[collection].find(query or {})
            if limit > 0:
                cursor = cursor.limit(limit)
            return list(cursor)
        except Exception as e:
            logger.error(f"[DataManager] find_many error: {e}")
            return []

    def update_one(
        self,
        collection: str,
        query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> int:
        """단일 문서를 업데이트하고 수정된 문서 수를 반환합니다."""
        if self.db is None:
            logger.warning("[DataManager] update_one: not connected")
            return 0
        try:
            result = self.db[collection].update_one(query, update, upsert=upsert)
            return result.modified_count
        except Exception as e:
            logger.error(f"[DataManager] update_one error: {e}")
            return 0

    def delete_one(self, collection: str, query: Dict[str, Any]) -> int:
        """단일 문서를 삭제하고 삭제된 문서 수를 반환합니다."""
        if self.db is None:
            logger.warning("[DataManager] delete_one: not connected")
            return 0
        try:
            result = self.db[collection].delete_one(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"[DataManager] delete_one error: {e}")
            return 0

    # ── 연결 복구 ──────────────────────────────────────────────────────────────

    def ensure_connection(self, max_retries: int = 3) -> bool:
        """DB 연결 상태를 확인하고 끊겼으면 자동 재연결합니다."""
        if self._is_connected():
            return True

        logger.warning("[DataManager] DB 연결 끊김, 재연결 시도...")
        for attempt in range(1, max_retries + 1):
            try:
                self.disconnect()
                if self.connect():
                    logger.info(
                        "[DataManager] 재연결 성공 (시도 %d/%d)", attempt, max_retries
                    )
                    return True
            except Exception as exc:
                logger.warning(
                    "[DataManager] 재연결 실패 (시도 %d/%d): %s", attempt, max_retries, exc
                )

        logger.error("[DataManager] 재연결 최종 실패 (%d회 시도)", max_retries)
        return False

    def _is_connected(self) -> bool:
        """현재 MongoDB 연결이 유효한지 확인합니다."""
        if self.client is None or self.db is None:
            return False
        if not _HAS_PYMONGO:
            return False
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def start(self) -> None:
        """서버/연결 시작. server.py DataManager 와의 호환 인터페이스."""
        self.connect()

    def stop(self) -> None:
        """서버/연결 종료. server.py DataManager 와의 호환 인터페이스."""
        self.disconnect()

    def __enter__(self) -> "DataManager":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()


__all__ = ["DataManager"]