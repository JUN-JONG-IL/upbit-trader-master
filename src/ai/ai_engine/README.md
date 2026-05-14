# AI Engine Module

## Overview

The AI Engine module provides AI-powered trading analysis using state-of-the-art language models including GPT-4o and Gemini.

## Features

- **Multi-Model Support**: GPT-4o, GPT-4o-mini, Gemini 1.5 Pro, Gemini 2.0 Flash
- **Real-time Analysis**: Continuous market data analysis and signal generation
- **Confidence Thresholding**: Adjustable confidence levels for trading signals
- **Emergency Stop**: Instant trading halt functionality
- **Performance Metrics**: Track accuracy, win rate, and average profit
- **API Key Management**: Secure configuration of API credentials

## File Structure

```
src/ai_engine/
├── __init__.py                 # Module initialization
├── widget_ai_engine.py         # Qt UI widget
├── ai_engine.ui                # Qt Designer UI definition
├── ai_engine_logic.py          # Business logic and AI integration
├── dialog_api_settings.py      # API settings dialog
└── README.md                   # This file
```

## Usage

### Basic Usage

```python
from src.ai_engine import AIEngineWidget

# Create widget
widget = AIEngineWidget()
widget.show()
```

### Programmatic Control

```python
from src.ai_engine import AIEngineLogic

# Initialize logic
logic = AIEngineLogic()

# Start analysis
logic.start_analysis(model="GPT-4o", confidence=0.7)

# Get prediction
market_data = {...}
result = logic.predict(market_data)
print(f"Signal: {result['signal']}, Confidence: {result['confidence']}")

# Stop analysis
logic.stop_analysis()
```

## Configuration

### API Keys

Configure API keys in `.env` file:

```
OPENAI_API_KEY=sk-your-openai-key
GOOGLE_API_KEY=AIza-your-google-key
```

Or use the API Settings dialog in the UI.

### Model Selection

Available models:
- **GPT-4o**: Most capable OpenAI model
- **GPT-4o-mini**: Faster, cost-effective OpenAI model
- **Gemini 1.5 Pro**: Google's advanced model
- **Gemini 2.0 Flash**: Google's fast model

### Confidence Threshold

Adjust the confidence threshold (0.0 - 1.0) to filter signals:
- Higher threshold: More conservative, fewer signals
- Lower threshold: More aggressive, more signals

## UI Components

### Status Display
- **Green (🟢)**: Analysis running
- **Yellow (🟡)**: Ready/Stopped
- **Red (🔴)**: Emergency stop

### Controls
- **AI Analysis Start**: Begin market analysis
- **Stop**: Pause analysis
- **Emergency Stop**: Immediate halt of all trading
- **API Settings**: Configure API keys

### Results Table
- **Time**: Signal generation time
- **Signal**: BUY/SELL/HOLD
- **Confidence**: Confidence score (0.0 - 1.0)
- **Reason**: AI-generated reasoning

### Performance Metrics
- **Accuracy**: Prediction accuracy
- **Win Rate**: Percentage of profitable trades
- **Avg Profit**: Average profit per trade

## Qt Designer Principles

This module follows Qt Designer best practices:

1. **Separation of Concerns**: UI (.ui) separate from logic (.py)
2. **Signal/Slot Pattern**: All UI interactions via signals
3. **Dynamic Loading**: UI loaded at runtime with uic.loadUi()
4. **Reusability**: Widget can be embedded in any Qt application

## Dependencies

```
PyQt5>=5.15.0
openai>=1.0.0
google-generativeai>=0.3.0
python-dotenv>=1.0.0
```

## Testing

Run tests:

```bash
pytest tests/test_ai_engine_ui.py -v
```

## Security

- API keys are stored in `.env` file (not in version control)
- Password fields use echo mode masking
- Emergency stop functionality for risk management

## Integration

The AI Engine integrates with:
- Market data sources
- Order execution system
- Risk management system
- Performance tracking

## Future Enhancements

