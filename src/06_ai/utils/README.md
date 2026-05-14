# AI Utilities Module (`src/06_ai/utils/`)

Shared utilities for feature engineering and data preprocessing.

## Components

- **`feature_engineering.py`** (`FeatureEngineer`): Technical indicators, sequence generation
- **`preprocessing.py`** (`DataPreprocessor`): Scaling, splitting, data cleaning

## Usage

```python
from src.06_ai.utils import FeatureEngineer, DataPreprocessor

engineer = FeatureEngineer()
features = engineer.compute(ohlcv_df)
```
