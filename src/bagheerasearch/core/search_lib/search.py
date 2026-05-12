"""
Bagheera Search Library
A Python interface for the Baloo search wrapper.
"""

import ctypes
import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, Iterator, Optional, Union

from ...tools.baloo_tools import (get_info, get_tags)
from ..query_parser_lib import parse_date

from pyparsing import (
    alphanums, one_of, infix_notation,
    Group, opAssoc, ParserElement, QuotedString, Word
)

ParserElement.enable_packrat()


def expression_contains_property(text):
    pattern = r"\b(?!tags\b)\w+[ \t]*(?:>=|<=|!=|=|>|<|:)"
    return bool(re.search(pattern, text, re.IGNORECASE))


def expression_contains_tags(text):
    pattern = r"\btags\b[ \t]*(?:>=|<=|!=|=|>|<|:)"
    return bool(re.search(pattern, text, re.IGNORECASE))


class EvaluateExpression:
    def __init__(self):
        self.grammar = self._build_grammar()

    def _compare_single(self, l_val, op, r_val):
        # 1. CASE SENSITIVE (Strict)
        if op == "==":
            return str(l_val) == str(r_val)

        # 2. NUMERIC LOGIC
        if op in (">", "<", ">=", "<="):
            try:
                # We use float for numeric magnitude
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
                # Fallback to case-insensitive string if not numeric
                pass

        # 3. CASE INSENSITIVE (Default for =, !=, :)
        curr_l = str(l_val).lower()
        curr_r = str(r_val).lower()

        if op == "=":
            return curr_l == curr_r
        if op == "!=":
            return curr_l != curr_r
        if op == ":":
            return curr_r in curr_l

        # String fallback for magnitude if numeric failed
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
        # Normalizing keys for lookup, but KEEPING the values intact
        normalized_data = {k.lower(): v for k, v in data.items()}

        # Get left value from data or use as literal
        l_val = normalized_data.get(left_key.lower(), left_key)

        # Resolve right value: if it's a key in data, use its value.
        # Important: use lower() only for the KEY lookup, not the value itself.
        r_key_lookup = str(right_val).lower()
        if r_key_lookup in normalized_data:
            r_val = normalized_data[r_key_lookup]
        else:
            r_val = right_val

        if isinstance(l_val, list):
            return any(self._compare_single(item, op, r_val) for item in l_val)

        return self._compare_single(l_val, op, r_val)

    def _build_grammar(self):
        # CRITICAL: '==' must come BEFORE '=' in the list
        # We use a list to ensure explicit priority in the parser
        operators = one_of(["==", ">=", "<=", "!=", "=", ">", "<", ":"])

        identifier = Word(alphanums + "_./\\")
        quoted_string = QuotedString("'") | QuotedString('"')
        operand = quoted_string | identifier

        condition = Group((operand + operators + operand) | operand)
        condition.set_parse_action(lambda t: self._create_evaluator_func(t[0]))

        return infix_notation(
            condition,
            [
                ("NOT", 1, opAssoc.RIGHT, lambda t: (
                    lambda data: not t[0][1](data))),
                ("AND", 2, opAssoc.LEFT, lambda t: (
                    lambda data: all(f(data) for f in t[0] if callable(f)))),
                ("OR", 2, opAssoc.LEFT, lambda t: (
                    lambda data: any(f(data) for f in t[0] if callable(f)))),
            ],
        )

    def _create_evaluator_func(self, tokens):
        if len(tokens) == 1:
            return lambda data: self._compare(data, 'path', ':', tokens[0])
        else:
            return lambda data: self._compare(
                data, tokens[0], tokens[1], tokens[2])

    def compile(self, expression):
        try:
            return self.grammar.parse_string(expression, parse_all=True)[0]
        except Exception as e:
            print(f"Compilation Error: {e}")
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

        for item in files:
            if search_opts.get("limit", 0) <= 0:
                break

            file_id = int(item["id"], 16)
            if file_id in self.ids_processed:
                continue

            self.ids_processed.add(file_id)

            if having_evaluator:
                file_info = {'path': item["path"],
                             'filename': Path(item["path"]).name}
                if having_sources.get('properties'):
                    file_info = file_info | get_info(file_id)
                if having_sources.get('tags'):
                    file_info = file_info | get_tags(file_id)
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
            having_evaluator = ee.compile(search_opts['having'])
            having_sources = {}
            if expression_contains_property(search_opts['having']):
                having_sources['properties'] = True
            if expression_contains_tags(search_opts['having']):
                having_sources['tags'] = True
        else:
            having_evaluator = None
            having_sources = {}

        if search_opts['subquery_having']:
            ee = EvaluateExpression()
            subquery_having_evaluator = ee.compile(
                search_opts['subquery_having'])
            subquery_having_sources = {}
            if expression_contains_property(search_opts['subquery_having']):
                subquery_having_sources['properties'] = True
            if expression_contains_tags(search_opts['subquery_having']):
                subquery_having_sources['tags'] = True
        else:
            subquery_having_evaluator = None
            subquery_having_sources = {}

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
                file_info = {'path': item["path"],
                             'filename': Path(item["path"]).name}
                if having_sources.get('properties'):
                    file_info = file_info | get_info(file_id)
                if having_sources.get('tags'):
                    file_info = file_info | get_tags(file_id)
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
    # Test de integración rápido
    print(f"Testing {__file__} integration:")
    try:
        searcher = BagheeraSearcher()
        print("✔ Library and wrapper loaded successfully.")

        # Intento de búsqueda de prueba (limitado a 1 resultado)
        test_main_opts = {"limit": 1}
        test_search_opts = {"limit": 1}

        print("Searching for recent files...")
        results = list(searcher.search("MODIFIED TODAY", test_main_opts,
                                       test_search_opts))

        if results:
            print(f"✔ Found: {results[0].get('path')}")
        else:
            print("? No files found for today, but search executed correctly.")

    except FileNotFoundError as e:
        print(f"✘ Setup error: {e}")
    except Exception as e:
        print(f"✘ Unexpected error: {e}")


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
