# app/ — 서버 애플리케이션 핵심 모듈

## 개요

FastAPI 기반 서버 애플리케이션의 핵심 구현체입니다.
WebSocket 실시간 스트리밍, 정적 파일, API 엔드포인트 등을 포함합니다.

## 주요 파일 및 폴더

| 경로 | 역할 |
|---|---|
| `server.py` | FastAPI/uvicorn 기반 DataManager, SaveManager, RequestManager |
| `data_manager.py` | 경량 DataManager (의존성 미설치 환경 폴백) |
| `api/` | API 라우트 및 미들웨어 정의 |
| `endpoints/` | health, metrics 엔드포인트 |
| `static/` | 정적 파일 서빙 모듈 |
| `websocket/` | 실시간 스트림 핸들러 (chart, scanner) |

## 사용 예시

```python
from src.11_server.app import DataManager, SaveManager, RequestManager

manager = DataManager()
manager.start()
```

## 이름 변경 내역

- `src/11_server/server/` → `src/11_server/app/` (Flask/FastAPI 표준 명명, 중복 명명 제거)
