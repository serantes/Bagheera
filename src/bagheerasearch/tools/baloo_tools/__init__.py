import json
from .baloo_tools import BalooTools
from typing import Tuple


def get_docterms(id: int) -> str:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_docterms(id)


def get_info(id: int) -> json:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_info(id)


def get_mime_type(id: int) -> str:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_mime_type(id)


def get_rating(id: int) -> int:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_rating(id)


def get_resolution(id: int) -> Tuple[int, int]:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_resolution(id)


def get_tags(id: int) -> json:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_tags(id)


def get_user_comment(id: int) -> str:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_user_comment(id)
