# workers/ — 백그라운드 계산 워커

## 개요

백그라운드에서 지속적으로 계산 작업을 처리하는 워커 클래스 모음입니다.

## 주요 클래스

| 클래스 | 파일 | 역할 |
|---|---|---|
| `ComputeWorker` | `compute_worker.py` | 계산 프로세스 백그라운드 워커 |
| `AggregationWorker` | `aggregation_worker.py` | 집계 작업 워커 |
| `SchedulerWorker` | `scheduler_worker.py` | 주기적 계산 스케줄러 |

## 사용 예시

```python
from src.compute.workers import ComputeWorker

worker = ComputeWorker()
await worker.run()
```
