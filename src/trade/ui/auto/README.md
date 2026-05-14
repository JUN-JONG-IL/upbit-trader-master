# Settings (자동매매 설정)

## 목적
GUI에서 자동매매 시작/중지 및 전략 타입(VariousIndicator / VolatilityBreakout)을 선택한다.

## 포함 파일
- `widget_settings.py`
  - `SettingsWidget`: settings.ui 기반 설정 창(Frameless)
- `settings.ui`
  - 설정 창 UI

## 동작 개요
- Start:
  - `static.signal_manager` 생성/시작
  - 선택된 전략(VariousIndicatorStrategy 또는 VolatilityBreakoutStrategy) 생성/시작
  - `static.config.settings_auto_trading=True` 저장
- Stop:
  - 실행 중인 `static.strategy`, `static.signal_manager` terminate 시도
  - `static.config.settings_auto_trading=False` 저장

## 의존성
- `static.config`, `static.signal_queue`
- `strategy.SignalManager`, `VariousIndicatorStrategy`, `VolatilityBreakoutStrategy`

## 주의사항
- 창 드래그(타이틀 라벨 이벤트 바인딩) 로직 포함
- `static.settings_start` 플래그로 중복 실행 방지