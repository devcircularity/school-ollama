# app/ai/__init__.py
"""
AI Module
Contains Mistral integration, orchestrator, and action handlers
"""

from app.ai.router import router

__all__ = ["router"]