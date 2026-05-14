"""
[Purpose]
ui/settings/ - 서버 및 DB 설정 UI 패키지

[Responsibilities]
- ServerSettingsWidget re-export
- TimescaleDB/MongoDB/Redis/Kafka/ClickHouse 모니터링 다이얼로그 re-export (02_data로 이동됨)
- 각 DB별 클러스터/브로커/샤드 모니터링 탭 위젯 re-export

[Notes]
- DB별 설정 UI 는 각 DB 모듈의 ui/ 폴더로 이동: src/02_data/{db}/ui/
- 하위 호환성을 위해 이 __init__.py 에서 재-export
"""
import os as _os
import sys as _sys

# src/02_data/ 를 sys.path 에 추가하여 DB 설정 UI 임포트 가능하게 함
_data_dir = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "02_data"
))
if _data_dir not in _sys.path:
    _sys.path.insert(0, _data_dir)

from .widget_server_settings import ServerSettingsWidget

# TimescaleDB 설정 UI (src/02_data/timescale/ui/ 로 이동)
try:
    from timescale.ui.timescale_settings_dialog import TimescaleSettingsDialog
    from timescale.ui.widget_timescale_settings import TimescaleClusterTab
except ImportError:
    TimescaleSettingsDialog = None  # type: ignore[assignment]
    TimescaleClusterTab = None  # type: ignore[assignment]

# MongoDB 설정 UI (src/02_data/mongodb/ui/ 로 이동)
try:
    from mongodb.ui.mongodb_settings_dialog import MongoDBSettingsDialog
except ImportError:
    MongoDBSettingsDialog = None  # type: ignore[assignment]

# Redis 설정 UI (src/02_data/redis/ui/ 로 이동)
try:
    from redis.ui.redis_settings_dialog import RedisSettingsDialog
    from redis.ui.widget_redis_settings import RedisClusterTab
except ImportError:
    RedisSettingsDialog = None  # type: ignore[assignment]
    RedisClusterTab = None  # type: ignore[assignment]

# Kafka 설정 UI (src/02_data/kafka/ui/ 로 이동)
try:
    from kafka.ui.kafka_settings_dialog import KafkaSettingsDialog
    from kafka.ui.widget_kafka_settings import KafkaBrokersTab
except ImportError:
    KafkaSettingsDialog = None  # type: ignore[assignment]
    KafkaBrokersTab = None  # type: ignore[assignment]

# ClickHouse 설정 UI (src/02_data/clickhouse/ui/ 로 이동)
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

