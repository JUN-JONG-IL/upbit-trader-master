"""
[Purpose]
헬스체크 엔드포인트

[Responsibilities]
- 서비스 상태 확인
- WebSocket 연결 상태
- DB 연결 상태
"""

from fastapi import APIRouter
from typing import Dict, Any
import server.static as static

router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """헬스체크"""
    ws_connected = False
    db_connected = False
    
    if hasattr(static, 'chart') and static.chart is not None:
        ws_connected = static.chart.alive
    
    try:
        if hasattr(static, 'data_manager') and static.data_manager is not None:
            db_connected = True
    except:
        pass
    
    status = "healthy" if (ws_connected and db_connected) else "degraded"
    
    return {
        "status": status,
        "ws_connected": ws_connected,
        "db_connected": db_connected,
        "message": "서비스가 정상적으로 실행 중입니다." if status == "healthy" else "일부 서비스가 실행되지 않았습니다."
    }
