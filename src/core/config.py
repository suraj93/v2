"""
Configuration loading for treasury auto-sweep engine.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class Settings:
    """Treasury auto-sweep configuration settings."""
    data_dir: Path
    policy: Dict[str, Any]
    calendar: Dict[str, Any]
    model_params: Dict[str, Any]


def load_settings(data_dir: str | Path) -> Settings:
    """
    Reads policy.json, cutoff_calendar.json, and ar_ap_model_params.json from data_dir.
    Returns structured Settings.
    
    Args:
        data_dir: Path to directory containing policy.json and cutoff_calendar.json
        
    Returns:
        Settings object with loaded configuration
        
    Raises:
        FileNotFoundError: If required config files are missing
        json.JSONDecodeError: If config files contain invalid JSON
    """
    data_path = Path(data_dir)
    
    # Load policy.json
    policy_path = data_path / "policy.json"
    if not policy_path.exists():
        raise FileNotFoundError(f"Policy file not found: {policy_path}")
    
    with open(policy_path, 'r') as f:
        policy = json.load(f)
    
    # Load cutoff_calendar.json
    calendar_path = data_path / "cutoff_calendar.json"
    if not calendar_path.exists():
        raise FileNotFoundError(f"Calendar file not found: {calendar_path}")
    
    with open(calendar_path, 'r') as f:
        calendar = json.load(f)
    
    # Load ar_ap_model_params.json
    model_params_path = data_path / "ar_ap_model_params.json"
    if not model_params_path.exists():
        raise FileNotFoundError(f"Model parameters file not found: {model_params_path}")
    
    with open(model_params_path, 'r') as f:
        model_params = json.load(f)
    
    return Settings(
        data_dir=data_path,
        policy=policy,
        calendar=calendar,
        model_params=model_params
    )
