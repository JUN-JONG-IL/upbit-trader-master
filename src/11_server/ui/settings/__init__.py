"""
[Purpose]
ui/settings/ - ?œë²„ ë°?DB ?¤ì • UI ?¨í‚¤ì§€

[Responsibilities]
- ServerSettingsWidget re-export
- TimescaleDB/MongoDB/Redis/Kafka/ClickHouse ëª¨ë‹ˆ?°ë§ ?¤ì´?¼ë¡œê·?re-export (data_01ë¡??´ë™??
- ê°?DBë³??´ëŸ¬?¤í„°/ë¸Œë¡œì»??¤ë“œ ëª¨ë‹ˆ?°ë§ ???„ì ¯ re-export

[Notes]
- DBë³??¤ì • UI ??ê°?DB ëª¨ë“ˆ??ui/ ?´ë”ë¡??´ë™: src/data_01/{db}/ui/
- ?˜ìœ„ ?¸í™˜?±ì„ ?„í•´ ??__init__.py ?ì„œ ??export
"""
import os as _os
import sys as _sys

# src/data_01/ ë¥?sys.path ??ì¶”ê??˜ì—¬ DB ?¤ì • UI ?„í¬??ê°€?¥í•˜ê²???
_data_dir = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "data_01"
))
if _data_dir not in _sys.path:
    _sys.path.insert(0, _data_dir)

from .widget_server_settings import ServerSettingsWidget

# TimescaleDB ?¤ì • UI (src/data_01/timescale/ui/ ë¡??´ë™)
try:
    from timescale.ui.timescale_settings_dialog import TimescaleSettingsDialog
    from timescale.ui.widget_timescale_settings import TimescaleClusterTab
except ImportError:
    TimescaleSettingsDialog = None  # type: ignore[assignment]
    TimescaleClusterTab = None  # type: ignore[assignment]

# MongoDB ?¤ì • UI (src/data_01/mongodb/ui/ ë¡??´ë™)
try:
    from mongodb.ui.mongodb_settings_dialog import MongoDBSettingsDialog
except ImportError:
    MongoDBSettingsDialog = None  # type: ignore[assignment]

# Redis ?¤ì • UI (src/data_01/redis/ui/ ë¡??´ë™)
try:
    from redis.ui.redis_settings_dialog import RedisSettingsDialog
    from redis.ui.widget_redis_settings import RedisClusterTab
except ImportError:
    RedisSettingsDialog = None  # type: ignore[assignment]
    RedisClusterTab = None  # type: ignore[assignment]

# Kafka ?¤ì • UI (src/data_01/kafka/ui/ ë¡??´ë™)
try:
    from kafka.ui.kafka_settings_dialog import KafkaSettingsDialog
    from kafka.ui.widget_kafka_settings import KafkaBrokersTab
except ImportError:
    KafkaSettingsDialog = None  # type: ignore[assignment]
    KafkaBrokersTab = None  # type: ignore[assignment]

# ClickHouse ?¤ì • UI (src/data_01/clickhouse/ui/ ë¡??´ë™)
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


