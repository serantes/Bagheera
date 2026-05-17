from .search import (
    BagheeraSearcher, EvaluateExpression
)


def search(query):
    """Simplified interface for the library."""
    bs = BagheeraSearcher()
    return bs.search(query)


def create_evaluator(expression):
    """Utility function to create an evaluator for a given expression."""
    ee = EvaluateExpression()
    return ee.compile(expression)
