"""Main bot package."""
from .bot import create_main_bot
from .handlers import router

__all__ = ["create_main_bot", "router"]
