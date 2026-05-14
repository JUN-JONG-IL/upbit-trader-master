# Signal (시그널)

## 목적
전략/SignalManager가 생성한 신호(매수/매도 등)를 DB에서 읽어 UI에 표시한다.

## 포함 파일(현재 단계)
- `widget_signal_list.py`
  - `SignallistWidget`: signal_list.ui 기반 테이블 위젯
  - `SignalListWorker`: MongoDB에서 당일 signal_history 컬렉션을 폴링하여 테이블 갱신

- `signal_list.ui`
  - 시그널 리스트 화면 UI

## 데이터 소스
- MongoDB
  - DB: `signal_history`
  - Collection: `YYYY-MM-DD` (당일 날짜 문자열)

## 주의사항
- UI 갱신은 QThread에서 emit 한 시그널로 수행
- closeEvent에서 워커 종료를 요청해야 함