#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MLflow 기반 모델 레지스트리
모델 등록, 버전 관리, 상태 추적
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

try:
    import mlflow
    import mlflow.pytorch
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    logging.warning("MLflow not available. Model registry will use mock implementation.")

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """모델 메타데이터"""
    name: str
    version: str
    stage: str  # Staging, Production, Archived
    accuracy: float
    trained_at: datetime
    artifact_uri: str
    model_type: str = "unknown"
    status: str = "active"
    parameters: Dict[str, Any] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.created_at is None:
            self.created_at = datetime.now()


class ModelRegistry:
    """
    MLflow 기반 모델 레지스트리
    
    모델 등록, 버전 관리, 메타데이터 추적
    """
    
    def __init__(self, tracking_uri: str = "sqlite:///data/mlruns.db"):
        """
        Args:
            tracking_uri: MLflow tracking server URI
        """
        self.tracking_uri = tracking_uri
        self._models: Dict[str, ModelInfo] = {}
        
        if MLFLOW_AVAILABLE:
            try:
                mlflow.set_tracking_uri(tracking_uri)
                logger.info(f"MLflow 레지스트리 초기화: {tracking_uri}")
            except Exception as e:
                logger.error(f"MLflow 초기화 실패: {e}. Mock 모드로 실행됩니다.")
        else:
            logger.warning("MLflow 미설치. Mock 레지스트리 사용.")
    
    def register_model(self, model: Any, name: str, version: str, 
                      metrics: Optional[Dict[str, float]] = None,
                      model_type: str = "pytorch") -> ModelInfo:
        """
        모델 등록
        
        Args:
            model: 등록할 모델 객체
            name: 모델 이름
            version: 모델 버전
            metrics: 성능 메트릭 (accuracy, loss 등)
            model_type: 모델 타입 (pytorch, sklearn 등)
        
        Returns:
            ModelInfo: 등록된 모델 정보
        """
        try:
            artifact_uri = ""
            
            if MLFLOW_AVAILABLE:
                with mlflow.start_run(run_name=f"{name}_v{version}"):
                    # 메트릭 로깅
                    if metrics:
                        for key, value in metrics.items():
                            mlflow.log_metric(key, value)
                    
                    # 모델 로깅
                    if model_type == "pytorch":
                        mlflow.pytorch.log_model(model, name)
                    elif model_type == "sklearn":
                        mlflow.sklearn.log_model(model, name)
                    else:
                        logger.warning(f"지원되지 않는 모델 타입: {model_type}")
                    
                    artifact_uri = mlflow.get_artifact_uri()
            
            # 모델 정보 생성
            model_info = ModelInfo(
                name=name,
                version=version,
                stage="Staging",
                accuracy=metrics.get("accuracy", 0.0) if metrics else 0.0,
                trained_at=datetime.now(),
                artifact_uri=artifact_uri,
                model_type=model_type,
                status="active",
                parameters=metrics or {}
            )
            
            # 레지스트리에 저장
            key = f"{name}:{version}"
            self._models[key] = model_info
            
            logger.info(f"모델 등록 완료: {name}@{version}")
            return model_info
            
        except Exception as e:
            logger.error(f"모델 등록 실패: {e}")
            raise
    
    def promote_to_production(self, name: str, version: str) -> bool:
        """
        모델을 Production 스테이지로 승격
        
        Args:
            name: 모델 이름
            version: 모델 버전
        
        Returns:
            bool: 성공 여부
        """
        try:
            key = f"{name}:{version}"
            
            if key not in self._models:
                raise ValueError(f"모델을 찾을 수 없습니다: {key}")
            
            if MLFLOW_AVAILABLE:
                client = mlflow.tracking.MlflowClient()
                client.transition_model_version_stage(
                    name=name,
                    version=version,
                    stage="Production"
                )
            
            # 기존 Production 모델을 Archived로 변경
            for model_key, model_info in self._models.items():
                if model_info.name == name and model_info.stage == "Production":
                    model_info.stage = "Archived"
            
            # 새 모델을 Production으로 설정
            self._models[key].stage = "Production"
            
            logger.info(f"모델 Production 승격: {name}@{version}")
            return True
            
        except Exception as e:
            logger.error(f"Production 승격 실패: {e}")
            return False
    
    def list_models(self, stage: Optional[str] = None) -> List[ModelInfo]:
        """
        모델 목록 조회
        
        Args:
            stage: 필터링할 스테이지 (None이면 전체)
        
        Returns:
            List[ModelInfo]: 모델 정보 리스트
        """
        models = list(self._models.values())
        
        if stage:
            models = [m for m in models if m.stage == stage]
        
        # 최신순 정렬
        models.sort(key=lambda x: x.created_at, reverse=True)
        
        return models
    
    def get_model(self, name: str, version: str) -> Optional[ModelInfo]:
        """
        특정 모델 정보 조회
        
        Args:
            name: 모델 이름
            version: 모델 버전
        
        Returns:
            Optional[ModelInfo]: 모델 정보 (없으면 None)
        """
        key = f"{name}:{version}"
        return self._models.get(key)
    
    def get_production_model(self, name: str) -> Optional[ModelInfo]:
        """
        Production 스테이지 모델 조회
        
        Args:
            name: 모델 이름
        
        Returns:
            Optional[ModelInfo]: Production 모델 정보
        """
        for model_info in self._models.values():
            if model_info.name == name and model_info.stage == "Production":
                return model_info
        return None
    
    def delete_model(self, name: str, version: str) -> bool:
        """
        모델 삭제
        
        Args:
            name: 모델 이름
            version: 모델 버전
        
        Returns:
            bool: 성공 여부
        """
        try:
            key = f"{name}:{version}"
            
            if key in self._models:
                del self._models[key]
                logger.info(f"모델 삭제: {name}@{version}")
                return True
            else:
                logger.warning(f"모델을 찾을 수 없습니다: {key}")
                return False
                
        except Exception as e:
            logger.error(f"모델 삭제 실패: {e}")
            return False
    
    def update_metrics(self, name: str, version: str, 
                      metrics: Dict[str, float]) -> bool:
        """
        모델 메트릭 업데이트
        
        Args:
            name: 모델 이름
            version: 모델 버전
            metrics: 업데이트할 메트릭
        
        Returns:
            bool: 성공 여부
        """
        try:
            key = f"{name}:{version}"
            
            if key not in self._models:
                raise ValueError(f"모델을 찾을 수 없습니다: {key}")
            
            # 메트릭 업데이트
            self._models[key].parameters.update(metrics)
            
            # accuracy 업데이트
            if "accuracy" in metrics:
                self._models[key].accuracy = metrics["accuracy"]
            
            logger.info(f"모델 메트릭 업데이트: {name}@{version}")
            return True
            
        except Exception as e:
            logger.error(f"메트릭 업데이트 실패: {e}")
            return False


# 싱글톤 인스턴스
_registry_instance = None


def get_registry() -> ModelRegistry:
    """글로벌 레지스트리 인스턴스 반환"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ModelRegistry()
    return _registry_instance
