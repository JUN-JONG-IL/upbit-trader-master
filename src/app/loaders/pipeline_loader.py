#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline 통합 로더 (정석적 경로 우선, shim 제거)

주요 변경/보완:
- src 루트 계산을 더 견고하게 함 (상위에서 'src' 디렉토리 발견을 우선).
- 파일로 로드한 모듈을 sys.modules에 등록하여 내부 import 안정성 보강.
- static.log 우선 사용 유지, 없으면 모듈 로거 또는 print 폴백.
- repo-wide heavy search 제거 (성능/노이즈 문제 회피).
- Noop 대체는 유지(PIPELINE_ALLOW_NOOP=True 기본)하여 안전하게 앱이 동작하도록 함.
- ✅ Stager/Finalizer 주기적 flush 자동 시작 추가
- ✅ Timescale 관련 모듈에서 get_timescale_connector() 호출을 시도하여
      connector/전역풀을 pg_pool 후보로 사용하는 로직을 보강.
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import os
import sys
import traceback
import pathlib
from typing import Any, Optional, Iterable, Dict, List, Tuple

_logger = logging.getLogger("app.loaders.pipeline_loader")


def _log(static: Any, level: str, msg: str, *args) -> None:
    """static.log가 있으면 사용, 없으면 모듈 로거 또는 print 폴백."""
    try:
        log_obj = getattr(static, "log", None)
        if log_obj is not None and hasattr(log_obj, level):
            getattr(log_obj, level)(msg % args if args else msg)
            return
    except Exception:
        pass
    try:
        getattr(_logger, level)(msg % args if args else msg)
        return
    except Exception:
        pass
    try:
        print(msg % args if args else msg)
    except Exception:
        pass


def _short_list(iterable: Iterable, limit: int = 20) -> List[Any]:
    """디버그 출력을 위해 리스트를 짧게 줄임."""
    try:
        lst = list(iterable)
        if len(lst) > limit:
            return lst[:limit] + ["...(+%d more)" % (len(lst) - limit)]
        return lst
    except Exception:
        return ["<unreadable>"]


def _debug_component_failure(static: Any, name: str, mod: Optional[Any], obj: Any, avail: Dict[str, Any], exc: Exception) -> None:
    """
    인스턴스 생성 실패 시 상세 디버그를 남김.
    """
    try:
        _log(static, "error", "[pipeline_loader] %s instantiation FAILED: %s", name, str(exc))
        if mod is not None:
            mf = getattr(mod, "__file__", "<built-in/module>")
            _log(static, "debug", "[pipeline_loader] %s module file: %s", name, mf)
            try:
                attrs = sorted([a for a in dir(mod) if not a.startswith("_")])
                _log(static, "debug", "[pipeline_loader] %s module public attrs: %s", name, _short_list(attrs, 50))
            except Exception:
                _log(static, "debug", "[pipeline_loader] %s module attrs: <unreadable>", name)
        else:
            _log(static, "debug", "[pipeline_loader] %s module: None", name)

        try:
            if inspect.isclass(obj):
                _log(static, "debug", "[pipeline_loader] attempted class: %s", f"{obj.__module__}.{obj.__name__}")
                try:
                    sig = inspect.signature(obj)
                    _log(static, "debug", "[pipeline_loader] constructor signature for %s: %s", name, sig)
                except Exception:
                    _log(static, "debug", "[pipeline_loader] could not obtain constructor signature for %s", name)
            elif callable(obj):
                _log(static, "debug", "[pipeline_loader] attempted factory/callable: %s", getattr(obj, "__name__", repr(obj)))
                try:
                    sig = inspect.signature(obj)
                    _log(static, "debug", "[pipeline_loader] factory signature for %s: %s", name, sig)
                except Exception:
                    _log(static, "debug", "[pipeline_loader] could not obtain factory signature for %s", name)
            else:
                _log(static, "debug", "[pipeline_loader] attempted object (non-callable): %s", repr(obj))
        except Exception:
            _log(static, "debug", "[pipeline_loader] object introspection failed for %s", name)

        try:
            summary = {k: (None if v is None else type(v).__name__) for k, v in avail.items()}
            _log(static, "debug", "[pipeline_loader] resources available for %s: %s", name, summary)
        except Exception:
            _log(static, "debug", "[pipeline_loader] failed to summarize available resources for %s", name)

        tb = traceback.format_exc()
        _log(static, "debug", "[pipeline_loader] traceback for %s:\n%s", name, tb)
    except Exception:
        try:
            print("[pipeline_loader] debug logging failed for", name)
            traceback.print_exc()
        except Exception:
            pass


