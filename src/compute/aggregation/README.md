# aggregation/ — 데이터 집계

## 개요

틱 데이터를 초/분/시/일/주/월/년 단위 캔들로 롤업하는 집계 로직입니다.

## 주요 클래스

| 클래스 | 파일 | 역할 |
|---|---|---|
| `TickAggregator` | `tick_aggregator.py` | 틱 → 초 단위 캔들 변환 |
| `OHLCVAggregator` | `ohlcv_aggregator.py` | OHLCV 상위 단위 롤업 |
| `VolumeAggregator` | `volume_aggregator.py` | 거래량 집계 |

## 사용 예시

```python
from src.compute.aggregation import TickAggregator

agg = TickAggregator(interval_seconds=1)
candle = agg.process(tick_data)
```