- [ ] Multi-timeframe analysis
- [ ] Custom model fine-tuning
- [ ] Backtesting integration
- [ ] Real-time streaming analysis
- [ ] Advanced risk management
- [ ] Portfolio optimization

## License

See main project LICENSE file.

## Author

Upbit Trader Team

## Version

1.0.0 (2026-02-06)

---

## 🆕 Phase 11-13 Enhancements (2026-02-08)

### New Features Added

#### 1. Model Explainability (SHAP)
**File:** `explainability.py`

SHAP (SHapley Additive exPlanations) for model interpretation.

**Usage:**
```python
from src.ai_engine.explainability import ModelExplainer

explainer = ModelExplainer()
result = explainer.explain_prediction(
    model=trained_model,
    X=input_data,
    feature_names=['RSI', 'MACD', 'Volume'],
    model_type="tree"
)

# Get top features
top_features = explainer.get_top_features(n=10)
```

**Features:**
- ✅ SHAP values calculation (Tree, Linear, Deep models)
- ✅ Feature importance extraction
- ✅ Waterfall plot data generation
- ✅ Force plot support

#### 2. Auto Retraining
**File:** `auto_retraining.py`

Automatic model retraining based on drift detection.

**Usage:**
```python
from src.ai_engine.auto_retraining import AutoRetrainingManager

manager = AutoRetrainingManager(psi_threshold=0.2)
manager.set_baseline(training_data, baseline_accuracy=0.92)

should_retrain, result = manager.should_retrain(
    reference_data=training_data,
    current_data=production_data,
    current_accuracy=0.88
)
```

**Features:**
- ✅ PSI (Population Stability Index) calculation
- ✅ Data distribution drift detection
- ✅ Accuracy drop monitoring
- ✅ Automatic retraining triggers
- ✅ Alert notifications

**Trigger Conditions:**
- PSI > 0.2: Significant data drift
- Accuracy drop > 5%: Performance degradation

### Dependencies Added

```bash
pip install shap scipy
```

### Performance Metrics

- **SHAP Calculation:** ~1-2 seconds for 100 samples
- **PSI Calculation:** ~10ms for 1000 samples
- **Memory Usage:** ~50MB for medium models

### References

- Stock-Prediction-Models (SHAP, ensemble)
- Algorithmic-trading-with-ML (Canary deployment)
- ML Stock Price Prediction (Auto-retraining)

---

## 🆕 Advanced Features (2026-02-08)

### 3. Real-time Data Feed (realtime_data.py)

**freqtrade의 CCXT WebSocket 패턴 참조**

```python
from ai_engine.realtime_data import RealtimeDataFeed
import asyncio

async def main():
    feed = RealtimeDataFeed(use_ccxt_pro=False)  # 폴링 모드
    
    async for ticker in feed.watch_ticker('BTC/KRW'):
        print(f"BTC: {ticker['last']}")
        
        if len(feed.ticker_buffer) >= 10:
            feed.stop()
            break

asyncio.run(main())
```

**Features:**
- ✅ CCXT Pro WebSocket support (optional)
- ✅ Polling-based fallback
- ✅ Ticker/OHLCV streaming
- ✅ Buffer and replay

**Dependencies (optional):**
```bash
pip install ccxt[pro]
```

### 4. Hyperopt Optimization (hyperopt.py)

**freqtrade의 Hyperopt 최적화 패턴 참조**

```python
from ai_engine.hyperopt import optimize_lstm_params
import numpy as np

X_train = np.random.randn(100, 10, 5)
y_train = np.random.randn(100, 1)

best_params = optimize_lstm_params(X_train, y_train, use_hyperopt=False)
```

**Features:**
- ✅ Bayesian optimization (Hyperopt)
- ✅ Grid search fallback
- ✅ Save/load results
- ✅ Custom search space

**Dependencies (optional):**
```bash
pip install hyperopt
```

### References (Advanced Features)

- **freqtrade** (39.9k⭐): CCXT WebSocket, Hyperopt optimization
- **FinRL** (12k⭐): PPO reinforcement learning
- **stocksight**: Twitter streaming, Elasticsearch
- **Stock-Prediction-Models**: LSTM-GAN