def _load_module_from_file(path: str, alias: str) -> Optional[Any]:
    """
    파일 경로에서 모듈 로드 시도. 성공 시 sys.modules에 alias로 등록하여
    모듈 내부의 상대/절대 import가 안정적으로 동작하도록 함.
    """
    try:
        if not os.path.isfile(path):
            return None
        spec = importlib.util.spec_from_file_location(alias, path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            # 조기 등록(상호참조를 안정화)
            try:
                sys.modules[alias] = mod
            except Exception:
                pass
            spec.loader.exec_module(mod)
            _log(None, "debug", "[pipeline_loader] file-loaded module %s from %s", alias, path)
            return mod
    except Exception:
        _log(None, "debug", "[pipeline_loader] file load failed for %s: %s", path, traceback.format_exc())
    return None


def _try_candidates_with_file(candidates: Iterable[str], file_relpath: Optional[str], static: Any, src_root: str) -> Optional[Any]:
    """
    후보 네임스페이스들을 순차 import 시도하고, 실패하면 src_root + file_relpath 를 file-load 시도.
    file_relpath은 src 루트 기준 상대경로(예: 'data_01/pipeline/processor.py').
    """
    tried: List[Tuple[str, str]] = []

    # 1) namespace imports (정석적 순서)
    for nm in candidates:
        if not nm:
            continue
        if nm in sys.modules:
            try:
                mod = sys.modules[nm]
                _log(static, "debug", "[pipeline_loader] module already loaded: %s -> %s", nm, getattr(mod, "__file__", None))
                return mod
            except Exception:
                pass
        try:
            mod = importlib.import_module(nm)
            _log(static, "debug", "[pipeline_loader] import success: %s -> %s", nm, getattr(mod, "__file__", None))
            return mod
        except Exception as e:
            tried.append((nm, f"{type(e).__name__}: {e}"))
            _log(static, "debug", "[pipeline_loader] import %s failed: %s", nm, f"{type(e).__name__}: {e}")

    # 2) file-level load from src root (정석적, 소스 우선)
    if file_relpath:
        try:
            fp = os.path.join(src_root, file_relpath)
            exists = os.path.isfile(fp)
            _log(static, "debug", "[pipeline_loader] file candidate: %s exists=%s", fp, exists)
            if exists:
                alias = f"file_candidate_{os.path.basename(fp)}"
                mod = _load_module_from_file(fp, alias=alias)
                if mod is not None:
                    _log(static, "debug", "[pipeline_loader] file load success: %s", fp)
                    return mod
                else:
                    _log(static, "debug", "[pipeline_loader] file load failed (spec.exec failed): %s", fp)
        except Exception as e:
            _log(static, "debug", "[pipeline_loader] file candidate check failed: %s -> %s", file_relpath, f"{type(e).__name__}: {e}")

    _log(static, "debug", "[pipeline_loader] no module found for candidates or file: %s / %s", list(candidates), file_relpath)
    return None


# -----------------------------
# A) pg_pool 탐색 자동화 (강화)
# -----------------------------
def _discover_pg_pool(static: Any) -> Optional[Any]:
    """
    static 및 static.data_manager에서 가능한 pg_pool 후보들을 찾아 반환.
    또한 timescale 관련 모듈에서 get_timescale_connector() 호출을 시도하여
    connector/전역풀을 후보로 포함합니다.
    반환값은 'pool' 형태 또는 Connector 객체(실행/커밋/ executemany 지원)를 허용합니다.
    """
    candidates = [
        "pg_pool", "pool", "engine", "db_pool", "connection_pool", "asyncpg_pool", "sa_engine", "sqlalchemy_engine",
        "timescale_pool", "timescale_pg_pool", "pg_engine", "postgres_pool"
    ]

    # 1) top-level static attributes
    for name in candidates:
        try:
            if hasattr(static, name):
                val = getattr(static, name)
                if val is not None:
                    _log(static, "debug", "[pipeline_loader] discovered pg candidate on static: %s -> %s", name, type(val).__name__)
                    return val
        except Exception:
            continue

    # 2) static.data_manager attributes
    dm = getattr(static, "data_manager", None)
    if dm is not None:
        for name in candidates:
            try:
                if hasattr(dm, name):
                    val = getattr(dm, name)
                    if val is not None:
                        _log(static, "debug", "[pipeline_loader] discovered pg candidate on data_manager: %s -> %s", name, type(val).__name__)
                        return val
            except Exception:
                continue

        for fn_name in ("get_pg_pool", "get_pool", "get_pg_engine", "get_sqlalchemy_engine"):
            try:
                fn = getattr(dm, fn_name, None)
                if callable(fn):
                    val = fn()
                    if val is not None:
                        _log(static, "debug", "[pipeline_loader] discovered pg candidate via data_manager.%s -> %s", fn_name, type(val).__name__)
                        return val
            except Exception:
                continue

    # 3) timescale 관련 모듈에서 connector 얻기 시도 (강화)
    try:
        try:
            ts_mod = importlib.import_module("data_01.timescale.timescale_db")
        except Exception:
            # 파일 레벨로 직접 로드 시도 (비패키지 실행 환경)
            base = pathlib.Path(__file__).resolve().parents[1]  # project/src/.. -> project
            ts_path = base / "src" / "data_01" / "timescale" / "timescale_db.py"
            if ts_path.exists():
                ts_mod = _load_module_from_file(str(ts_path), alias="file_timescale_timescale_db")
            else:
                ts_mod = None
        if ts_mod is not None:
            # 우선, 모듈 내부에서 이미 pool/pg_pool 같은 심볼이 있는지 체크
            for name in ("pg_pool", "pool", "timescale_pool"):
                try:
                    if hasattr(ts_mod, name):
                        val = getattr(ts_mod, name)
                        if val is not None:
                            _log(static, "debug", "[pipeline_loader] discovered pg candidate on %s.%s -> %s", getattr(ts_mod, "__name__", "timescale_db"), name, type(val).__name__)
                            return val
                except Exception:
                    continue
            # 다음으로 get_timescale_connector 시도 (자동 초기화 포함)
            get_conn_fn = getattr(ts_mod, "get_timescale_connector", None)
            if callable(get_conn_fn):
                try:
                    _log(static, "debug", "[pipeline_loader] calling get_timescale_connector() to obtain connector/pool candidate")
                    connector = get_conn_fn()
                    if connector is not None:
                        _log(static, "debug", "[pipeline_loader] get_timescale_connector returned: %s", type(connector).__name__)
                        return connector
                except Exception as e:
                    _log(static, "debug", "[pipeline_loader] get_timescale_connector() call failed: %s", e)
    except Exception:
        _log(static, "debug", "[pipeline_loader] timescale module discovery failed: %s", traceback.format_exc())

    # 4) module-level minimal fallbacks (예전 방식 유지)
    for mod_name in ("data_01.timescale.timescale_db",):
        try:
            mod = importlib.import_module(mod_name)
            for name in ("pg_pool", "pool", "engine"):
                if hasattr(mod, name):
                    val = getattr(mod, name)
                    if val is not None:
                        _log(static, "debug", "[pipeline_loader] discovered pg candidate on module %s.%s -> %s", mod_name, name, type(val).__name__)
                        return val
        except Exception:
            continue

    _log(static, "debug", "[pipeline_loader] no pg_pool-like resource discovered")
    return None


# -----------------------------
# Noop 대체 클래스들 (최소 동작 보장)
# -----------------------------
class NoopWriter:
    def __init__(self, *args, **kwargs):
        _log(None, "debug", "NoopWriter created")

    def write_candles(self, *args, **kwargs):
        _log(None, "debug", "NoopWriter.write_candles called (no-op)")

    def close(self):
        _log(None, "debug", "NoopWriter.close called (no-op)")


class NoopMetadataManager:
    def __init__(self, *args, **kwargs):
        _log(None, "debug", "NoopMetadataManager created")

    def get(self, *args, **kwargs):
        return None

    def ensure_indexes(self, *args, **kwargs):
        _log(None, "debug", "NoopMetadataManager.ensure_indexes called (no-op)")


class NoopStager:
    def __init__(self, *args, **kwargs):
        _log(None, "debug", "NoopStager created")

    def stage(self, *args, **kwargs):
        _log(None, "debug", "NoopStager.stage called (no-op)")


class NoopFinalizer:
    def __init__(self, *args, **kwargs):
        _log(None, "debug", "NoopFinalizer created")

    def finalize(self, *args, **kwargs):
        _log(None, "debug", "NoopFinalizer.finalize called (no-op)")


class NoopIsolator:
    def __init__(self, *args, **kwargs):
        _log(None, "debug", "NoopIsolator created")

    def isolate(self, *args, **kwargs):
        _log(None, "debug", "NoopIsolator.isolate called (no-op)")


# -----------------------------
# 헬퍼: 인스턴스화 / 팩토리 호출 (기존 로직 유지)
# -----------------------------
def _instantiate_class_with_best_args(cls: Any, avail: Dict[str, Any], static: Any, extra: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    try:
        sig = inspect.signature(cls)
    except Exception:
        try:
            return cls()
        except Exception as e:
            _log(static, "debug", "[pipeline_loader] direct cls() failed: %s", e)
            return None

    params = sig.parameters
    kwargs: Dict[str, Any] = {}
    combined = dict(avail)
    if extra:
        combined.update(extra)

    mapping = {
        "stager": ["stager", "stage"],
        "finalizer": ["finalizer", "finalise", "finalize"],
        "writer": ["writer", "candle_writer", "cw"],
        "isolator": ["isolator"],
        "metadata": ["metadata", "meta"],
        "redis_client": ["redis_client", "redis"],
        "kafka_producer": ["kafka_producer", "kafka"],
        "validator": ["validator"],
        "concurrency": ["concurrency", "max_workers", "workers"],
        "publish_to_redis": ["publish_to_redis"],
        "publish_to_kafka": ["publish_to_kafka"],
    }

    for key, names in mapping.items():
        for name in names:
            if name in params and key in combined and combined[key] is not None:
                kwargs[name] = combined[key]
                break

    for name in ("pg_pool", "pool", "db_pool"):
        if name in params and combined.get("pg_pool") is not None:
            kwargs[name] = combined["pg_pool"]

    for p in ("static", "config", "settings"):
        if p in params:
            kwargs[p] = getattr(static, "config", None) or static
            break

    try:
        _log(static, "debug", "[pipeline_loader] attempting instantiate %s with kwargs=%s", getattr(cls, "__name__", repr(cls)), {k: (type(v).__name__ if v is not None else None) for k, v in kwargs.items()})
        if kwargs:
            return cls(**kwargs)
        else:
            try:
                return cls()
            except TypeError:
                try:
                    return cls(static)
                except Exception:
                    return None
    except Exception as e:
        _log(static, "debug", "[pipeline_loader] instantiate failed for %s with kwargs=%s: %s", getattr(cls, "__name__", repr(cls)), kwargs, str(e))
        return None


def _call_factory_with_best_args(factory: Any, avail: Dict[str, Any], static: Any) -> Optional[Any]:
    try:
        sig = inspect.signature(factory)
    except Exception:
        try:
            return factory()
        except Exception as e:
            _log(static, "debug", "[pipeline_loader] factory direct call failed: %s", e)
            return None

    params = sig.parameters
    kwargs: Dict[str, Any] = {}
    if "static" in params:
        kwargs["static"] = static
    if "config" in params:
        kwargs["config"] = getattr(static, "config", None) or static
    for key in ("stager", "finalizer", "writer", "isolator", "metadata", "redis_client", "kafka_producer", "pg_pool"):
        if key in params and key in avail and avail[key] is not None:
            kwargs[key] = avail[key]
    try:
        _log(static, "debug", "[pipeline_loader] calling factory %s with kwargs=%s", getattr(factory, "__name__", repr(factory)), {k: (type(v).__name__ if v is not None else None) for k, v in kwargs.items()})
        if kwargs:
            return factory(**kwargs)
        else:
            return factory()
    except Exception as e:
        _log(static, "debug", "[pipeline_loader] factory call failed with kwargs=%s: %s", kwargs, str(e))
        return None


# -----------------------------
# main setup_pipeline (정석적)
# -----------------------------
def _find_src_root(start: str) -> str:
    """
    start 경로에서 위로 올라가며 'src' 디렉토리를 찾는다. 못 찾으면 start의 상위 3단계 디렉토리를 사용.
    """
    p = os.path.abspath(start)
    for _ in range(6):
        candidate = os.path.join(p, "src")
        if os.path.isdir(candidate):
            return os.path.abspath(candidate)
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    # fallback: 상위 3단계를 src_root로 간주
    return os.path.abspath(os.path.join(start, "..", "..", ".."))


def setup_pipeline(static: Any) -> None:
    """
    Pipeline 구성요소를 동적으로 로드하고 PipelineProcessor 인스턴스를 생성하여
    static.processor에 등록합니다.

    설계 원칙: shim/비정상 후보 제거, src 루트 기준의 표준 경로 우선, 파일 이동 금지.
    """
    _log(static, "info", "[pipeline_loader] setup_pipeline invoked")
    try:
        # 더 견고한 src_root 계산
        here = os.path.dirname(os.path.abspath(__file__))
        src_root = _find_src_root(here)

        # --------------------
        # PipelineProcessor 로드 (정석 경로만)
        # --------------------
        proc_candidates = ("data_01.pipeline.processor",)
        proc_relpath = os.path.join("data_01", "pipeline", "processor.py")
        proc_mod = _try_candidates_with_file(proc_candidates, proc_relpath, static, src_root)
        if proc_mod is None:
            _log(static, "info", "[pipeline_loader] PipelineProcessor not found — skipping pipeline setup (candidates tried logged)")
            return

        PipelineProcessor = getattr(proc_mod, "PipelineProcessor", None)
        create_processor_fn = getattr(proc_mod, "create_processor", None) or getattr(proc_mod, "create_pipeline_processor", None)
        if PipelineProcessor is None and not callable(create_processor_fn):
            _log(static, "warning", "[pipeline_loader] PipelineProcessor class or factory missing in module — skipping")
            return

        _log(static, "info", "[pipeline_loader] PipelineProcessor module loaded from %s", getattr(proc_mod, "__file__", None))

        # --------------------
        # 리소스 수집 (pg_pool, redis, kafka, data_manager)
        # --------------------
        pg_pool = _discover_pg_pool(static)
        redis_client = getattr(static, "redis_client", None) or getattr(getattr(static, "data_manager", None), "redis_client", None)
        kafka_producer = getattr(static, "kafka_producer", None)
        data_manager = getattr(static, "data_manager", None)

        avail: Dict[str, Any] = {
            "pg_pool": pg_pool,
            "redis_client": redis_client,
            "kafka_producer": kafka_producer,
            "data_manager": data_manager,
        }
        _log(static, "debug", "[pipeline_loader] resource summary: %s", {k: (None if v is None else type(v).__name__) for k, v in avail.items()})

        allow_noop = getattr(static, "PIPELINE_ALLOW_NOOP", True)

        # --------------------
        # MetadataManager (정상 경로 우선, 파일 폴백)
        # --------------------
        metadata = None
        meta_candidates = ("data_01.pipeline.metadata_manager", "data_01.mongodb.metadata_manager")
        meta_relpath = os.path.join("data_01", "pipeline", "metadata_manager.py")
        meta_mod = _try_candidates_with_file(meta_candidates, meta_relpath, static, src_root)

        if meta_mod is None:
            # try mongodb metadata file as secondary explicit path
            mongo_rel = os.path.join("data_01", "mongodb", "metadata_manager.py")
            meta_mod = _try_candidates_with_file((), mongo_rel, static, src_root)

        if meta_mod is not None:
            create_meta_fn = getattr(meta_mod, "create_metadata_manager", None) or getattr(meta_mod, "get_metadata_manager", None)
            MetadataManager = getattr(meta_mod, "MetadataManager", None)
            mongo_db = None
            if data_manager is not None and hasattr(data_manager, "db"):
                mongo_db = getattr(data_manager, "db")
            else:
                try:
                    mmod = _try_candidates_with_file(("data_01.mongodb.init_mongodb",), os.path.join("data_01", "mongodb", "init_mongodb.py"), static, src_root)
                    get_db = getattr(mmod, "get_db", None) if mmod is not None else None
                    if callable(get_db):
                        mongo_db = get_db()
                except Exception:
                    mongo_db = None

            if callable(create_meta_fn):
                try:
                    # 시그니처 기반 호출 우선
                    try:
                        sig = inspect.signature(create_meta_fn)
                        params = sig.parameters
                    except Exception:
                        params = {}
                    kwargs: Dict[str, Any] = {}
                    if "db" in params:
                        kwargs["db"] = mongo_db
                    elif "mongo_db" in params:
                        kwargs["mongo_db"] = mongo_db
                    elif "data_manager" in params and data_manager is not None:
                        kwargs["data_manager"] = data_manager
                    elif "static" in params:
                        kwargs["static"] = static

                    if kwargs:
                        metadata = create_meta_fn(**kwargs)
                    else:
                        metadata = _call_factory_with_best_args(create_meta_fn, {"mongo_db": mongo_db, "data_manager": data_manager, "pg_pool": pg_pool}, static)

                    if metadata is None:
                        try:
                            metadata = create_meta_fn(mongo_db)
                        except Exception:
                            pass

                    if metadata is not None:
                        _log(static, "info", "[pipeline_loader] MetadataManager created via factory")
                except Exception as e:
                    _debug_component_failure(static, "MetadataManagerFactory", meta_mod, create_meta_fn, avail, e)
            elif MetadataManager:
                try:
                    metadata = _instantiate_class_with_best_args(MetadataManager, {"mongo_db": mongo_db}, static)
                    if metadata is not None:
                        _log(static, "info", "[pipeline_loader] MetadataManager created (class)")
                except Exception as e:
                    _debug_component_failure(static, "MetadataManager", meta_mod, MetadataManager, avail, e)
            else:
                _log(static, "debug", "[pipeline_loader] metadata module found but no factory/class symbols present; public attrs: %s", _short_list([a for a in dir(meta_mod) if not a.startswith("_")], 60))
        else:
            _log(static, "debug", "[pipeline_loader] MetadataManager candidates tried and not found")

        if metadata is None and allow_noop:
            metadata = NoopMetadataManager()
            _log(static, "info", "[pipeline_loader] MetadataManager missing — using NoopMetadataManager (PIPELINE_ALLOW_NOOP=True)")

        # --------------------
        # CandleWriter (정석 경로 + file load)
        # --------------------
        writer = None
        CandleWriter = None
        cw_candidates = ("data_01.timescale.operations.candle_writer",)
        cw_relpath = os.path.join("data_01", "timescale", "operations", "candle_writer.py")
        cw_mod = _try_candidates_with_file(cw_candidates, cw_relpath, static, src_root)

        if cw_mod is not None:
            CandleWriter = getattr(cw_mod, "CandleWriter", None) or getattr(cw_mod, "TimescaleCandleWriter", None)
            if CandleWriter is None:
                _log(static, "debug", "[pipeline_loader] CandleWriter symbol not found in module; public attrs: %s", _short_list([a for a in dir(cw_mod) if not a.startswith("_")], 50))

        if CandleWriter and pg_pool:
            try:
                writer = _instantiate_class_with_best_args(CandleWriter, {"pg_pool": pg_pool}, static, extra={"pg_pool": pg_pool})
                if writer is not None:
                    _log(static, "info", "[pipeline_loader] CandleWriter created (Timescale pool)")
                else:
                    raise RuntimeError("CandleWriter instantiation returned None")
            except Exception as e:
                _debug_component_failure(static, "CandleWriter", cw_mod, CandleWriter, avail, e)
        else:
            reason_parts = []
            if cw_mod is None:
                reason_parts.append("module_not_found")
            elif CandleWriter is None:
                reason_parts.append("symbol_missing")
            if pg_pool is None:
                reason_parts.append("pg_pool_missing")
            _log(static, "info", "[pipeline_loader] CandleWriter not created (%s)", ", ".join(reason_parts) or "unknown")

            if writer is None and allow_noop:
                writer = NoopWriter()
                _log(static, "info", "[pipeline_loader] CandleWriter missing — using NoopWriter (PIPELINE_ALLOW_NOOP=True)")

        # --------------------
        # Stager
        # --------------------
        stager = None
        stager_candidates = ("data_01.pipeline.stager",)
        s_relpath = os.path.join("data_01", "pipeline", "stager.py")
        s_mod = _try_candidates_with_file(stager_candidates, s_relpath, static, src_root)
        if s_mod is not None:
            Stager = getattr(s_mod, "CandleStager", None) or getattr(s_mod, "Stager", None)
            if Stager:
                try:
                    stager = _instantiate_class_with_best_args(Stager, {"pg_pool": pg_pool}, static, extra={"pg_pool": pg_pool})
                    if stager is not None:
                        _log(static, "info", "[pipeline_loader] CandleStager created")
                except Exception as e:
                    _debug_component_failure(static, "CandleStager", s_mod, Stager, avail, e)
        else:
            _log(static, "debug", "[pipeline_loader] Stager candidates tried and not found")

        if stager is None and allow_noop:
            stager = NoopStager()
            _log(static, "info", "[pipeline_loader] Stager missing — using NoopStager (PIPELINE_ALLOW_NOOP=True)")

        # --------------------
        # Finalizer
        # --------------------
        finalizer = None
        f_candidates = ("data_01.pipeline.finalizer",)
        f_relpath = os.path.join("data_01", "pipeline", "finalizer.py")
        f_mod = _try_candidates_with_file(f_candidates, f_relpath, static, src_root)
        if f_mod is not None:
            Finalizer = getattr(f_mod, "CandlesFinalizer", None) or getattr(f_mod, "Finalizer", None)
            if Finalizer:
                try:
                    finalizer = _instantiate_class_with_best_args(Finalizer, {"pg_pool": pg_pool}, static, extra={"pg_pool": pg_pool})
                    if finalizer is not None:
                        _log(static, "info", "[pipeline_loader] CandlesFinalizer created")
                except Exception as e:
                    _debug_component_failure(static, "CandlesFinalizer", f_mod, Finalizer, avail, e)
        else:
            _log(static, "debug", "[pipeline_loader] Finalizer candidates tried and not found")

        if finalizer is None and allow_noop:
            finalizer = NoopFinalizer()
            _log(static, "info", "[pipeline_loader] Finalizer missing — using NoopFinalizer (PIPELINE_ALLOW_NOOP=True)")

        # --------------------
        # Isolator
        # --------------------
        isolator = None
        iso_candidates = ("data_01.pipeline.isolator",)
        iso_relpath = os.path.join("data_01", "pipeline", "isolator.py")
        iso_mod = _try_candidates_with_file(iso_candidates, iso_relpath, static, src_root)
        if iso_mod is not None:
            Isolator = getattr(iso_mod, "CandleIsolator", None) or getattr(iso_mod, "Isolator", None)
            if Isolator:
                try:
                    isolator = _instantiate_class_with_best_args(Isolator, {"pg_pool": pg_pool, "redis_client": redis_client}, static, extra={"pg_pool": pg_pool, "redis_client": redis_client})
                    if isolator is not None:
                        _log(static, "info", "[pipeline_loader] CandleIsolator created")
                except Exception as e:
                    _debug_component_failure(static, "CandleIsolator", iso_mod, Isolator, avail, e)
        else:
            _log(static, "debug", "[pipeline_loader] Isolator candidates tried and not found")

        if isolator is None and allow_noop:
            isolator = NoopIsolator()
            _log(static, "info", "[pipeline_loader] Isolator missing — using NoopIsolator (PIPELINE_ALLOW_NOOP=True)")

        # --------------------
        # Instantiate PipelineProcessor
        # --------------------
        processor = None
        avail_processor: Dict[str, Any] = {
            "stager": stager,
            "finalizer": finalizer,
            "writer": writer,
            "isolator": isolator,
            "metadata": metadata,
            "redis_client": redis_client,
            "kafka_producer": kafka_producer,
            "pg_pool": pg_pool,
            "concurrency": getattr(static, "PIPELINE_CONCURRENCY", getattr(static, "concurrency", 32)),
            "publish_to_redis": bool(redis_client),
            "publish_to_kafka": bool(kafka_producer),
        }

        if PipelineProcessor is not None and inspect.isclass(PipelineProcessor):
            _log(static, "info", "[pipeline_loader] instantiating PipelineProcessor class")
            try:
                processor = _instantiate_class_with_best_args(PipelineProcessor, avail_processor, static)
                if processor is None:
                    raise RuntimeError("PipelineProcessor instantiation returned None")
            except Exception as e:
                _debug_component_failure(static, "PipelineProcessor", proc_mod, PipelineProcessor, avail_processor, e)
        elif callable(create_processor_fn):
            _log(static, "info", "[pipeline_loader] calling PipelineProcessor factory")
            try:
                processor = _call_factory_with_best_args(create_processor_fn, avail_processor, static)
                if processor is None:
                    raise RuntimeError("PipelineProcessor factory returned None")
            except Exception as e:
                _debug_component_failure(static, "PipelineProcessorFactory", proc_mod, create_processor_fn, avail_processor, e)

        if processor is None:
            _log(static, "warning", "[pipeline_loader] PipelineProcessor instantiation failed — skipping pipeline registration")
            return

        try:
            static.processor = processor
            _log(static, "info", "[pipeline_loader] PipelineProcessor instance created and registered to static.processor")
        except Exception:
            _log(static, "warning", "[pipeline_loader] Failed to assign processor to static: %s", traceback.format_exc())
            return

        # ✅ ========================================
        # ✅ Stager 주기적 flush 시작 (30초마다)
        # ✅ ========================================
        if stager is not None and hasattr(stager, "start_periodic_flush"):
            try:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(stager.start_periodic_flush(interval_seconds=30))
                        _log(static, "info", "[pipeline_loader] CandleStager 주기적 flush 시작 (30초)")
                    else:
                        _log(static, "info", "[pipeline_loader] 이벤트 루프 미실행 - Stager 주기적 flush 스킵")
                except RuntimeError:
                    _log(static, "info", "[pipeline_loader] 이벤트 루프 없음 - Stager 주기적 flush 스킵")
            except Exception as e:
                _log(static, "warning", "[pipeline_loader] Stager 주기적 flush 시작 실패: %s", e)
        else:
            if stager is None:
                _log(static, "debug", "[pipeline_loader] Stager가 None - 주기적 flush 스킵")
            elif not hasattr(stager, "start_periodic_flush"):
                _log(static, "debug", "[pipeline_loader] Stager에 start_periodic_flush 메서드 없음")

        # ✅ ========================================
        # ✅ Finalizer 주기적 flush 시작 (기존 로직)
        # ✅ ========================================
        if finalizer is not None and hasattr(finalizer, "start_periodic_flush"):
            try:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(finalizer.start_periodic_flush())
                        _log(static, "info", "[pipeline_loader] CandlesFinalizer 주기적 flush 시작")
                    else:
                        _log(static, "info", "[pipeline_loader] 이벤트 루프 미실행 - Finalizer 주기적 flush 스킵")
                except RuntimeError:
                    _log(static, "info", "[pipeline_loader] 이벤트 루프 없음 - Finalizer 주기적 flush 스킵")
            except Exception as e:
                _log(static, "warning", "[pipeline_loader] Finalizer 주기적 flush 시작 실패: %s", e)

        # --------------------
        # Hook RealtimeManager -> processor callback
        # --------------------
        try:
            chart = getattr(static, "chart", None)
            if chart is not None:
                if hasattr(chart, "set_on_candle"):
                    try:
                        chart.set_on_candle(static.processor.process_candle)
                        _log(static, "info", "[pipeline_loader] RealtimeManager.set_on_candle connected")
                    except Exception:
                        _log(static, "warning", "[pipeline_loader] set_on_candle connection failed: %s", traceback.format_exc())
                elif hasattr(chart, "on_candle"):
                    try:
                        setattr(chart, "on_candle", static.processor.process_candle)
                        _log(static, "info", "[pipeline_loader] RealtimeManager.on_candle monkeypatched")
                    except Exception:
                        _log(static, "warning", "[pipeline_loader] on_candle monkeypatch failed: %s", traceback.format_exc())
                else:
                    for name in ("register_callback", "add_listener", "subscribe"):
                        fn = getattr(chart, name, None)
                        if callable(fn):
                            try:
                                fn(static.processor.process_candle)
                                _log(static, "info", "[pipeline_loader] RealtimeManager.%s callback registered", name)
                                break
                            except Exception:
                                _log(static, "debug", "[pipeline_loader] attempt to register via %s failed", name)
                    else:
                        _log(static, "info", "[pipeline_loader] No public API found on RealtimeManager to register on_candle callback")
        except Exception:
            _log(static, "warning", "[pipeline_loader] Hooking RealtimeManager failed: %s", traceback.format_exc())

        # --------------------
        # Register RealtimeManager to static (enables UI monitoring via get_realtime_manager())
        # --------------------
        try:
            realtime_manager = getattr(static, "chart", None)
            if realtime_manager is not None:
                static.realtime_manager = realtime_manager
                static.rt_manager = realtime_manager
                static.manager = realtime_manager
                _log(static, "info", "[pipeline_loader] RealtimeManager 등록 완료: realtime_manager, rt_manager, manager")
            else:
                _log(static, "warning", "[pipeline_loader] ⚠️ static.chart is None - RealtimeManager를 등록할 수 없습니다")
        except Exception as e:
            _log(static, "warning", "[pipeline_loader] RealtimeManager 등록 실패: %s", e)

    except Exception:
        _log(static, "error", "[pipeline_loader] Pipeline setup encountered unexpected error:\n%s", traceback.format_exc())
        return