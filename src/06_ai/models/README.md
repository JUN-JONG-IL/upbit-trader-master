# 예측 모델 모듈 (Steps 11-13)

## 개요
다양한 AI 모델을 활용한 가격 예측 및 패턴 인식 시스템. LSTM, Transformer, XGBoost 등 여러 모델을 통합 제공.

## 파일 구조
```
src/models/
├── prediction_dialog.py         # QDialog UI 컨트롤러
├── prediction_dialog.ui         # Qt Designer UI
├── base_predictor.py           # 기본 예측기 인터페이스
│
├── timeseries/                 # 시계열 예측 모델
│   ├── lstm_predictor.py       # LSTM 모델
│   ├── transformer_predictor.py # Transformer
│   └── xgboost_predictor.py    # XGBoost
│
├── classification/             # 분류 모델
│   ├── direction_classifier.py # 상승/하락 분류
│   └── anomaly_detector.py     # 이상 탐지
│
└── ensemble/                   # 앙상블 모델
    └── meta_model.py           # 메타 모델
```

## UI 다이얼로그 (prediction_dialog.py)

### 주요 기능
- 다양한 예측 모델 선택 및 실행
- 실시간/과거 데이터 소스 선택
- 예측 기간 설정 (1-168시간)
- 신뢰도 임계값 조정
- 예측 결과 시각화 (차트)
- 백테스트 성능 평가
- Feature Importance 분석
- 결과 내보내기 (CSV/JSON)

### UI 구성
- **컨트롤 패널**: 모델 선택, 데이터 소스, 예측 기간, 신뢰도 슬라이더
- **예측 차트**: 실시간 예측 vs 실제 가격
- **성능 메트릭**: MAE, RMSE, MAPE, R²
- **Feature Importance**: 바 차트
- **백테스트**: 수익률, Sharpe Ratio, MDD

## 지원 모델

### 1. LSTM (Long Short-Term Memory)
- **구조**: 3-layer LSTM + Attention
- **입력**: 시계열 데이터 (sequence, features)
- **출력**: 가격 예측 + 불확실성 (Monte Carlo Dropout)
- **특징**: 
  - Attention 메커니즘으로 중요 시점 강조
  - MC Dropout으로 예측 신뢰도 제공
  - Dropout 0.2, Hidden Size 128
- **용도**: 중장기 가격 예측

### 2. Transformer
- **구조**: Multi-head Attention (8 heads, 3 layers)
- **입력**: 시계열 데이터 + Positional Encoding
- **출력**: 가격 예측
- **특징**:
  - Self-Attention으로 시간적 의존성 포착
  - Positional Encoding으로 순서 정보 유지
  - d_model=128, feedforward=512
- **용도**: 복잡한 패턴 예측

### 3. XGBoost
- **구조**: Gradient Boosting Tree
- **입력**: 기술적 지표 특징
- **출력**: 가격 예측
- **특징**:
  - 빠른 학습 및 추론
  - Feature Importance 제공
  - 과적합 방지 정규화
- **용도**: 단기 가격 예측

### 4. Direction Classifier
- **구조**: 이진 분류 모델
- **입력**: 기술적 지표
- **출력**: 상승(1)/하락(0) 확률
- **특징**: 방향성 예측에 최적화
- **용도**: 매수/매도 시그널

### 5. Anomaly Detector
- **구조**: Autoencoder
- **입력**: 정상 패턴 데이터
- **출력**: 이상 여부 + 점수
- **특징**: 비정상 거래 탐지
- **용도**: 리스크 관리

### 6. Meta Model (Ensemble)
- **구조**: 여러 모델의 앙상블
- **입력**: 각 모델의 예측 결과
- **출력**: 가중 평균 예측
- **특징**: 
  - 모델 다양성으로 안정성 향상
  - 동적 가중치 조정
- **용도**: 종합 예측

## 사용 방법

### 다이얼로그 오픈
```python
from src.models.prediction_dialog import PredictionDialog

# QDialog로 실행
dialog = PredictionDialog(parent=self)
dialog.exec_()  # 모달 다이얼로그
```

### LSTM 예측
```python
from src.models.timeseries.lstm_predictor import LSTMPredictor
import numpy as np

# 모델 생성
model = LSTMPredictor(input_size=50, hidden_size=128, num_layers=3)

# 예측 (불확실성 포함)
data = np.random.rand(30, 50)  # (sequence, features)
mean, std, confidence = model.predict_with_uncertainty(data, n_samples=100)

print(f"예측: {mean:.2f} ± {std:.2f} (신뢰도: {confidence:.2%})")
```

### Transformer 예측
```python
from src.models.timeseries.transformer_predictor import TransformerPredictor

model = TransformerPredictor(input_size=50, d_model=128, nhead=8)
prediction = model.predict(data)
```

### 앙상블 예측
```python
from src.models.ensemble.meta_model import MetaModel

meta = MetaModel()
meta.add_model("lstm", lstm_model, weight=0.4)
meta.add_model("transformer", transformer_model, weight=0.3)
meta.add_model("xgboost", xgboost_model, weight=0.3)

ensemble_prediction = meta.predict(data)
```

## 백테스트

### 성능 메트릭
- **MAE** (Mean Absolute Error): 평균 절대 오차
- **RMSE** (Root Mean Square Error): 제곱근 평균 제곱 오차
- **MAPE** (Mean Absolute Percentage Error): 평균 절대 백분율 오차
- **R²** (Coefficient of Determination): 결정 계수

### 거래 성능
- **총 수익률**: 백테스트 기간 수익률
- **Sharpe Ratio**: 위험 조정 수익률
- **MDD** (Maximum Drawdown): 최대 낙폭
- **승률**: 수익 거래 비율

## Feature Engineering

### 기술적 지표
- SMA, EMA (이동평균)
- RSI (상대강도지수)
- MACD (이동평균수렴확산)
- Bollinger Bands (볼린저 밴드)
- Stochastic Oscillator (스토캐스틱)

### 파생 특징
- 가격 변화율
- 거래량 변화율
- 변동성
- 추세 강도
- 시간 특징 (시간, 요일)

## 의존성
- PyTorch: LSTM, Transformer, Autoencoder
- XGBoost: XGBoost 모델
- scikit-learn: 전처리, 메트릭
- pandas, numpy: 데이터 처리
- PyQt5: UI

## 참고사항
- 모든 모델은 Mock 모드 지원
- 모델 저장/로드 기능 제공
- GPU 가속 지원 (CUDA)
- 실시간 예측 및 백테스트 통합

