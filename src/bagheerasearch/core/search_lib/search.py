"""
Bagheera Search Library
A Python interface for the Baloo search wrapper.
"""

import ctypes
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, Iterator, Optional, Union

from ...tools.baloo_tools import (get_dates, get_info, get_mime_type, get_xattr_terms)
from ..query_parser_lib import parse_date

from pyparsing import (
    alphanums, one_of, infix_notation, Group, OneOrMore, opAssoc,
    ParserElement, QuotedString, Word, Optional as pyOptional, Forward,
    Suppress
)

ParserElement.enable_packrat()


PROP_ANALYSIS_PATTERN = re.compile(
    r"\"[^\"]*\"|'[^']*'|\b(\w+)[ \t]*(?:==|!=|!:|>=|<=|=|>|<|:)",
    re.IGNORECASE
)


def analyze_query_properties(text: str) -> dict:
    """
    Analyzes a query string and classifies properties, correctly handling
    quoted values while identifying the property name preceding them.

    Categories:
    - dates: created, modified
    - mimetype: mimetype, type
    - property: any other property followed by an operator
    - xattr: rating, tags, usercomment
    """
    results = {
        "dates": 0,
        "mimetype": 0,
        "property": 0,
        "xattr": 0,
    }

    # Created is not supported by Baloo, but we can still recognize it as a date property.
    date_keywords = {"created", "modified"}
    mimetype_keywords = {"type", "mimetype"}
    xattr_keywords = {"tags", "rating", "usercomment"}

    # finditer allows us to process matches one by one
    for match in PROP_ANALYSIS_PATTERN.finditer(text):
        # group(1) will only be present if the third part of the regex (the
        # property) matched
        prop_name = match.group(1)

        if prop_name:
            prop_lower = prop_name.lower()

            if prop_lower in xattr_keywords:
                results["xattr"] += 1
            elif prop_lower in date_keywords:
                results["dates"] += 1
            elif prop_lower in mimetype_keywords:
                results["mimetype"] += 1
            else:
                results["property"] += 1

    return results


class EvaluateExpression:
    """
    A class to parse and evaluate complex search expressions.

    Features:
    - Logical operators (AND, OR, NOT).
    - Comparison operators (==, =, !=, !:, :, >, <, >=, <=).
    - True recursive implicit AND logic (handles 'a (b c)' and '(a b)').
    - Empty value handling (property: matches non-existence).
    """

    def __init__(self):
        """Initializes the evaluator and builds the grammar."""
        self.grammar = self._build_grammar()

    def _is_empty(self, value):
        """Checks if a value is None, an empty string, or an empty list."""
        if value is None:
            return True
        if isinstance(value, (str, list)) and len(value) == 0:
            return True
        return False

    def _compare_single(self, l_val, op, r_val):
        """Performs comparison between two values based on the operator."""
        r_is_empty_query = not r_val or (
            isinstance(r_val, str) and not r_val.strip()
        )

        if r_is_empty_query:
            l_is_empty = self._is_empty(l_val)
            if op in ("=", ":", "=="):
                return l_is_empty
            if op in ("!=", "!:"):
                return not l_is_empty
            return False

        if op == "==":
            return str(l_val) == str(r_val)

        if op in (">", "<", ">=", "<="):
            # Faster numeric check: avoid try/except if types are already numbers
            is_l_num = isinstance(l_val, (int, float))
            is_r_num = isinstance(r_val, (int, float))
            if is_l_num and is_r_num:
                if op == ">":
                    return l_val > r_val
                if op == "<":
                    return l_val < r_val
                if op == ">=":
                    return l_val >= r_val
                if op == "<=":
                    return l_val <= r_val

            try:
                curr_l, curr_r = float(l_val), float(r_val)
                if op == ">":
                    return curr_l > curr_r
                if op == "<":
                    return curr_l < curr_r
                if op == ">=":
                    return curr_l >= curr_r
                if op == "<=":
                    return curr_l <= curr_r
            except (ValueError, TypeError):
                pass

        curr_l = str(l_val).lower()
        curr_r = str(r_val).lower()

        if op == "=":
            return curr_l == curr_r
        if op == "!=":
            return curr_l != curr_r
        if op == "!:":
            return curr_r not in curr_l
        if op == ":":
            return curr_r in curr_l

        if op == ">":
            return curr_l > curr_r
        if op == "<":
            return curr_l < curr_r
        if op == ">=":
            return curr_l >= curr_r
        if op == "<=":
            return curr_l <= curr_r

        return False

    def _compare(self, data, left_key, op, right_val):
        """Resolves data keys and handles list-type values."""
        l_val = data.get(left_key)

        r_key_lookup = str(right_val).lower()
        if r_key_lookup in data:
            r_val = data[r_key_lookup]
        else:
            r_val = right_val

        if isinstance(l_val, list):
            if not l_val:
                return self._compare_single(None, op, r_val)
            return any(self._compare_single(item, op, r_val) for item in l_val)

        return self._compare_single(l_val, op, r_val)

    def _create_evaluator_func(self, tokens):
        """Creates a lambda function for a parsed condition block."""
        t = tokens[0]
        if len(t) == 1:
            return lambda data: self._compare(data, 'path', ':', t[0])

        # Pre-lower the key during compilation to save time in the loop
        l_key = t[0].lower()
        op = t[1]
        r_val = t[2] if len(t) > 2 else ""
        return lambda data: self._compare(data, l_key, op, r_val)

    def _build_grammar(self):
        """
        Constructs a grammar where parentheses always contain
        an Implicit AND sequence of expressions.
        """
        operators = one_of(["==", ">=", "<=", "!=", "!:", "=", ">", "<", ":"])
        identifier = Word(alphanums + "_./\\-")
        quoted_string = QuotedString("'") | QuotedString('"')
        operand = quoted_string | identifier

        condition = Group(
            (operand + operators + pyOptional(operand)) |
            operand
        )
        condition.set_parse_action(self._create_evaluator_func)

        # Forward declaration for the full recursive sequence
        full_expr_seq = Forward()

        # Handle implicit AND (sequence of expressions)
        def handle_implicit_and(t):
            items = t.as_list()
            if len(items) == 1:
                return items[0]
            return lambda data: all(f(data) for f in items if callable(f))

        # Manually define parentheses to wrap the full sequence
        lpar = Suppress("(")
        rpar = Suppress(")")

        # Parenthesized expression contains a sequence
        parens = lpar + full_expr_seq + rpar

        # Infix notation handles NOT, AND, OR
        # We include 'parens' as a primary atom alongside 'condition'
        atom = parens | condition

        logical_expr = infix_notation(
            atom,
            [
                ("NOT", 1, opAssoc.RIGHT, lambda t: (
                    lambda d: not t[0][1](d))),
                ("AND", 2, opAssoc.LEFT, lambda d_l: (
                    lambda d: all(f(d) for f in d_l[0] if callable(f)))),
                ("OR", 2, opAssoc.LEFT, lambda d_l: (
                    lambda d: any(f(d) for f in d_l[0] if callable(f)))),
            ]
        )

        # Define the sequence: a sequence is one or more logical expressions
        full_expr_seq <<= OneOrMore(logical_expr).set_parse_action(
            handle_implicit_and)

        return full_expr_seq

    def compile(self, expression):
        """Compiles a query string into a callable function."""
        if not expression or not expression.strip():
            return lambda data: True

        try:
            parsed = self.grammar.parse_string(expression, parse_all=True)
            return parsed[0]
        except Exception as e:
            print(f"Syntax error on expression: {e}")
            return lambda data: False


