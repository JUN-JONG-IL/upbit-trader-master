# 백그라운드 워커 (scanner/workers)

## 개요

`workers/` 패키지는 PyQt5 QThread 기반 백그라운드 작업 클래스를 포함합니다.

---

## 파일 구조

| 파일 | 설명 |
|------|------|
| `scanner_worker.py` | 스캔 실행 QThread |
| `data_fetcher.py` | OHLCV 데이터 일괄 취득 QThread |

---

## ScannerWorker

```python
from scanner.workers import ScannerWorker

worker = ScannerWorker(settings)
worker.scan_finished.connect(on_results)    # [(symbol, interval, score), ...]
worker.progress_updated.connect(on_prog)   # (current, total)
worker.error_occurred.connect(on_error)    # error message
worker.start()
worker.stop()  # 중단
```

## DataFetcher

```python
from scanner.workers import DataFetcher

fetcher = DataFetcher(['KRW-BTC', 'KRW-ETH'], 'minute5', 200)
fetcher.fetch_all_done.connect(on_done)     # {symbol: DataFrame}
fetcher.data_fetched.connect(on_single)    # (symbol, DataFrame)
fetcher.progress_updated.connect(on_prog)  # (current, total)
fetcher.start()
```

---

## 레이트리밋

`DataFetcher`는 Upbit API 레이트리밋(초당 10 요청)을 준수하여 요청 간 0.1초 대기합니다.
