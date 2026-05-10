from .query_parser import BagheeraQueryParser


def parse_date(query):
    parser = BagheeraQueryParser()
    return parser.parse_date(query)
