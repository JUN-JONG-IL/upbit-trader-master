# src/10_trade/oems — OEMS (Order Execution & Management System) 책임 및 템플릿

목표
- 레포의 주문 집행 계층(OEMS)을 명확히 정의하고, 모의/실거래 라우팅, 리스크 검사, 원장(ledger) 기록 책임을 분리합니다.
- 스프린트 1 산출물(간단 PoC)을 빠르게 작성/검증할 수 있도록 구현 우선순위, 인터페이스, 예제 시그니처, 테스트 체크리스트를 제공합니다.

설계 원칙 (필수)
- 단일 책임: 각 모듈은 한 가지 책임(리스크 검증 / 라우팅 / 원장 기록 / 시뮬레이션)만 가집니다.
- 멱등성: 모든 외부 요청/주문에는 client_oid 또는 trace_id를 포함하여 멱등성 보장.
- 비동기 우선: 네트워크 I/O는 비동기(AsyncIO)로 구현.
- 안전성 우선: Redis Lua(atomic pre-check), DB 트랜잭션, DLQ(재시도/휴지통) 패턴을 사용.
- 테스트 가능성: 각 기능은 단위 테스트와 통합 테스트로 검증 가능해야 함.

권장 디렉터리/파일 (초기)
- src/10_trade/oems/__init__.py
- src/10_trade/oems/risk.py           — 리스크 체크(동기/비동기 인터페이스)
- src/10_trade/oems/router.py         — 주문 라우팅(SOR) / 분할
- src/10_trade/oems/ledger.py         — 원장(orders_ledger) 기록 / idempotent insert
- src/10_trade/oems/adapter_upbit.py  — 거래소 어댑터(REST/WebSocket) 샘플(추후)
- README.md (이 파일)

우선 구현 항목(스프린트1 우선순위)
1. risk.py (PoC)
   - 잔고/사용가능성 검사(동시성 안전성: Redis Lua 사용 권장)
   - 주문 사이즈/레버리지/마진 체크
   - API: async def check_order(order) -> (bool, reason)
2. ledger.py (PoC)
   - idempotent 기록 함수: async def record_order(order) -> bool
   - 실패시 재시도/로그
3. router.py (PoC)
   - 단순 SOR: 시장/거래소 선호도에 따른 라우팅(동일한 주문을 분할하여 여러 엔드포인트로 전송하지는 않음; PoC는 단일 라우팅)
   - API: async def route_order(order) -> execution_plan
4. sim/연동: 시뮬레이션 엔진(외부 또는 내부 모듈)으로 주문을 전송하는 스텁 구현

Order 데이터 모델(권장 필드)
- client_oid: str (클라이언트 제공 멱등성 ID)
- trace_id: str (분산 추적용)
- user_id: str
- symbol: str (예: KRW-BTC)
- side: str ("buy"|"sell")
- order_type: str ("limit"|"market")
- price: Decimal | None
- quantity: Decimal
- timestamp: ISO8601 str
- metadata: dict (optional, 예: algo, tag)

risk.py — 예제 시그니처 (설계 문서)
- check_order(order: Dict) -> Dict:
  - 반환 예:
    {
      "ok": True,
      "reason": "",
      "reserved": {"balance": 123.45, "locked": 10.0}
    }

ledger.py — 예제 시그니처 (설계 문서)
- record_order(order: Dict) -> Dict:
  - idempotent 동작 (client_oid 혹은 trace_id 사용)
  - 반환 예: {"ok": True, "order_id": "ledger-xxxxx", "inserted": True}

router.py — 예제 시그니처 (설계 문서)
- route_order(order: Dict) -> Dict:
  - 반환 예: execution_plan: {"target": "sim"|"upbit", "instructions": [...]}

통합 흐름 (단순화 PoC)
1. API 수신 → validate payload
2. call risk.check_order(order) — 실패면 reject
3. call ledger.record_order(order) — 성공시 proceed
4. call router.route_order(order) -> execution_plan
5. execute against adapter (sim 또는 exchange adapter)
6. record execution/confirmation → update ledger / publish event (Kafka/Redis)

Redis Lua 권장 스니펫 (pre-trade atomic check)
- 기능: 사용자 잔고에서 주문 금액을 원자적으로 차감하고, locked 필드에 적재
```lua
local user_key = KEYS[1]
local amount = tonumber(ARGV[1])
local avail = tonumber(redis.call('HGET', user_key, 'available') or '0')
if avail >= amount then
  redis.call('HINCRBYFLOAT', user_key, 'available', -amount)
  redis.call('HINCRBYFLOAT', user_key, 'locked', amount)
  return 1
else
  return 0
end