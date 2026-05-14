# Prediction Module

Machine learning-based price prediction module for cryptocurrency trading.

## Overview

The Prediction module provides advanced machine learning capabilities for cryptocurrency price prediction using multiple model architectures and data sources.

## Features

### Model Types

1. **Deep Learning Models**
   - **LSTM** (Long Short-Term Memory): Excellent for sequential data and long-term dependencies
   - **GRU** (Gated Recurrent Unit): Faster training with similar performance to LSTM
   - **Transformer**: Attention-based architecture for complex pattern recognition

2. **Gradient Boosting Models**
   - **XGBoost**: High-performance gradient boosting with regularization
   - **LightGBM**: Fast, distributed, high-performance gradient boosting

### Data Sources

- **Price (OHLCV)**: Open, High, Low, Close, Volume data
- **Technical Indicators**: SMA, RSI, and other technical indicators
- **Order Book**: Bid/ask prices and volume data
- **Combined**: All features combined for maximum information

### Prediction Periods

- 5 minutes
- 15 minutes
- 1 hour
- 4 hours
- 1 day

### Performance Metrics

- **MAE** (Mean Absolute Error): Average prediction error
- **RMSE** (Root Mean Squared Error): Penalty for large errors
- **R²** (R-squared): Goodness of fit (0-1, higher is better)
- **Sharpe Ratio**: Risk-adjusted returns (higher is better)

## Architecture

```
prediction/
├── __init__.py           # Module initialization
├── prediction.ui         # Qt Designer UI file
├── widget_prediction.py  # Qt widget implementation
├── prediction_logic.py   # Business logic
└── README.md            # This file
```

## Components

### widget_prediction.py

Qt widget providing the user interface:

- Model configuration controls
- Training progress display
- Performance metrics table
- Matplotlib chart for visualization
- Log output

**Key Classes:**
- `PredictionWidget`: Main widget class
- `TrainingThread`: Background thread for model training

**Signals:**
- `signal_log`: Log message updates
- `signal_update_metrics`: Metrics updates
- `signal_update_chart`: Chart updates

### prediction_logic.py

Business logic for prediction:

- Data preprocessing and feature engineering
- Model training and evaluation
- Prediction generation
- Backtesting

**Key Methods:**
- `prepare_data()`: Load and prepare training data
- `train_model()`: Train selected model
- `predict()`: Generate future predictions
- `backtest()`: Evaluate model on historical data
- `save_model()` / `load_model()`: Model persistence

## Usage

### Basic Usage

```python
from prediction import PredictionWidget

# Create widget
widget = PredictionWidget()
widget.show()
```

### Programmatic Usage

```python
from prediction import PredictionLogic

# Initialize logic
logic = PredictionLogic()

# Train model
metrics = logic.train_model(
    model_type="LSTM",
    data_source="Price (OHLCV)",
    lookback=60,
    progress_callback=lambda e, t, l: print(f"Epoch {e}/{t}, Loss: {l}")
)

# Generate predictions
predictions = logic.predict(steps=10)

# Run backtest
backtest_results = logic.backtest()

# Save model
logic.save_model("my_model.h5")
```

## Workflow

1. **Select Model Configuration**
   - Choose model type (LSTM, GRU, Transformer, XGBoost, LightGBM)
   - Select data source
   - Set prediction period
   - Configure lookback window

2. **Train Model**
   - Click "Train Model" button
   - Monitor training progress
   - View metrics after completion

3. **Generate Predictions**
   - Click "Predict" button
   - View predictions on chart
   - Check log for detailed output

4. **Backtest Strategy**
   - Click "Backtest" button
   - View backtest results
   - Analyze performance metrics

5. **Save/Load Models**
   - Save trained model for later use
   - Load previously trained model

## Model Details

### LSTM Architecture

```
Input Layer (timesteps, features)
├── LSTM Layer (128 units, return_sequences=True)
├── Dropout (0.2)
├── LSTM Layer (64 units, return_sequences=True)
├── Dropout (0.2)
├── LSTM Layer (32 units)
├── Dropout (0.2)
├── Dense Layer (32 units, ReLU)
└── Output Layer (1 unit)
```

### GRU Architecture

```
Input Layer (timesteps, features)
├── GRU Layer (128 units, return_sequences=True)
├── Dropout (0.2)
├── GRU Layer (64 units, return_sequences=True)
├── Dropout (0.2)
├── GRU Layer (32 units)
├── Dropout (0.2)
├── Dense Layer (32 units, ReLU)
└── Output Layer (1 unit)
```

### Transformer Architecture

