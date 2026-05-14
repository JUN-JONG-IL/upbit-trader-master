"""
?대뜑 紐⑹쟻: ?곗씠??怨꾩링(MongoDB/Motor, Redis, SQLAlchemy ?? ?듯빀 IO ?몃뱾?? 
?곸슜 ?ㅽ깮: Python 3.11, motor, redis, sqlalchemy, orjson, dask, polars, pandas  
[Purpose]
- NoSQL/SQL/罹먯떆 寃쎌쑀 ?곗씠???낆텧?? ??⑸웾 理쒖쟻?? 罹먯떆 ?곕룞, 遺꾩궛泥섎━ 吏??
"""
import logging
import asyncio
import importlib
import importlib.util
import os
import sys
from typing import Optional

import pandas as pd
import polars as pl
import motor.motor_asyncio
from pymongo import CursorType, IndexModel, ASCENDING
import sqlalchemy
import orjson

# Import the PyPI 'redis' package, bypassing the local 'redis' package in src/data_01/.
# The local redis package (src/data_01/redis/) would otherwise shadow the PyPI package
# when src/data_01/ is on sys.path.
def _load_external_redis():
    """Load the PyPI redis package from site-packages, avoiding local namespace collision."""
    our_data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # mongodb/
    data_dir = os.path.dirname(our_data_dir)  # src/data_01/
    local_redis_dir = os.path.realpath(os.path.join(data_dir, 'redis'))
    for entry in sys.path:
        if not entry:
            continue
        candidate = os.path.join(entry, 'redis', '__init__.py')
        if not os.path.isfile(candidate):
            continue
        candidate_dir = os.path.realpath(os.path.join(entry, 'redis'))
        # Skip if this candidate is our own local redis package
        if candidate_dir == local_redis_dir:
            continue
        try:
            spec = importlib.util.spec_from_file_location('_ext_redis_for_handler', candidate)
            if spec is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            if hasattr(mod, 'Redis'):
                return mod
        except Exception:
            continue
    return None

_redis_lib = _load_external_redis()
if _redis_lib is None:
    try:
        import redis as _redis_lib  # type: ignore  # may find local package but try anyway
    except ImportError:
        _redis_lib = None

# NOTE: dask.dataframe import is intentionally lazy below to avoid import-time
# compatibility issues between dask and pandas (see runtime logs). Use
# _get_dask_dataframe() to obtain the module if available.
_dask_dataframe = None


def _get_redis_url() -> str:
    """config.yaml 湲곕컲 Redis URL 諛섑솚 (fallback: ?ы듃 58530, password=dummy)"""
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parents[3] / "01_core" / "database" / "redis_factory.py"
        spec = importlib.util.spec_from_file_location("_redis_factory_mh", str(_factory_path))
        if spec is not None:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod.get_redis_url()
    except Exception:
        pass
    return "redis://:dummy@127.0.0.1:58530/0"


def _get_dask_dataframe():
    """
    Lazy import for dask.dataframe. Returns the module or None on failure.
    This avoids import-time failures that may occur when pandas/dask attempt
    to bind accessors during module load.
    """
    global _dask_dataframe
    if _dask_dataframe is not None:
        return _dask_dataframe
    try:
        import dask.dataframe as dd  # type: ignore
        _dask_dataframe = dd
        return _dask_dataframe
    except Exception as e:
        logging.warning("dask.dataframe import failed: %s", e, exc_info=False)
        _dask_dataframe = None
        return None


