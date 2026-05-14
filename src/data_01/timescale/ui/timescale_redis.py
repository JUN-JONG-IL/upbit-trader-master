# name=src/data_01/timescale/ui/timescale_redis.py
# -*- coding: utf-8 -*-
"""
Redis ?†Ìã∏
- redis.asyncio ?∞ÏÑ†, ?ÜÏúºÎ©?redis-py(?ôÍ∏∞) ?¨Ïö©
- enqueue_tasks(tasks) Î°?ZSET???àÏ†Ñ???±Î°ù
"""

from __future__ import annotations

import os
import json
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("timescale.redis")
if logger.level == 0:
    logger.setLevel(logging.INFO)

DEFAULT_REDIS_URL = os.getenv("UPBIT_REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
DEFAULT_ZSET_KEY = os.getenv("GAP_ZSET_KEY", "gap_fill_queue")


def get_redis_client():
    """redis.asyncio ?∞ÏÑ†, ?ÜÏúºÎ©?redis(?ôÍ∏∞). ?§Ìå®?òÎ©¥ None Î∞òÌôò."""
    try:
        import redis.asyncio as _redis_async  # type: ignore
        return _redis_async.from_url(DEFAULT_REDIS_URL)
    except Exception:
        pass
    try:
        import redis as _redis  # type: ignore
        return _redis.from_url(DEFAULT_REDIS_URL, decode_responses=False)
    except Exception as e:
        logger.debug("[timescale_redis] redis ?¥Îùº?¥Ïñ∏???ùÏÑ± ?§Ìå®: %s", e, exc_info=True)
        return None


def _serialize(ev: Dict[str, Any]) -> str:
    try:
        return json.dumps(ev, ensure_ascii=False)
    except Exception:
        return str(ev)


def enqueue_tasks(tasks: List[Tuple[Dict[str, Any], float]], zset_key: str = DEFAULT_ZSET_KEY) -> Tuple[int, List[str]]:
    """
    tasks: [(event_dict, score), ...]
    Î∞òÌôò: (?±Î°ù?? ?§Î•òÎ™©Î°ù)
    """
    client = get_redis_client()
    if client is None:
        return 0, ["redis client ?ùÏÑ± ?§Ìå®"]
    added = 0
    errors: List[str] = []

    # async client ?êÏ†ï
    if client.__class__.__module__.startswith("redis.asyncio"):
        import asyncio
        async def _push_async():
            nonlocal added
            for ev, score in tasks:
                try:
                    member = _serialize(ev)
                    await client.zadd(zset_key, {member: float(score)})
                    added += 1
                except Exception as e:
                    logger.debug("[timescale_redis] async zadd ?§Ìå®: %s", e, exc_info=True)
                    errors.append(str(e))
            try:
                await client.close()
            except Exception:
                pass
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_push_async())
    else:
        try:
            for ev, score in tasks:
                try:
                    member = _serialize(ev)
                    client.zadd(zset_key, {member: float(score)})
                    added += 1
                except Exception as e:
                    logger.debug("[timescale_redis] sync zadd ?§Ìå®: %s", e, exc_info=True)
                    errors.append(str(e))
        finally:
            try:
                client.close()
            except Exception:
                pass

    return added, errors
