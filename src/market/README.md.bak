# CHANGELOG
# 2026-03-16 | Copilot | 업그레이드: 03_market README v4.0. 폴더명 coinlist/trades 최신화.
# 2026-03-13 | Copilot | 업그레이드: 03_market README v3.0. 한국어 전체 템플릿으로 업그레이드.
# 2026-03-05 | Copilot | Restructure: Renamed market → symbol_list, added trade module

Version: v4.0
Last Modified: 2026-03-16
References:
  - work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md
  - work_order/DB설계.md

# src/03_market — 마켓 데이터

## 개요

업비트 거래소의 **종목 목록, 호가(오더북), 체결 데이터를 실시간으로 표시**하는 마켓 데이터 모듈입니다.
WebSocket 및 REST API를 통해 시세 데이터를 수신하고, PyQt5 위젯으로 표시합니다.
종목 선택 시그널을 통해 차트·스캐너·트레이드 모듈과 연동됩니다.

## 디렉토리 구조

```
src/03_market/
├── __init__.py                    # 모듈 진입점
├── README.md                      # 이 파일
├── coinlist/                      # 종목 목록 서브모듈
│   ├── __init__.py
│   ├── ui/                        # coin_list.ui, favorite.ui, widget_coin_list.py, widget_favorite.py
│   ├── logic/                     # 종목 정렬·필터·검색 로직
│   │   ├── formatting/
│   │   ├── scanner/
│   │   └── search/
│   ├── services/                  # 종목 데이터 서비스
│   └── workers/                   # 백그라운드 종목 업데이트 워커
├── orderbook/                     # 호가창 서브모듈
│   ├── __init__.py
│   ├── ui/                        # 호가창 위젯
│   └── logic/                     # 호가 파싱·정규화 로직
├── trades/                        # 체결 데이터 서브모듈
│   ├── __init__.py
│   ├── ui/                        # 체결 위젯
│   └── logic/                     # 체결 데이터 처리 로직
├── websocket/                     # WebSocket 클라이언트
└── rest/                          # REST API 클라이언트
```

## 주요 기능

- **종목 목록**: 업비트 전체 종목 표시, 실시간 가격·변동률·거래량 업데이트
- **검색·정렬**: 종목명/코드 검색, 다중 기준 정렬
- **즐겨찾기**: 관심 종목 등록/해제, 즐겨찾기 탭 분리
- **호가창**: 매수/매도 호가 실시간 표시, 잔량 비율 시각화
- **체결 내역**: 최근 체결가·수량·시간 실시간 스트리밍
- **종목 선택 연동**: Qt 시그널로 차트·스캐너·트레이드 위젯과 동기화

## 사용 예시

```python
from src._03_market import CoinlistWidget, OrderbookWidget, TradeWidget

# 위젯 생성
coinlist = CoinlistWidget()
orderbook = OrderbookWidget()

# 종목 선택 시 호가창 자동 업데이트
coinlist.symbol_selected.connect(orderbook.update_symbol)
coinlist.symbol_selected.connect(trade_widget.update_symbol)

coinlist.show()
orderbook.show()
```

## 의존성

- `src/01_core/` : 설정 관리, 이벤트 버스
- `src/02_data/redis/` : 실시간 시세 캐시
- `src/02_data/timescale/` : OHLCV 데이터 조회
- PyQt5 : UI 위젯
- aiohttp, websockets : WebSocket 스트리밍

## 참고 문서

- [`work_order/3_단계_MONITOR_모드_안정화.md`](../../work_order/3_단계_MONITOR_모드_안정화.md)
- [`work_order/DB설계.md`](../../work_order/DB설계.md) — TimescaleDB 종목 데이터 스키마
- [`work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md`](../../work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md)
