#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prediction Module Demo

This demo shows how to use the prediction module in the upbit-trader application.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def demo_widget():
    """Demo using the widget interface"""
    print("=" * 70)
    print("PREDICTION MODULE - WIDGET DEMO")
    print("=" * 70)
    
    print("\n1. Import the widget:")
    print("   from src.prediction import PredictionWidget")
    
    print("\n2. Create and show widget:")
    print("   app = QApplication(sys.argv)")
    print("   widget = PredictionWidget()")
    print("   widget.show()")
    print("   app.exec_()")
    
    print("\n3. User actions:")
    print("   - Select model type (LSTM, GRU, Transformer, XGBoost, LightGBM)")
    print("   - Choose data source (Price, Technical Indicators, Order Book, Combined)")
    print("   - Set prediction period (5m, 15m, 1h, 4h, 1d)")
    print("   - Click 'Train Model' button")
    print("   - View progress and metrics")
    print("   - Click 'Predict' to generate predictions")
    print("   - Click 'Backtest' to evaluate performance")
    print("   - Save/Load models as needed")


def demo_logic():
    """Demo using the logic interface directly"""
    print("\n" + "=" * 70)
    print("PREDICTION MODULE - LOGIC DEMO")
    print("=" * 70)
    
    print("\n1. Import the logic:")
    print("   from src.prediction import PredictionLogic")
    
    print("\n2. Initialize:")
    print("   logic = PredictionLogic()")
    
    print("\n3. Train a model:")
    print("   def progress_callback(epoch, total, loss):")
    print("       print(f'Epoch {epoch}/{total}, Loss: {loss:.6f}')")
    print("")
    print("   metrics = logic.train_model(")
    print("       model_type='LSTM',")
    print("       data_source='Price (OHLCV)',")
    print("       lookback=60,")
    print("       progress_callback=progress_callback")
    print("   )")
    
    print("\n4. View metrics:")
    print("   print(f\"Train MAE: {metrics['train_mae']:.6f}\")")
    print("   print(f\"Val MAE: {metrics['val_mae']:.6f}\")")
    print("   print(f\"R²: {metrics['val_r2']:.6f}\")")
    
    print("\n5. Generate predictions:")
    print("   predictions = logic.predict(steps=10)")
    print("   print(f\"Next 10 predictions: {predictions}\")")
    
    print("\n6. Run backtest:")
    print("   results = logic.backtest()")
    print("   print(f\"Total Return: {results['total_return']:.2f}%\")")
    print("   print(f\"Sharpe Ratio: {results['sharpe_ratio']:.3f}\")")
    
    print("\n7. Save model:")
    print("   logic.save_model('my_lstm_model.h5')")
    
    print("\n8. Load model later:")
    print("   new_logic = PredictionLogic()")
    print("   new_logic.load_model('my_lstm_model.h5')")


def demo_integration():
    """Demo integration with main application"""
    print("\n" + "=" * 70)
    print("PREDICTION MODULE - INTEGRATION DEMO")
    print("=" * 70)
    
    print("\n1. Add to main window:")
    print("   from src.prediction import PredictionWidget")
    print("")
    print("   class MainWindow(QMainWindow):")
    print("       def __init__(self):")
    print("           super().__init__()")
    print("           ...")
    print("           # Add prediction tab")
    print("           self.prediction_widget = PredictionWidget()")
    print("           self.tab_widget.addTab(self.prediction_widget, 'Prediction')")
    
    print("\n2. Connect to trading module:")
    print("   # Get prediction signal")
    print("   predictions = self.prediction_widget.logic.predict(steps=1)")
    print("   ")
    print("   # Use in trading decision")
    print("   if predictions[0] > current_price * 1.02:  # Expect 2% rise")
    print("       self.trading_module.place_buy_order()")
    
    print("\n3. Use in strategy:")
    print("   class PredictionStrategy:")
    print("       def __init__(self, prediction_logic):")
    print("           self.logic = prediction_logic")
    print("       ")
    print("       def get_signal(self):")
    print("           pred = self.logic.predict(steps=1)[0]")
    print("           current = get_current_price()")
    print("           ")
    print("           if pred > current * 1.01:")
    print("               return 'BUY'")
    print("           elif pred < current * 0.99:")
    print("               return 'SELL'")
    print("           return 'HOLD'")


def demo_models():
    """Demo different model types"""
    print("\n" + "=" * 70)
    print("PREDICTION MODULE - MODEL COMPARISON")
    print("=" * 70)
    
    models = [
        ("LSTM", "Long Short-Term Memory", "Best for long-term patterns"),
        ("GRU", "Gated Recurrent Unit", "Faster training, similar to LSTM"),
        ("Transformer", "Attention-based", "Best for complex patterns"),
        ("XGBoost", "Gradient Boosting", "Fast, works well with many features"),
        ("LightGBM", "Light GBM", "Very fast, good for large datasets")
    ]
    
    print("\nAvailable Models:\n")
    for name, full_name, description in models:
        print(f"  {name:12s} - {full_name:25s} - {description}")
    
    print("\nExample usage:")
    print("  logic = PredictionLogic()")
    print("")
    print("  # Try each model")
    print("  for model in ['LSTM', 'GRU', 'Transformer', 'XGBoost', 'LightGBM']:")
    print("      metrics = logic.train_model(model, 'Price (OHLCV)', 60)")
    print("      print(f\"{model}: MAE={metrics['val_mae']:.6f}\")")


def main():
    """Run all demos"""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║              PREDICTION MODULE - USAGE DEMO                        ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    
    demo_widget()
    demo_logic()
    demo_integration()
    demo_models()
    
    print("\n" + "=" * 70)
    print("For more information, see:")
    print("  - src/prediction/README.md")
    print("  - PREDICTION_MODULE_SUMMARY.md")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
