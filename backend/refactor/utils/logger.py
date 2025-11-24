#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logging utility for CP-SAT Scheduling System
Provides centralized logging configuration
"""

import logging
import sys
from typing import Optional
import os

def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Setup logging configuration for the scheduling system
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path. If None, defaults to logs/system.log
        format_string: Optional custom format string
    
    Returns:
        Configured logger instance
    """
    
    # Default log file path
    if log_file is None:
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        log_file = os.path.join(log_dir, "system.log")
    
    # Default format string
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger('scheduling_system')
    logger.setLevel(numeric_level)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(format_string)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (always create)
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    logger.info(f"Logging initialized - Level: {level}, File: {log_file}")
    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a logger instance
    
    Args:
        name: Optional logger name. If None, returns the main scheduling system logger
    
    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f'scheduling_system.{name}')
    return logging.getLogger('scheduling_system')


# Convenience function for quick setup
def quick_setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Quick setup for logging with default configuration
    
    Args:
        level: Logging level
    
    Returns:
        Configured logger instance
    """
    return setup_logging(level=level)