# CHANGELOG
# 2026-03-16 | Copilot | 업그레이드: 09_sentiment README v4.0. 버전 통일.
# 2026-03-13 | Copilot | 업그레이드: 09_sentiment README v2.0. 전체 템플릿(개요/구조/기능/예시/의존성/참고) 추가.
# 2026-03-06 | Copilot | 생성: 09_sentiment README 초안

Version: v4.0
Last Modified: 2026-03-16
References:
  - work_order/13_단계_뉴스_소셜_감성_분석_시스템.md
  - work_order/DB설계.md

# src/09_sentiment — 뉴스 및 소셜 감성 분석

## 개요

뉴스(Bloomberg, Reuters, 네이버 등), 트위터/X, Reddit 등 **다중 소스에서 암호화폐 감성 데이터를 수집·분석**하여 거래 신호를 생성하는 모듈입니다.
FinBERT/KoBERT 기반 감성 점수 산출과 영향력 가중치(팔로워 수, 리트윗 등)를 활용하여 뉴스 급등/급락 시 알림 신호를 발행합니다.

## 디렉토리 구조

```
src/09_sentiment/
├── __init__.py                    # 모듈 진입점
├── README.md                      # 이 파일
└── analysis/
    ├── __init__.py
    ├── ui/                        # 감성 분석 PyQt5 위젯
    │   ├── __init__.py
    │   ├── widget_sentiment.py    # 메인 감성 분석 위젯
    │   └── widget_wordcloud.py   # 워드클라우드 위젯
    ├── core/                      # 데이터 수집 및 분석 엔진
    │   ├── __init__.py
    │   ├── news_collector.py      # 뉴스 수집기
    │   ├── social_collector.py   # 소셜 데이터 수집기
    │   └── sentiment_engine.py   # 감성 분석 엔진
    ├── models/                    # NLP 모델
    │   ├── __init__.py
    │   ├── finbert_model.py       # FinBERT (금융 감성)
    │   ├── kobert_model.py        # KoBERT (한국어 감성)
    │   └── summarizer.py         # 텍스트 요약 모델
    ├── preprocessing/             # 텍스트 전처리
    │   ├── __init__.py
    │   ├── text_cleaner.py        # 텍스트 정제
    │   └── tokenizer.py          # 토큰화
    ├── analytics/                 # 고급 분석 ✅ (analysis/ → analytics/ 변경)
    │   ├── __init__.py
    │   ├── correlation_analysis.py # 감성-가격 상관관계 분석
    │   ├── influence_score.py      # 영향력 점수 계산
    │   └── topic_modeling.py      # 토픽 모델링
    └── workers/                   # 백그라운드 수집 워커
        ├── __init__.py
        ├── news_worker.py         # 뉴스 수집 워커
        └── social_worker.py      # 소셜 수집 워커
```

## 주요 기능

- **다중 소스 수집**: 뉴스(Bloomberg, Reuters, 네이버), 트위터/X, Reddit 실시간 수집
- **감성 분석**: FinBERT(영문), KoBERT(한국어) 기반 긍정/부정/중립 점수 산출
- **영향력 가중치**: 팔로워 수, 리트윗, 조회수 기반 가중치 적용
- **감성 시각화**: 워드클라우드, 시계열 감성 차트, 분포 파이차트
- **소스 필터링**: 소스별·키워드별 필터링
- **신호 생성**: 감성 급등/급락 탐지 → `01_core/events/` 이벤트 버스 발행
- **MongoDB 저장**: 감성 데이터 및 원본 텍스트 영구 저장

## 사용 예시

```python
from src._09_sentiment import SentimentWidget, SentimentEngine

# UI 위젯
widget = SentimentWidget()
widget.show()

# 감성 분석 엔진 직접 사용
engine = SentimentEngine()
score = engine.analyze("비트코인 급등 예상, 기관 매수 증가")
print(score)  # SentimentScore(positive=0.85, negative=0.05, neutral=0.10)

# 뉴스 수집 워커
from src._09_sentiment.analysis.workers import NewsWorker
worker = NewsWorker(config)
worker.start()
```

## 의존성

- `src/01_core/` : 이벤트 버스 (신호 발행), 설정 관리
- `src/02_data/mongodb/` : 감성 데이터 저장 (MongoDB)
- `src/02_data/redis/` : 실시간 감성 캐시
- transformers : FinBERT, KoBERT 모델
- torch : 딥러닝 추론
- aiohttp, httpx : 비동기 뉴스/소셜 수집
- PyQt5 : UI 위젯

## 참고 문서

- [`work_order/13_단계_뉴스_소셜_감성_분석_시스템.md`](../../work_order/13_단계_뉴스_소셜_감성_분석_시스템.md)
- [`work_order/DB설계.md`](../../work_order/DB설계.md) — MongoDB 감성 데이터 스키마
- [`work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md`](../../work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md) § 21장
