#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI Engine Logic

Business logic for AI-powered trading analysis including:
- OpenAI GPT-4o integration
- Google Gemini integration
- Market data analysis
- Signal generation
"""

import os
import logging
from typing import Dict, Optional
from datetime import datetime
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class AIEngineLogic:
    """
    AI Engine Business Logic
    
    Handles AI model integration and trading signal generation
    """
    
    def __init__(self):
        """Initialize AI Engine Logic"""
        self.current_model = "GPT-4o"
        self.confidence_threshold = 0.7
        self.is_running = False
        
        # API clients (lazy loading)
        self._openai_client = None
        self._gemini_model = None
        
        # Results storage
        self._latest_results = []
        self._metrics = {
            'accuracy': 0.0,
            'win_rate': 0.0,
            'avg_profit': 0.0
        }
        
        logger.info("AI Engine Logic initialized")
    
    @property
    def openai_client(self):
        """Lazy load OpenAI client"""
        if self._openai_client is None:
            try:
                from openai import OpenAI
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    self._openai_client = OpenAI(api_key=api_key)
                    logger.info("OpenAI client initialized")
                else:
                    logger.warning("OPENAI_API_KEY not found in environment")
            except ImportError:
                logger.error("openai package not installed")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
        return self._openai_client
    
    @property
    def gemini_model(self):
        """Lazy load Gemini model"""
        if self._gemini_model is None:
            try:
                import google.generativeai as genai
                api_key = os.getenv("GOOGLE_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                    self._gemini_model = genai.GenerativeModel("gemini-1.5-pro")
                    logger.info("Gemini model initialized")
                else:
                    logger.warning("GOOGLE_API_KEY not found in environment")
            except ImportError:
                logger.error("google-generativeai package not installed")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini model: {e}")
        return self._gemini_model
    
    def start_analysis(self, model: str, confidence: float):
        """
        Start AI analysis
        
        Args:
            model: Model name (GPT-4o, GPT-4o-mini, Gemini 1.5 Pro, etc.)
            confidence: Confidence threshold (0.0 - 1.0)
        """
        self.current_model = model
        self.confidence_threshold = confidence
        self.is_running = True
        
        logger.info(f"AI analysis started: {model}, confidence: {confidence}")
        
        # In a real implementation, this would start a background thread
        # for continuous market analysis
    
    def stop_analysis(self):
        """Stop AI analysis"""
        self.is_running = False
        logger.info("AI analysis stopped")
    
    def emergency_stop(self):
        """Emergency stop all trading"""
        self.is_running = False
        logger.warning("EMERGENCY STOP executed")
        
        # In a real implementation, this would:
        # 1. Cancel all pending orders
        # 2. Close all positions
        # 3. Disable all automated trading
    
    def set_confidence_threshold(self, value: float):
        """Set confidence threshold"""
        self.confidence_threshold = value
        logger.info(f"Confidence threshold set to {value:.2f}")
    
    def set_model(self, model: str):
        """Set AI model"""
        self.current_model = model
        logger.info(f"Model set to {model}")
    
    def predict(self, market_data: dict) -> dict:
        """
        Generate trading prediction
        
        Args:
            market_data: Market data dictionary
        
        Returns:
            Dictionary with signal, confidence, and reason
        """
        if "GPT" in self.current_model:
            return self._predict_openai(market_data)
        else:
            return self._predict_gemini(market_data)
    
    def _predict_openai(self, data: dict) -> dict:
        """
        Generate prediction using OpenAI
        
        Args:
            data: Market data
        
        Returns:
            Prediction result
        """
        try:
            if self.openai_client is None:
                return {
                    'signal': 'HOLD',
                    'confidence': 0.0,
                    'reason': 'OpenAI client not available'
                }
            
            # Prepare market data summary
            data_summary = self._format_market_data(data)
            
            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model="gpt-4o" if "4o" in self.current_model else "gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert cryptocurrency trading analyst. "
                                   "Analyze market data and provide BUY, SELL, or HOLD signals "
                                   "with confidence scores and clear reasoning."
                    },
                    {
                        "role": "user",
                        "content": f"Analyze this market data and provide a trading signal:\n{data_summary}"
                    }
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            # Parse response
            content = response.choices[0].message.content
            
            # Simple parsing (in production, use structured output)
            signal = 'HOLD'
            confidence = 0.5
            
            if 'BUY' in content.upper():
                signal = 'BUY'
                confidence = 0.75
            elif 'SELL' in content.upper():
                signal = 'SELL'
                confidence = 0.75
            
            return {
                'signal': signal,
                'confidence': confidence,
                'reason': content[:200]  # Truncate for display
            }
            
        except Exception as e:
            logger.error(f"OpenAI prediction error: {e}")
            return {
                'signal': 'HOLD',
                'confidence': 0.0,
                'reason': f'Error: {str(e)}'
            }
    
    def _predict_gemini(self, data: dict) -> dict:
        """
        Generate prediction using Gemini
        
        Args:
            data: Market data
        
        Returns:
            Prediction result
        """
        try:
            if self.gemini_model is None:
                return {
                    'signal': 'HOLD',
                    'confidence': 0.0,
                    'reason': 'Gemini model not available'
                }
            
            # Prepare market data summary
            data_summary = self._format_market_data(data)
            
            # Call Gemini API
            prompt = (
                "You are an expert cryptocurrency trading analyst. "
                "Analyze this market data and provide a BUY, SELL, or HOLD signal "
                "with reasoning:\n\n"
                f"{data_summary}"
            )
            
            response = self.gemini_model.generate_content(prompt)
            content = response.text
            
            # Simple parsing
            signal = 'HOLD'
            confidence = 0.5
            
            if 'BUY' in content.upper():
                signal = 'BUY'
                confidence = 0.72
            elif 'SELL' in content.upper():
                signal = 'SELL'
                confidence = 0.72
            
            return {
                'signal': signal,
                'confidence': confidence,
                'reason': content[:200]  # Truncate for display
            }
            
        except Exception as e:
            logger.error(f"Gemini prediction error: {e}")
            return {
                'signal': 'HOLD',
                'confidence': 0.0,
                'reason': f'Error: {str(e)}'
            }
    
    def _format_market_data(self, data: dict) -> str:
        """Format market data for AI analysis"""
        # This is a simplified version
        # In production, include technical indicators, volume, etc.
        return f"Market Data: {data}"
    
    def get_latest_results(self) -> Optional[dict]:
        """Get latest analysis results"""
        if self._latest_results:
            return self._latest_results[-1]
        return None
    
    def get_metrics(self) -> dict:
        """Get performance metrics"""
        return self._metrics.copy()
