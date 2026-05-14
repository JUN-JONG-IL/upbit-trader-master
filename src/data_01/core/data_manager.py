#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- DataManager: MongoDB ?곌껐 諛?湲곕낯 CRUD 瑜??쒓났?섎뒗 寃쎈웾 ?곗씠??愿由ъ옄.
- FastAPI/uvicorn ?섏〈???놁씠 ?⑤룆 ?꾪룷?멸? 媛?ν븯?꾨줉 ?ㅺ퀎??
- server.py ???꾩껜 DataManager 媛 ?꾪룷??遺덇??ν븳 ?섍꼍(?섏〈 ?⑦궎吏 誘몄꽕移????먯꽌
  ?대갚?쇰줈 ?ъ슜?쒕떎.

[異붽? 蹂寃?
- Timescale(Postgres) 而ㅻ꽖?????理쒖꽑???몃젰?쇰줈 ?먯깋?섏뿬
  self.timescale_connector, self.pg_pool ?띿꽦?쇰줈 ?몄텧?섎룄濡?蹂닿컯?덉뒿?덈떎.
  ?대뒗 pipeline_loader媛 pg_pool???먮룞 ?먯??섏뿬 CandleWriter ?깆쓣 ?쒖꽦?뷀븷 ???덇쾶 ?⑸땲??
- ?먯깋? ?щ윭 ?ㅼ엫?ㅽ럹?댁뒪 ?꾨낫? repo ?뚯씪 寃?됱쓣 ?ъ슜?섎ŉ, 諛쒓껄 ???붾쾭洹?濡쒓렇瑜??④퉩?덈떎.
- 媛?ν븳 ??遺?묒슜??以꾩씠?꾨줉 connect()瑜?媛뺤젣濡??몄텧?섏? ?딄퀬, connector??怨듦컻 ?띿꽦???곗꽑 ?ъ슜?⑸땲??
"""
from __future__ import annotations

import logging
import os
import sys
import importlib
import importlib.util
from typing import Optional, Any, Dict, List

logger = logging.getLogger(__name__)

# pymongo ???좏깮???섏〈?????놁뼱???대옒???뺤쓽??媛??
try:
    import pymongo
    _HAS_PYMONGO = True
except ImportError:
    _HAS_PYMONGO = False
    logger.warning("[DataManager] pymongo not installed; MongoDB features disabled")


class DataManager:
    """
    寃쎈웾 ?곗씠??愿由ъ옄 (MongoDB CRUD ?섑띁).

    server.py ???꾩껜 DataManager 瑜??꾪룷?명븷 ???녿뒗 ?섍꼍(?섏〈 ?⑦궎吏 誘몄꽕移????먯꽌
    ?대갚?쇰줈 ?ъ슜?섎뒗 理쒖냼 援ы쁽?낅땲??
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
        # Timescale 愿???먯깋/?몄텧 ?띿꽦
        # ----------------------------
        # timescale 而ㅻ꽖???몄뒪?댁뒪 (諛쒓껄 ??
        self.timescale_connector: Optional[Any] = None
        # pipeline_loader媛 李얜뒗 ?쒖? ?대쫫??以??섎굹濡?pool/engine 媛앹껜瑜??몄텧
        self.pg_pool: Optional[Any] = None

        # ?먯깋 ?쒕룄 (理쒖꽑???몃젰?쇰줈 ?ㅼ젙; ?ㅽ뙣 ??None)
        try:
            self._discover_timescale_connector()
        except Exception:
            logger.debug("[DataManager] timescale discovery raised unexpected error", exc_info=True)

        logger.info(
            f"[DataManager] Initialized (MongoDB {self.db_ip}:{self.db_port})"
        )

    # ----------------------------
    # Timescale ?먯깋 濡쒖쭅 (理쒖꽑???몃젰)
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
        ?щ윭 ?꾨낫 ?ㅼ엫?ㅽ럹?댁뒪? repo ?뚯씪 寃?됱쓣 ?듯빐 Timescale 而ㅻ꽖?????諛쒓껄?섎젮 ?쒕룄?⑸땲??
        諛쒓껄 ??self.timescale_connector 諛?self.pg_pool???ㅼ젙?⑸땲??
        """
        tried: List[str] = []

        # ?꾨낫 紐⑤뱢 ?ㅼ엫 (?좎궗???⑦꽩 ?ы븿)
        candidates = (
            "src.data_01.timescale.timescale_db",
            "data_01.timescale.timescale_db",
            "src.data_01.timescale.timescale_connector",
            "data_01.timescale.timescale_connector",
            "src.data_01.timescale.timescale_db.timescale_db",
            "src.data_01.timescale.timescale_db",
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
                # ?쇰컲?곸쑝濡?TimescaleConnector ?쇰뒗 ?대옒?ㅻ챸???ъ슜??
                if hasattr(mod, "TimescaleConnector"):
                    connector_cls = getattr(mod, "TimescaleConnector")
                # ?먮뒗 timescale_db 紐⑤뱢??connector factory ?⑥닔瑜?媛吏????덉쓬
                elif hasattr(mod, "get_timescale_connector"):
                    connector_cls = getattr(mod, "get_timescale_connector")
                if connector_cls:
                    if logger:
                        logger.debug(f"[DataManager] Found timescale module {name} -> {getattr(mod, '__file__', None)}")
                    break
            except Exception as e:
                # 紐⑤뱢 import ?ㅽ뙣???붾쾭洹몃줈 湲곕줉
                if logger:
                    logger.debug(f"[DataManager] import {name} failed: {type(e).__name__}: {e}")

        # repo ?뚯씪 寃??(留덉?留??섎떒)
        if connector_cls is None and connector_mod is None:
            try:
                here = os.path.dirname(os.path.abspath(__file__))
                repo_root = os.path.abspath(os.path.join(here, "..", ".."))  # src/data_01/core -> src
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

        # connector_cls ?먮뒗 connector_mod瑜?諛뷀깢?쇰줈 ?몄뒪?댁뒪/? ?앹꽦 ?쒕룄
        try:
            if connector_cls:
                # connector_cls媛 ?대옒?ㅼ씠硫??몄뒪?댁뒪 ?쒕룄 (媛?ν븯硫??몄옄 ?놁씠)
                try:
                    inst = connector_cls()
                except TypeError:
                    # ?쒓렇?덉쿂媛 ?ㅻ? ???덉쓬(?? config ?몄옄), 洹몃윭硫??앹꽦?섏? ?딄퀬 ?대옒???먯껜瑜?蹂닿?
                    inst = None
                if inst is not None:
                    self.timescale_connector = inst
                    # 媛?ν븳 pool/engine ?띿꽦 寃??
                    for attr in ("pg_pool", "pool", "engine", "get_pool", "get_engine"):
                        try:
                            if hasattr(inst, attr):
                                val = getattr(inst, attr)
                                # get_* ?⑥닔?대㈃ ?몄텧 ?쒕룄(遺?묒슜 媛?μ꽦 ?덉쓬; ?몄텧 ?꾩뿉 癒쇱? ?뺤씤)
                                if callable(val) and attr.startswith("get_"):
                                    try:
                                        pool_candidate = val()
                                        if pool_candidate:
                                            self.pg_pool = pool_candidate
                                            if logger:
                                                logger.info(f"[DataManager] pg_pool discovered via connector.{attr}()")
                                            break
                                    except Exception:
                                        # ?몄텧 ?ㅽ뙣 ??臾댁떆
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
                    # ?대옒?ㅻ쭔 李얠븯怨??몄뒪?댁뒪???ㅽ뙣??寃쎌슦, 蹂댁닔?곸쑝濡??대옒???뺣낫留?蹂닿?
                    self.timescale_connector = connector_cls
            elif connector_mod:
                # 紐⑤뱢 ?섏??먯꽌 pool/engine???몄텧?덉쓣 ???덉쓬
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

    # ?? MongoDB ?곌껐 愿由??????????????????????????????????????????????????????????????

    def connect(self) -> bool:
        """MongoDB ???곌껐???쒕룄?⑸땲?? ?깃났 ?щ?瑜?諛섑솚?⑸땲??"""
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
            # ?곌껐 ?뺤씤 (ping)
            self.client.admin.command("ping")
            self.db = self.client.get_default_database(default=self.db_name)
            logger.info("[DataManager] MongoDB connection established")
            return True
        except Exception as e:
            logger.error(f"[DataManager] MongoDB connection failed: {e}")
            return False

    def disconnect(self) -> None:
        """MongoDB ?곌껐??醫낅즺?⑸땲??"""
        if self.client is not None:
            try:
                self.client.close()
                logger.info("[DataManager] MongoDB connection closed")
            except Exception as e:
                logger.warning(f"[DataManager] disconnect error: {e}")
            finally:
                self.client = None
                self.db = None

    # ?? 湲곕낯 CRUD ?????????????????????????????????????????????????????????????

    def insert_one(self, collection: str, document: Dict[str, Any]) -> Optional[str]:
        """?⑥씪 臾몄꽌瑜??쎌엯?섍퀬 ?쎌엯??_id 臾몄옄?댁쓣 諛섑솚?⑸땲??"""
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
        """荑쇰━ 議곌굔??留욌뒗 臾몄꽌 紐⑸줉??諛섑솚?⑸땲??"""
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
        """?⑥씪 臾몄꽌瑜??낅뜲?댄듃?섍퀬 ?섏젙??臾몄꽌 ?섎? 諛섑솚?⑸땲??"""
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
        """?⑥씪 臾몄꽌瑜???젣?섍퀬 ??젣??臾몄꽌 ?섎? 諛섑솚?⑸땲??"""
        if self.db is None:
            logger.warning("[DataManager] delete_one: not connected")
            return 0
        try:
            result = self.db[collection].delete_one(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"[DataManager] delete_one error: {e}")
            return 0

    # ?? ?곌껐 蹂듦뎄 ??????????????????????????????????????????????????????????????

    def ensure_connection(self, max_retries: int = 3) -> bool:
        """DB ?곌껐 ?곹깭瑜??뺤씤?섍퀬 ?딄꼈?쇰㈃ ?먮룞 ?ъ뿰寃고빀?덈떎."""
        if self._is_connected():
            return True

        logger.warning("[DataManager] DB ?곌껐 ?딄?, ?ъ뿰寃??쒕룄...")
        for attempt in range(1, max_retries + 1):
            try:
                self.disconnect()
                if self.connect():
                    logger.info(
                        "[DataManager] ?ъ뿰寃??깃났 (?쒕룄 %d/%d)", attempt, max_retries
                    )
                    return True
            except Exception as exc:
                logger.warning(
                    "[DataManager] ?ъ뿰寃??ㅽ뙣 (?쒕룄 %d/%d): %s", attempt, max_retries, exc
                )

        logger.error("[DataManager] ?ъ뿰寃?理쒖쥌 ?ㅽ뙣 (%d???쒕룄)", max_retries)
        return False

    def _is_connected(self) -> bool:
        """?꾩옱 MongoDB ?곌껐???좏슚?쒖? ?뺤씤?⑸땲??"""
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
        """?쒕쾭/?곌껐 ?쒖옉. server.py DataManager ????명솚 ?명꽣?섏씠??"""
        self.connect()

    def stop(self) -> None:
        """?쒕쾭/?곌껐 醫낅즺. server.py DataManager ????명솚 ?명꽣?섏씠??"""
        self.disconnect()

    def __enter__(self) -> "DataManager":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()


__all__ = ["DataManager"]
