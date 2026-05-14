"""
[Purpose]
- Preset management for scanner settings
- Save, load, and delete preset configurations

[Responsibilities]
- Save preset settings to JSON files
- Load preset settings from JSON files
- Delete preset files
- List available presets
- Provide default presets

[Main Flow]
- save_preset(name, settings) - Save settings to file
- load_preset(name) - Load settings from file
- delete_preset(name) - Delete preset file
- list_presets() - List all available presets
- get_default_preset(name) - Get built-in default presets

[Dependencies]
- json: For serialization
- os, pathlib: For file operations

[Storage]
- Presets stored in: ~/.upbit-trader/presets/scanner/

[Author] GitHub Copilot
[Created] 2026-02-03
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


# Preset storage directory
PRESET_DIR = Path.home() / ".upbit-trader" / "presets" / "scanner"


def _ensure_preset_dir():
    """Ensure preset directory exists"""
    PRESET_DIR.mkdir(parents=True, exist_ok=True)


def _preset_file_path(preset_name: str) -> Path:
    """Get preset file path"""
    # Sanitize filename
    safe_name = "".join(c for c in preset_name if c.isalnum() or c in (' ', '-', '_'))
    return PRESET_DIR / f"{safe_name}.json"


def save_preset(preset_name: str, settings: Dict[str, Any]) -> bool:
    """
    Save preset settings to file
    
    Args:
        preset_name: Name of the preset
        settings: Settings dictionary
    
    Returns:
        True if successful, False otherwise
    """
    try:
        _ensure_preset_dir()
        file_path = _preset_file_path(preset_name)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"Error saving preset '{preset_name}': {e}")
        return False


def load_preset(preset_name: str) -> Optional[Dict[str, Any]]:
    """
    Load preset settings from file
    
    Args:
        preset_name: Name of the preset
    
    Returns:
        Settings dictionary if found, None otherwise
    """
    # Try built-in presets first
    if preset_name in ["기본", "단타용", "스윙용"]:
        return get_default_preset(preset_name)
    
    # Try user presets
    try:
        file_path = _preset_file_path(preset_name)
        
        if not file_path.exists():
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        return settings
    except Exception as e:
        print(f"Error loading preset '{preset_name}': {e}")
        return None


def delete_preset(preset_name: str) -> bool:
    """
    Delete preset file
    
    Args:
        preset_name: Name of the preset
    
    Returns:
        True if successful, False otherwise
    """
    # Don't allow deleting built-in presets
    if preset_name in ["기본", "단타용", "스윙용"]:
        print(f"Cannot delete built-in preset: {preset_name}")
        return False
    
    try:
        file_path = _preset_file_path(preset_name)
        
        if file_path.exists():
            file_path.unlink()
            return True
        else:
            print(f"Preset '{preset_name}' does not exist")
            return False
    except Exception as e:
        print(f"Error deleting preset '{preset_name}': {e}")
        return False


def list_presets() -> List[str]:
    """
    List all available presets
    
    Returns:
        List of preset names
    """
    presets = ["기본", "단타용", "스윙용"]  # Built-in presets
    
    try:
        _ensure_preset_dir()
        
        # Add user presets
        for file_path in PRESET_DIR.glob("*.json"):
            preset_name = file_path.stem
            if preset_name not in presets:
                presets.append(preset_name)
    except Exception as e:
        print(f"Error listing presets: {e}")
    
    return presets


def get_default_preset(preset_name: str) -> Optional[Dict[str, Any]]:
    """
    Get built-in default preset
    
    Args:
        preset_name: Name of the preset ("기본", "단타용", "스윙용")
    
    Returns:
        Default settings dictionary
    """
    if preset_name == "기본":
        return {
            # Tab 1: Basic Indicators
            'chart_compare_enabled': False,
            'base_coin': 'KRW-BTC',
            'chart_interval': '1분',
            'ohlc_interval': '1분',
            'open_value': 0.0,
            'close_value': 0.0,
            'high_value': 0.0,
            'low_value': 0.0,
            'exclude_recent': 0,
            'golden_enabled': True,
            'golden_short_interval': '1분',
            'golden_short_period': 5,
            'golden_long_interval': '1분',
            'golden_long_period': 20,
            'use_price_diff': False,
            'price_diff_value': 1.0,
            'ma_interval': '1분',
            'ma_short': 5,
            'ma_long': 20,
            'ma_condition': '골든크로스',
            'rsi_interval': '1분',
            'rsi_period': 14,
            'rsi_threshold': 30,
            'rsi_condition': '이하',
            'rsi_div': {
                '1m': True, '5m': True, '15m': True, '30m': True,
                '1h': True, '4h': True, '1d': True,
            },
            'rsi_div_max': 70,
            'rsi_div_min': 30,
            'rsi_div_ignore': 3,
            'rsi_div_time_allow': 20,
            'rsi_div_recent_exclude': 4,
            'volume_surge': {
                '1m': False, '5m': True, '15m': True, '30m': True,
                '1h': True, '4h': True, '1d': True,
            },
            'vol_avg_count': 20,
            'vol_avg_ratio': 10,
            
            # Tab 2: Advanced Indicators
            'bb_period': 20,
            'bb_std_dev': 2.0,
            'bb_lower_touch': True,
            'bb_upper_touch': False,
            'bb_squeeze': True,
            'bb_expand': False,
            'macd_short': 12,
            'macd_long': 26,
            'macd_signal': 9,
            'macd_golden': True,
            'macd_dead': False,
            'macd_histo_inc': True,
            'macd_divergence': False,
            'stoch_k': 14,
            'stoch_d': 3,
            'stoch_slow': 3,
            'stoch_overbought': 80,
            'stoch_oversold': 20,
            'stoch_k_gt_d': True,
            'stoch_k_lt_d': False,
            'cci_period': 20,
            'cci_overbought': 100,
            'cci_oversold': -100,
            'atr_period': 14,
            'atr_multiple': 2.0,
            'atr_increase': 50,
            'fibo_period': 100,
            'fibo_236': True,
            'fibo_382': True,
            'fibo_500': True,
            'fibo_618': True,
            'fibo_786': False,
            'fibo_tolerance': 0.5,
            
            # Tab 3: Patterns & Volume
            'pattern_hammer': True,
            'pattern_doji': True,
            'pattern_triangle': False,
            'pattern_head_shoulder': False,
            'pattern_double_top': False,
            'pattern_flag': False,
            'pattern_wedge': False,
            'pattern_period': 50,
            'obv_inc': True,
            'volume_ma_cross': True,
            'volume_spike': True,
            'volume_dry_up': False,
            'volume_spike_multiple': 3.0,
            
            # Tab 4: Filters
            'min_price': 0,
            'max_price': 0,
            'min_market_cap': 0,
            'max_market_cap': 0,
            'change_24h': 0,
            'from_52w_high': 0,
            'from_52w_low': 0,
            'use_time_range': False,
            'start_time': '09:00',
            'end_time': '18:00',
            'exclude_weekend': False,
            'exclude_market_start': False,
            'exclude_market_end': False,
            'market_start_minutes': 0,
            'market_end_minutes': 0,
            'favorite_only': False,
            'use_blacklist': False,
            'blacklist': '',
            'top_market_cap': False,
            'top_market_cap_count': 50,
            'top_volume': False,
            'top_volume_count': 50,
            
            # Tab 5: Alerts
            'sound_alert': False,
            'popup_alert': True,
            'telegram_alert': False,
            'email_alert': False,
            'telegram_token': '',
            'telegram_chat_id': '',
            'email_address': '',
            'alert_cooldown': 5,
            'auto_refresh': False,
            'auto_refresh_interval': 10,
        }
    
    elif preset_name == "단타용":
        # Short-term trading preset
        base = get_default_preset("기본")
        base.update({
            'chart_interval': '1분',
            'ma_short': 3,
            'ma_long': 10,
            'rsi_threshold': 40,
            'rsi_div': {
                '1m': True, '5m': True, '15m': False, '30m': False,
                '1h': False, '4h': False, '1d': False,
            },
            'volume_surge': {
                '1m': True, '5m': True, '15m': True, '30m': False,
                '1h': False, '4h': False, '1d': False,
            },
            'vol_avg_ratio': 20,  # Higher volume threshold
            'bb_squeeze': True,
            'bb_expand': True,
            'macd_histo_inc': True,
            'auto_refresh': True,
            'auto_refresh_interval': 5,  # More frequent refresh
        })
        return base
    
    elif preset_name == "스윙용":
        # Swing trading preset
        base = get_default_preset("기본")
        base.update({
            'chart_interval': '1시간',
            'ma_short': 10,
            'ma_long': 50,
            'rsi_threshold': 30,
            'rsi_div': {
                '1m': False, '5m': False, '15m': False, '30m': False,
                '1h': True, '4h': True, '1d': True,
            },
            'volume_surge': {
                '1m': False, '5m': False, '15m': False, '30m': False,
                '1h': True, '4h': True, '1d': True,
            },
            'vol_avg_ratio': 15,
            'pattern_triangle': True,
            'pattern_head_shoulder': True,
            'pattern_double_top': True,
            'macd_divergence': True,
            'auto_refresh': True,
            'auto_refresh_interval': 30,  # Less frequent refresh
        })
        return base
    
    return None


class PresetManager:
    """
    Preset management class for scanner settings.

    Wraps module-level functions as instance methods for easy injection and testing.
    """

    def save(self, preset_name: str, settings: Dict[str, Any]) -> bool:
        """Save preset settings to file."""
        return save_preset(preset_name, settings)

    def load(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """Load preset settings from file."""
        return load_preset(preset_name)

    def delete(self, preset_name: str) -> bool:
        """Delete preset file."""
        return delete_preset(preset_name)

    def list(self) -> List[str]:
        """List all available presets."""
        return list_presets()

    def get_default(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """Get built-in default preset."""
        return get_default_preset(preset_name)


# For testing
if __name__ == '__main__':
    # Test save/load
    test_settings = get_default_preset("기본")
    save_preset("테스트", test_settings)
    
    loaded = load_preset("테스트")
    print(f"Loaded preset: {loaded is not None}")
    
    # List presets
    presets = list_presets()
    print(f"Available presets: {presets}")
    
    # Delete test preset
    delete_preset("테스트")