class DBHandler:
    """MongoDB/SQL/Redis/DF ?듯빀 ?몃뱾??""
    def __init__(self,
                 ip='localhost',
                 port=27017,
                 id=None,
                 password=None,
                 loop=None):
        self.ip = ip
        self.port = port
        self.id = id
        self.password = password
        # ID/PW ?놁쑝硫??몄쬆 ?놁씠 ?곌껐
        if self.id is not None and self.password is not None:
            self.host = f'mongodb://{self.id}:{self.password}@{self.ip}:{self.port}'
        else:
            self.host = f'mongodb://{self.ip}:{self.port}'
        if loop:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(self.host, io_loop=loop)
            self.loop = loop
        else:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(self.host)
        # RDB ?붿쭊(SQLAlchemy, ?덉떆: SQLite, ?뺤옣 媛??
        self.engine = sqlalchemy.create_engine('sqlite:///trade.db')
        # Redis ?대씪?댁뼵??(config.yaml 湲곕컲)
        if _redis_lib is not None and hasattr(_redis_lib, 'from_url'):
            self.redis = _redis_lib.from_url(_get_redis_url(), decode_responses=True)
        elif _redis_lib is not None and hasattr(_redis_lib, 'Redis'):
            self.redis = _redis_lib.Redis.from_url(_get_redis_url(), decode_responses=True)
        else:
            self.redis = None

    async def ensure_index(self, db_name: str, collection_name: str):
        """collection??time ?몃뜳???앹꽦(?깅뒫 理쒖쟻??"""
        collection = self.client[db_name][collection_name]
        await collection.create_indexes([IndexModel([("time", ASCENDING)])])

    async def insert_item_one(self, data: dict = None, db_name: str = None, collection_name: str = None) -> str:
        """Document 1媛???? RDB/Redis ?숈떆 ?숆린??""
        await self.ensure_index(db_name, collection_name)
        # orjson.dumps -> bytes, loads -> python object (to ensure serializable)
        data_serialized = orjson.loads(orjson.dumps(data))
        result = await self.client[db_name][collection_name].insert_one(data_serialized)
        # RDB (?덉떆) - convert to pandas for SQL append
        try:
            pd.DataFrame([data_serialized]).to_sql(collection_name, self.engine, if_exists='append', index=False)
        except Exception:
            logging.exception("RDB insert failed for single item; continuing")
        # Redis cache
        key = f"{db_name}:{collection_name}:{data_serialized.get('_id', str(result.inserted_id))}"
        if self.redis is not None:
            try:
                self.redis.set(key, orjson.dumps(data_serialized))
            except Exception:
                logging.exception("Redis set failed for key %s", key)
        return str(result.inserted_id)

    async def insert_item_many(self, data: list, db_name: str, collection_name: str, ordered: bool = False) -> list:
        """Document ?ㅼ닔 ??? RDB/Redis??蹂묐젹 泥섎━ (batching)."""
        await self.ensure_index(db_name, collection_name)
        batch_size = 1000
        results = []

        # Use polars for fast ingestion; convert to pandas chunks for DB insert.
        try:
            pl_df = pl.DataFrame(data)
        except Exception:
            # fallback: build pandas directly
            pl_df = None

        dd_mod = _get_dask_dataframe()

        if dd_mod is not None and pl_df is not None:
            # preferred path: try to use dask from polars converted to pandas first
            try:
                pandas_df = pl_df.to_pandas()
                # create dask dataframe if desired (but we'll batch via pandas for motor)
                ddf = dd_mod.from_pandas(pandas_df, npartitions=4)
                pdf = ddf.compute()
            except Exception as e:
                logging.warning("dask processing failed in insert_item_many, falling back to pandas: %s", e, exc_info=False)
                pdf = pl_df.to_pandas()
        else:
            # fallback: polars -> pandas or direct pandas
            if pl_df is not None:
                pdf = pl_df.to_pandas()
            else:
                pdf = pd.DataFrame(data)

        # iterate in batches using the pandas DataFrame
        for i in range(0, len(pdf), batch_size):
            chunk = pdf.iloc[i:i + batch_size]
            batch = chunk.to_dict(orient='records')
            # ensure JSON serializable
            batch_serialized = [orjson.loads(orjson.dumps(d)) for d in batch]
            try:
                result = await self.client[db_name][collection_name].insert_many(batch_serialized, ordered=ordered)
                results.extend(list(map(str, result.inserted_ids)))
            except Exception:
                logging.exception("Mongo insert_many failed for batch starting at %d", i)
                # try per-document insert as fallback
                for doc in batch_serialized:
                    try:
                        r = await self.client[db_name][collection_name].insert_one(doc)
                        results.append(str(r.inserted_id))
                    except Exception:
                        logging.exception("Mongo insert_one failed for doc: %s", doc)

            # RDB append
            try:
                chunk.to_sql(collection_name, self.engine, if_exists='append', index=False)
            except Exception:
                logging.exception("RDB append failed for batch starting at %d", i)

            # Redis cache set
            if self.redis is not None:
                try:
                    for doc in batch_serialized:
                        key = f"{db_name}:{collection_name}:{doc.get('_id', '')}"
                        self.redis.set(key, orjson.dumps(doc))
                except Exception:
                    logging.exception("Redis set failed for batch starting at %d", i)

        return results

    async def find_item_one(self, condition: dict = None, db_name: str = None, collection_name: str = None) -> dict:
        """罹먯떆 ?곗꽑, ?놁쑝硫?DB?먯꽌 1媛?議고쉶"""
        cache_key = f"{db_name}:{collection_name}:{orjson.dumps(condition).decode()}"
        if self.redis is not None:
            try:
                cached = self.redis.get(cache_key)
                if cached:
                    return orjson.loads(cached)
            except Exception:
                logging.exception("Redis get failed for key %s", cache_key)

        result = await self.client[db_name][collection_name].find_one(condition, {"_id": False})
        if result and self.redis is not None:
            try:
                self.redis.set(cache_key, orjson.dumps(result))
            except Exception:
                logging.exception("Redis set failed for key %s", cache_key)
        return result

    async def find_item(self, condition: dict = None, db_name: str = None, collection_name: str = None):
        """???議고쉶, Dask DF濡?遺꾩궛 蹂??(?놁쑝硫?pandas DataFrame 諛섑솚)"""
        cursor = self.client[db_name][collection_name].find(
            condition or {}, {"_id": False}, no_cursor_timeout=True, cursor_type=CursorType.EXHAUST)
        data = await cursor.to_list(length=None)
        dd_mod = _get_dask_dataframe()
        if dd_mod is not None:
            try:
                return dd_mod.from_pandas(pd.DataFrame(data), npartitions=4)
            except Exception:
                logging.warning("dask.from_pandas failed, returning pandas DataFrame instead", exc_info=False)
        # fallback: return pandas DataFrame (caller may convert)
        return pd.DataFrame(data)

    async def delete_item_one(self, condition: dict = None, db_name: str = None, collection_name: str = None):
        """?꾪걧癒쇳듃 1媛???젣"""
        return await self.client[db_name][collection_name].delete_one(condition)

    async def delete_item_many(self, condition: dict = None, db_name: str = None, collection_name: str = None):
        """?щ윭媛???젣"""
        return await self.client[db_name][collection_name].delete_many(condition)

    async def update_item_one(self, condition: dict = None, update_value=None, db_name: str = None, collection_name: str = None):
        """?꾪걧癒쇳듃 1媛??낅뜲?댄듃"""
        return await self.client[db_name][collection_name].update_one(filter=condition, update=update_value)

    async def update_item_many(self, condition: dict = None, update_value=None, db_name: str = None, collection_name: str = None):
        """?щ윭媛??낅뜲?댄듃"""
        return await self.client[db_name][collection_name].update_many(filter=condition, update=update_value)

    async def text_search(self, text=None, db_name: str = None, collection_name: str = None):
        """?띿뒪???몃뜳???꾩껜 寃??""
        return self.client[db_name][collection_name].find({"$text": {"$search": text}})


# ?섑뵆 ?ㅽ뻾/?뚯뒪??
async def main():
    import server.static as static
    db = DBHandler(
        ip=static.config.mongo_ip,
        port=static.config.mongo_port,
        id=static.config.mongo_id,
        password=static.config.mongo_password,
    )
    # ?덉떆: 'candles' DB??'KRW-ADA_minute_1' 而щ젆?섏뿉???꾩껜(?대┝李⑥닚)
    data = await db.find_item(condition=None, db_name='candles', collection_name='KRW-ADA_minute_1')
    # data may be a dask.dataframe or pandas.DataFrame depending on availability
    if hasattr(data, "compute"):
        try:
            df = data.compute().sort_values('time', ascending=False)
        except Exception:
            # fallback to converting via pandas
            df = pd.DataFrame(await (db.client['candles']['KRW-ADA_minute_1'].find().to_list(length=None)))
    else:
        df = data.sort_values('time', ascending=False)

    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time', inplace=False)
    # Resampling
    RESAMPLING = 'B'
    new_df = pd.DataFrame()
    new_df['open'] = df.open.resample(RESAMPLING).first()
    new_df['high'] = df.high.resample(RESAMPLING).max()
    new_df['low'] = df.low.resample(RESAMPLING).min()
    new_df['close'] = df.close.resample(RESAMPLING).last()
    new_df['volume'] = df.volume.resample(RESAMPLING).sum()
    new_df = new_df.sort_index(ascending=True)
    print(new_df)


if __name__ == '__main__':
    import asyncio
    import server.static as static
    from config import Config
    static.config = Config()
    static.config.load()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