```
Input Layer (timesteps, features)
├── MultiHeadAttention (4 heads, key_dim=32)
├── Dropout (0.1)
├── LayerNormalization
├── GlobalAveragePooling1D
├── Dense Layer (64 units, ReLU)
├── Dropout (0.1)
└── Output Layer (1 unit)
```

### XGBoost Parameters

```python
{
    'objective': 'reg:squarederror',
    'max_depth': 6,
    'learning_rate': 0.1,
    'subsample': 0.8,
    'colsample_bytree': 0.8
}
```

### LightGBM Parameters

```python
{
    'objective': 'regression',
    'metric': 'rmse',
    'max_depth': 6,
    'learning_rate': 0.1,
    'num_leaves': 31,
    'subsample': 0.8,
    'colsample_bytree': 0.8
}
```

## Data Processing

### Feature Engineering

**Price Data:**
- Raw OHLCV data
- Normalization using MinMaxScaler

**Technical Indicators:**
- SMA (Simple Moving Average): 20, 50 periods
- RSI (Relative Strength Index): 14 periods
- Additional indicators as needed

**Order Book:**
- Bid/Ask prices
- Volume data
- Spread analysis

### Data Splitting

- Training: 70%
- Validation: 15%
- Test: 15%

### Sequence Creation

- Lookback window: 10-200 periods (default: 60)
- Sliding window approach
- Overlap between sequences

## Performance Evaluation

### Training Metrics

- **Loss**: Training loss per epoch
- **Validation Loss**: Generalization performance
- **Early Stopping**: Prevents overfitting

### Evaluation Metrics

- **MAE**: Average absolute error in price units
- **RMSE**: Root mean squared error (penalizes outliers)
- **R²**: Coefficient of determination (0-1 scale)
- **Sharpe Ratio**: Risk-adjusted returns

### Backtesting

- **Total Return**: Cumulative return percentage
- **Win Rate**: Percentage of profitable trades
- **Max Drawdown**: Largest peak-to-trough decline

## Dependencies

### Required Packages

```bash
# Deep Learning
pip install tensorflow>=2.12.0

# Gradient Boosting
pip install xgboost>=1.7.0
pip install lightgbm>=4.0.0

# Data Processing
pip install numpy>=1.24.0
pip install pandas>=2.0.0
pip install scikit-learn>=1.3.0

# Visualization
pip install matplotlib>=3.7.0

# Qt
pip install PyQt5>=5.15.0
```

## Integration

### With Trading Module

```python
# Get prediction from module
prediction_widget = PredictionWidget()
predictions = prediction_widget.logic.predict(steps=1)

# Use in trading decision
if predictions[0] > current_price * 1.01:  # Expect 1% rise
    execute_buy_order()
```

### With Backtest Module

```python
# Run backtest with prediction model
backtest_results = prediction_logic.backtest()

# Analyze results
if backtest_results['sharpe_ratio'] > 1.0:
    enable_live_trading()
```

## Tips for Best Results

### Model Selection

- **LSTM**: Best for long-term patterns and trends
- **GRU**: Faster training, good for real-time predictions
- **Transformer**: Best for complex patterns with attention
- **XGBoost**: Fast, works well with many features
- **LightGBM**: Very fast, good for large datasets

### Data Source Selection

- **Price Only**: Simple, fast training
- **Technical Indicators**: Better pattern recognition
- **Order Book**: Captures market microstructure
- **Combined**: Best overall performance (slower training)

### Hyperparameter Tuning

- **Lookback Window**: 
  - Short-term trading: 10-30 periods
  - Medium-term: 30-60 periods
  - Long-term: 60-200 periods

- **Prediction Period**:
  - Match with your trading timeframe
  - Shorter periods are generally more accurate

### Training Tips

1. **Data Quality**: Ensure clean, complete data
2. **Normalization**: Always normalize input features
3. **Validation**: Monitor validation loss for overfitting
4. **Early Stopping**: Use to prevent overfitting
5. **Multiple Models**: Train several models and ensemble

## Troubleshooting

### Common Issues

**1. Training is very slow**
- Solution: Use GRU instead of LSTM, or try LightGBM
- Reduce lookback window
- Use smaller batch size

**2. Poor prediction accuracy**
- Solution: Try different model types
- Add more features (technical indicators)
- Increase lookback window
- Collect more training data

**3. Model overfitting (high train, low validation)**
- Solution: Add dropout layers
- Reduce model complexity
- Use early stopping
- Add more training data

**4. Out of memory errors**
- Solution: Reduce batch size
- Decrease lookback window
- Use gradient boosting instead of deep learning

