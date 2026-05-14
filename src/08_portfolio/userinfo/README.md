# Userinfo (계정 요약 + 자산분포 시각화)

## 목적
- 로그인/진입 후 생성되는 `static.account`의 잔고/평가/수익/자산분포 정보를
  UI에 주기적으로 표시 + 실시간 원/도넛차트로 시각화.

## 포함 파일
- `widget_userinfo.py`
  - `UserinfoWidget`: 계정 요약 위젯 (잔고/평가/수익/수익률 등 표시)
  - `UserinfoWorker(QThread)`: 0.5초 주기로 account 값을 읽어 UI 갱신
- `widget_piechart.py`
  - `PieChartWidget`: 실시간 자산 비율(코인+KRW) 도넛/파이차트 위젯
  - `PieWorker(QThread)`: 1초 주기로 자산 현황을 읽어 파이차트 갱신
  - `MyMplCanvas`: PyQt + matplotlib 연동 캔버스 (PieChartWidget 기반)

## 의존성
- `static.account` (로그인 또는 데모(Skip) 이후 준비됨)
- `ui_userinfo.py` (Qt Designer → py 변환 산출물, Ui_Form 제공)
- PyQt5, matplotlib

## MainWindow 연동
- `window_main.py`에서 `UserinfoWidget()`과 `PieChartWidget()` 생성
- 페이지 활성화 시 `thread_start()`로 두 worker가 안전하게 동작
- Account/Portfolio/분석 등 여러 위치에서 위젯 직접 배치 가능

## 주의사항
- GUI 스레드 블로킹 방지: QThread 기반 구현
- 종료 시 워커들은 `stop()`/`close()` 등으로 안전 종료
- PieChart는 코인+KRW 합이 7종 이상이면 기타코인으로 묶어 표시
- 위젯 기능 확장(리밸런싱 분석, 등급 표시 등)은 여기서 통합 관리

---