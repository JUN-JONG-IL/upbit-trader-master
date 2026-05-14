"""
Model Registry - Model metadata management and versioning
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import pickle

logger = logging.getLogger(__name__)


class ModelMetadata:
    """Model metadata container"""
    
    def __init__(
        self,
        name: str,
        version: str,
        accuracy: float = 0.0,
        status: str = "active",
        created_at: Optional[datetime] = None,
        model_type: str = "unknown",
        parameters: Optional[Dict] = None
    ):
        self.name = name
        self.version = version
        self.accuracy = accuracy
        self.status = status  # active, canary, deprecated
        self.created_at = created_at or datetime.now()
        self.model_type = model_type
        self.parameters = parameters or {}
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "version": self.version,
            "accuracy": self.accuracy,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "model_type": self.model_type,
            "parameters": self.parameters
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ModelMetadata':
        """Create from dictionary"""
        data = data.copy()
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


class ModelRegistry:
    """Model Registry for managing ML models"""
    
    def __init__(self, storage_path: str = "./models"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.storage_path / "registry.json"
        self.models: Dict[str, ModelMetadata] = {}
        self._load_metadata()
    
    def _load_metadata(self):
        """Load metadata from disk"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    data = json.load(f)
                    for key, meta in data.items():
                        self.models[key] = ModelMetadata.from_dict(meta)
                logger.info(f"Loaded {len(self.models)} models from registry")
            except Exception as e:
                logger.error(f"Failed to load metadata: {e}")
                self.models = {}
    
    def _save_metadata(self):
        """Save metadata to disk"""
        try:
            data = {key: meta.to_dict() for key, meta in self.models.items()}
            with open(self.metadata_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self.models)} models to registry")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
    
    def register_model(
        self,
        name: str,
        version: str,
        model_obj: Any,
        accuracy: float = 0.0,
        model_type: str = "unknown",
        parameters: Optional[Dict] = None
    ) -> str:
        """Register a new model"""
        model_key = f"{name}@{version}"
        
        # Save model object
        model_path = self.storage_path / f"{model_key}.pkl"
        try:
            with open(model_path, 'wb') as f:
                pickle.dump(model_obj, f)
            logger.info(f"Saved model to {model_path}")
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
            raise
        
        # Create metadata
        metadata = ModelMetadata(
            name=name,
            version=version,
            accuracy=accuracy,
            status="active",
            model_type=model_type,
            parameters=parameters
        )
        
        self.models[model_key] = metadata
        self._save_metadata()
        
        logger.info(f"Registered model: {model_key}")
        return model_key
    
    def load_model(self, name: str, version: str) -> Optional[Any]:
        """Load a model by name and version"""
        model_key = f"{name}@{version}"
        model_path = self.storage_path / f"{model_key}.pkl"
        
        if not model_path.exists():
            logger.error(f"Model file not found: {model_path}")
            return None
        
        try:
            with open(model_path, 'rb') as f:
                model = pickle.load(f)
            logger.info(f"Loaded model: {model_key}")
            return model
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return None
    
    def get_metadata(self, name: str, version: str) -> Optional[ModelMetadata]:
        """Get model metadata"""
        model_key = f"{name}@{version}"
        return self.models.get(model_key)
    
    def list_models(self, status: Optional[str] = None) -> List[ModelMetadata]:
        """List all models, optionally filtered by status"""
        models = list(self.models.values())
        if status:
            models = [m for m in models if m.status == status]
        return models
    
    def update_status(self, name: str, version: str, status: str) -> bool:
        """Update model status"""
        model_key = f"{name}@{version}"
        if model_key not in self.models:
            logger.error(f"Model not found: {model_key}")
            return False
        
        self.models[model_key].status = status
        self._save_metadata()
        logger.info(f"Updated status for {model_key} to {status}")
        return True
    
    def get_latest_version(self, name: str, status: str = "active") -> Optional[str]:
        """Get the latest version of a model"""
        matching_models = [
            m for m in self.models.values()
            if m.name == name and m.status == status
        ]
        
        if not matching_models:
            return None
        
        # Sort by created_at descending
        latest = max(matching_models, key=lambda m: m.created_at)
        return latest.version
