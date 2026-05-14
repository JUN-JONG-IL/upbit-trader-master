"""
Synchronous Inference Client - Direct model inference
"""

import logging
from typing import Dict, Optional, Any
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class SyncInferenceClient:
    """Synchronous inference client for direct API calls"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def infer(
        self,
        model: str,
        prompt: str,
        context: Optional[Dict] = None,
        params: Optional[Dict] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Execute synchronous inference
        
        Args:
            model: Model name or model@version
            prompt: Input prompt
            context: Additional context
            params: Model parameters
            timeout: Request timeout in seconds
            
        Returns:
            Dictionary with inference results
            
        Raises:
            requests.HTTPError: If request fails
        """
        request_id = f"sync-{datetime.now().timestamp()}"
        
        payload = {
            "request_id": request_id,
            "model": model,
            "prompt": prompt,
            "context": context or {},
            "params": params or {}
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/v1/infer",
                json=payload,
                timeout=timeout
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Inference successful: model={model}, latency={result.get('latency_ms')}ms")
            return result
            
        except requests.Timeout:
            logger.error(f"Inference timeout for model {model}")
            raise
        except requests.HTTPError as e:
            logger.error(f"Inference HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Inference failed: {e}")
            raise
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check server health
        
        Returns:
            Health status dictionary
        """
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get server metrics
        
        Returns:
            Metrics dictionary
        """
        try:
            response = self.session.get(f"{self.base_url}/metrics", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Metrics fetch failed: {e}")
            return {}
