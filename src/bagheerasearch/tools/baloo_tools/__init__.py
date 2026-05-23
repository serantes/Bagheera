import json
from .baloo_tools import BalooTools
from typing import Tuple


def get_dates(file_id: int) -> json:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_dates(file_id)


def get_docterms(file_id: int) -> str:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_docterms(file_id)


def get_info(file_id: int) -> json:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_info(file_id)


def get_mime_type(file_id: int) -> json:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_mime_type(file_id)


def get_resolution(file_id: int) -> Tuple[int, int]:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_resolution(file_id)


def get_tags(file_id: int) -> json:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_tags(file_id)


def get_xattr_terms(file_id: int) -> json:
    """Simplified interface for the library."""
    tools = BalooTools()
    return tools.get_xattr_terms(file_id)
