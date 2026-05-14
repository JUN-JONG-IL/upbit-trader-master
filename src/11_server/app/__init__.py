"""
[Purpose]
- 서버/데이터관리 패키지(app)의 공식 인입점(export).

[Responsibilities]
- DataManager (FastAPI/uvicorn API), SaveManager, RequestManager 등 대표 객체 export.
- server.py 의 의존 패키지(apscheduler, pymongo 등)가 미설치된 환경에서는
  data_manager.py 의 경량 DataManager 를 폴백으로 제공한다.
"""

# 전체 기능 서버(server.py) 임포트 시도 — 의존 패키지가 없으면 경량 폴백 사용
try:
    from .server import DataManager, SaveManager, RequestManager
except ImportError:
    # apscheduler, pymongo, uvicorn 등 미설치 환경 폴백
    try:
        from .data_manager import DataManager  # type: ignore
    except ImportError:
        DataManager = None  # type: ignore
    SaveManager = None  # type: ignore
    RequestManager = None  # type: ignore

__all__ = ["DataManager", "SaveManager", "RequestManager"]