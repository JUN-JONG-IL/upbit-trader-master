# AI Strategy Module (`src/ai/strategy/`)

Provides automated strategy recommendation and hyperparameter optimization.

## Components

- **`recommender.py`** (`StrategyRecommender`): Market-regime-aware strategy ranking
- **`optimizer.py`** (`HyperparameterOptimizer`): Optuna hyperparameter optimisation

## Usage

```python
from src.ai.strategy import StrategyRecommender, HyperparameterOptimizer

recommender = StrategyRecommender()
best_strategy = recommender.recommend(market_data)
```
