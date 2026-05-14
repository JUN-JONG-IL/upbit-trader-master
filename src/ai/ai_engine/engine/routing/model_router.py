"""
Model Router - Routing, A/B testing, and Canary deployment support
"""

import time
import logging
import random
from typing import Dict, Optional, Any, List
from datetime import datetime

from ..registry.model_registry import ModelRegistry

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routes inference requests to appropriate model versions"""
    
    models: Dict[str, Any] = {}
    registry: Optional[ModelRegistry] = None
    start_time: float = time.time()
    canary_config: Dict[str, Dict] = {}  # model_name -> {version, traffic_pct}
    
    @classmethod
    def initialize(cls, registry_path: str = "./models"):
        """Initialize the model router"""
        cls.registry = ModelRegistry(registry_path)
        cls.start_time = time.time()
        logger.info("ModelRouter initialized")
    
    @classmethod
    def load_model(cls, name: str, version: str) -> bool:
        """
        Load a model into memory
        
        Args:
            name: Model name
            version: Model version
            
        Returns:
            True if successful, False otherwise
        """
        if not cls.registry:
            cls.initialize()
        
        model_key = f"{name}@{version}"
        
        # Check if already loaded
        if model_key in cls.models:
            logger.info(f"Model {model_key} already loaded")
            return True
        
        # Load from registry
        model = cls.registry.load_model(name, version)
        if model is None:
            logger.error(f"Failed to load model {model_key}")
            return False
        
        cls.models[model_key] = model
        logger.info(f"Loaded model {model_key}")
        return True
    
    @classmethod
    def get_model(cls, model_spec: str) -> Optional[Any]:
        """
        Get a model by specification
        
        Args:
            model_spec: Either "name" or "name@version"
            
        Returns:
            Model object or None
        """
        if not cls.registry:
            cls.initialize()
        
        # Parse model spec
        if '@' in model_spec:
            name, version = model_spec.split('@', 1)
        else:
            name = model_spec
            version = None
        
        # Check for canary deployment
        if name in cls.canary_config:
            canary = cls.canary_config[name]
            traffic_pct = canary.get('traffic_pct', 0)
            
            # Route to canary with specified probability
            if random.random() < traffic_pct:
                version = canary['version']
                logger.debug(f"Routing to canary: {name}@{version}")
        
        # If no version specified, get latest
        if version is None:
            version = cls.registry.get_latest_version(name, status="active")
            if version is None:
                logger.error(f"No active version found for model {name}")
                return None
        
        model_key = f"{name}@{version}"
        
        # Load if not in memory
        if model_key not in cls.models:
            success = cls.load_model(name, version)
            if not success:
                return None
        
        return cls.models.get(model_key)
    
    @classmethod
    def set_canary(cls, name: str, version: str, traffic_pct: float = 0.05):
        """
        Set up canary deployment for a model
        
        Args:
            name: Model name
            version: Canary version
            traffic_pct: Percentage of traffic to route to canary (0.0-1.0)
        """
        cls.canary_config[name] = {
            'version': version,
            'traffic_pct': min(1.0, max(0.0, traffic_pct))
        }
        
        # Update model status in registry
        if cls.registry:
            cls.registry.update_status(name, version, "canary")
        
        logger.info(f"Set canary for {name}: version={version}, traffic={traffic_pct*100:.1f}%")
    
    @classmethod
    def promote_to_stable(cls, name: str, version: str):
        """
        Promote a canary model to stable
        
        Args:
            name: Model name
            version: Version to promote
        """
        # Remove canary config
        if name in cls.canary_config:
            del cls.canary_config[name]
        
        # Update status in registry
        if cls.registry:
            # Deprecate old active versions
            active_models = cls.registry.list_models(status="active")
            for model in active_models:
                if model.name == name and model.version != version:
                    cls.registry.update_status(model.name, model.version, "deprecated")
            
            # Promote new version to active
            cls.registry.update_status(name, version, "active")
        
        logger.info(f"Promoted {name}@{version} to stable")
    
    @classmethod
    def rollback(cls, name: str):
        """
        Rollback canary deployment
        
        Args:
            name: Model name
        """
        if name in cls.canary_config:
            canary_version = cls.canary_config[name]['version']
            del cls.canary_config[name]
            
            # Update status in registry
            if cls.registry:
                cls.registry.update_status(name, canary_version, "deprecated")
            
            logger.warning(f"Rolled back canary deployment for {name}")
        else:
            logger.warning(f"No canary deployment found for {name}")
    
    @classmethod
    def list_loaded_models(cls) -> List[str]:
        """Get list of loaded model keys"""
        return list(cls.models.keys())
    
    @classmethod
    def unload_model(cls, name: str, version: str) -> bool:
        """
        Unload a model from memory
        
        Args:
            name: Model name
            version: Model version
            
        Returns:
            True if successful
        """
        model_key = f"{name}@{version}"
        if model_key in cls.models:
            del cls.models[model_key]
            logger.info(f"Unloaded model {model_key}")
            return True
        return False
