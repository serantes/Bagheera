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
from .search_lib import BagheeraSearcher

# --- CONFIGURATION ---
PROG_NAME = "Bagheera Search Tool"
PROG_ID = "bagheerasearch"
PROG_VERSION = "1.0.0"
PROG_BY = "Ignacio Serantes"
PROG_DATE = "2026-05-22"

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


- SEARCHABLE PROPERTIES -

The full list of searchable properties is listed below, grouped by file type.

All Files
  · filename
  · mimetype (Note: You cannot search for full strings like `"text/plain"`. Search for individual words: `mimetype:text AND mimetype:plain`)
  · modified (Formatted as yyyy-MM-dd)
  · rating
  · tags
  · userComment (Note: Search for individual words: `userComment:ready AND userComment:script` because **Baloo engine** does not support quoted strings within the `userComment` search)

Audio
  · Album
  · AlbumArtist
  · Artist
  · BitRate
  · Channels
  · Comment
  · Composer
  · Duration (Value in seconds; e.g., `'duration > 300'` for files longer than 5 minutes)
  · Genre
  · Lyricist
  · ReleaseYear
  · SampleRate
  · TrackNumber

Documents
  · Author
  · Copyright
  · CreationDate (Formatted as yyyy-MM-dd)
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
  · ImageDateTime (Formatted as yyyy-MM-dd. Note: Currently inconsistent in **Baloo**; use in `having` options for reliability).
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

The following properties are undocumented but available in the source code. They may or may not work, but are worth trying:
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


- BAGHEERA-SPECIFIC FEATURES -

The search engine recognizes certain English natural language phrases, provided they are capitalized, and transforms them into interpretable queries.

Supported natural language patterns are:
  · MODIFIED TODAY
  · MODIFIED YESTERDAY
  · MODIFIED THIS [ DAY | WEEK | MONTH | YEAR ]
  · MODIFIED LAST <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ]
  · MODIFIED <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ] AGO

<NUMBER> can be any number or a number text from ONE to TWENTY.

- 'Subquery' option -

The '--subquery' option allows you to perform a secondary search within the folders obtained from main query. This is particularly useful for refining searches within specific folders. When using '--subquery', the main query first filters folders based on the initial criteria; the subquery is then applied to all files located within those folders to further narrow down the search.
You can provide a query string with the '--subquery' option to filter the results of the main query, or you can use the option without additional text to simply list all items within those results.
This behavior is useful for performing deep searches. For example, you can search for all folders with 'Project' in their name and then use a subquery to find documents within those folders that were modified in the last week.

Example:
This is a complex query to locate all files of the 'Presentation' type situated within any directory that contains 'KDE' in its name, specifically under the '~/Documents' path. The search is further refined to include only those files that contain either 'Baloo' or 'Bagheera' in their metadata or filename and are not tagged as 'Obsolete' or 'Revised'.

    {PROG_ID} --directory '~/Documents' KDE --subquery 'Baloo OR Bagheera' --type Presentation --having 'NOT (tags=Obsolete OR tags=Revised)'


- 'Having' and 'subquery-having' options -

The '--having' and '--subquery-having' options allow you to filter the results returned by **Baloo**. They support the standard **Baloo** syntax plus the `NOT` operator.

Additionally, you can use:

- '==' (case-sensitive equal)
- '!=' (not equal)
- '!:' (does not contains)
- Property-to-property comparison (e.g., `width > height`).
- 'created', a **Bagheera-specific** property for file creation dates (Formatted as `yyyy-MM-dd`).

Important Remarks:
· Case Sensitivity: All text comparisons are case-insensitive unless '==' is used.
· Empty Values: You can check for the presence or absence of values using empty quotes. For example, 'tags!=""' matches any file with at least one tag, while 'tags=""' matches files with no tags.
· Tag Levels: Comparisons are performed against the full tag path and each individual level. A file tagged 'Person/Maria Callas' matches 'Maria', 'Callas', 'Person', and the full string.
· Character Limit: Unlike Baloo, the 3-character minimum limit for string values is not enforced within 'having' options.

Having exclusion example:
Get files tagget as "Science" ignoring "Science Fiction" tag.

    {PROG_ID} tags=Science --having "NOT tags=Fiction" """
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

        # Consume the library generator
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
        # Capture Ctrl+C inside main for an immediate and clean exit
        print("\nSearch canceled at user request.")
        sys.exit(0)
    except BrokenPipeError:
        # Silence errors when used with 'head' or 'less' and the pipe is closed
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
        # Backup in case the interruption occurs outside the main block of main
        print("\nSearch canceled at user request.")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
    except Exception as e:
        print(f"Critical error: {e}")
        sys.exit(1)