**5. TensorFlow/XGBoost not installed**
- Solution: Install required packages:
  ```bash
  pip install tensorflow xgboost lightgbm
  ```

## Future Enhancements

- [ ] Ensemble models (combining multiple predictions)
- [ ] AutoML for hyperparameter optimization
- [ ] Multi-asset prediction
- [ ] Sentiment analysis integration
- [ ] Real-time model updating
- [ ] Model explanation (SHAP values)
- [ ] Cloud training support
- [ ] GPU acceleration
- [ ] Advanced feature engineering
- [ ] Custom loss functions

## References

### Academic Papers

- Hochreiter & Schmidhuber (1997): "Long Short-Term Memory"
- Cho et al. (2014): "Learning Phrase Representations using RNN Encoder-Decoder"
- Vaswani et al. (2017): "Attention Is All You Need"
- Chen & Guestrin (2016): "XGBoost: A Scalable Tree Boosting System"
- Ke et al. (2017): "LightGBM: A Highly Efficient Gradient Boosting Decision Tree"

### Resources

- TensorFlow Documentation: https://www.tensorflow.org/
- XGBoost Documentation: https://xgboost.readthedocs.io/
- LightGBM Documentation: https://lightgbm.readthedocs.io/
- Scikit-learn Documentation: https://scikit-learn.org/

## License

Copyright (c) 2024 Upbit Trader Team. All rights reserved.

## Support

For issues, questions, or contributions, please refer to the main project repository.

---

## 🆕 Phase 11-13 Enhancements (2026-02-08)

### New Advanced Features

#### 1. Uncertainty Quantification (MC Dropout)
**File:** `uncertainty.py`

Monte Carlo Dropout for prediction uncertainty estimation.

**Usage:**
```python
from src.prediction.uncertainty import UncertaintyQuantifier

quantifier = UncertaintyQuantifier(n_iterations=100, confidence_level=0.95)
result = quantifier.quantify_uncertainty(model, X_test)

print(f"Mean prediction: {result['mean_prediction']}")
print(f"Confidence interval: [{result['lower_bound']}, {result['upper_bound']}]")
print(f"Uncertainty score: {result['uncertainty_score']:.4f}")
```

**Features:**
- ✅ Monte Carlo Dropout with 100 forward passes
- ✅ 95% confidence interval calculation
- ✅ Uncertainty score (entropy)
- ✅ Prediction reliability assessment

#### 2. Fourier Analysis (Periodicity Detection)
**File:** `fourier_analysis.py`

FFT-based periodicity detection and seasonal decomposition.

**Usage:**
```python
from src.prediction.fourier_analysis import FourierAnalyzer

analyzer = FourierAnalyzer(sampling_rate=1.0)
result = analyzer.detect_periodicity(price_data, top_n=5)

for period in result['periods']:
    print(f"Period: {period['period_hours']:.1f} hours")
    print(f"Power: {period['power']:.2f}")

# Seasonal decomposition
decomp = analyzer.seasonal_decomposition(price_data)
trend = decomp['trend']
seasonal = decomp['seasonal']
```

**Features:**
- ✅ FFT periodicity detection (4-hour, daily, weekly cycles)
- ✅ Seasonal decomposition (trend + seasonal + residual)
- ✅ Autocorrelation function (ACF)
- ✅ Partial autocorrelation (PACF)

#### 3. Ensemble Meta-Learner
**File:** `ensemble.py`

Advanced ensemble combining multiple models.

**Usage:**
```python
from src.prediction.ensemble import EnsembleMetaLearner

ensemble = EnsembleMetaLearner(meta_model_type="xgboost", dynamic_weighting=True)
ensemble.add_base_model("LSTM", lstm_model)
ensemble.add_base_model("Transformer", transformer_model)
ensemble.add_base_model("XGBoost", xgb_model)

# Train meta-learner
X_meta = np.column_stack([lstm_pred, transformer_pred, xgb_pred])
ensemble.train_meta_learner(X_meta, y_train)

# Make predictions
predictions = ensemble.predict(X_test)

# Update weights based on recent performance
ensemble.update_weights(y_true, X_test)
```

**Features:**
- ✅ Meta-learner stacking (XGBoost, Linear, Neural)
- ✅ Dynamic weighting based on recent performance
- ✅ Optuna hyperparameter optimization
- ✅ Model contribution analysis

### Dependencies Added

```bash
pip install scipy umap-learn hdbscan
```

### Performance Improvements

- **MC Dropout:** Provides uncertainty quantification (crucial for risk management)
- **Fourier Analysis:** Identifies dominant market cycles
- **Ensemble:** Typically 2-5% accuracy improvement over single models

### Chart Enhancements