class BagheeraSearcher:
    """Class to handle Baloo searches and interact with the C wrapper."""

    def __init__(self, lib_path: Optional[Union[str, Path]] = None) -> None:
        self.ids_processed: set[int] = set()
        self.baloo_lib = self._load_baloo_wrapper(lib_path)

    def _load_baloo_wrapper(self, custom_path: Optional[Union[str, Path]]) \
            -> ctypes.CDLL:
        """Loads and configures the Baloo C wrapper library."""
        if custom_path:
            lib_path = Path(custom_path)
        else:
            lib_name = "libbaloo_wrapper.so"
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                base_dir = Path(getattr(sys, '_MEIPASS')) / 'lib'
            else:
                base_dir = Path(__file__).parent.absolute()

            search_paths = [base_dir]

            if sys.prefix != sys.base_prefix:
                venv_base = Path(sys.prefix)
                search_paths.append(venv_base / "lib64")
                search_paths.append(venv_base / "lib")

            search_paths.extend([
                Path("/lib64"),
                Path("/lib"),
                Path("/usr/lib64"),
                Path("/usr/lib"),
                Path("/usr/local/lib64"),
                Path("/usr/local/lib")
            ])

            lib_path = None
            for path in search_paths:
                potential_path = path / lib_name
                if potential_path.exists():
                    lib_path = potential_path
                    break

        if lib_path is None or not lib_path.exists():
            raise FileNotFoundError(
                f"ERROR: Baloo wrapper '{lib_name}' not found at "
                f"{search_paths}"
            )

        lib = ctypes.CDLL(str(lib_path))
        lib.execute_baloo_query.argtypes = [ctypes.c_char_p]
        lib.execute_baloo_query.restype = ctypes.c_char_p
        lib.get_file_properties.argtypes = [ctypes.c_char_p]
        lib.get_file_properties.restype = ctypes.c_char_p

        return lib

    def get_baloo_info(self, file_path: str) -> Dict[str, str]:
        """Extract properties for a specific file directly from file."""
        result = self.baloo_lib.get_file_properties(file_path.encode("utf-8"))
        if not result:
            return {}

        data_raw = result.decode("utf-8")
        properties = {}
        for entry in data_raw.split("|"):
            if ":" in entry:
                k, v = entry.split(":", 1)
                properties[k] = v

        return properties

    def _execute_query(self, options: Dict[str, Any]) -> list:
        """Helper method to execute the query against the C wrapper."""
        query_json = json.dumps(options).encode("utf-8")
        result_ptr = self.baloo_lib.execute_baloo_query(query_json)

        if not result_ptr:
            return []

        try:
            raw_results = result_ptr.decode("utf-8")
            return json.loads(raw_results)
        except json.JSONDecodeError as e:
            print(f"JSON decode error from Baloo wrapper: {e}")
            return []

    def _get_item_info(self, item, file_id, needs: dict) -> dict:
        """
        Optimized helper to build the file metadata dictionary.
        It populates keys in lowercase directly to avoid redundant loops.
        """
        info = {
            'path': item["path"],
            'filename': os.path.basename(item["path"]),
            'type': "unknown"
        }
        if needs['property']:
            for k, v in get_info(file_id).items():
                info[k.lower()] = v
        if needs['xattr']:
            for k, v in get_xattr_terms(file_id).items():
                info[k.lower()] = v
        if needs['mimetype']:
            for k, v in get_mime_type(file_id).items():
                info[k.lower()] = v
        if needs['dates']:
            for k, v in get_dates(file_id).items():
                info[k.lower()] = v
        return info

    def search_subquery(
        self,
        query_text: str,
        options: Dict[str, Any],
        search_opts: Dict[str, Any],
        files_count: int,
        having_evaluator: Any,
        having_sources: Dict[str, bool]
    ) -> Iterator[Dict[str, Any]]:
        """Executes a subquery search yielded item by item."""
        options["query"] = query_text
        files = self._execute_query(options)

        # Pre-calculate source requirements
        needs = {k: v > 0 for k, v in having_sources.items()}

        for item in files:
            if search_opts.get("limit", 0) <= 0:
                break

            file_id = int(item["id"], 16)
            if file_id in self.ids_processed:
                continue

            self.ids_processed.add(file_id)

            if having_evaluator:
                file_info = self._get_item_info(item, file_id, needs)
            else:
                file_info = None

            if not file_info or having_evaluator(file_info):
                if files_count >= search_opts.get("offset", 0):
                    search_opts["limit"] -= 1
                    yield item
                files_count += 1

    def search(
        self,
        query_text: str,
        main_options: Dict[str, Any],
        search_opts: Dict[str, Any],
    ) -> Iterator[Dict[str, Any]]:
        """
        Main search generator. Yields file dictionaries.
        """
        if search_opts['having']:
            ee = EvaluateExpression()
            having = parse_date(search_opts['having'])
            # print(f"Debug: having={having}")
            having_evaluator = ee.compile(having)
            having_sources = analyze_query_properties(having)
        else:
            having_sources = {}
            having_evaluator = None

        if search_opts['subquery_having']:
            ee = EvaluateExpression()
            having = parse_date(search_opts['subquery_having'])
            # print(f"Debug: subquery_having={having}")
            subquery_having_evaluator = ee.compile(having)
            subquery_having_sources = analyze_query_properties(having)
        else:
            subquery_having_sources = {}
            subquery_having_evaluator = None

        # Pre-calculate source requirements for the main 'having'
        needs = {k: v > 0 for k, v in having_sources.items()}

        main_options["query"] = parse_date(query_text)
        files = self._execute_query(main_options)

        if not files:
            return

        is_subquery = search_opts.get("subquery") is not None
        if is_subquery:
            if search_opts.get("type"):
                main_options["type"] = search_opts["type"]
            elif "type" in main_options:
                main_options.pop("type")

            rec_query = search_opts.get("subquery")
            query_text = parse_date(rec_query) if rec_query else ""

        files_count = 0
        for item in files:
            if search_opts.get("limit", 0) <= 0:
                break

            file_id = int(item["id"], 16)
            if file_id in self.ids_processed:
                continue

            self.ids_processed.add(file_id)

            if having_evaluator:
                file_info = self._get_item_info(item, file_id, needs)
            else:
                file_info = None

            if not file_info or having_evaluator(file_info):
                if is_subquery:
                    main_options["directory"] = item["path"]
                    yield from self.search_subquery(
                        query_text, main_options, search_opts, files_count,
                        subquery_having_evaluator, subquery_having_sources
                    )
                else:
                    yield item
                    files_count += 1

    def reset_state(self) -> None:
        """Clears the processed IDs to allow for fresh consecutive searches."""
        self.ids_processed.clear()


if __name__ == "__main__":
    # Integration test block
    print(f"Testing {__file__} integration:")
    try:
        searcher = BagheeraSearcher()
        print("✔ Library and wrapper loaded successfully.")

        # Test search (limited to 1 result for today)
        test_main_opts = {"limit": 1}
        test_search_opts = {"limit": 1}

        print("Searching for recent files...")
        results = list(searcher.search(
            "MODIFIED TODAY", test_main_opts, test_search_opts
        ))

        if results:
            print(f"✔ Found: {results[0].get('path')}")
        else:
            print("? No files found for today, but search executed correctly.")

    except FileNotFoundError as e:
        print(f"✘ Setup error: {e}")
    except Exception as e:
        print(f"✘ Unexpected error: {e}")
