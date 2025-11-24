#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration settings for CP-SAT Scheduling System
"""

import os
from typing import Dict, Any

# Default configuration
DEFAULT_CONFIG = {
    # Logging configuration
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "file": None  # Set to a path to enable file logging
    },
    
    # Google Sheets configuration
    "google_sheets": {
        "credentials_file": "service-account-creds.json",
        "scope": [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
    },
    
    # CP-SAT solver configuration
    "solver": {
        "time_limit": 90.0,
        "num_search_workers": 8,
        "log_search_progress": False
    },
    
    # Default penalties
    "default_penalties": {
        "ineligible_post": 1000,
        "skill_mismatch": 2000,
        "skill_preference_mismatch": 200,
        "consecutive_shift": 100,
        "split_shift": 5000,
        "unmet_demand": 100000,
        "over_staffing": 100000,
    },
    
    # Chart configuration
    "chart": {
        "figure_size": (20, 10),
        "shift_colors": {
            'A': 'skyblue',
            'B': 'lightgreen', 
            'C': 'lightcoral'
        },
        "font_family": ['Meiryo', 'Microsoft JhengHei', 'SimHei', 'sans-serif']
    }
}

def get_config() -> Dict[str, Any]:
    """
    Get configuration with environment variable overrides
    
    Returns:
        Configuration dictionary
    """
    config = DEFAULT_CONFIG.copy()
    
    # Override with environment variables if they exist
    if os.getenv("SCHEDULING_LOG_LEVEL"):
        config["logging"]["level"] = os.getenv("SCHEDULING_LOG_LEVEL")
    
    if os.getenv("SCHEDULING_TIME_LIMIT"):
        try:
            config["solver"]["time_limit"] = float(os.getenv("SCHEDULING_TIME_LIMIT"))
        except ValueError:
            pass
    
    if os.getenv("GOOGLE_CREDENTIALS_FILE"):
        config["google_sheets"]["credentials_file"] = os.getenv("GOOGLE_CREDENTIALS_FILE")
    
    return config