"""
[Purpose]
Configuration loader for YAML files

[Responsibilities]
- Load and parse config.yaml
- Validate configuration structure
- Provide default values

[Main Flow]
1. Locate config.yaml file
2. Parse YAML structure
3. Validate required fields
4. Return configuration dictionary

[Dependencies]
- PyYAML
- pathlib

[Author] Copilot Workspace Refactor
[Created] 2026-03-05
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


def get_config_path(config_name: str = "config.yaml") -> Path:
    """
    Get absolute path to configuration file

    Args:
        config_name: Name of config file (default: config.yaml)

    Returns:
        Path object to config file

    Raises:
        FileNotFoundError: If config file doesn't exist
    """
    # Get src/01_core/config directory
    config_dir = Path(__file__).parent
    config_path = config_dir / config_name

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Please copy config.yaml.example to config.yaml and edit it."
        )

    return config_path


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load configuration from YAML file

    Args:
        config_path: Optional path to config file. If None, uses default config.yaml

    Returns:
        Dictionary containing configuration

    Example:
        >>> config = load_config()
        >>> print(config['UPBIT']['ACCESS_KEY'])
    """
    if config_path is None:
        config_path = get_config_path()

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # Validate required sections
    required_sections = ['LOG', 'MONGO', 'UPBIT', 'STRATEGY', 'PROGRAM']
    missing_sections = [s for s in required_sections if s not in config]

    if missing_sections:
        raise ValueError(
            f"Missing required configuration sections: {', '.join(missing_sections)}"
        )

    return config


def validate_config(config: Dict[str, Any]) -> bool:
    """
    Validate configuration structure and values

    Args:
        config: Configuration dictionary

    Returns:
        True if valid

    Raises:
        ValueError: If validation fails
    """
    # Check UPBIT keys
    upbit = config.get('UPBIT', {})
    if upbit.get('ACCESS_KEY') == 'INPUT_YOUR_UPBIT_ACCESS_KEY':
        raise ValueError(
            "UPBIT ACCESS_KEY not configured. Please edit config.yaml"
        )

    if upbit.get('SECRET_KEY') == 'INPUT_YOUR_UPBIT_SECRET_KEY':
        raise ValueError(
            "UPBIT SECRET_KEY not configured. Please edit config.yaml"
        )

    return True
