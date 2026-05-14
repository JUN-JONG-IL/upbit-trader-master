# Scanner 패키지

## 개요

`scanner/` 패키지는 종목 스캐너의 모든 기능을 포함하는 메인 패키지입니다.

---

## 하위 패키지

| 패키지 | 설명 |
|--------|------|
| `ui/` | PyQt5 UI 위젯 및 팝업 |
| `logic/` | 스캔 엔진, 룰, 조건 빌더, 필터 |
| `workers/` | QThread 기반 백그라운드 워커 |
| `models/` | 데이터 모델 (dataclass) |
| `indicators/` | 기술 지표 계산 함수 |
| `patterns/` | 캔들/차트 패턴 감지 함수 |
| `tests/` | 단위 테스트 |
| `docs/` | 아키텍처, API, 예제 문서 |

---

## UI 매핑

- `ScannerFrameWidget` ↔ `widget_scanner_frame.ui`
  - `settingsButton`: 설정창 열기
  - `refreshButton`: 즉시 스캔 실행
  - `autoRefreshCheckBox`: 자동 갱신 on/off
  - `remainingTimeLabel`: 다음 갱신까지 남은 시간 표시
  - `progressBar`: 스캔 진행률
  - `searchTable`: 결과 목록(코인명, 분봉)

---

## 공개 심볼

```python
from scanner import (
    # UI
    ScannerFrameWidget, ScannerSettingsPopup, ScannerSettingsAdvancedPopup,
    # Logic
    ScannerEngine, RULES, PresetManager, ConditionBuilder, FilterEngine,
    # Workers
    ScannerWorker, DataFetcher,
    # Models
    ScanResult, Condition, ConditionGroup, ConditionOperator, Preset,
)
```

---

## 주의사항

- GUI 스레드 블로킹 금지: 스캔은 `ScannerWorker(QThread)`에서 수행
- 레이트리밋 준수: `DataFetcher`에서 초당 10 요청 제한 적용
- `.ui` 파일 직접 수정 금지