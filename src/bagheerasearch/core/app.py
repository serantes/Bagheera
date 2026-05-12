#!/usr/bin/env python3
# flake8: noqa: E501
"""
Bagheera Search Tool - CLI Client
"""

import argparse
import json
import os
import sys
from pathlib import Path
# from baloo_tools import get_resolution
# from date_query_parser import parse_date
from .search_lib import BagheeraSearcher

# --- CONFIGURATION ---
PROG_NAME = "Bagheera Search Tool"
PROG_ID = "bagheerasearch"
PROG_VERSION = "1.1.0"
PROG_BY = "Ignacio Serantes"
PROG_DATE = "2026-05-10"

CONFIG_DIR = Path.home() / ".config" / PROG_ID
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """Loads user configuration from disk."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not load config file: {e}")
    return {}


def save_config(config: dict) -> None:
    """Saves user configuration to disk."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except OSError as e:
        print(f"Warning: Could not save config file: {e}")


def print_help_query() -> None:
    """Prints the detailed help for query syntax."""
    help_query = f"""{PROG_NAME} uses the Baloo search engine, which is part of the KDE ecosystem. The following help section is derived from Baloo documentation (as of 2025-01-01) with additional Bagheera-specific details. It may not reflect the latest Baloo features; please refer to official Baloo resources for the most up-to-date information.

Baloo offers a rich syntax for searching through your files. Certain attributes of a file can be searched through.

For example 'type' can be used to filter for files based on their general type:

  type:Audio OR type:Document

The following comparison operators are supported, but note that 'not equal' (!=) operator is not available in Baloo search engine.
  · :   - contains (only for text comparison)
  · =   - equal
  · >   - greater than
  · >=  - greater than or equal to
  · <   - less than
  · <=  - less than or equal to

Currently the following types, to use in --type property, are supported:
  · Archive
  · Folder
  · Audio
  · Video
  · Image
  · Document
    · Spreadsheet
    · Presentation
  · Text

These expressions can be combined using logical operators 'AND' or 'OR' and additional parenthesis, but note that 'NOT' logical operator is not available.


The full list of properties which can be searched is listed below. They are grouped by file types.

All Files
  · filename
  · mimetype
  · modified (formated as yyyy-MM-dd[ hh[:mm[:ss]]])
  · rating
  · tags
  · userComment

Audio
  · Album
  · AlbumArtist
  · Artist
  · BitRate
  · Channels
  · Comment
  · Composer
  · Duration (this value must be in seconds, for example use 'duration > 300' to find files longer than 5 minutes)
  · Genre
  · Lyricist
  · ReleaseYear
  · SampleRate
  · TrackNumber

Documents
  · Author
  · Copyright
  · CreationDate (formated as yyyy-MM-dd[ hh[:mm[:ss]]])
  · Generator
  · Keywords
  · Language
  · LineCount
  · PageCount
  · Publisher
  · Subject
  · Title
  · WordCount

Media
  · AspectRatio
  · FrameRate
  · Height
  · Width

Images
  · ImageDateTime
  · ImageMake
  · ImageModel
  · ImageOrientation
  · PhotoApertureValue
  · PhotoDateTimeOriginal
  · PhotoExposureBiasValue
  · PhotoExposureTime
  · PhotoFlash
  · PhotoFNumber
  · PhotoFocalLength
  · PhotoFocalLengthIn35mmFilm
  · PhotoGpsAltitude
  · PhotoGpsLatitude
  · PhotoGpsLongitude
  · PhotoISOSpeedRatings
  · PhotoMeteringMode
  · PhotoPixelXDimension
  · PhotoPixelYDimension
  · PhotoSaturation
  · PhotoSharpness
  · PhotoWhiteBalance

Next properties are undocumented but available in source code, may work or not, but worth trying:
  · AssistiveAlternateDescription
  · Arranger
  · AudioCodec
  · ColorSpace
  · Compilation
  · Conductor
  · Description
  · DiscNumber
  · Ensemble
  · Label
  · License
  · Location
  · Lyrics
  · Manufacturer
  · Model
  · Opus
  · OriginUrl
  · OriginEmailSubject
  · OriginEmailSender
  · OriginEmailMessageId
  · Performer
  · PixelFormat
  · ReplayGainAlbumPeak
  · ReplayGainAlbumGain
  · ReplayGainTrackPeak
  · ReplayGainTrackGain
  · TranslationUnitsTotal
  · TranslationUnitsWithTranslation
  · TranslationUnitsWithDraftTranslation
  · TranslationLastAuthor
  · TranslationLastUpDate
  · TranslationTemplateDate
  · VideoCodec

Baloo documentation ends here, but {PROG_NAME} adds some extra features on top of it.

Search engine recognizes some natural language sentences in English, as long as they are capitalized, and transforms them into queries that can be interpreted by the search engine.

Supported natural language sentences and patterns for queries are:
  · MODIFIED TODAY
  · MODIFIED YESTERDAY
  · MODIFIED THIS [ DAY | WEEK | MONTH | YEAR ]
  · MODIFIED LAST <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ]
  · MODIFIED <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ] AGO

<NUMBER> can be any number or a number text from ONE to TWENTY.


The --having and --subquery-having options allow you to filter files out of the results.
The syntax for both options supports parentheses and logical operators (AND, OR, and NOT) to combine multiple patterns.
In addition to standard query comparison operators, the not equal (!=) operator is available for comparing properties against specific values. Furthermore, you can compare two properties directly; for example, 'width > height' is a valid expression.

Remarks:
  · Text comparisons are case sensitive with '==' operator but case insensitive with '=' and ':' operators. For example, 'filename:report' would match 'report.docx', 'Report.docx', and 'REPORT.docx', while 'filename==report.docx' would only match 'report.docx'.
  · Tags comparisons are performed against both individual full tag string (using the '/' character as a level separator) and each individual level. All individual level values are normalized stripped of accents or diacritics. For example, a file tagged as 'Opera,Person/María Callas,Singer' would match any of the following elements: ['Callas', 'Maria', 'Person', 'Opera', 'Person/María Callas', 'Singer']."
  · Only text and numeric data are supported, dates are not supported as of now.
  · Baloo limit of at least three characters for property values is not applied in --having and --subquery-having options, so you can use shorter values in those options.

For example, if you have a tag named 'Science' and another one 'Science Fiction' you can't obtain only results tagged with 'Science' becouse Baloo search engine will match both 'Science' and 'Science Fiction' tags when you use 'tags:Science' in your query. To exclude results tagged with 'Science Fiction' you can use the following query:
    {PROG_ID} tags:Science --having "NOT tags=Fiction" """
    print(help_query)


