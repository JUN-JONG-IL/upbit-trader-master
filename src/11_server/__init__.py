"""
[Purpose]
src.11_server - 서버 및 API 계층

[Responsibilities]
- FastAPI 기반 API Gateway
- WebSocket 실시간 통신
- TimescaleDB → Redis 자동 동기화
- Gap Detection 워커
- Rate Limit 및 인증 미들웨어

[Structure]
- core/: FastAPI 앱, WebSocket, 세션 관리
- api/: REST API 엔드포인트
- workers/: 백그라운드 작업
- middleware/: Rate Limit, 인증, CORS
- ui/: 서버 설정 및 모니터링 UI
- config/: 서버/Redis 설정
- utils/: 공통 유틸리티

[Backward Compatibility]
기존 경로 (component/, app/, settings/) 는 그대로 유지됩니다.

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

# ── 신규 구조 re-export ────────────────────────────────────────────────────────
from .core.fastapi_app import app as FastAPIApp, create_app
from .core.websocket_manager import WebSocketManager
from .core.session_manager import SessionManager
from .workers.data_sync import DataSyncWorker, hydrate_redis
from .workers.gap_detector import GapDetector, detect_gaps
from .workers.aggregator import Aggregator, refresh_cagg
from .config.server_config import ServerConfig
from .config.redis_config import RedisConfig

# ── 기존 구조 re-export (Backward Compatibility) ──────────────────────────────
try:
    from .app.server import DataManager, SaveManager, RequestManager
except ImportError:
    pass

try:
    from .component.component import RealtimeManager, Account, Coin
except ImportError:
    pass

try:
    from .settings import SettingsWidget
except ImportError:
    pass

__all__ = [
    # 신규
    "FastAPIApp",
    "create_app",
    "WebSocketManager",
    "SessionManager",
    "DataSyncWorker",
    "hydrate_redis",
    "GapDetector",
    "detect_gaps",
    "Aggregator",
    "refresh_cagg",
    "ServerConfig",
    "RedisConfig",
    # 하위 호환
    "DataManager",
    "SaveManager",
    "RequestManager",
    "RealtimeManager",
    "Account",
    "Coin",
    "SettingsWidget",
]
