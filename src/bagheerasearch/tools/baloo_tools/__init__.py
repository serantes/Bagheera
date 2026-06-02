from .baloo_tools import BalooTools
from typing import Tuple

# Singleton instance to avoid recreating BalooTools (and its LMDB environment)
# for every property lookup on each file.
_tools: BalooTools = None


def _get_tools() -> BalooTools:
    """Lazily creates and caches the BalooTools singleton."""
    global _tools
    if _tools is None:
        _tools = BalooTools()
    return _tools


def get_dates(file_id: int) -> dict:
    """Simplified interface for the library."""
    return _get_tools().get_dates(file_id)


def get_docterms(file_id: int) -> str:
    """Simplified interface for the library."""
    return _get_tools().get_docterms(file_id)


def get_info(file_id: int) -> dict:
    """Simplified interface for the library."""
    return _get_tools().get_info(file_id)


def get_mime_type(file_id: int) -> dict:
    """Simplified interface for the library."""
    return _get_tools().get_mime_type(file_id)


def get_resolution(file_id: int) -> Tuple[int, int]:
    """Simplified interface for the library."""
    return _get_tools().get_resolution(file_id)


def get_tags(file_id: int) -> dict:
    """Simplified interface for the library."""
    return _get_tools().get_tags(file_id)


def get_xattr_terms(file_id: int) -> dict:
    """Simplified interface for the library."""
    return _get_tools().get_xattr_terms(file_id)