def print_version() -> None:
    """Prints version information."""
    print(f"{PROG_NAME} v{PROG_VERSION} - {PROG_DATE}")
    print(
        f"Copyright (C) {PROG_DATE[:4]} by {PROG_BY} and, mostly, "
        "the good people at KDE"
    )

def main():
    parser = argparse.ArgumentParser(
        description="An improved search tool for Baloo"
    )
    parser.add_argument("query", nargs="?", help="list of words to query for")
    parser.add_argument("-d", "--directory", help="limit search to specified directory tree")
    parser.add_argument("-e", "--having", help="having expression applied over query results")
    parser.add_argument("-i", "--id", action="store_true", help="show document IDs")
    parser.add_argument("-k", "--konsole", action="store_true", help="show files using file:/ and quotes")
    parser.add_argument("-l", "--limit", type=int, help="the maximum number of results")
    parser.add_argument("-o", "--offset", type=int, help="offset from which to start the search")
    parser.add_argument("-q", "--subquery", nargs="?", const="", default=None, help="enable a subquery over folder results with or without a query")
    parser.add_argument("-n", "--subquery-indent", help="subquery results indent character")
    parser.add_argument("-x", "--subquery-having", help="having expression applied over subquery results")
    parser.add_argument("-s", "--sort", help="sorting criteria <auto|none>")
    parser.add_argument("-t", "--type", help="type of Baloo data to be searched")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode")

    parser.add_argument("--day", type=int, help="day fixed filter, --month is required")
    parser.add_argument("--month", type=int, help="month fixed filter, --year is required")
    parser.add_argument("--year", type=int, help="year fixed filter")

    parser.add_argument("--help-query", action="store_true", help="show query syntax help")
    parser.add_argument("--version", action="store_true", help="show version information")

    args, unknown_args = parser.parse_known_args()

    query_parts = [args.query] if args.query else []
    if unknown_args:
        query_parts.extend(unknown_args)

    query_text = " ".join(query_parts)

    if args.day is not None and args.month is None:
        raise ValueError("Missing --month (required when --day is used)")

    if args.month is not None and args.year is None:
        raise ValueError("Missing --year (required when --month is used)")

    if args.help_query:
        print_help_query()
        return

    if args.version:
        print_version()
        return

    if not query_text and not args.subquery and not args.type and not args.directory:
        parser.print_help()
        return

    # Configuration and Sort restoring
    user_config = load_config()
    if args.sort:
        user_config["last_sort_order"] = args.sort
        save_config(user_config)
    elif "last_sort_order" in user_config:
        args.sort = user_config["last_sort_order"]

    # Build options dictionary
    main_options = {}
    if args.subquery is not None:
        main_options["type"] = "folder"
    else:
        if args.limit is not None:
            main_options["limit"] = args.limit
        if args.offset is not None:
            main_options["offset"] = args.offset
        if args.type:
            main_options["type"] = args.type

    if args.directory:
        main_options["directory"] = args.directory
    if args.year is not None:
        main_options["year"] = args.year
    if args.month is not None:
        main_options["month"] = args.month
    if args.day is not None:
        main_options["day"] = args.day
    if args.sort:
        main_options["sort"] = args.sort

    other_options = {
        "having": args.having,
        "id": args.id,
        "konsole": args.konsole,
        "limit": args.limit if args.limit and args.subquery is not None else 99999999999,
        "offset": args.offset if args.offset and args.subquery is not None else 0,
        "subquery": args.subquery,
        "subquery_indent": args.subquery_indent or "",
        "subquery_having": args.subquery_having,
        "sort": args.sort,
        "type": args.type if args.subquery is not None else None,
        "verbose": args.verbose,
    }

    if other_options["verbose"]:
        print(f"Query: '{query_text}'")
        print(f"Main Options: {main_options}")
        print(f"Other Options: {other_options}")
        print("-" * 30)

    try:
        searcher = BagheeraSearcher()
        files_count = 0

        # Consumir el generador de la librería
        for item in searcher.search(query_text, main_options, other_options):
            if other_options["konsole"]:
                output = f"file:/'{item['path']}'"
            else:
                output = item["path"]

            if other_options["id"]:
                output += f" [ID: {item['id']}]"

            print(output)
            files_count += 1

        if other_options["verbose"]:
            if files_count == 0:
                print("No results found.")
            else:
                print(f"Total: {files_count} files found.")

    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
    except KeyboardInterrupt:
        # Captura Ctrl+C dentro de main para una salida inmediata y limpia
        print("\nSearch canceled at user request.")
        sys.exit(0)
    except BrokenPipeError:
        # Silencia errores cuando se usa con 'head' o 'less' y se cierra el pipe
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(1)
    except Exception as e:
        print(f"Error executing search: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Respaldo por si la interrupción ocurre fuera del bloque principal de main
        print("\nSearch canceled at user request.")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
    except Exception as e:
        print(f"Critical error: {e}")
        sys.exit(1)
