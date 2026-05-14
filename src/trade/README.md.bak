# src/10_trade 폴더

## 목적
upbit-trader 플랫폼의 **주문 실행 및 리스크 관리 모듈**을 제공합니다.

## 폴더 구조

```
src/10_trade/
├── core/               # 주문 실행 엔진, 포지션 관리, 유효성 검증
├── risk/               # 리스크 서비스, 포지션 사이징, 손절 전략
├── orders/             # 주문 타입별 처리 (시장가/지정가/스탑/트레일링) + UI
│   ├── market_order.py
│   ├── limit_order.py
│   ├── stop_order.py
│   ├── trailing_stop.py
│   └── ui/             # 매수/매도 주문 위젯 (TradeWidget)
├── ui/                 # 주문 입력·시그널·주문 내역 UI 위젯
│   ├── trade/          # 매수/매도 주문 위젯
│   ├── signals/        # 시그널 리스트/선택 위젯
│   └── order_history/  # 주문 내역 위젯
├── workers/            # 백그라운드 QThread 워커
└── utils/              # 공통 유틸리티 (포맷터, 헬퍼)
```

## 각 폴더 설명

### core/ - 주문 실행 엔진

주문 실행의 핵심 로직을 담당합니다.

**주요 클래스**:
- `OrderEngine`: 시장가/지정가/스탑/트레일링스탑 주문 실행, 멱등성 키(client_order_id) 관리
- `PositionManager`: 보유 포지션 추적, 평균 매수가, 미실현 PnL 계산
- `TradeValidator`: 주문 파라미터 유효성 검사, 잔고 확인, 중복 주문 방지

**사용 예시**:
```python
from src.10_trade.core import OrderEngine, PositionManager, TradeValidator

engine = OrderEngine()
result = engine.place_order(
    market="KRW-BTC",
    side="bid",
    order_type="limit",
    price=50_000_000,
    volume=0.001,
)

pm = PositionManager()
pm.update_position("KRW-BTC", volume=0.001, avg_buy_price=50_000_000)
pnl = pm.calculate_pnl("KRW-BTC", current_price=52_000_000)
```

### risk/ - 리스크 관리

주문 전 종합 리스크 점검 및 포지션 사이징 전략을 제공합니다.

**주요 클래스**:
- `RiskService`: 개별 주문 리스크 점검, 일간 손실 한도, 익스포저 제어
- `PositionSizing`: 고정 금액 / 고정 비율 / 켈리 기준 / 리스크 패리티
- `StopLoss`: 고정 비율 / 트레일링 / ATR 기반 손절가 계산

**사용 예시**:
```python
from src.10_trade.risk import RiskService, PositionSizing, StopLoss

risk = RiskService(max_order_amount=1_000_000, daily_loss_limit=500_000)
ok, reason = risk.check_order_risk({"price": 50_000_000, "volume": 0.01})

size = PositionSizing.fixed_percentage(total_assets=10_000_000, ratio=0.05)
stop = StopLoss.fixed_rate(entry_price=50_000_000, stop_rate=0.03)
```

### orders/ - 주문 타입 (통합)

각 주문 타입의 파라미터 조립 로직을 분리합니다.

**주요 클래스**:
- `MarketOrder`: 시장가 매수/매도 파라미터 빌더
- `LimitOrder`: 지정가 매수/매도 파라미터 빌더
- `StopOrder`: 스탑 주문 파라미터 빌더 및 트리거 판단
- `TrailingStop`: 트레일링 스탑 최고가 추적 및 손절가 동적 관리

**사용 예시**:
```python
from src.10_trade.orders import LimitOrder, TrailingStop

params = LimitOrder().build_bid("KRW-BTC", price=50_000_000, volume=0.001)

ts = TrailingStop(trail_rate=0.03)
ts.update(current_price=52_000_000)
if ts.is_triggered(current_price=50_440_000):
    print(f"손절 트리거! 스탑가: {ts.stop_price:,}")
```

### ui/ - UI 위젯

**하위 폴더**:
- `trade/`: 매수/매도 주문 입력 위젯 (`TradeWidget`)
- `signals/`: 시그널 리스트(`SignallistWidget`) 및 시그널 선택(`SignalselectWidget`)
- `order_history/`: 주문 내역 테이블 위젯 (`OrderHistoryWidget`)

**사용 예시**:
```python
from src.10_trade.ui import TradeWidget, SignallistWidget, OrderHistoryWidget

trade_widget = TradeWidget()
trade_widget.update_symbol("KRW-BTC")
```

### workers/ - 백그라운드 워커

QThread 기반 비동기 처리를 담당합니다.

**주요 클래스**:
- `TradeWorker`: 체결/미체결 주문 주기적 조회 → `orders_updated` 시그널
- `PositionMonitor`: 포지션 상태 모니터링 → `positions_updated`, `stop_loss_triggered` 시그널

**사용 예시**:
```python
from src.10_trade.workers import TradeWorker

worker = TradeWorker(interval_ms=3000)
worker.orders_updated.connect(my_slot)
worker.start()
```

### utils/ - 공통 유틸리티

**주요 모듈**:
- `order_helpers.py`: `format_price()`, `format_quantity()`, `calculate_total()`, `generate_client_order_id()`
- `trade_formatter.py`: `TradeFormatter` – 주문 상태/방향 코드 한국어 변환, 타임스탬프 포맷

**사용 예시**:
```python
from src.10_trade.utils import format_price, generate_client_order_id, TradeFormatter

print(format_price(50_123_456.789))          # "50,123,456"
print(TradeFormatter.status("wait"))          # "미체결"
print(TradeFormatter.side("bid"))             # "매수"
order_id = generate_client_order_id()        # "upbit-xxxxxxxx-xxxx-..."
```

## 하위 호환성

기존 import 경로는 shim을 통해 계속 동작합니다:

```python
# 구 경로 (여전히 동작 — orders/ shim)
from src.10_trade.orders import TradeWidget
from src.10_trade.signals import SignallistWidget, SignalselectWidget
from src.10_trade.orders.ui import TradeWidget
from src.10_trade.signals.ui import SignallistWidget, SignalselectWidget

# 신 경로 (권장)
from src.10_trade.ui.trade import TradeWidget
from src.10_trade.ui.signals import SignallistWidget, SignalselectWidget

# 주문 타입 (신 경로)
from src.10_trade.orders import LimitOrder, MarketOrder, StopOrder, TrailingStop
```

## 개발 가이드

### 폴더 네이밍 규칙
- 기능 도메인 단위 폴더 구성: `core`, `risk`, `orders`, `ui`, `workers`, `utils`
- UI 파일은 반드시 `ui/` 하위에 도메인별로 분리

### import 패턴
- `from __future__ import annotations` 최상단 선언
- PyQt5 import는 try/except로 감싸 테스트 환경에서도 동작 보장

### 파일 크기
- 파일 1개당 500줄 이하 유지

---

**작성**: Copilot Workspace Refactor
**날짜**: 2026-03-15
