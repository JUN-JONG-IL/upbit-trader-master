# -*- coding: utf-8 -*-
"""
src/data_01/ui/settings_storage.py

설정 저장 및 복원 유틸

기능:
- MongoDB가 가능하면 'app_settings' 컬렉션에 저장, 아니면 로컬 파일(.app_settings.json)에 폴백
- 함수:
    save_setting(namespace, key, value)
    load_setting(namespace, key, default=None)
    delete_setting(namespace, key)
    list_namespace(namespace) -> dict(key->value)
- 값은 JSON 직렬화(기본)로 저장합니다. 복원 시 가능한 경우 원형 타입으로 복원하고,
  복원 불가한 경우 문자열 형태로 반환합니다.

사용 예:
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

# 로컬 폴백 파일 경로 (레포 루트에 숨김 파일)
_DEFAULT_LOCAL_SETTINGS = ".app_settings.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_local_settings_path() -> str:
    # 파일을 repo 루트(이 파일의 부모 부모) 또는 현재 작업 디렉터리에 둡니다.
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
        logger.debug("[settings_storage] 로컬 설정 파일 로드 실패: %s", exc)
    return {}


def _save_local_store(store: Dict[str, Dict[str, Any]]) -> None:
    path = _get_local_settings_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("[settings_storage] 로컬 설정 파일 저장 실패: %s", exc)


# MongoDB helper: try to use existing MongoConnector if available
def _get_mongo_collection():
    """
    가능하면 MongoConnector를 사용하여 'app_settings' 컬렉션을 ��환합니다.
    실패하면 None을 반환합니다.
    """
    try:
        # 프로젝트의 mongo wrapper가 src.data_01.mongodb.mongo_db.MongoConnector 같은 위치에 있다고 가정
        from src.data_01.mongodb.mongo_db import MongoConnector  # type: ignore
        connector = MongoConnector()
        if getattr(connector, "db", None) is None:
            # connector.connect() 호출 가능하면 시도
            try:
                connector.connect()
            except Exception:
                pass
        db = getattr(connector, "db", None)
        if db is not None:
            return db["app_settings"]
    except Exception:
        # 경고성 로그는 디버깅에서만 출력
        logger.debug("[settings_storage] MongoConnector 로드 실패 또는 DB 미사용 (폴백 로컬 파일 사용)")
    return None


def _serialize_value(v: Any) -> Any:
    """
    저장 가능한 형태로 직렬화.
    - 기본 ���입 / 리스트 / dict -> JSON 그대로 사용
    - 그 외(예: datetime 등) -> ISO 문자열로 변환
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
    _serialize_value 와 반대 작업: datetime 등 복원 시도
    """
    if isinstance(raw, dict) and raw.get("__type") == "datetime" and "iso" in raw:
        try:
            return datetime.fromisoformat(raw["iso"])
        except Exception:
            return raw["iso"]
    return raw


def save_setting(namespace: str, key: str, value: Any) -> bool:
    """
    설정 저장
    Args:
        namespace: 논리적 그룹 (예: "backfill")
        key: 설정 키 (예: "collect_mode")
        value: 저장할 값 (가능하면 JSON 직렬화 가능)
    Returns:
        성공 여부 (bool)
    """
    ns = str(namespace)
    k = str(key)
    payload = {
        "namespace": ns,
        "key": k,
        "value": _serialize_value(value),
        "updated_at": _now_iso(),
    }

    # 1) 시도: MongoDB
    col = _get_mongo_collection()
    if col is not None:
        try:
            # upsert style
            col.update_one({"namespace": ns, "key": k}, {"$set": payload}, upsert=True)
            logger.debug("[settings_storage] MongoDB에 설정 저장: %s.%s", ns, k)
            return True
        except Exception as exc:
            logger.warning("[settings_storage] MongoDB 저장 실패(로컬로 폴백): %s", exc)

    # 2) 로컬 파일 폴백
    try:
        store = _load_local_store()
        if ns not in store:
            store[ns] = {}
        store[ns][k] = payload
        _save_local_store(store)
        logger.debug("[settings_storage] 로컬 파일에 설정 저장: %s.%s", ns, k)
        return True
    except Exception as exc:
        logger.error("[settings_storage] 설정 저장 실패: %s", exc)
        return False


def load_setting(namespace: str, key: str, default: Optional[Any] = None) -> Any:
    """
    설정 불러오기. 저장된 값이 없으면 default 반환.
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
            logger.debug("[settings_storage] MongoDB load 실패 (로컬 폴백): %s", exc)

    # 2) 로컬 파일
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
        logger.warning("[settings_storage] 로컬 설정 불러오기 실패: %s", exc)
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
            logger.debug("[settings_storage] MongoDB 삭제 실패: %s", exc)
    # 로컬 폴백
    try:
        store = _load_local_store()
        if ns in store and k in store[ns]:
            del store[ns][k]
            _save_local_store(store)
        return True
    except Exception as exc:
        logger.warning("[settings_storage] 로컬 설정 삭제 실패: %s", exc)
        return False


def list_namespace(namespace: str) -> Dict[str, Any]:
    """
    네임스페이스에 속한 모든 설정 반환 (key -> 값)
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
            logger.debug("[settings_storage] MongoDB list 실패: %s", exc)
    # 로컬
    try:
        store = _load_local_store()
        ns_store = store.get(ns, {})
        for k, v in ns_store.items():
            out[k] = _deserialize_value(v.get("value"))
    except Exception as exc:
        logger.debug("[settings_storage] 로컬 list 실패: %s", exc)
    return out