## Phase 11 Enhancements (2026-02)

### MLflow Model Registry Integration

The AI Engine now integrates with MLflow for production-grade model management:

```python
from src.ai.engine.model_registry import ModelRegistry

# Initialize registry
registry = ModelRegistry()

# List available models
models = registry.list_models(stage="Production")
for model in models:
    print(f"{model.name} v{model.version} - Accuracy: {model.accuracy:.2f}%")

# Get specific model
model_info = registry.get_model("LSTM_Predictor", "2.1.0")
```

**Features:**
- Automatic model loading from MLflow tracking server
- Version management and stage tracking (Staging/Production/Archived)
- Model metadata display (accuracy, trained date, parameters)
- Integration with widget dropdown for model selection

### Canary Deployment

Progressive model deployment with automatic rollback on errors:

```python
# Start Canary deployment via widget
widget.start_canary_deployment("LSTM_Predictor", "2.1.0")

# Deployment stages:
# 0% → 5%    : Initial test with small traffic
# 5% → 25%   : Stability verification
# 25% → 50%  : Half traffic switch
# 50% → 75%  : Majority traffic switch
# 75% → 100% : Complete deployment

# Automatic rollback if error rate > 5%
```

**QThread Implementation:**
- Non-blocking UI during deployment
- Real-time progress updates (percentage and status message)
- Automatic error detection and rollback
- Graceful thread shutdown on widget close

### Help System

Comprehensive help documentation accessible via ❓ button:

- **Canary Deployment**: Explains progressive rollout stages
- **Drift Detection**: KS test and performance monitoring
- **SHAP Explainability**: Feature importance interpretation
- **Auto Retraining**: PSI-based triggers (PSI > 0.2)
- **Rollback Procedures**: Manual and automatic rollback

### Technical Implementation

**QThread Usage:**
```python
class CanaryDeploymentThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)
    error = pyqtSignal(str)
    
    def run(self):
        # Progressive deployment with monitoring
        # Each stage: 5% → 25% → 50% → 75% → 100%
        # Real-time error rate checking
```

**Chart Specifications:**
- Minimum size: 800x600px (as per work_order/규칙.md)
- Antialiasing: Enabled via `QPainter.Antialiasing`
- Colors: Standard scheme (positive=green, neutral=blue, negative=red)

### Requirements

```
mlflow>=2.7.0
shap>=0.42.0
torch>=2.0.0  # For model loading
```

### API Reference

#### AIEngineWidget

```python
class AIEngineWidget(QWidget):
    """Main widget for AI Engine functionality"""
    
    # Signals
    signal_log = pyqtSignal(str)
    signal_update_metrics = pyqtSignal(dict)
    
    def load_mlflow_models(self):
        """Load models from MLflow registry"""
        
    def start_canary_deployment(self, model_name: str, model_version: str):
        """Start Canary deployment for a model"""
        
    @pyqtSlot(int, str)
    def on_canary_progress(self, percentage: int, message: str):
        """Handle deployment progress updates"""
        
    @pyqtSlot(bool, str)
    def on_canary_finished(self, success: bool, message: str):
        """Handle deployment completion"""
```

### Troubleshooting

**MLflow models not loading:**
- Check if MLflow server is running
- Verify `tracking_uri` configuration
- Check network connectivity to MLflow server

**Canary deployment fails:**
- Check model compatibility
- Verify error rate threshold settings
- Review deployment logs in the log panel

**UI freezes during deployment:**
- Ensure QThread is properly initialized
- Check for blocking operations in main thread
- Verify signal/slot connections

### Performance

- Model loading: < 2 seconds
- Canary deployment: ~15 seconds (3 seconds per stage)
- UI response time: < 100ms (as per work_order/규칙.md)
- Thread cleanup timeout: 3 seconds

### See Also

- [MLflow Documentation](https://mlflow.org/docs/latest/index.html)
- [SHAP Explainability](https://github.com/slundberg/shap)
- [Qt Threading Best Practices](https://doc.qt.io/qt-5/threads-qobject.html)
