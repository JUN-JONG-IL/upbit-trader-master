"""
NER Model - Named Entity Recognition for crypto entities
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class NERModel:
    """Named Entity Recognition for cryptocurrency entities"""
    
    def __init__(self):
        # Common crypto entities
        self.crypto_entities = [
            "BTC", "Bitcoin", "ETH", "Ethereum", "XRP", "Ripple",
            "DOGE", "Dogecoin", "ADA", "Cardano", "SOL", "Solana"
        ]
    
    def extract_entities(self, text: str) -> List[Dict]:
        """
        Extract named entities from text
        
        Args:
            text: Input text
            
        Returns:
            List of entity dictionaries
        """
        entities = []
        
        # Simple pattern matching for crypto entities
        for entity in self.crypto_entities:
            if entity.lower() in text.lower():
                entities.append({
                    "text": entity,
                    "type": "CRYPTO",
                    "confidence": 0.9
                })
        
        return entities
    
    def extract_crypto_symbols(self, text: str) -> List[str]:
        """
        Extract cryptocurrency symbols from text
        
        Args:
            text: Input text
            
        Returns:
            List of symbols
        """
        symbols = []
        
        for entity in self.crypto_entities:
            if entity.lower() in text.lower():
                # Extract symbol (first token)
                symbol = entity.split()[0]
                if symbol not in symbols:
                    symbols.append(symbol)
        
        return symbols


# Alias for compatibility
NamedEntityRecognizer = NERModel
