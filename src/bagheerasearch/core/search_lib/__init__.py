from .search import (
    BagheeraSearcher, EvaluateExpression, _get_evaluator
)


def search(query, main_options=None, search_opts=None):
    """Simplified interface for the library."""
    if main_options is None:
        main_options = {}
    if search_opts is None:
        search_opts = {}
    bs = BagheeraSearcher()
    return bs.search(query, main_options, search_opts)


def create_evaluator(expression):
    """Utility function to create an evaluator for a given expression."""
    return _get_evaluator().compile(expression)
