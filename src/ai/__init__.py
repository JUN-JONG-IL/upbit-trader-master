"""
AI/ML 엔진 통합 모듈

[통합 내역]
- 05_ai, 05_ml, 08_ml_ai, 10_ai_ml → ai

[주요 컴포넌트]
- ai_engine: GPT-4o, Gemini 통합
- prediction: LSTM, XGBoost, Transformer 예측 모델
- models: ML 모델 저장소
- rl: 강화학습 (DQN Trader)
- detection: 이상 탐지
- prompt: AI 프롬프트 (LLM용)
- ui: AI UI 통합 (v4.0)
- priority/: 우선순위 설정 및 AI/ML 모델 선택 (PyQt5 UI + FastAPI 라우터)

[사용 예시]
```python
from src.ai.ui import AIEngineWidget, PredictionWidget

ai_engine = AIEngineWidget(parent=main_window)
prediction = PredictionWidget(parent=main_window)
```

[의존성]
- PyTorch (LSTM, Transformer)
- XGBoost, LightGBM
- OpenAI API (GPT-4o)
- Google Gemini API

[작성자] GitHub Copilot
[작성일] 2026-03-13
"""
try:
    from .ui import AIEngineWidget, PredictionWidget

    __all__ = [
        'AIEngineWidget',
        'PredictionWidget',
    ]
except ImportError:
    # Allow the package to be imported in headless/test environments
    # where PyQt5 or other heavy dependencies are not installed.
    __all__ = []