- ✅ Chart size increased to 800x600px
- ✅ Antialiasing enabled for smoother rendering
- ✅ Confidence intervals displayed
- ✅ Uncertainty zones highlighted

### References

- Advanced Stock Price Prediction with ML (MC Dropout)
- Stockpredictionai (LSTM-GAN, Fourier Transform)
- Final-Year ML Stock Prediction (Meta-Learner)
- Stock-Prediction-Models (SHAP, ensemble)

## Phase 12 Enhancements (2026-02)

### MC Dropout Uncertainty Quantification

Visualize prediction uncertainty using Monte Carlo Dropout:

```python
from src.prediction.uncertainty import UncertaintyQuantifier

# Initialize quantifier
quantifier = UncertaintyQuantifier(n_iterations=100, confidence_level=0.95)

# Get predictions with uncertainty
mean_pred, std_pred, all_preds = quantifier.mc_dropout_predict(model, X)

# Calculate confidence intervals
lower_bound, upper_bound = quantifier.get_confidence_interval(mean_pred, std_pred)
```

**Chart Visualization:**
- Main prediction line (green, dashed)
- 95% confidence interval (light green fill)
- Historical actual prices (blue, solid)
- Chart size: 1000x600px with antialiasing
- Real-time uncertainty updates

### Enhanced Chart Rendering

**Specifications:**
- Size: 1000x600px (exceeds 800x600px minimum)
- Antialiasing: `QPainter.Antialiasing` enabled
- Color scheme:
  - Actual prices: Blue (#3498db)
  - Predicted prices: Green (#27ae60) 
  - Confidence interval: Light green with 30% opacity
- Font sizes: Title 12pt bold, Labels 10pt

### QThread Training

Non-blocking model training with progress updates:

```python
class TrainingThread(QThread):
    progress = pyqtSignal(int, str)  # percentage, message
    finished = pyqtSignal(dict)      # training metrics
    error = pyqtSignal(str)          # error message
    
    def run(self):
        # Background training
        # Progress callbacks for UI updates
        # Automatic metric collection
```

**Features:**
- Real-time epoch progress (0-100%)
- Loss tracking per epoch
- No UI freezing during training
- Graceful cancellation support

### Help System

Comprehensive help via ❓ button:

- **Model Selection**: Characteristics of each model type
- **Confidence Interval**: How to interpret uncertainty
- **Feature Importance**: Top contributing features
- **Model Comparison**: Performance trade-offs

### Technical Implementation

**Uncertainty Visualization:**
```python
def update_chart(self, data: dict):
    # Plot predictions
    self.ax.plot(pred_x, predictions, label='Predicted Price', 
                color='#27ae60', linewidth=2, marker='o')
    
    # Add uncertainty bounds
    if uncertainty_lower and uncertainty_upper:
        self.ax.fill_between(pred_x, uncertainty_lower, uncertainty_upper,
                            alpha=0.3, color='#2ecc71',
                            label='95% Confidence Interval (MC Dropout)')
```

### Requirements

```
xgboost>=2.0.0
torch>=2.0.0
transformers>=4.30.0
numpy>=1.20.3
matplotlib>=3.4.2
```

### API Reference

#### PredictionWidget

```python
class PredictionWidget(QWidget):
    """Widget for prediction functionality with uncertainty"""
    
    # Signals
    signal_log = pyqtSignal(str)
    signal_update_chart = pyqtSignal(dict)
    
    def setup_chart(self):
        """Setup chart with proper size and antialiasing"""
        
    def update_chart(self, data: dict):
        """Update chart with predictions and uncertainty"""
```

#### UncertaintyQuantifier

```python
class UncertaintyQuantifier:
    """Monte Carlo Dropout uncertainty quantification"""
    
    def __init__(self, n_iterations: int = 100, confidence_level: float = 0.95):
        """Initialize with iteration count and confidence level"""
    
    def mc_dropout_predict(self, model, X, training=True):
        """Run MC Dropout prediction"""
        # Returns: (mean, std, all_predictions)
    
    def get_confidence_interval(self, mean, std, confidence_level=None):
        """Calculate confidence bounds"""
```

### Performance

- Chart rendering: < 50ms
- MC Dropout (100 iterations): ~2 seconds
- Training progress updates: Every epoch
- UI response: < 100ms (non-blocking)

### See Also

- [Monte Carlo Dropout Paper](https://arxiv.org/abs/1506.02142)
- [Uncertainty in Deep Learning](https://www.cs.ox.ac.uk/people/yarin.gal/website/thesis.pdf)
- [src/prediction/uncertainty.py](./uncertainty.py)
