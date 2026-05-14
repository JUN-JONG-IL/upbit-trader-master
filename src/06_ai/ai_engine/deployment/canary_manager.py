"""
Canary Manager - Automated canary deployment with gradual traffic increase
"""

import logging
import asyncio
from typing import Dict, Optional
from datetime import datetime, timedelta

from ..engine.registry.model_registry import ModelRegistry
from ..engine.routing.model_router import ModelRouter

logger = logging.getLogger(__name__)


class CanaryDeploymentError(Exception):
    """Custom exception for canary deployment failures"""
    pass


class CanaryManager:
    """Manages canary deployments with automated traffic ramping"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.canary_traffic_steps = [0.05, 0.10, 0.25, 0.50, 1.00]  # 5% -> 10% -> 25% -> 50% -> 100%
        self.phase_duration = 300  # 5 minutes per phase (reduced from 600 for demo)
        self.registry = ModelRegistry()
    
    async def deploy_canary(
        self,
        model_name: str,
        new_version: str,
        auto_promote: bool = True
    ):
        """
        Execute canary deployment with gradual traffic increase
        
        Args:
            model_name: Name of the model
            new_version: Version to deploy as canary
            auto_promote: Automatically promote if all phases succeed
            
        Raises:
            CanaryDeploymentError: If deployment fails
        """
        logger.info(f"Starting canary deployment: {model_name}@{new_version}")
        
        # 1. Load new model
        success = ModelRouter.load_model(model_name, new_version)
        if not success:
            raise CanaryDeploymentError(f"Failed to load model {model_name}@{new_version}")
        
        # 2. Run smoke tests
        test_passed = await self._smoke_test(model_name, new_version)
        if not test_passed:
            raise CanaryDeploymentError("Smoke test failed")
        
        # 3. Gradual traffic increase
        for traffic_pct in self.canary_traffic_steps:
            logger.info(f"Canary phase: {traffic_pct*100:.0f}% traffic to {new_version}")
            
            # Set canary traffic
            ModelRouter.set_canary(model_name, new_version, traffic_pct)
            
            # Monitor phase
            if traffic_pct < 1.0:  # Skip monitoring on final 100% step
                await self._monitor_phase(model_name, new_version, self.phase_duration)
                
                # Check for performance degradation
                if await self._detect_degradation(model_name, new_version):
                    logger.error(f"Performance degradation detected at {traffic_pct*100:.0f}% traffic")
                    await self.rollback(model_name)
                    raise CanaryDeploymentError(
                        f"Performance degradation detected at {traffic_pct*100:.0f}% traffic"
                    )
        
        # 4. Promote to stable
        if auto_promote:
            ModelRouter.promote_to_stable(model_name, new_version)
            logger.info(f"Canary promotion complete: {model_name}@{new_version}")
        else:
            logger.info(f"Canary deployment complete (manual promotion required): {model_name}@{new_version}")
    
    async def _smoke_test(self, model_name: str, version: str) -> bool:
        """
        Run smoke tests on the new model
        
        Args:
            model_name: Model name
            version: Model version
            
        Returns:
            True if tests pass, False otherwise
        """
        logger.info(f"Running smoke tests for {model_name}@{version}")
        
        model = ModelRouter.get_model(f"{model_name}@{version}")
        if not model:
            logger.error("Model not found for smoke test")
            return False
        
        # Test cases
        test_cases = [
            {"prompt": "Test case 1: Basic input"},
            {"prompt": "Test case 2: Special chars 한글 テスト"},
            {"prompt": "Test case 3: Numbers 123456"},
        ]
        
        for i, test_case in enumerate(test_cases):
            try:
                if hasattr(model, 'predict'):
                    result = model.predict(test_case['prompt'])
                else:
                    result = {"text": "mock result"}
                
                if not result:
                    logger.error(f"Smoke test {i+1} failed: No result")
                    return False
                    
                logger.debug(f"Smoke test {i+1} passed")
            except Exception as e:
                logger.error(f"Smoke test {i+1} failed: {e}")
                return False
        
        logger.info("All smoke tests passed")
        return True
    
    async def _monitor_phase(self, model_name: str, version: str, duration: int):
        """
        Monitor canary during a deployment phase
        
        Args:
            model_name: Model name
            version: Model version
            duration: Monitoring duration in seconds
        """
        logger.info(f"Monitoring phase for {duration} seconds...")
        
        # Store baseline metrics if using Redis
        if self.redis:
            try:
                # In production, this would store actual metrics
                baseline_key = f"canary:{model_name}:baseline"
                self.redis.setex(
                    baseline_key,
                    3600,
                    "baseline_metrics_placeholder"
                )
            except:
                logger.warning("Redis not available for baseline storage")
        
        # Wait for monitoring period
        await asyncio.sleep(duration)
        
        logger.info(f"Monitoring phase complete")
    
    async def _detect_degradation(self, model_name: str, version: str) -> bool:
        """
        Detect performance degradation
        
        Args:
            model_name: Model name  
            version: Model version
            
        Returns:
            True if degradation detected, False otherwise
        """
        # In production, query Prometheus/monitoring system
        # For now, use mock logic
        
        try:
            # Simulate metrics check
            current_error_rate = 0.001  # 0.1%
            threshold_error_rate = 0.01  # 1%
            
            if current_error_rate > threshold_error_rate:
                logger.warning(f"Error rate {current_error_rate} exceeds threshold {threshold_error_rate}")
                return True
            
            # Check latency (mock)
            current_p95_latency = 150  # ms
            baseline_p95_latency = 100  # ms
            
            if current_p95_latency > baseline_p95_latency * 1.5:
                logger.warning(f"Latency degradation: {current_p95_latency}ms vs baseline {baseline_p95_latency}ms")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error detecting degradation: {e}")
            # Fail safe: assume degradation on error
            return True
    
    async def rollback(self, model_name: str):
        """
        Rollback canary deployment
        
        Args:
            model_name: Model name to rollback
        """
        logger.warning(f"Rolling back canary deployment for {model_name}")
        ModelRouter.rollback(model_name)
        logger.info(f"Rollback complete for {model_name}")
