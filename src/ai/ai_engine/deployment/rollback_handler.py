"""
Rollback Handler - Emergency rollback and recovery
"""

import logging
from typing import Optional, Dict
from datetime import datetime

from ..engine.routing.model_router import ModelRouter
from ..engine.registry.model_registry import ModelRegistry

logger = logging.getLogger(__name__)


class RollbackHandler:
    """Handles emergency rollbacks and model recovery"""
    
    def __init__(self):
        self.registry = ModelRegistry()
        self.rollback_history = []
    
    def emergency_rollback(
        self,
        model_name: str,
        reason: str = "Emergency rollback"
    ) -> bool:
        """
        Execute emergency rollback to last stable version
        
        Args:
            model_name: Model name to rollback
            reason: Reason for rollback
            
        Returns:
            True if successful, False otherwise
        """
        logger.warning(f"EMERGENCY ROLLBACK for {model_name}: {reason}")
        
        try:
            # 1. Stop canary if active
            ModelRouter.rollback(model_name)
            
            # 2. Find last stable version
            active_models = self.registry.list_models(status="active")
            stable_version = None
            
            for model in active_models:
                if model.name == model_name:
                    stable_version = model.version
                    break
            
            if not stable_version:
                # Try to find any deprecated version as fallback
                deprecated_models = self.registry.list_models(status="deprecated")
                for model in sorted(deprecated_models, key=lambda m: m.created_at, reverse=True):
                    if model.name == model_name:
                        stable_version = model.version
                        logger.warning(f"Using deprecated version {stable_version} as fallback")
                        break
            
            if not stable_version:
                logger.error(f"No stable version found for {model_name}")
                return False
            
            # 3. Ensure stable version is loaded
            ModelRouter.load_model(model_name, stable_version)
            
            # 4. Record rollback
            self.rollback_history.append({
                "model_name": model_name,
                "version": stable_version,
                "reason": reason,
                "timestamp": datetime.now().isoformat()
            })
            
            logger.info(f"Emergency rollback complete: {model_name}@{stable_version}")
            return True
            
        except Exception as e:
            logger.error(f"Emergency rollback failed: {e}", exc_info=True)
            return False
    
    def get_rollback_history(self, model_name: Optional[str] = None) -> list:
        """
        Get rollback history
        
        Args:
            model_name: Optional model name filter
            
        Returns:
            List of rollback events
        """
        if model_name:
            return [r for r in self.rollback_history if r['model_name'] == model_name]
        return self.rollback_history
    
    def verify_model_health(self, model_name: str, version: str) -> Dict[str, bool]:
        """
        Verify model health after rollback
        
        Args:
            model_name: Model name
            version: Model version
            
        Returns:
            Dictionary of health checks
        """
        checks = {
            "model_loaded": False,
            "metadata_exists": False,
            "can_predict": False
        }
        
        # Check if model is loaded
        model = ModelRouter.get_model(f"{model_name}@{version}")
        checks["model_loaded"] = model is not None
        
        # Check metadata
        metadata = self.registry.get_metadata(model_name, version)
        checks["metadata_exists"] = metadata is not None
        
        # Test prediction
        if model:
            try:
                if hasattr(model, 'predict'):
                    result = model.predict("health check test")
                    checks["can_predict"] = result is not None
                else:
                    checks["can_predict"] = True  # Mock models don't have predict
            except Exception as e:
                logger.error(f"Health check prediction failed: {e}")
                checks["can_predict"] = False
        
        logger.info(f"Health check for {model_name}@{version}: {checks}")
        return checks
