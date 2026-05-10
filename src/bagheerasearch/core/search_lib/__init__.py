from .search import (
    BagheeraSearcher, EvaluateExpression
)


def search(query):
    """Interfaz simplificada para la librería."""
    bs = BagheeraSearcher()
    return bs.search(query)


def create_evaluator(expression):
    ee = EvaluateExpression()
    return ee.compile(expression)
