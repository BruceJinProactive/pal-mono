"""
OLO menu processing for knowledge service.

This module provides OLO menu processing capabilities for the knowledge base,
converting OLO API responses into structured, indexed menu data.
"""

from ._implementation import OloMenuProcessor
from .menu_data import compile_olo_menu_data

__all__ = ["OloMenuProcessor", "compile_olo_menu_data"]
