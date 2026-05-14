#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FastAPI 기반 모델 서빙 서버
RESTful API를 통한 실시간 예측 제공
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException, BackgroundTasks
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logging.warning("FastAPI not available. Model server will use mock implementation.")
    # Mock BaseModel for type hints
    class BaseModel:
        pass

from .model_registry import ModelRegistry

logger = logging.getLogger(__name__)


class PredictionRequest(BaseModel):
    """예측 요청 모델"""
    model_name: str
    model_version: Optional[str] = None
    features: List[float]
    metadata: Optional[Dict[str, Any]] = None


class PredictionResponse(BaseModel):
    """예측 응답 모델"""
    prediction: float
    confidence: float
    model_name: str
    model_version: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None


class ModelServer:
    """
    FastAPI 기반 모델 서빙 서버
    
    실시간 예측 API 제공
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        """
        Args:
            host: 서버 호스트
            port: 서버 포트
        """
        self.host = host
        self.port = port
        self.registry = ModelRegistry()
        self.loaded_models: Dict[str, Any] = {}
        
        if FASTAPI_AVAILABLE:
            self.app = FastAPI(
                title="AI Model Serving API",
                description="실시간 AI 모델 예측 서비스",
                version="1.0.0"
            )
            self._setup_routes()
        else:
            self.app = None
            logger.warning("FastAPI 미설치. Mock 서버 사용.")
    
    def _setup_routes(self):
        """API 라우트 설정"""
        
        @self.app.get("/")
        async def root():
            return {"message": "AI Model Server is running"}
        
        @self.app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "loaded_models": len(self.loaded_models)
            }
        
        @self.app.post("/predict", response_model=PredictionResponse)
        async def predict(request: PredictionRequest):
            try:
                # 모델 버전 결정
                version = request.model_version
                if not version:
                    # Production 모델 사용
                    model_info = self.registry.get_production_model(request.model_name)
                    if not model_info:
                        raise HTTPException(404, "Production 모델을 찾을 수 없습니다")
                    version = model_info.version
                
                # 모델 로드 (캐싱)
                model_key = f"{request.model_name}:{version}"
                if model_key not in self.loaded_models:
                    await self._load_model(request.model_name, version)
                
                model = self.loaded_models.get(model_key)
                if not model:
                    raise HTTPException(500, "모델 로드 실패")
                
                # 예측 수행
                prediction, confidence = await self._predict(
                    model, request.features
                )
                
                return PredictionResponse(
                    prediction=prediction,
                    confidence=confidence,
                    model_name=request.model_name,
                    model_version=version,
                    timestamp=datetime.now().isoformat(),
                    metadata=request.metadata
                )
                
            except Exception as e:
                logger.error(f"예측 실패: {e}")
                raise HTTPException(500, str(e))
        
        @self.app.get("/models")
        async def list_models():
            """등록된 모델 목록 조회"""
            models = self.registry.list_models()
            return {
                "count": len(models),
                "models": [
                    {
                        "name": m.name,
                        "version": m.version,
                        "stage": m.stage,
                        "accuracy": m.accuracy,
                        "trained_at": m.trained_at.isoformat()
                    }
                    for m in models
                ]
            }
        
        @self.app.post("/models/{name}/load")
        async def load_model(name: str, version: Optional[str] = None):
            """모델 로드"""
            try:
                if not version:
                    model_info = self.registry.get_production_model(name)
                    if not model_info:
                        raise HTTPException(404, "모델을 찾을 수 없습니다")
                    version = model_info.version
                
                await self._load_model(name, version)
                return {"status": "success", "model": f"{name}:{version}"}
                
            except Exception as e:
                logger.error(f"모델 로드 실패: {e}")
                raise HTTPException(500, str(e))
        
        @self.app.post("/models/{name}/unload")
        async def unload_model(name: str, version: Optional[str] = None):
            """모델 언로드"""
            try:
                if version:
                    key = f"{name}:{version}"
                else:
                    # 해당 이름의 모든 버전 언로드
                    keys = [k for k in self.loaded_models.keys() if k.startswith(f"{name}:")]
                    for key in keys:
                        del self.loaded_models[key]
                    return {"status": "success", "unloaded": len(keys)}
                
                if key in self.loaded_models:
                    del self.loaded_models[key]
                    return {"status": "success", "model": key}
                else:
                    raise HTTPException(404, "로드된 모델을 찾을 수 없습니다")
                
            except Exception as e:
                logger.error(f"모델 언로드 실패: {e}")
                raise HTTPException(500, str(e))
    
    async def _load_model(self, name: str, version: str):
        """
        모델 로드 (비동기)
        
        Args:
            name: 모델 이름
            version: 모델 버전
        """
        model_key = f"{name}:{version}"
        
        # 레지스트리에서 모델 정보 조회
        model_info = self.registry.get_model(name, version)
        if not model_info:
            raise ValueError(f"모델을 찾을 수 없습니다: {model_key}")
        
        # TODO: 실제 모델 로드 구현
        # 현재는 Mock 모델 생성
        self.loaded_models[model_key] = {
            "name": name,
            "version": version,
            "loaded_at": datetime.now()
        }
        
        logger.info(f"모델 로드 완료: {model_key}")
    
    async def _predict(self, model: Any, features: List[float]) -> tuple:
        """
        예측 수행
        
        Args:
            model: 로드된 모델
            features: 입력 특징
        
        Returns:
            (prediction, confidence): 예측값과 신뢰도
        """
        # TODO: 실제 예측 로직 구현
        # 현재는 Mock 예측
        import random
        prediction = sum(features) / len(features) if features else 0.0
        confidence = random.uniform(0.7, 0.95)
        
        return prediction, confidence
    
    def start(self):
        """서버 시작"""
        if not FASTAPI_AVAILABLE:
            logger.error("FastAPI가 설치되지 않았습니다")
            return
        
        try:
            import uvicorn
            logger.info(f"모델 서버 시작: {self.host}:{self.port}")
            uvicorn.run(self.app, host=self.host, port=self.port)
        except ImportError:
            logger.error("uvicorn이 설치되지 않았습니다")
        except Exception as e:
            logger.error(f"서버 시작 실패: {e}")


# 싱글톤 인스턴스
_server_instance = None


def get_server() -> ModelServer:
    """글로벌 서버 인스턴스 반환"""
    global _server_instance
    if _server_instance is None:
        _server_instance = ModelServer()
    return _server_instance


# CLI 실행
if __name__ == "__main__":
    server = ModelServer()
    server.start()
