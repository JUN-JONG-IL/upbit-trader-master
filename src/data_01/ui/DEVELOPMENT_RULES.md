# data_01/ui 개발 규칙

## 파일 크기 원칙 (R-06)
- **각 파일 최대 500줄** 엄격 준수
- 기능 추가 시 기존 파일이 아닌 **별도 Mixin/모듈에 작성** 후 import

## 모듈 구조
```
status_widget/    ← StatusWidget 패키지 (Mixin 분리)
tabs/             ← 탭별 UI 로직 (탭당 1개 .py + 1개 .ui)
controllers/      ← 백그라운드 컨트롤러 (헬스체크, 지표 수집 등)
dialogs/          ← 팝업 다이얼로그
widgets/          ← 재사용 위젯 컴포넌트
utils/            ← 공통 유틸리티 (DB 커넥터, 포맷터 등)
```

## 기능 추가 가이드
1. 새 기능 → 기존 파일에 추가 **금지**
2. 새 기능의 종류 판별:
   - DB 조회 로직 → `utils/data_queries.py` 또는 `utils/db_status.py`
   - UI 상태 업데이트 → 해당 탭의 `_tab_xxx.py`
   - 백그라운드 작업 → `controllers/` 내 새 파일
   - 새 설정 항목 → `dialogs/` 내 해당 다이얼로그
3. 파일이 400줄을 넘으면 **즉시 분리** (500줄 한도 도달 전)

## 절대 규칙

| 번호 | 규칙 |
|------|------|
| R-01 | 모든 패키지 디렉터리에 `__init__.py` 필수 |
| R-02 | 패키지 내부 임포트는 상대 임포트 사용 (`.module`) |
| R-06 | 파일당 최대 500~700줄 준수. 초과 시 SRP에 따라 분리 |
| R-09 | 모든 함수·메서드에 Python Type Hints 100% 적용 |
| R-14 | 클래스·주요 함수에 Docstring (인자/반환/예외) 명시 |
| R-17 | UI 메인 스레드에서 DB 조회 금지 |
| R-18 | 백그라운드 스레드에서 UI 위젯 직접 변경 금지 — 시그널/슬롯 사용 |
| R-19 | 공유 자원은 Lock/Mutex 사용 |
| R-30 | `except Exception: pass` 절대 금지 — 예외 명시 + 로깅 |

## status_widget 패키지 구조

```
status_widget/
├── __init__.py            ← StatusWidget re-export
├── widget.py              ← StatusWidget 메인 클래스 (init, closeEvent, public API)
├── tab_manager.py         ← TabManagerMixin (_init_tabs)
├── controller_manager.py  ← ControllerManagerMixin (컨트롤러 초기화, WebSocket 관리)
├── signal_handlers.py     ← SignalHandlersMixin (헬스/메트릭/WebSocket 시그널 처리)
├── ui_updaters.py         ← UIUpdatersMixin (flow 레이블, 통신 테이블, 업타임 등)
├── log_streaming.py       ← LogStreamingMixin (QtLogHandler, MonitoringWorker)
└── settings_handler.py    ← SettingsHandlerMixin (설정 저장/복원, 다이얼로그)
```

## Mixin 상속 순서 주의사항

- Python MRO(Method Resolution Order) 주의: `QWidget`은 항상 마지막에 상속
- Mixin 간 직접 import 금지 — `TYPE_CHECKING`으로 타입 힌트만 사용
- `@pyqtSlot` 데코레이터는 Mixin 클래스에 정의된 슬롯에도 적용 가능
