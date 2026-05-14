# 비즈니스 로직 (scanner/logic)

## 개요

`logic/` 패키지는 스캐너의 핵심 비즈니스 로직을 담당합니다.

---

## 파일 구조

| 파일 | 설명 |
|------|------|
| `scanner_engine.py` | 메인 스캔 엔진 (병렬 처리, 캐싱) |
| `scanner_rules.py` | 기본 룰 (RSI, 골든크로스, 거래량, OHLC) |
| `scanner_rules_extended.py` | 확장 룰 (18개 지표 그룹) |
| `condition_builder.py` | settings dict → ConditionGroup 변환 |
| `filter_engine.py` | 스캔 결과 후처리 필터 |
| `preset_manager.py` | 프리셋 저장/로드 |

---

## 사용 예제

```python
from scanner.logic import ScannerEngine, ConditionBuilder, FilterEngine, PresetManager

# 스캔 실행
engine = ScannerEngine()
results = asyncio.run(engine.scan(settings))

# 조건 빌드
builder = ConditionBuilder()
group = builder.from_settings(settings)

# 필터 적용
engine2 = FilterEngine(settings)
filtered = engine2.apply(results)

# 프리셋 관리
pm = PresetManager()
pm.save("내 프리셋", settings)
loaded = pm.load("내 프리셋")
```
