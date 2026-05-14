# -*- coding: utf-8 -*-
"""
src/data_01/ui/settings_storage.py

?ㅼ젙 ???諛?蹂듭썝 ?좏떥

湲곕뒫:
- MongoDB媛 媛?ν븯硫?'app_settings' 而щ젆?섏뿉 ??? ?꾨땲硫?濡쒖뺄 ?뚯씪(.app_settings.json)???대갚
- ?⑥닔:
    save_setting(namespace, key, value)
    load_setting(namespace, key, default=None)
    delete_setting(namespace, key)
    list_namespace(namespace) -> dict(key->value)
- 媛믪? JSON 吏곷젹??湲곕낯)濡???ν빀?덈떎. 蹂듭썝 ??媛?ν븳 寃쎌슦 ?먰삎 ??낆쑝濡?蹂듭썝?섍퀬,
  蹂듭썝 遺덇???寃쎌슦 臾몄옄???뺥깭濡?諛섑솚?⑸땲??

?ъ슜 ??
    from src.data_01.ui.settings_storage import save_setting, load_setting
    save_setting("backfill", "collect_mode", "hybrid")
    mode = load_setting("backfill", "collect_mode", "hybrid")
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# 濡쒖뺄 ?대갚 ?뚯씪 寃쎈줈 (?덊룷 猷⑦듃???④? ?뚯씪)
_DEFAULT_LOCAL_SETTINGS = ".app_settings.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_local_settings_path() -> str:
    # ?뚯씪??repo 猷⑦듃(???뚯씪??遺紐?遺紐? ?먮뒗 ?꾩옱 ?묒뾽 ?붾젆?곕━???〓땲??
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    path = os.path.join(repo_root, _DEFAULT_LOCAL_SETTINGS)
    return path


def _load_local_store() -> Dict[str, Dict[str, Any]]:
    path = _get_local_settings_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.debug("[settings_storage] 濡쒖뺄 ?ㅼ젙 ?뚯씪 濡쒕뱶 ?ㅽ뙣: %s", exc)
    return {}


def _save_local_store(store: Dict[str, Dict[str, Any]]) -> None:
    path = _get_local_settings_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("[settings_storage] 濡쒖뺄 ?ㅼ젙 ?뚯씪 ????ㅽ뙣: %s", exc)


# MongoDB helper: try to use existing MongoConnector if available
def _get_mongo_collection():
    """
    媛?ν븯硫?MongoConnector瑜??ъ슜?섏뿬 'app_settings' 而щ젆?섏쓣 占쏙옙?섑빀?덈떎.
    ?ㅽ뙣?섎㈃ None??諛섑솚?⑸땲??
    """
    try:
        # ?꾨줈?앺듃??mongo wrapper媛 src.data_01.mongodb.mongo_db.MongoConnector 媛숈? ?꾩튂???덈떎怨?媛??
        from src.data_01.mongodb.mongo_db import MongoConnector  # type: ignore
        connector = MongoConnector()
        if getattr(connector, "db", None) is None:
            # connector.connect() ?몄텧 媛?ν븯硫??쒕룄
            try:
                connector.connect()
            except Exception:
                pass
        db = getattr(connector, "db", None)
        if db is not None:
            return db["app_settings"]
    except Exception:
        # 寃쎄퀬??濡쒓렇???붾쾭源낆뿉?쒕쭔 異쒕젰
        logger.debug("[settings_storage] MongoConnector 濡쒕뱶 ?ㅽ뙣 ?먮뒗 DB 誘몄궗??(?대갚 濡쒖뺄 ?뚯씪 ?ъ슜)")
    return None


def _serialize_value(v: Any) -> Any:
    """
    ???媛?ν븳 ?뺥깭濡?吏곷젹??
    - 湲곕낯 占쏙옙占쎌엯 / 由ъ뒪??/ dict -> JSON 洹몃?濡??ъ슜
    - 洹????? datetime ?? -> ISO 臾몄옄?대줈 蹂??
    """
    try:
        # try json serializable
        json.dumps(v)
        return v
    except Exception:
        # fallback conversions
        if isinstance(v, datetime):
            return {"__type": "datetime", "iso": v.isoformat()}
        try:
            return str(v)
        except Exception:
            return repr(v)


def _deserialize_value(raw: Any) -> Any:
    """
    _serialize_value ? 諛섎? ?묒뾽: datetime ??蹂듭썝 ?쒕룄
    """
    if isinstance(raw, dict) and raw.get("__type") == "datetime" and "iso" in raw:
        try:
            return datetime.fromisoformat(raw["iso"])
        except Exception:
            return raw["iso"]
    return raw


def save_setting(namespace: str, key: str, value: Any) -> bool:
    """
    ?ㅼ젙 ???
    Args:
        namespace: ?쇰━??洹몃９ (?? "backfill")
        key: ?ㅼ젙 ??(?? "collect_mode")
        value: ??ν븷 媛?(媛?ν븯硫?JSON 吏곷젹??媛??
    Returns:
        ?깃났 ?щ? (bool)
    """
    ns = str(namespace)
    k = str(key)
    payload = {
        "namespace": ns,
        "key": k,
        "value": _serialize_value(value),
        "updated_at": _now_iso(),
    }

    # 1) ?쒕룄: MongoDB
    col = _get_mongo_collection()
    if col is not None:
        try:
            # upsert style
            col.update_one({"namespace": ns, "key": k}, {"$set": payload}, upsert=True)
            logger.debug("[settings_storage] MongoDB???ㅼ젙 ??? %s.%s", ns, k)
            return True
        except Exception as exc:
            logger.warning("[settings_storage] MongoDB ????ㅽ뙣(濡쒖뺄濡??대갚): %s", exc)

    # 2) 濡쒖뺄 ?뚯씪 ?대갚
    try:
        store = _load_local_store()
        if ns not in store:
            store[ns] = {}
        store[ns][k] = payload
        _save_local_store(store)
        logger.debug("[settings_storage] 濡쒖뺄 ?뚯씪???ㅼ젙 ??? %s.%s", ns, k)
        return True
    except Exception as exc:
        logger.error("[settings_storage] ?ㅼ젙 ????ㅽ뙣: %s", exc)
        return False


def load_setting(namespace: str, key: str, default: Optional[Any] = None) -> Any:
    """
    ?ㅼ젙 遺덈윭?ㅺ린. ??λ맂 媛믪씠 ?놁쑝硫?default 諛섑솚.
    """
    ns = str(namespace)
    k = str(key)

    # 1) MongoDB
    col = _get_mongo_collection()
    if col is not None:
        try:
            doc = col.find_one({"namespace": ns, "key": k}, {"_id": 0, "value": 1})
            if doc and "value" in doc:
                return _deserialize_value(doc["value"])
        except Exception as exc:
            logger.debug("[settings_storage] MongoDB load ?ㅽ뙣 (濡쒖뺄 ?대갚): %s", exc)

    # 2) 濡쒖뺄 ?뚯씪
    try:
        store = _load_local_store()
        ns_store = store.get(ns, {})
        if not ns_store:
            return default
        entry = ns_store.get(k)
        if not entry:
            return default
        raw = entry.get("value")
        return _deserialize_value(raw)
    except Exception as exc:
        logger.warning("[settings_storage] 濡쒖뺄 ?ㅼ젙 遺덈윭?ㅺ린 ?ㅽ뙣: %s", exc)
        return default


def delete_setting(namespace: str, key: str) -> bool:
    ns = str(namespace)
    k = str(key)
    col = _get_mongo_collection()
    if col is not None:
        try:
            col.delete_one({"namespace": ns, "key": k})
            return True
        except Exception as exc:
            logger.debug("[settings_storage] MongoDB ??젣 ?ㅽ뙣: %s", exc)
    # 濡쒖뺄 ?대갚
    try:
        store = _load_local_store()
        if ns in store and k in store[ns]:
            del store[ns][k]
            _save_local_store(store)
        return True
    except Exception as exc:
        logger.warning("[settings_storage] 濡쒖뺄 ?ㅼ젙 ??젣 ?ㅽ뙣: %s", exc)
        return False


def list_namespace(namespace: str) -> Dict[str, Any]:
    """
    ?ㅼ엫?ㅽ럹?댁뒪???랁븳 紐⑤뱺 ?ㅼ젙 諛섑솚 (key -> 媛?
    """
    ns = str(namespace)
    out = {}
    col = _get_mongo_collection()
    if col is not None:
        try:
            for doc in col.find({"namespace": ns}, {"_id": 0, "key": 1, "value": 1}):
                out[doc["key"]] = _deserialize_value(doc.get("value"))
            return out
        except Exception as exc:
            logger.debug("[settings_storage] MongoDB list ?ㅽ뙣: %s", exc)
    # 濡쒖뺄
    try:
        store = _load_local_store()
        ns_store = store.get(ns, {})
        for k, v in ns_store.items():
            out[k] = _deserialize_value(v.get("value"))
    except Exception as exc:
        logger.debug("[settings_storage] 濡쒖뺄 list ?ㅽ뙣: %s", exc)
    return out
