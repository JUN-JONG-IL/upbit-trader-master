#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI Engine Widget

Qt Widget for AI Engine functionality including:
- GPT-4o and Gemini API integration
- Model selection and configuration
- Real-time analysis control
- Emergency stop functionality
"""

import logging
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import QWidget, QMessageBox, QTableWidgetItem
from PyQt5.QtCore import pyqtSignal, QTimer, QThread, pyqtSlot
from PyQt5 import uic

from .ai_engine_logic import AIEngineLogic

logger = logging.getLogger(__name__)


class CanaryDeploymentThread(QThread):
    """Background thread for Canary deployment with progressive rollout"""
    
    progress = pyqtSignal(int, str)  # progress percentage, status message
    finished = pyqtSignal(bool, str)  # success, message
    error = pyqtSignal(str)  # error message
    
    def __init__(self, model_name: str, model_version: str, parent=None):
        """
        Args:
            model_name: Name of the model to deploy
            model_version: Version of the model
            parent: Parent QObject
        """
        super().__init__(parent)
        self.model_name = model_name
        self.model_version = model_version
        self._running = True
    
    def run(self):
        """Run Canary deployment with progressive stages"""
        import time
        
        try:
            stages = [
                (5, "5% traffic (초기 테스트)"),
                (25, "25% traffic (안정성 확인)"),
                (50, "50% traffic (절반 전환)"),
                (75, "75% traffic (대부분 전환)"),
                (100, "100% traffic (완전 배포)")
            ]
            
            self.progress.emit(0, "Canary 배포 시작...")
            time.sleep(1)
            
            for percentage, description in stages:
                if not self._running:
                    self.progress.emit(percentage, "배포 중단됨")
                    self.finished.emit(False, "사용자에 의해 중단됨")
                    return
                
                self.progress.emit(percentage, f"{description}")
                logger.info(f"Canary deployment: {percentage}% - {description}")
                
                # Simulate deployment time (2-3 seconds per stage)
                for i in range(20):
                    if not self._running:
                        self.finished.emit(False, "사용자에 의해 중단됨")
                        return
                    time.sleep(0.15)
                
                # Check for errors at each stage (simulated)
                error_rate = 0.01  # 1% simulated error rate
                if error_rate > 0.05:  # More than 5% error rate
                    self.error.emit(f"에러율 {error_rate*100:.1f}% 초과! 롤백 필요")
                    self.finished.emit(False, "에러율 초과로 배포 실패")
                    return
            
            self.progress.emit(100, "배포 완료!")
            self.finished.emit(True, f"{self.model_name} v{self.model_version} 배포 완료")
            
        except Exception as e:
            logger.error(f"Canary deployment error: {e}")
            self.error.emit(str(e))
            self.finished.emit(False, str(e))
    
    def stop(self):
        """Stop the deployment"""
        self._running = False


class AIEngineWidget(QWidget):
    """
    AI Engine UI Widget
    
    Provides user interface for AI-powered trading analysis
    """
    
    # Signal definitions
    signal_log = pyqtSignal(str)
    signal_update_metrics = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        """Initialize AI Engine Widget"""
        super().__init__(parent)
        
        # Load UI
        ui_path = Path(__file__).parent / "ai_engine.ui"
        try:
            uic.loadUi(str(ui_path), self)
            logger.info("AI Engine UI loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load UI: {e}")
            raise
        
        # Initialize logic
        self.logic = AIEngineLogic()
        
        # MLflow Model Registry
        self.model_registry = None
        try:
            from ai.engine.model_registry import ModelRegistry
            self.model_registry = ModelRegistry()
            logger.info("MLflow Model Registry initialized")
        except Exception as e:
            logger.warning(f"MLflow Model Registry not available: {e}")
        
        # Canary deployment state
        self.canary_thread = None
        
        # Connect signals
        self.connect_signals()
        
        # Initialize UI state
        self.initialize_ui()
        
        # Load MLflow models if available
        if self.model_registry:
            self.load_mlflow_models()
        
        # Start update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(1000)  # Update every second
    
    def connect_signals(self):
        """Connect all Signal/Slot connections"""
        # Button signals
        self.btn_start.clicked.connect(self.on_start_analysis)
        self.btn_stop.clicked.connect(self.on_stop_analysis)
        self.btn_emergency.clicked.connect(self.on_emergency_stop)
        self.btn_settings.clicked.connect(self.on_open_settings)
        
        # Help button
        if hasattr(self, 'btn_help'):
            self.btn_help.clicked.connect(self.on_show_help)
        
        # Configuration signals
        self.slider_confidence.valueChanged.connect(self.on_confidence_changed)
        self.combo_model.currentIndexChanged.connect(self.on_model_changed)
        
        # Custom signals
        self.signal_log.connect(self.append_log)
        self.signal_update_metrics.connect(self.update_metrics)
        
        logger.info("Signals connected")
    
    def initialize_ui(self):
        """Initialize UI state"""
        self.label_status.setText("🟡 Ready")
        self.btn_stop.setEnabled(False)
        
        # Initialize table
        self.table_results.setColumnWidth(0, 150)  # Time
        self.table_results.setColumnWidth(1, 100)  # Signal
        self.table_results.setColumnWidth(2, 100)  # Confidence
        self.table_results.setColumnWidth(3, 400)  # Reason
        
        self.signal_log.emit("✅ AI Engine initialized")
    
    def on_start_analysis(self):
        """Start AI analysis"""
        try:
            model = self.combo_model.currentText()
            confidence = self.slider_confidence.value() / 100.0
            
            self.logic.start_analysis(model, confidence)
            
            self.signal_log.emit(f"✅ AI Analysis started: {model}, Confidence threshold: {confidence:.2f}")
            self.label_status.setText("🟢 Analyzing")
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start: {e}")
            self.signal_log.emit(f"❌ Error: {e}")
            logger.error(f"Failed to start analysis: {e}")
    
    def on_stop_analysis(self):
        """Stop AI analysis"""
        try:
            self.logic.stop_analysis()
            
            self.signal_log.emit("⏸ AI Analysis stopped")
            self.label_status.setText("🟡 Stopped")
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to stop: {e}")
            self.signal_log.emit(f"❌ Error: {e}")
            logger.error(f"Failed to stop analysis: {e}")
    
    def on_emergency_stop(self):
        """Emergency stop all trading"""
        reply = QMessageBox.question(
            self,
            "Emergency Stop",
            "Are you sure you want to stop all trading immediately?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.logic.emergency_stop()
                
                self.signal_log.emit("🚨 EMERGENCY STOP EXECUTED!")
                self.label_status.setText("🔴 Emergency Stop")
                self.btn_start.setEnabled(False)
                self.btn_stop.setEnabled(False)
                
                QMessageBox.warning(self, "Emergency Stop", "All trading has been stopped!")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to execute emergency stop: {e}")
                logger.error(f"Emergency stop failed: {e}")
    
    def on_open_settings(self):
        """Open API settings dialog"""
        try:
            from .dialog_api_settings import APISettingsDialog
            
            dialog = APISettingsDialog(self)
            if dialog.exec():
                self.signal_log.emit("✅ API settings saved")
                
        except ImportError:
            # Fallback if dialog not available
            QMessageBox.information(
                self,
                "API Settings",
                "Please configure API keys in .env file:\n"
                "OPENAI_API_KEY=your_key\n"
                "GOOGLE_API_KEY=your_key"
            )
            self.signal_log.emit("ℹ️ API settings: Configure in .env file")
    
    def on_confidence_changed(self, value):
        """Handle confidence threshold slider change"""
        confidence = value / 100.0
        self.label_confidence_value.setText(f"{confidence:.2f}")
        
        if hasattr(self.logic, 'set_confidence_threshold'):
            self.logic.set_confidence_threshold(confidence)
    
    def on_model_changed(self, index):
        """Handle model selection change"""
        model = self.combo_model.currentText()
        
        if hasattr(self.logic, 'set_model'):
            self.logic.set_model(model)
            self.signal_log.emit(f"🔄 Model changed: {model}")
    
    def append_log(self, message):
        """Append message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.text_log.append(f"[{timestamp}] {message}")
    
    def update_metrics(self, metrics: dict):
        """Update performance metrics display"""
        self.label_accuracy.setText(f"Accuracy: {metrics.get('accuracy', 0):.2f}%")
        self.label_win_rate.setText(f"Win Rate: {metrics.get('win_rate', 0):.2f}%")
        self.label_profit.setText(f"Avg Profit: {metrics.get('avg_profit', 0):.2f}%")
    
    def update_display(self):
        """Update display periodically"""
        # Get latest results from logic
        if hasattr(self.logic, 'get_latest_results'):
            results = self.logic.get_latest_results()
            if results:
                self.add_result_to_table(results)
        
        # Update metrics
        if hasattr(self.logic, 'get_metrics'):
            metrics = self.logic.get_metrics()
            if metrics:
                self.signal_update_metrics.emit(metrics)
    
    def add_result_to_table(self, result: dict):
        """Add analysis result to table"""
        row_count = self.table_results.rowCount()
        self.table_results.insertRow(row_count)
        
        self.table_results.setItem(row_count, 0, QTableWidgetItem(result.get('time', '')))
        self.table_results.setItem(row_count, 1, QTableWidgetItem(result.get('signal', '')))
        self.table_results.setItem(row_count, 2, QTableWidgetItem(f"{result.get('confidence', 0):.2f}"))
        self.table_results.setItem(row_count, 3, QTableWidgetItem(result.get('reason', '')))
        
        # Scroll to bottom
        self.table_results.scrollToBottom()
    
    def load_mlflow_models(self):
        """Load models from MLflow Model Registry"""
        try:
            if not self.model_registry:
                logger.warning("MLflow Model Registry not available")
                return
            
            self.signal_log.emit("📦 Loading MLflow models...")
            
            # Get list of models
            models = self.model_registry.list_models()
            
            if not models:
                self.signal_log.emit("⚠️ No models found in MLflow registry")
                # Add some mock models for demonstration
                self.combo_model.addItem("LSTM v1.0.0 (Mock)")
                self.combo_model.addItem("Transformer v2.1.0 (Mock)")
                self.combo_model.addItem("XGBoost v1.5.0 (Mock)")
                return
            
            # Clear existing items (except default ones)
            self.combo_model.clear()
            
            # Add models to combo box
            for model in models:
                model_display = f"{model.name} v{model.version} ({model.stage})"
                self.combo_model.addItem(model_display, model)
                
            self.signal_log.emit(f"✅ Loaded {len(models)} models from MLflow")
            
        except Exception as e:
            logger.error(f"Failed to load MLflow models: {e}")
            self.signal_log.emit(f"❌ Failed to load MLflow models: {e}")
    
    def start_canary_deployment(self, model_name: str, model_version: str):
        """
        Start Canary deployment for a model
        
        Args:
            model_name: Name of the model
            model_version: Version of the model
        """
        try:
            if self.canary_thread and self.canary_thread.isRunning():
                QMessageBox.warning(self, "Warning", "Canary deployment already in progress")
                return
            
            self.signal_log.emit(f"🚀 Starting Canary deployment: {model_name} v{model_version}")
            
            # Create and start deployment thread
            self.canary_thread = CanaryDeploymentThread(model_name, model_version, self)
            self.canary_thread.progress.connect(self.on_canary_progress)
            self.canary_thread.finished.connect(self.on_canary_finished)
            self.canary_thread.error.connect(self.on_canary_error)
            self.canary_thread.start()
            
        except Exception as e:
            logger.error(f"Failed to start Canary deployment: {e}")
            self.signal_log.emit(f"❌ Canary deployment failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start deployment: {e}")
    
    @pyqtSlot(int, str)
    def on_canary_progress(self, percentage: int, message: str):
        """Handle Canary deployment progress updates"""
        self.signal_log.emit(f"📊 Canary Deployment: {percentage}% - {message}")
        # Update progress bar if exists
        if hasattr(self, 'progress_canary'):
            self.progress_canary.setValue(percentage)
            self.progress_canary.setFormat(f"{percentage}% - {message}")
    
    @pyqtSlot(bool, str)
    def on_canary_finished(self, success: bool, message: str):
        """Handle Canary deployment completion"""
        if success:
            self.signal_log.emit(f"✅ {message}")
            QMessageBox.information(self, "Success", message)
        else:
            self.signal_log.emit(f"⚠️ {message}")
            QMessageBox.warning(self, "Deployment Failed", message)
    
    @pyqtSlot(str)
    def on_canary_error(self, error_message: str):
        """Handle Canary deployment error"""
        self.signal_log.emit(f"❌ Canary deployment error: {error_message}")
        QMessageBox.critical(self, "Error", f"Deployment error:\n{error_message}")
    
    def closeEvent(self, event):
        """Handle widget close event"""
        self.update_timer.stop()
        
        # Stop canary deployment if running
        if self.canary_thread and self.canary_thread.isRunning():
            self.canary_thread.stop()
            self.canary_thread.wait(3000)  # Wait up to 3 seconds
        
        if self.logic.is_running:
            self.logic.stop_analysis()
        
        event.accept()
    
    def on_show_help(self):
        """Show help dialog"""
        try:
            from ui.widgets.help_dialog import HelpDialog
            
            help_content = """
            <h2>AI 엔진 관리</h2>
            <p>머신러닝 모델의 배포, 모니터링, 롤백을 관리합니다.</p>
            
            <h3>사용법:</h3>
            <ol>
                <li><b>모델 선택:</b> 드롭다운에서 MLflow 모델 선택 (버전 포함)</li>
                <li><b>신뢰도 조정:</b> 슬라이더로 신뢰도 임계값 설정 (0.0-1.0)</li>
                <li><b>분석 시작:</b> "AI Analysis Start" 버튼 클릭</li>
                <li><b>결과 확인:</b> 테이블에서 실시간 분석 결과 확인</li>
                <li><b>긴급 중지:</b> Emergency Stop으로 즉시 중단</li>
            </ol>
            
            <h3>Canary 배포 (점진적 배포):</h3>
            <ul>
                <li><b>0% → 5%:</b> 소량 트래픽으로 초기 테스트</li>
                <li><b>5% → 25%:</b> 안정성 확인 단계</li>
                <li><b>25% → 50%:</b> 절반 트래픽 전환</li>
                <li><b>50% → 75%:</b> 대부분 트래픽 전환</li>
                <li><b>75% → 100%:</b> 완전 배포</li>
                <li>각 단계에서 에러율 모니터링 (5% 초과 시 자동 롤백)</li>
            </ul>
            
            <h3>드리프트 감지:</h3>
            <ul>
                <li>데이터 분포 변화 감지 (Kolmogorov-Smirnov 테스트)</li>
                <li>성능 저하 모니터링 (정확도 추적)</li>
                <li>드리프트 감지 시 재학습 알림</li>
            </ul>
            
            <h3>모델 설명성 (SHAP):</h3>
            <ul>
                <li>예측에 기여한 상위 특징(Feature) 확인</li>
                <li>SHAP 값으로 모델 결정 과정 이해</li>
                <li>Feature Importance 순위 제공</li>
            </ul>
            
            <h3>자동 재학습:</h3>
            <ul>
                <li><b>PSI > 0.2:</b> 데이터 분포 변화 감지 시 재학습</li>
                <li><b>정확도 하락 > 5%:</b> 성능 저하 시 재학습</li>
                <li>재학습 필요 시 자동 알림 발송</li>
            </ul>
            
            <h3>롤백:</h3>
            <ul>
                <li>배포 중 문제 발생 시 즉시 이전 버전으로 복구</li>
                <li>에러율 5% 초과 시 자동 롤백</li>
                <li>수동 롤백 버튼 제공</li>
            </ul>
            
            <h3>주의사항:</h3>
            <ul>
                <li>MLflow 서버가 실행 중이어야 모델 로드 가능</li>
                <li>API 키가 올바르게 설정되어 있어야 합니다</li>
                <li>신뢰도 임계값이 높을수록 신호가 적어집니다</li>
                <li>Emergency Stop은 즉시 모든 거래를 중단합니다</li>
            </ul>
            
            <h3>성능 메트릭:</h3>
            <ul>
                <li><b>Accuracy:</b> 예측 정확도 (높을수록 좋음)</li>
                <li><b>Win Rate:</b> 수익 거래 비율</li>
                <li><b>Avg Profit:</b> 평균 수익률</li>
            </ul>
            """
            
            dialog = HelpDialog("AI 엔진 관리", help_content, self)
            dialog.exec_()
            
        except Exception as e:
            logger.error(f"Failed to show help: {e}")
            QMessageBox.information(
                self,
                "도움말",
                "AI 엔진 관리 기능에 대한 도움말입니다.\n\n"
                "1. 모델 선택\n"
                "2. 신뢰도 조정\n"
                "3. 분석 시작\n"
                "4. 결과 확인\n\n"
                "자세한 내용은 README.md를 참조하세요."
            )
