#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prediction Widget

Qt Widget for machine learning prediction functionality including:
- Multiple model types (LSTM, GRU, Transformer, XGBoost, LightGBM)
- Model training and evaluation
- Real-time prediction
- Backtesting
- Visualization
"""

import logging
from pathlib import Path
from datetime import datetime
import numpy as np

from PyQt5.QtWidgets import QWidget, QMessageBox, QTableWidgetItem, QFileDialog, QVBoxLayout
from PyQt5.QtCore import pyqtSignal, QThread, pyqtSlot
from PyQt5 import uic

from .prediction_logic import PredictionLogic

# Matplotlib setup for Qt
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)


class TrainingThread(QThread):
    """Background thread for model training"""
    
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, logic, model_type, data_source, lookback):
        super().__init__()
        self.logic = logic
        self.model_type = model_type
        self.data_source = data_source
        self.lookback = lookback
    
    def run(self):
        """Run training in background"""
        try:
            # Training callback for progress updates
            def progress_callback(epoch, total_epochs, loss):
                progress = int((epoch / total_epochs) * 100)
                message = f"Epoch {epoch}/{total_epochs}, Loss: {loss:.6f}"
                self.progress.emit(progress, message)
            
            # Train model
            metrics = self.logic.train_model(
                self.model_type,
                self.data_source,
                self.lookback,
                progress_callback
            )
            
            self.finished.emit(metrics)
            
        except Exception as e:
            logger.error(f"Training error: {e}")
            self.error.emit(str(e))


class PredictionWidget(QWidget):
    """
    Prediction UI Widget
    
    Provides user interface for machine learning prediction functionality
    """
    
    # Signal definitions
    signal_log = pyqtSignal(str)
    signal_update_metrics = pyqtSignal(dict)
    signal_update_chart = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        """Initialize Prediction Widget"""
        super().__init__(parent)
        
        # Load UI
        ui_path = Path(__file__).parent / "prediction.ui"
        try:
            uic.loadUi(str(ui_path), self)
            logger.info("Prediction UI loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load UI: {e}")
            raise
        
        # Initialize logic
        self.logic = PredictionLogic()
        
        # Training thread
        self.training_thread = None
        
        # Setup matplotlib canvas
        self.setup_chart()
        
        # Connect signals
        self.connect_signals()
        
        # Initialize UI state
        self.initialize_ui()
    
    def setup_chart(self):
        """Setup matplotlib chart widget with proper size and antialiasing"""
        from PyQt5.QtGui import QPainter
        
        # Create matplotlib figure - minimum 800x600 as per rules
        # Using figsize in inches (1000px / 100dpi = 10in, 600px / 100dpi = 6in)
        self.figure = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        
        # Enable antialiasing as per rules
        self.canvas.setRenderHint(QPainter.Antialiasing)
        
        # Add canvas to widget_chart
        layout = QVBoxLayout(self.widget_chart)
        layout.addWidget(self.canvas)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create axes
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("Price Prediction with Confidence Interval", fontsize=12, fontweight='bold')
        self.ax.set_xlabel("Time", fontsize=10)
        self.ax.set_ylabel("Price (KRW)", fontsize=10)
        self.ax.grid(True, alpha=0.3)
        
        self.canvas.draw()
        logger.info("Chart setup complete with antialiasing (1000x600px)")
    
    def connect_signals(self):
        """Connect all Signal/Slot connections"""
        # Button signals
        self.btn_train.clicked.connect(self.on_train_model)
        self.btn_predict.clicked.connect(self.on_predict)
        self.btn_backtest.clicked.connect(self.on_backtest)
        self.btn_save_model.clicked.connect(self.on_save_model)
        self.btn_load_model.clicked.connect(self.on_load_model)
        
        # Configuration signals
        self.combo_model.currentIndexChanged.connect(self.on_model_changed)
        self.combo_data_source.currentIndexChanged.connect(self.on_data_source_changed)
        self.combo_period.currentIndexChanged.connect(self.on_period_changed)
        
        # Help button
        if hasattr(self, 'btn_help'):
            self.btn_help.clicked.connect(self.on_show_help)
        
        # Custom signals
        self.signal_log.connect(self.append_log)
        self.signal_update_metrics.connect(self.update_metrics)
        self.signal_update_chart.connect(self.update_chart)
        
        logger.info("Signals connected")
    
    def initialize_ui(self):
        """Initialize UI state"""
        self.label_progress_status.setText("Ready")
        self.progress_bar.setValue(0)
        
        # Initialize table column widths
        self.table_metrics.setColumnWidth(0, 150)  # Metric
        self.table_metrics.setColumnWidth(1, 150)  # Train
        self.table_metrics.setColumnWidth(2, 150)  # Validation
        self.table_metrics.setColumnWidth(3, 150)  # Test
        
        self.signal_log.emit("✅ Prediction module initialized")
        self.signal_log.emit(f"📊 Available models: LSTM, GRU, Transformer, XGBoost, LightGBM")
    
    def on_train_model(self):
        """Start model training"""
        try:
            model_type = self.combo_model.currentText()
            data_source = self.combo_data_source.currentText()
            lookback = self.spin_lookback.value()
            
            self.signal_log.emit(f"🏋️ Starting training: {model_type} with {data_source}")
            self.signal_log.emit(f"📈 Lookback window: {lookback} periods")
            
            # Disable controls during training
            self.set_training_mode(True)
            
            # Create and start training thread
            self.training_thread = TrainingThread(
                self.logic,
                model_type,
                data_source,
                lookback
            )
            self.training_thread.progress.connect(self.on_training_progress)
            self.training_thread.finished.connect(self.on_training_finished)
            self.training_thread.error.connect(self.on_training_error)
            self.training_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start training: {e}")
            self.signal_log.emit(f"❌ Error: {e}")
            logger.error(f"Failed to start training: {e}")
            self.set_training_mode(False)
    
    @pyqtSlot(int, str)
    def on_training_progress(self, progress, message):
        """Handle training progress updates"""
        self.progress_bar.setValue(progress)
        self.label_progress_status.setText(message)
        self.signal_log.emit(f"⏳ {message}")
    
    @pyqtSlot(dict)
    def on_training_finished(self, metrics):
        """Handle training completion"""
        self.progress_bar.setValue(100)
        self.label_progress_status.setText("Training completed")
        self.signal_log.emit("✅ Training completed successfully!")
        
        # Update metrics display
        self.signal_update_metrics.emit(metrics)
        
        # Enable prediction buttons
        self.btn_predict.setEnabled(True)
        self.btn_backtest.setEnabled(True)
        self.btn_save_model.setEnabled(True)
        
        # Reset training mode
        self.set_training_mode(False)
        
        # Show metrics summary
        train_mae = metrics.get('train_mae', 0)
        val_mae = metrics.get('val_mae', 0)
        self.signal_log.emit(f"📊 Train MAE: {train_mae:.4f}, Val MAE: {val_mae:.4f}")
    
    @pyqtSlot(str)
    def on_training_error(self, error_message):
        """Handle training error"""
        self.progress_bar.setValue(0)
        self.label_progress_status.setText("Training failed")
        self.signal_log.emit(f"❌ Training failed: {error_message}")
        
        QMessageBox.critical(self, "Training Error", f"Training failed:\n{error_message}")
        
        self.set_training_mode(False)
    
    def set_training_mode(self, training):
        """Enable/disable controls during training"""
        self.btn_train.setEnabled(not training)
        self.btn_load_model.setEnabled(not training)
        self.combo_model.setEnabled(not training)
        self.combo_data_source.setEnabled(not training)
        self.combo_period.setEnabled(not training)
        self.spin_lookback.setEnabled(not training)
    
    def on_predict(self):
        """Generate predictions"""
        try:
            if not self.logic.model:
                QMessageBox.warning(self, "Warning", "Please train or load a model first")
                return
            
            self.signal_log.emit("🔮 Generating predictions...")
            
            # Get predictions
            predictions = self.logic.predict()
            
            if predictions is not None:
                self.signal_log.emit(f"✅ Generated {len(predictions)} predictions")
                
                # Update chart
                self.signal_update_chart.emit({
                    'type': 'prediction',
                    'predictions': predictions
                })
                
                # Log first few predictions
                for i, pred in enumerate(predictions[:5]):
                    self.signal_log.emit(f"  Prediction {i+1}: {pred:.2f}")
                
                if len(predictions) > 5:
                    self.signal_log.emit(f"  ... and {len(predictions)-5} more")
            else:
                self.signal_log.emit("⚠️ No predictions generated")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to predict: {e}")
            self.signal_log.emit(f"❌ Error: {e}")
            logger.error(f"Failed to predict: {e}")
    
    def on_backtest(self):
        """Run backtest"""
        try:
            if not self.logic.model:
                QMessageBox.warning(self, "Warning", "Please train or load a model first")
                return
            
            self.signal_log.emit("📊 Running backtest...")
            
            # Run backtest
            backtest_results = self.logic.backtest()
            
            if backtest_results:
                self.signal_log.emit("✅ Backtest completed")
                
                # Update chart with backtest results
                self.signal_update_chart.emit({
                    'type': 'backtest',
                    'results': backtest_results
                })
                
                # Log backtest metrics
                total_return = backtest_results.get('total_return', 0)
                sharpe = backtest_results.get('sharpe_ratio', 0)
                max_drawdown = backtest_results.get('max_drawdown', 0)
                
                self.signal_log.emit(f"📈 Total Return: {total_return:.2f}%")
                self.signal_log.emit(f"📊 Sharpe Ratio: {sharpe:.3f}")
                self.signal_log.emit(f"📉 Max Drawdown: {max_drawdown:.2f}%")
            else:
                self.signal_log.emit("⚠️ Backtest failed")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to backtest: {e}")
            self.signal_log.emit(f"❌ Error: {e}")
            logger.error(f"Failed to backtest: {e}")
    
    def on_save_model(self):
        """Save trained model"""
        try:
            if not self.logic.model:
                QMessageBox.warning(self, "Warning", "No model to save")
                return
            
            # Open file dialog
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Model",
                str(Path.home() / "prediction_model.pkl"),
                "Model Files (*.pkl *.h5);;All Files (*)"
            )
            
            if file_path:
                self.logic.save_model(file_path)
                self.signal_log.emit(f"💾 Model saved: {file_path}")
                QMessageBox.information(self, "Success", "Model saved successfully")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save model: {e}")
            self.signal_log.emit(f"❌ Error: {e}")
            logger.error(f"Failed to save model: {e}")
    
    def on_load_model(self):
        """Load saved model"""
        try:
            # Open file dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Load Model",
                str(Path.home()),
                "Model Files (*.pkl *.h5);;All Files (*)"
            )
            
            if file_path:
                self.logic.load_model(file_path)
                self.signal_log.emit(f"📂 Model loaded: {file_path}")
                
                # Enable prediction buttons
                self.btn_predict.setEnabled(True)
                self.btn_backtest.setEnabled(True)
                self.btn_save_model.setEnabled(True)
                
                QMessageBox.information(self, "Success", "Model loaded successfully")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load model: {e}")
            self.signal_log.emit(f"❌ Error: {e}")
            logger.error(f"Failed to load model: {e}")
    
    def on_model_changed(self, index):
        """Handle model selection change"""
        model = self.combo_model.currentText()
        self.signal_log.emit(f"🔄 Model selected: {model}")
    
    def on_data_source_changed(self, index):
        """Handle data source selection change"""
        data_source = self.combo_data_source.currentText()
        self.signal_log.emit(f"🔄 Data source selected: {data_source}")
    
    def on_period_changed(self, index):
        """Handle prediction period change"""
        period = self.combo_period.currentText()
        self.signal_log.emit(f"🔄 Prediction period: {period}")
    
    def append_log(self, message):
        """Append message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.text_log.append(f"[{timestamp}] {message}")
    
    def update_metrics(self, metrics: dict):
        """Update performance metrics display"""
        try:
            # MAE
            if 'train_mae' in metrics:
                self.table_metrics.setItem(0, 1, QTableWidgetItem(f"{metrics['train_mae']:.6f}"))
            if 'val_mae' in metrics:
                self.table_metrics.setItem(0, 2, QTableWidgetItem(f"{metrics['val_mae']:.6f}"))
            if 'test_mae' in metrics:
                self.table_metrics.setItem(0, 3, QTableWidgetItem(f"{metrics['test_mae']:.6f}"))
            
            # RMSE
            if 'train_rmse' in metrics:
                self.table_metrics.setItem(1, 1, QTableWidgetItem(f"{metrics['train_rmse']:.6f}"))
            if 'val_rmse' in metrics:
                self.table_metrics.setItem(1, 2, QTableWidgetItem(f"{metrics['val_rmse']:.6f}"))
            if 'test_rmse' in metrics:
                self.table_metrics.setItem(1, 3, QTableWidgetItem(f"{metrics['test_rmse']:.6f}"))
            
            # R²
            if 'train_r2' in metrics:
                self.table_metrics.setItem(2, 1, QTableWidgetItem(f"{metrics['train_r2']:.6f}"))
            if 'val_r2' in metrics:
                self.table_metrics.setItem(2, 2, QTableWidgetItem(f"{metrics['val_r2']:.6f}"))
            if 'test_r2' in metrics:
                self.table_metrics.setItem(2, 3, QTableWidgetItem(f"{metrics['test_r2']:.6f}"))
            
            # Sharpe Ratio
            if 'train_sharpe' in metrics:
                self.table_metrics.setItem(3, 1, QTableWidgetItem(f"{metrics['train_sharpe']:.4f}"))
            if 'val_sharpe' in metrics:
                self.table_metrics.setItem(3, 2, QTableWidgetItem(f"{metrics['val_sharpe']:.4f}"))
            if 'test_sharpe' in metrics:
                self.table_metrics.setItem(3, 3, QTableWidgetItem(f"{metrics['test_sharpe']:.4f}"))
                
        except Exception as e:
            logger.error(f"Failed to update metrics: {e}")
    
    def update_chart(self, data: dict):
        """Update prediction chart with uncertainty visualization"""
        try:
            chart_type = data.get('type', 'prediction')
            
            self.ax.clear()
            self.ax.set_title("Price Prediction with Confidence Interval", fontsize=12, fontweight='bold')
            self.ax.set_xlabel("Time", fontsize=10)
            self.ax.set_ylabel("Price (KRW)", fontsize=10)
            self.ax.grid(True, alpha=0.3)
            
            if chart_type == 'prediction':
                predictions = data.get('predictions', [])
                if predictions:
                    # Get historical data from logic
                    historical = self.logic.get_historical_data()
                    
                    # Plot historical (actual prices in blue)
                    if historical is not None and len(historical) > 0:
                        hist_x = range(len(historical))
                        self.ax.plot(hist_x, historical, label='Actual Price', 
                                   color='#3498db', linewidth=2)
                    
                    # Plot predictions (predicted prices in green as positive)
                    pred_x = range(len(historical), len(historical) + len(predictions))
                    self.ax.plot(pred_x, predictions, label='Predicted Price', 
                               color='#27ae60', linewidth=2, linestyle='--', marker='o')
                    
                    # Add MC Dropout uncertainty (신뢰 구간) if available
                    uncertainty_lower = data.get('uncertainty_lower', None)
                    uncertainty_upper = data.get('uncertainty_upper', None)
                    
                    if uncertainty_lower is not None and uncertainty_upper is not None:
                        # Fill between upper and lower bounds (95% confidence interval)
                        self.ax.fill_between(pred_x, uncertainty_lower, uncertainty_upper,
                                           alpha=0.3, color='#2ecc71',
                                           label='95% Confidence Interval (MC Dropout)')
                        
                        self.signal_log.emit(f"📊 Showing predictions with MC Dropout uncertainty")
                    else:
                        self.signal_log.emit(f"📊 Showing predictions (uncertainty not available)")
                    
                    self.ax.legend(loc='best', fontsize=9)
            
            elif chart_type == 'backtest':
                results = data.get('results', {})
                actual = results.get('actual', [])
                predicted = results.get('predicted', [])
                
                if actual and predicted:
                    x = range(len(actual))
                    self.ax.plot(x, actual, label='Actual Price', 
                               color='#3498db', linewidth=2)
                    self.ax.plot(x, predicted, label='Predicted Price', 
                               color='#27ae60', linewidth=2, linestyle='--')
                    
                    # Calculate and show error metrics
                    mae = np.mean(np.abs(np.array(actual) - np.array(predicted)))
                    self.ax.text(0.02, 0.98, f'MAE: {mae:.2f}',
                               transform=self.ax.transAxes,
                               verticalalignment='top',
                               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
                    
                    self.ax.legend(loc='best', fontsize=9)
            
            self.canvas.draw()
            
        except Exception as e:
            logger.error(f"Failed to update chart: {e}")
            self.signal_log.emit(f"❌ Chart update failed: {e}")
    
    def closeEvent(self, event):
        """Handle widget close event"""
        if self.training_thread and self.training_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Training in Progress",
                "Training is still running. Are you sure you want to close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.training_thread.terminate()
                self.training_thread.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
    
    def on_show_help(self):
        """Show help dialog"""
        try:
            from ui.widgets.help_dialog import HelpDialog
            
            help_content = """
            <h2>예측 모델</h2>
            <p>머신러닝 기반 가격 예측 기능을 제공합니다.</p>
            
            <h3>사용법:</h3>
            <ol>
                <li><b>모델 선택:</b> LSTM, Transformer, XGBoost 등 선택</li>
                <li><b>데이터 소스:</b> Price, Technical Indicators, Combined 선택</li>
                <li><b>Lookback 설정:</b> 과거 몇 개 데이터 포인트 사용할지 지정</li>
                <li><b>학습 시작:</b> "Train Model" 버튼으로 학습 시작</li>
                <li><b>예측 실행:</b> "Predict" 버튼으로 예측 수행</li>
            </ol>
            
            <h3>모델 종류:</h3>
            <ul>
                <li><b>LSTM:</b> 시계열 패턴 학습, 단기 예측 강점</li>
                <li><b>Transformer:</b> 장기 의존성 포착, 장기 예측 강점</li>
                <li><b>XGBoost:</b> 특징 기반 예측, 빠른 추론</li>
            </ul>
            
            <h3>신규 기능:</h3>
            <ul>
                <li><b>불확실성 정량화:</b> MC Dropout으로 예측 신뢰 구간 계산</li>
                <li><b>푸리에 분석:</b> 가격 주기성 탐지 (4시간, 1일, 1주)</li>
                <li><b>앙상블:</b> 여러 모델 결합으로 정확도 향상</li>
            </ul>
            
            <h3>신뢰 구간 해석:</h3>
            <ul>
                <li><b>좁은 구간:</b> 예측 신뢰도 높음 (80% 이상)</li>
                <li><b>넓은 구간:</b> 예측 불확실성 높음 (50% 이하)</li>
                <li>구간이 좁을 때 거래, 넓으면 관망 권장</li>
            </ul>
            
            <h3>성능 메트릭:</h3>
            <ul>
                <li><b>MAE:</b> 평균 절대 오차 (낮을수록 좋음)</li>
                <li><b>RMSE:</b> 평균 제곱근 오차 (낮을수록 좋음)</li>
                <li><b>R²:</b> 결정계수 (1에 가까울수록 좋음)</li>
            </ul>
            
            <h3>주의사항:</h3>
            <ul>
                <li>학습 데이터가 많을수록 정확도 향상</li>
                <li>과적합 방지를 위해 검증 세트 확인</li>
                <li>실시간 데이터로 주기적 재학습 필요</li>
            </ul>
            """
            
            dialog = HelpDialog("예측 모델", help_content, self)
            dialog.exec_()
            
        except Exception as e:
            logger.error(f"Failed to show help: {e}")
            QMessageBox.information(
                self,
                "도움말",
                "예측 모델 기능에 대한 도움말입니다.\n\n"
                "1. 모델 선택\n"
                "2. 데이터 소스 선택\n"
                "3. 모델 학습\n"
                "4. 예측 실행\n\n"
                "자세한 내용은 README.md를 참조하세요."
            )
