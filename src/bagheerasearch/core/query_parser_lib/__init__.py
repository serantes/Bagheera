from .query_parser import BagheeraQueryParser

# Singleton instance to avoid recreating the parser on every call.
_parser: BagheeraQueryParser = None


def _get_parser() -> BagheeraQueryParser:
    """Lazily creates and caches the BagheeraQueryParser singleton."""
    global _parser
    if _parser is None:
        _parser = BagheeraQueryParser()
    return _parser


def parse_date(query):
    return _get_parser().parse_date(query)