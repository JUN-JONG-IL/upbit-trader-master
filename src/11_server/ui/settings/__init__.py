"""
[Purpose]
ui/settings/ - ?쒕쾭 諛?DB ?ㅼ젙 UI ?⑦궎吏

[Responsibilities]
- ServerSettingsWidget re-export
- TimescaleDB/MongoDB/Redis/Kafka/ClickHouse 紐⑤땲?곕쭅 ?ㅼ씠?쇰줈洹?re-export (data_01濡??대룞??
- 媛?DB蹂??대윭?ㅽ꽣/釉뚮줈而??ㅻ뱶 紐⑤땲?곕쭅 ???꾩젽 re-export

[Notes]
- DB蹂??ㅼ젙 UI ??媛?DB 紐⑤뱢??ui/ ?대뜑濡??대룞: src/data_01/{db}/ui/
- ?섏쐞 ?명솚?깆쓣 ?꾪빐 ??__init__.py ?먯꽌 ??export
"""
import os as _os
import sys as _sys

# src/data_01/ 瑜?sys.path ??異붽??섏뿬 DB ?ㅼ젙 UI ?꾪룷??媛?ν븯寃???
_data_dir = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "data_01"
))
if _data_dir not in _sys.path:
    _sys.path.insert(0, _data_dir)

from .widget_server_settings import ServerSettingsWidget

# TimescaleDB ?ㅼ젙 UI (src/data_01/timescale/ui/ 濡??대룞)
try:
    from timescale.ui.timescale_settings_dialog import TimescaleSettingsDialog
    from timescale.ui.widget_timescale_settings import TimescaleClusterTab
except ImportError:
    TimescaleSettingsDialog = None  # type: ignore[assignment]
    TimescaleClusterTab = None  # type: ignore[assignment]

# MongoDB ?ㅼ젙 UI (src/data_01/mongodb/ui/ 濡??대룞)
try:
    from mongodb.ui.mongodb_settings_dialog import MongoDBSettingsDialog
except ImportError:
    MongoDBSettingsDialog = None  # type: ignore[assignment]

# Redis ?ㅼ젙 UI (src/data_01/redis/ui/ 濡??대룞)
try:
    from redis.ui.redis_settings_dialog import RedisSettingsDialog
    from redis.ui.widget_redis_settings import RedisClusterTab
except ImportError:
    RedisSettingsDialog = None  # type: ignore[assignment]
    RedisClusterTab = None  # type: ignore[assignment]

# Kafka ?ㅼ젙 UI (src/data_01/kafka/ui/ 濡??대룞)
try:
    from kafka.ui.kafka_settings_dialog import KafkaSettingsDialog
    from kafka.ui.widget_kafka_settings import KafkaBrokersTab
except ImportError:
    KafkaSettingsDialog = None  # type: ignore[assignment]
    KafkaBrokersTab = None  # type: ignore[assignment]

# ClickHouse ?ㅼ젙 UI (src/data_01/clickhouse/ui/ 濡??대룞)
try:
    from clickhouse.ui.clickhouse_settings_dialog import ClickHouseSettingsDialog
    from clickhouse.ui.widget_clickhouse_settings import ClickHouseShardsTab
except ImportError:
    ClickHouseSettingsDialog = None  # type: ignore[assignment]
    ClickHouseShardsTab = None  # type: ignore[assignment]

__all__ = [
    "ServerSettingsWidget",
    "TimescaleSettingsDialog",
    "MongoDBSettingsDialog",
    "RedisSettingsDialog",
    "KafkaSettingsDialog",
    "ClickHouseSettingsDialog",
    "TimescaleClusterTab",
    "RedisClusterTab",
    "KafkaBrokersTab",
    "ClickHouseShardsTab",
]


